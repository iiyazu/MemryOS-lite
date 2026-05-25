"""HTTP callback server for mid-execution agent communication.

Design reference: cat-cafe-tutorials/05-mcp-callback.md
Exposes callback endpoints so agents can post messages, check worklist
status, and trigger chain aborts over HTTP during execution.

Intended for local use alongside xmuse agents — no TLS or auth middleware.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from xmuse_core.routing.callbacks import CallbackRouter
from xmuse_core.routing.worklist import Worklist


class PostMessageRequest(BaseModel):
    invocation_id: str
    callback_token: str
    content: str


class AbortRequest(BaseModel):
    invocation_id: str
    callback_token: str


def create_app(worklist: Worklist, router: CallbackRouter) -> FastAPI:
    """Create a FastAPI app wired to the given worklist and callback router."""

    app = FastAPI(title="xmuse-callback-server", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/callbacks/worklist-status")
    def worklist_status() -> dict[str, Any]:
        return router._worklist.snapshot()

    @app.post("/callbacks/post-message")
    def post_message(req: PostMessageRequest) -> dict[str, Any]:
        result = router.post_message(
            invocation_id=req.invocation_id,
            token=req.callback_token,
            content=req.content,
        )
        if not result["ok"]:
            raise HTTPException(status_code=401, detail=result["error"])
        return result

    @app.post("/callbacks/abort")
    def abort(req: AbortRequest) -> dict[str, Any]:
        creds = router.validate(req.invocation_id, req.callback_token)
        if creds is None:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        worklist.chain.abort()
        return {"ok": True, "aborted": True}

    return app
