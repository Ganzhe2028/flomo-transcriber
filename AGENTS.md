# AGENTS.md

本文件给接手本仓库的 AI Agent 使用。改动前先确认当前任务的完成标准，改动后必须验证。

## 先读

1. `README.md` 或 `README.en.md`
2. `pyproject.toml`
3. 相关 stage 的 `src/flomo_pipeline/<stage>/`
4. 对应测试文件

## 当前边界

- Stage 1 extract：`raw/ -> store/*.raw.jsonl`
- Stage 2 enrich：`store/image.raw.jsonl -> store/image.enriched.jsonl`
- Stage 3 merge：`store/*.jsonl -> monthly/YYYY-MM.enriched.jsonl`
- Stage 4 chunk：`monthly/YYYY-MM.enriched.jsonl -> llm_chunks/YYYY-MM/*.json`
- Stage 5 report：`llm_chunks/YYYY-MM/*.json -> reports/YYYY-MM.report.*`

`common/` 只放跨 stage 共享的基础工具，例如文件读写和校验报告。不要把 stage 专属业务规则搬进 `common/`。

普通用户主入口是 `python scripts/guide.py`。单阶段脚本和 bat/sh 脚本保留给排错、高级参数和自动化使用。

## 改动规则

- 真实 Flomo 导出、图片、生成的 JSONL、chunks、reports、日志和 `.env` 不得进入 Git。
- Stage 1 raw JSONL 是事实层，下游不得改写。
- 下游产物必须可以重新生成。
- 路径字段保持相对路径。
- 不静默丢弃 `failed` / `skipped` 图片。
- 不在 Stage 4 调用 LLM。
- 不默认重构无关 stage。
- 开发后更新相关文档；如果没有相关文档，不需要主动新增，除非任务明确要求。

## 验证

按改动范围选择验证，交付前至少跑相关测试。

```bash
python -m pytest
python -m mypy src
python scripts/check_open_source_readiness.py
```

Ruff 按改动范围运行。全仓库 Ruff 仍有历史格式项；除非任务明确要求清理，不把它当作默认完成条件。

如果改动只影响一个 stage，可以先跑对应测试文件；最终合并前仍建议跑完整测试。
