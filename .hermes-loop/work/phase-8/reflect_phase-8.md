# phase: phase-8

# Reflection: Legacy Adapter + Deprecation Decision

The right call for this round was to defer default promotion. The benchmark reports now carry v3 diagnostics, but they do not justify reclassifying v3 as the default path.

The repository now says the same thing in code, docs, and state: v1 remains default, v2 and v3 remain opt-in, and phase-8 closes on a conservative compatibility decision.
