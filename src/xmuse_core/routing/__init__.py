"""A2A routing infrastructure for xmuse control plane.

Implements unified worklist dispatch, @mention parsing, and callback
enqueue patterns based on cat-cafe-tutorials A2A routing design (F27).
"""

from xmuse_core.routing.mentions import parse_mentions
from xmuse_core.routing.worklist import DispatchChain, Worklist

__all__ = ["DispatchChain", "Worklist", "parse_mentions"]
