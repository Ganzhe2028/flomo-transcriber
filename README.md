# flomo-transcriber

[English](README.en.md)

把你的 Flomo 记忆库变成 **LLM 友好**的资料包。

> [!NOTE]
> 亲测自己的flomo导出包：缩减至原大小的约 **0.059%**，即减少了约 **99.94%**。

很多人把几千条 Flomo 记成了自己的长期记忆，但导出后很难直接交给模型处理：文字分散，图片没人读，月份不好拆，来源也不好追。`flomo-transcriber` 解决的就是这件事。

它会把本地 Flomo 导出内容整理成干净、可检查、可重复生成的数据。memo 原文会保留，图片里的文字和画面信息也可以转成文本，最后生成外部 LLM 可以直接读取的 chunk 文件。

它做的事很具体：

1. 从 Flomo HTML 导出里提取 memo 和图片。
2. 把结果保存成稳定的 JSONL 文件。
3. 可选：用本地 LM Studio 视觉模型读取图片里的文字和画面信息。
4. 按月份合并 memo 和图片描述。
5. 生成 `llm_chunks/YYYY-MM/*.json`，给 OpenRouter、ChatGPT、Claude 或其他外部模型读取。
6. 可选：用本地文本模型生成月度报告。

它不是一个 Web 应用，也不需要数据库。所有输入输出都是本地文件。

## 你应该从哪里开始

不同身份看不同部分：

