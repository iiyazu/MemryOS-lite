#!/usr/bin/env python3
"""Backward-compatible wrapper for xmuse.master_loop."""
from __future__ import annotations

import asyncio

import master_loop

ensure_worktree = master_loop.ensure_worktree
load_lanes = master_loop.load_lanes
parse_args = master_loop.parse_args
update_lane_status = master_loop.update_lane_status


async def main(args):
    return await master_loop.main(args)


def cli():
    return parse_args()


if __name__ == "__main__":
    asyncio.run(main(cli()))
