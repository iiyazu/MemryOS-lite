#!/bin/bash
# God Launcher — 启动独立的 God Codex 进程
cd /home/iiyatu/projects/python/memoryOS
exec codex exec --yolo "$(cat .hermes-loop/god_loop_prompt.md)"
