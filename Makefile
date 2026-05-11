.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install test lint fmt typecheck up down logs ps eval demo api clean

help: ## 显示可用 target
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## 安装依赖（含 dev）
	uv sync --dev

test: ## 跑单元测试
	uv run pytest -q

lint: ## ruff + mypy 检查
	uv run ruff check .
	uv run mypy src

fmt: ## 格式化 + 自动修复
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## 只跑 mypy
	uv run mypy src

up: ## 启动 docker-compose（app + postgres + redis）
	docker compose up -d --build

down: ## 关闭 docker-compose
	docker compose down

logs: ## tail app 日志
	docker compose logs -f app

ps: ## 查看服务状态
	docker compose ps

eval: ## 跑内置确定性 benchmark
	uv run memoryos eval run --baseline all

demo: ## 跑端到端 demo
	uv run memoryos demo run

api: ## 本机跑 API（热重载）
	uv run memoryos api --reload

clean: ## 清理缓存
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
