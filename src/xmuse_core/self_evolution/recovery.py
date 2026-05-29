"""Configurable recovery primitives for xmuse runtime paths.

The helpers here are intentionally framework-neutral so MemoryOS engine code,
agent graph nodes, and the xmuse platform orchestrator can share the same retry
and circuit-breaker semantics while emitting their own local traces.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a component is blocked by an open circuit."""

    def __init__(self, component: str, retry_after_s: float) -> None:
        self.component = component
        self.retry_after_s = max(0.0, retry_after_s)
        super().__init__(
            f"circuit open for {component}; retry after {self.retry_after_s:.3f}s"
        )


class TransientRecoveryError(RuntimeError):
    """Wraps a result-level transient failure so retry policy can handle it."""


@dataclass(frozen=True)
class RecoveryConfig:
    enabled: bool = True
    max_attempts: int = 3
    initial_delay_s: float = 0.05
    max_delay_s: float = 2.0
    backoff_multiplier: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_s: float = 60.0
    graceful_degradation: bool = True

    @classmethod
    def from_env(cls, prefix: str = "XMUSE_RECOVERY") -> RecoveryConfig:
        return cls(
            enabled=_env_bool(f"{prefix}_ENABLED", cls.enabled),
            max_attempts=_env_int(f"{prefix}_MAX_ATTEMPTS", cls.max_attempts),
            initial_delay_s=_env_float(f"{prefix}_INITIAL_DELAY_S", cls.initial_delay_s),
            max_delay_s=_env_float(f"{prefix}_MAX_DELAY_S", cls.max_delay_s),
            backoff_multiplier=_env_float(
                f"{prefix}_BACKOFF_MULTIPLIER", cls.backoff_multiplier
            ),
            circuit_failure_threshold=_env_int(
                f"{prefix}_CIRCUIT_FAILURE_THRESHOLD",
                cls.circuit_failure_threshold,
            ),
            circuit_recovery_timeout_s=_env_float(
                f"{prefix}_CIRCUIT_RECOVERY_TIMEOUT_S",
                cls.circuit_recovery_timeout_s,
            ),
            graceful_degradation=_env_bool(
                f"{prefix}_GRACEFUL_DEGRADATION",
                cls.graceful_degradation,
            ),
        ).normalized()

    def normalized(self) -> RecoveryConfig:
        return RecoveryConfig(
            enabled=self.enabled,
            max_attempts=max(1, int(self.max_attempts)),
            initial_delay_s=max(0.0, float(self.initial_delay_s)),
            max_delay_s=max(0.0, float(self.max_delay_s)),
            backoff_multiplier=max(1.0, float(self.backoff_multiplier)),
            circuit_failure_threshold=max(1, int(self.circuit_failure_threshold)),
            circuit_recovery_timeout_s=max(0.0, float(self.circuit_recovery_timeout_s)),
            graceful_degradation=self.graceful_degradation,
        )

    def delay_for_attempt(self, failed_attempt: int) -> float:
        """Return the delay before the next attempt after *failed_attempt*."""
        if failed_attempt <= 0:
            return 0.0
        delay = self.initial_delay_s * (
            self.backoff_multiplier ** max(0, failed_attempt - 1)
        )
        return min(delay, self.max_delay_s)


@dataclass(frozen=True)
class RecoveryEvent:
    component: str
    operation: str
    kind: str
    attempt: int = 0
    max_attempts: int = 0
    delay_s: float = 0.0
    error_type: str | None = None
    error: str | None = None
    circuit_state: str | None = None
    degraded: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "operation": self.operation,
            "kind": self.kind,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "delay_s": self.delay_s,
            "error_type": self.error_type,
            "error": self.error,
            "circuit_state": self.circuit_state,
            "degraded": self.degraded,
        }


