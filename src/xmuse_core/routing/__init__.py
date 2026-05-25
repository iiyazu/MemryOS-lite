"""A2A routing infrastructure for xmuse control plane.

Implements unified worklist dispatch, @mention parsing, and callback
enqueue patterns based on cat-cafe-tutorials A2A routing design (F27).
"""

from xmuse_core.routing.callbacks import CallbackRouter
from xmuse_core.routing.mentions import parse_mentions
from xmuse_core.routing.server import create_app
from xmuse_core.routing.worklist import DispatchChain, Worklist

__all__ = [
    "CallbackRouter",
    "DispatchChain",
    "Worklist",
    "create_app",
    "parse_mentions",
]