- 只是想把 Flomo 数据整理给 LLM 用：看 [使用者：最短流程](#使用者最短流程)。
- 想改代码、跑测试、维护项目：看 [开发者：项目结构和测试](#开发者项目结构和测试)。
- 让 AI Agent 接手继续开发：看 [Agent：边界和契约](#agent边界和契约)。

## 使用者：最短流程

### 1. 安装

```bash
pip install -e .[dev]
```

### 2. 放入 Flomo 导出

把 Flomo 的 HTML 导出内容放到：

```text
raw/
```

支持常规结构 `raw/YYYY/flomo@User-YYYYMMDD/*.html`，也支持部分解压工具生成的同名包裹结构 `raw/YYYY/flomo@User-YYYYMMDD/flomo@User-YYYYMMDD/*.html`。

这个仓库不会自带你的真实 Flomo 数据。`raw/`、`store/`、`monthly/`、`llm_chunks/`、`reports/` 默认都被 `.gitignore` 保护，避免误传到 GitHub。

### 3. 生成 raw 数据层

```bash
python scripts/extract_raw.py --raw-root raw --store-root store
python scripts/validate_store.py --store-root store
```

成功后会得到：

```text
store/memo.raw.jsonl
store/image.raw.jsonl
store/missing_image.raw.jsonl
store/images/
```

### 4. 让图片进入可读文本

如果你只是测试流程，不想调用真实模型：

```bash
python scripts/enrich_images.py --store-root store --provider mock
python scripts/validate_enriched_images.py --store-root store
```

如果你要用 LM Studio 读取真实图片内容，先启动 LM Studio 的 OpenAI-compatible server，然后设置：

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="<你的视觉模型名>"
export FLOMO_VLM_TIMEOUT_SECONDS="180"
export FLOMO_VLM_MAX_TOKENS="1024"
```

先探测一张图片：

```bash
python scripts/probe_lmstudio_vlm.py --image store/images/2025/2025-12/example.png
```

探测成功后再跑整月：

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --month 2025-12
python scripts/validate_enriched_images.py --store-root store
```

`--month 2025-12` 不是必须的。不加 `--month` 会处理全部月份：

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio
```

如果本地模型服务允许并发，可以加 `--workers` 并行处理图片，例如：

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --workers 4
```

### 5. 生成给外部 LLM 读取的 chunks

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly
python scripts/validate_monthly.py --store-root store --monthly-root monthly
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --overwrite
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks
```

最终给外部模型读取的是：

```text
llm_chunks/YYYY-MM/*.json
```

如果你只处理某个月：

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly --month 2025-12
python scripts/validate_monthly.py --store-root store --monthly-root monthly --month 2025-12
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --overwrite
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --summary
```

## 常用脚本

### macOS / Linux

模型参与的 Stage 2：

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="<你的视觉模型名>"
export FLOMO_VLM_TIMEOUT_SECONDS="180"
export FLOMO_VLM_MAX_TOKENS="1024"

scripts/00_probe_lmstudio_image.sh store/images/2025/2025-12/example.png
scripts/10_stage2_enrich_lmstudio.sh 2025-12
```

纯本地 Stage 3-4：

```bash
scripts/20_stage3_4_build_context.sh 2025-12
```

不传月份时会处理全部月份：

```bash
scripts/10_stage2_enrich_lmstudio.sh
scripts/20_stage3_4_build_context.sh
```

### Windows

在 PowerShell 里先设置 LM Studio 环境变量：

```powershell
$env:FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
$env:FLOMO_VLM_MODEL="<你的视觉模型名>"
$env:FLOMO_VLM_TIMEOUT_SECONDS="180"
$env:FLOMO_VLM_MAX_TOKENS="1024"
```

在 CMD 里使用：

```bat
set FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1
set FLOMO_VLM_MODEL=<你的视觉模型名>
set FLOMO_VLM_TIMEOUT_SECONDS=180
set FLOMO_VLM_MAX_TOKENS=1024
```

单图探测：

```bat
scripts\00_probe_lmstudio_image.bat store\images\2025\2025-12\example.png
```

模型参与的 Stage 2：

```bat
scripts\10_stage2_enrich_lmstudio.bat 2025-12
```

纯本地 Stage 3-4：

```bat
scripts\20_stage3_4_build_context.bat 2025-12
```

从 Stage 2 到 Stage 4 一次跑完：

```bat
scripts\30_stage2_4_prepare_context.bat 2025-12
```

不传 `2025-12` 就会处理全部月份。

## 目录和输出

```text
raw/          你放进去的 Flomo 原始导出
store/        Stage 1-2 输出：raw JSONL、图片副本、图片增强结果
monthly/      Stage 3 输出：按月合并后的 memo 记录
llm_chunks/   Stage 4 输出：给外部 LLM 读取的 chunk JSON
reports/      Stage 5 输出：可选的本地月度报告
preview/      预留目录
scripts/      命令行入口
src/          Python 源码
tests/        测试
```

最重要的输出是：

```text
llm_chunks/YYYY-MM/*.json
```

如果你准备用 OpenRouter 跑最终总结，通常只需要把这个目录交给外部模型。

## 每个 Stage 做什么

| Stage | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| Stage 1 extract | `raw/` | `store/memo.raw.jsonl`, `store/image.raw.jsonl`, `store/images/` | 提取 memo 和图片引用 |
| Stage 2 enrich | `store/image.raw.jsonl` | `store/image.enriched.jsonl` | 读取静态图片，写入 OCR 和画面描述 |
| Stage 3 merge monthly | `memo.raw.jsonl`, `image.enriched.jsonl` | `monthly/YYYY-MM.enriched.jsonl` | 按月把 memo 和图片增强结果合并 |
| Stage 4 chunk | `monthly/YYYY-MM.enriched.jsonl` | `llm_chunks/YYYY-MM/*.json` | 生成 LLM 可读的分块上下文 |
| Stage 5 report | `llm_chunks/YYYY-MM/*.json` | `reports/YYYY-MM.report.md`, `reports/YYYY-MM.report.json` | 可选：生成本地月度报告 |

Stage 1-4 是推荐主流程。Stage 5 是可选功能；如果你要用 OpenRouter 生成最终报告，可以只用 Stage 1-4。

## Stage 2 图片增强说明

当前只处理静态图片：

- `.png`
- `.jpg`
- `.jpeg`

当前会明确跳过：

- `.mov`
- `.mp4`
- `.m4a`
- 其他非静态图片类型

图片描述会覆盖照片、物体、场景、图表、界面布局、diagram 和 screenshot 等可见非文字内容。

支持的 provider：

- `mock`：测试流程用，不调用模型。
- `lmstudio`：调用 LM Studio 的 OpenAI-compatible `/chat/completions` 接口。

`lmstudio` 读取这些环境变量：

- `FLOMO_VLM_BASE_URL`：例如 `http://127.0.0.1:1234/v1`
- `FLOMO_VLM_MODEL`：本地视觉模型名
- `FLOMO_VLM_API_KEY`：可选
- `FLOMO_VLM_TIMEOUT_SECONDS`：可选，默认 `60`
- `FLOMO_VLM_MAX_TOKENS`：可选，默认 `1024`，限制单张图片的模型输出长度

图片增强失败不会中断整个流程。脚本会先完整跑一遍，再只重试失败项，最多重试 3 轮。仍失败的图片会保留 `status=failed` 和失败原因。

默认不会覆盖已经成功的图片记录。需要重跑成功项时加：

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --overwrite
```

## Stage 4 chunk 说明

chunk 是给 LLM 读取的最终上下文文件。

每个 chunk 至少包含：

- `chunk_id`
- `month`
- `source_memo_ids`
- `created_at_range`
- `token_estimate`
- `text`
- `source_items`

其中：

- `text` 是给模型直接读的文本。
- `source_items` 保留来源 memo 和图片增强记录，方便追溯。
- memo 是最小单位，默认不会把一条 memo 拆成多个 chunk。
- `failed` / `skipped` 图片不会伪造成文字，但会在结构化字段里保留。

默认策略是按时间顺序装箱，目标大小约 `1200` tokens。估算方法是稳定启发式，不追求和某个模型 tokenizer 完全一致。

## 可选：生成本地 report

默认 mock report：

```bash
python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider mock
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports
```

用 LM Studio 文本模型生成 report：

```bash
export FLOMO_LLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_LLM_MODEL="<你的文本模型名>"
export FLOMO_LLM_TIMEOUT_SECONDS="120"

python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider lmstudio --month 2025-12 --overwrite
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports --month 2025-12 --summary
```

如果你使用 OpenRouter 或其他外部模型做最终报告，可以跳过这一节。

## 开发者：项目结构和测试

源码结构：

```text
src/flomo_pipeline/
├── extract/
├── enrich/
├── merge/
├── chunk/
├── report/
├── preview/
└── common/
```

说明：项目的公开名称是 `flomo-transcriber`。内部 Python import 包仍叫 `flomo_pipeline`，这是为了保持现有脚本和测试兼容。

常用命令：

```bash
python -m pytest
python scripts/check_open_source_readiness.py
```

Makefile 也提供同等入口：

```bash
make extract
make validate
make enrich
make enrich-lmstudio
make validate-enrich
make merge-monthly
make validate-monthly
make build-chunks
make validate-chunks
make build-reports
make validate-reports
make test
```

代码原则：

- 每个 stage 只读上游文件、写自己的派生产物。
- Stage 1 的 raw JSONL 是事实层，不被下游改写。
- 下游输出必须能重新生成。
- 所有路径字段保持相对路径。
- 所有关键输出都有 validator。

## Agent：边界和契约

Agent 接手时先读这三处：

1. `README.md` 或 `README.en.md`
2. `pyproject.toml`
3. `tests/`

不要默认重构旧阶段。已有边界如下：

- Stage 1：`raw -> store/*.raw.jsonl`
- Stage 2：`store/image.raw.jsonl -> store/image.enriched.jsonl`
- Stage 3：`store/*.jsonl -> monthly/YYYY-MM.enriched.jsonl`
- Stage 4：`monthly/YYYY-MM.enriched.jsonl -> llm_chunks/YYYY-MM/*.json`
- Stage 5：`llm_chunks/YYYY-MM/*.json -> reports/YYYY-MM.report.*`

新增能力时要遵守：

- 不把真实用户数据提交进 Git。
- 不把 `monthly`、`chunk`、`report` 当成新的 truth layer。
- 不静默丢弃 `failed` / `skipped` 图片。
- 不在 Stage 4 做 LLM 调用。
- 不在 Stage 2 处理视频或音频，除非明确新增对应 stage 设计。
- 改了用户可见行为就更新 README。

最小交付检查：

```bash
python -m pytest
python scripts/check_open_source_readiness.py
```

## Schema 速查

### `store/memo.raw.jsonl`

- `memo_id`
- `created_at`
- `body_md`
- `image_count`
- `source_relpath`
- `batch_label`
- `ordinal`

### `store/image.raw.jsonl`

- `image_id`
- `memo_id`
- `image_relpath`
- `source_relpath`
- `ordinal`

### `store/image.enriched.jsonl`

- `image_id`
- `memo_id`
- `created_at`
- `month`
- `relative_path`
- `source_relpath`
- `media_type`
- `ocr_text`
- `visual_description`
- `model_name`
- `prompt_version`
- `run_id`
- `status`
- `error_message`

### `monthly/YYYY-MM.enriched.jsonl`

- `memo_id`
- `created_at`
- `month`
- `memo_text`
- `source_relpath`
- `batch_label`
- `ordinal`
- `image_count_raw`
- `images`

`images` 保留 Stage 2 的关键字段，包括 `image_id`、路径、OCR、画面描述、模型信息、`status` 和 `error_message`。

### `llm_chunks/YYYY-MM/<chunk-id>.json`

- `chunk_id`
- `month`
- `chunk_index`
- `source_memo_ids`
- `source_count`
- `created_at_range`
- `token_estimate`
- `text`
- `source_items`
- `build_version`
- `strategy`
- `status`

### `reports/YYYY-MM.report.json`

- `report_id`
- `month`
- `source_chunk_ids`
- `source_count`
- `provider_name`
- `model_name`
- `prompt_version`
- `build_version`
- `status`
- `error_message`
- `report_md`
- `sections`

## Open Source Safety

真实 Flomo 导出和所有派生结果不应进入公开仓库。发布前运行：

```bash
python scripts/check_open_source_readiness.py
```

这个检查会确认没有把这些目录里的真实数据加入 Git：

- `raw/`
- `store/`
- `monthly/`
- `llm_chunks/`
- `reports/`
- `preview/`

当前 private 工作仓库的旧 Git history 不适合直接公开。公开发布应使用 clean orphan branch 或全新的 public repo。
