# Operator Note: benchmark-layer-organization

updated_at: 2026-05-25T16:25:00+08:00

Credential context from operator:

- `OPENAI_API_KEY` is not available.
- DeepSeek credentials are available through the feature worktree `.env`.

Use this only to classify verification blockers accurately. Do not claim OpenAI-backed gates ran unless `OPENAI_API_KEY` is actually present. If a DeepSeek-backed public LLM gate is in scope, load credentials from `.env` using the repository's normal environment-loading path.