class CircuitBreaker:
    def __init__(self, component: str, config: RecoveryConfig) -> None:
        self.component = component
        self.config = config.normalized()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None

    def before_call(self, now: float | None = None) -> None:
        reference = time.monotonic() if now is None else now
        if self.state is not CircuitState.OPEN:
            return
        opened_at = self.opened_at or reference
        elapsed = reference - opened_at
        if elapsed >= self.config.circuit_recovery_timeout_s:
            self.state = CircuitState.HALF_OPEN
            return
        raise CircuitOpenError(
            self.component,
            self.config.circuit_recovery_timeout_s - elapsed,
        )

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None
        self.state = CircuitState.CLOSED

    def record_failure(self) -> bool:
        self.failure_count += 1
        if self.failure_count >= self.config.circuit_failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            return True
        return False


RecoveryObserver = Callable[[RecoveryEvent], None]


class RecoveryManager:
    def __init__(
        self,
        config: RecoveryConfig | None = None,
        *,
        observer: RecoveryObserver | None = None,
        sleep: Callable[[float], None] = time.sleep,
        async_sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self.config = (config or RecoveryConfig()).normalized()
        self._observer = observer
        self._sleep = sleep
        self._async_sleep = async_sleep
        self._circuits: dict[str, CircuitBreaker] = {}

    def circuit(self, component: str) -> CircuitBreaker:
        if component not in self._circuits:
            self._circuits[component] = CircuitBreaker(component, self.config)
        return self._circuits[component]

    def reset(self, component: str | None = None) -> None:
        if component is None:
            self._circuits.clear()
        else:
            self._circuits.pop(component, None)

    def execute(
        self,
        component: str,
        operation: str,
        func: Callable[[], T],
        *,
        fallback: Callable[[BaseException], T] | None = None,
        critical: bool = True,
        is_transient: Callable[[BaseException], bool] = lambda exc: is_transient_failure(exc),
        observer: RecoveryObserver | None = None,
    ) -> T:
        if not self.config.enabled:
            return func()
        attempt = 1
        breaker = self.circuit(component)
        while True:
            try:
                breaker.before_call()
            except CircuitOpenError as exc:
                self._emit(
                    RecoveryEvent(
                        component=component,
                        operation=operation,
                        kind="circuit_blocked",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        error_type=type(exc).__name__,
                        error=str(exc),
                        circuit_state=breaker.state.value,
                    ),
                    observer,
                )
                return self._degrade_or_raise(
                    component,
                    operation,
                    attempt,
                    exc,
                    fallback,
                    critical,
                    breaker.state.value,
                    observer,
                )
            try:
                value = func()
            except Exception as exc:
                opened = breaker.record_failure()
                self._emit_failure(component, operation, attempt, exc, breaker, opened, observer)
                transient = is_transient(exc)
                if not transient or attempt >= self.config.max_attempts:
                    return self._degrade_or_raise(
                        component,
                        operation,
                        attempt,
                        exc,
                        fallback,
                        critical,
                        breaker.state.value,
                        observer,
                    )
                delay = self.config.delay_for_attempt(attempt)
                self._emit_retry(component, operation, attempt, delay, exc, breaker, observer)
                if delay > 0:
                    self._sleep(delay)
                attempt += 1
                continue
            breaker.record_success()
            if attempt > 1:
                self._emit(
                    RecoveryEvent(
                        component=component,
                        operation=operation,
                        kind="operation_succeeded",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        circuit_state=breaker.state.value,
                    ),
                    observer,
                )
            return value

    async def execute_async(
        self,
        component: str,
        operation: str,
        func: Callable[[], Awaitable[T]],
        *,
        fallback: Callable[[BaseException], T] | None = None,
        critical: bool = True,
        is_transient: Callable[[BaseException], bool] = lambda exc: is_transient_failure(exc),
        observer: RecoveryObserver | None = None,
    ) -> T:
        if not self.config.enabled:
            return await func()
        attempt = 1
        breaker = self.circuit(component)
        while True:
            try:
                breaker.before_call()
            except CircuitOpenError as exc:
                self._emit(
                    RecoveryEvent(
                        component=component,
                        operation=operation,
                        kind="circuit_blocked",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        error_type=type(exc).__name__,
                        error=str(exc),
                        circuit_state=breaker.state.value,
                    ),
                    observer,
                )
                return self._degrade_or_raise(
                    component,
                    operation,
                    attempt,
                    exc,
                    fallback,
                    critical,
                    breaker.state.value,
                    observer,
                )
            try:
                value = await func()
            except Exception as exc:
                opened = breaker.record_failure()
                self._emit_failure(component, operation, attempt, exc, breaker, opened, observer)
                transient = is_transient(exc)
                if not transient or attempt >= self.config.max_attempts:
                    return self._degrade_or_raise(
                        component,
                        operation,
                        attempt,
                        exc,
                        fallback,
                        critical,
                        breaker.state.value,
                        observer,
                    )
                delay = self.config.delay_for_attempt(attempt)
                self._emit_retry(component, operation, attempt, delay, exc, breaker, observer)
                if delay > 0:
                    await self._async_sleep(delay)
                attempt += 1
                continue
            breaker.record_success()
            if attempt > 1:
                self._emit(
                    RecoveryEvent(
                        component=component,
                        operation=operation,
                        kind="operation_succeeded",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        circuit_state=breaker.state.value,
                    ),
                    observer,
                )
            return value

    def _degrade_or_raise(
        self,
        component: str,
        operation: str,
        attempt: int,
        exc: BaseException,
        fallback: Callable[[BaseException], T] | None,
        critical: bool,
        circuit_state: str | None,
        observer: RecoveryObserver | None = None,
    ) -> T:
        if fallback is not None and self.config.graceful_degradation and not critical:
            self._emit(
                RecoveryEvent(
                    component=component,
                    operation=operation,
                    kind="degraded",
                    attempt=attempt,
                    max_attempts=self.config.max_attempts,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    circuit_state=circuit_state,
                    degraded=True,
                ),
                observer,
            )
            return fallback(exc)
        raise exc

    def _emit_retry(
        self,
        component: str,
        operation: str,
        attempt: int,
        delay: float,
        exc: BaseException,
        breaker: CircuitBreaker,
        observer: RecoveryObserver | None = None,
    ) -> None:
        self._emit(
            RecoveryEvent(
                component=component,
                operation=operation,
                kind="retry_scheduled",
                attempt=attempt,
                max_attempts=self.config.max_attempts,
                delay_s=delay,
                error_type=type(exc).__name__,
                error=str(exc),
                circuit_state=breaker.state.value,
            ),
            observer,
        )

    def _emit_failure(
        self,
        component: str,
        operation: str,
        attempt: int,
        exc: BaseException,
        breaker: CircuitBreaker,
        opened: bool,
        observer: RecoveryObserver | None = None,
    ) -> None:
        self._emit(
            RecoveryEvent(
                component=component,
                operation=operation,
                kind="operation_failed",
                attempt=attempt,
                max_attempts=self.config.max_attempts,
                error_type=type(exc).__name__,
                error=str(exc),
                circuit_state=breaker.state.value,
            ),
            observer,
        )
        if opened:
            self._emit(
                RecoveryEvent(
                    component=component,
                    operation=operation,
                    kind="circuit_opened",
                    attempt=attempt,
                    max_attempts=self.config.max_attempts,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    circuit_state=breaker.state.value,
                ),
                observer,
            )

    def _emit(self, event: RecoveryEvent, observer: RecoveryObserver | None = None) -> None:
        logger.info("recovery event: %s", event.to_payload())
        if self._observer is not None:
            self._observer(event)
        if observer is not None:
            observer(event)


def is_transient_failure(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, TransientRecoveryError)):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    transient_markers = (
        "timeout",
        "timed out",
        "temporar",
        "try again",
        "unavailable",
        "connection",
        "reset by peer",
        "rate limit",
        "too many requests",
        "429",
        "503",
        "internal server error",
        "exceeded retry limit",
    )
    return any(marker in text for marker in transient_markers)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
