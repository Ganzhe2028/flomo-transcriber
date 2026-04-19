# flomo-pipeline

`flomo-pipeline` 目前完成了五个最小闭环：

- Stage 1：`extract + validate + raw truth layer`
- Stage 2：`vision enrich -> image.enriched.jsonl`
- Stage 3：`merge monthly -> monthly/YYYY-MM.enriched.jsonl`
- Stage 4：`chunk -> llm_chunks/YYYY-MM/*.json`
- Stage 5：`report -> reports/YYYY-MM.report.md`

当前已实现：

- `extract`: 从 HTML 导出包解析 memo 和图片引用
- `validate`: 校验 raw truth layer 的结构与引用完整性
- `enrich-images`: 从 `image.raw.jsonl` 生成 `image.enriched.jsonl`
- `validate-enriched-images`: 校验增强层和 raw 层的一致性
- `merge-monthly`: 从 `memo.raw.jsonl` 和 `image.enriched.jsonl` 生成按月分组的 memo-centered 视图
- `validate-monthly`: 校验 monthly 派生层和 upstream 的一致性
- `build-chunks`: 从 monthly 派生层生成稳定的 chunk 输出
- `validate-chunks`: 校验 chunk 输出和 monthly source 的一致性
- `build-reports`: 从 chunk 输出生成按月报告
- `validate-reports`: 校验 report 输出和 chunk source 的一致性
- `run-pipeline`: 串联校验、monthly、chunk、report 的便捷入口

当前明确不做：

- preview 重构
- 真实视频理解
- 音频转写
- embeddings / retrieval / semantic clustering
- 数据库 / web 服务 / 队列系统

## 目录结构

```text
flomo-pipeline/
├── raw/
├── store/
├── monthly/
├── llm_chunks/
├── reports/
├── preview/
├── src/flomo_pipeline/
│   ├── extract/
│   ├── enrich/
│   ├── merge/
│   ├── chunk/
│   ├── preview/
│   └── common/
├── scripts/
├── tests/
├── pyproject.toml
└── Makefile
```

## Stage 1 输出

Stage 1 固定输出到 `store/`：

- `store/memo.raw.jsonl`
- `store/image.raw.jsonl`
- `store/missing_image.raw.jsonl`
- `store/images/` 下的物理图片副本

Markdown 不是 truth layer。真正的主输出是 JSONL。

## Stage 2 输出

Stage 2 固定输出到 `store/`：

- `store/image.enriched.jsonl`

这一层是派生增强层，不会改写 `image.raw.jsonl`。

## Stage 3 输出

Stage 3 固定输出到 `monthly/`：

- `monthly/YYYY-MM.enriched.jsonl`

这一层是按月分组的 memo-centered 派生视图，不会改写 `memo.raw.jsonl` 或 `image.enriched.jsonl`。

## Stage 4 输出

Stage 4 固定输出到 `llm_chunks/`：

- `llm_chunks/YYYY-MM/<chunk-id>.json`

这一层是面向下游 LLM 使用的派生 chunk 视图，但当前阶段只负责稳定分块，不做任何 LLM 调用。

## Stage 5 输出

Stage 5 固定输出到 `reports/`：

- `reports/YYYY-MM.report.json`
- `reports/YYYY-MM.report.md`

这一层从 `llm_chunks/YYYY-MM/*.json` 生成按月报告，不改写 Stage 1-4 的任何产物。

## Monthly Schema

### `monthly/YYYY-MM.enriched.jsonl`

每行是一条 merged memo record，当前至少包含：

- `memo_id`
- `created_at`
- `month`
- `memo_text`
- `source_relpath`
- `batch_label`
- `ordinal`
- `image_count_raw`
- `images`

其中：

- `memo_text` 直接来自 Stage 1 的 `body_md`
- `image_count_raw` 直接来自 Stage 1 的 `image_count`
- `images` 会保留 Stage 2 的关键增强字段，而不是改写成单一文本块

### nested `images`

当前每个 nested image 至少包含：

- `image_id`
- `memo_id`
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

## Chunk Schema

### `llm_chunks/YYYY-MM/<chunk-id>.json`

每个 chunk 当前至少包含：

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

当前实现里：

- `chunk_id` 格式是 `YYYY-MM-0001`
- `source_memo_ids` 保留 chunk 内 memo 的原始成员关系
- `source_items` 保留 memo 文本和 image enrich 的结构化来源信息
- `text` 是机器可读的 deterministic context，不是面向用户的成稿

## Report Schema

### `reports/YYYY-MM.report.json`

每个 report 当前至少包含：

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

其中：

- `source_chunk_ids` 保留报告对应的 chunk 来源
- `sections` 是逐 chunk 的小结结果
- `report_md` 与旁边的 `YYYY-MM.report.md` 内容一致
- `status=failed` 时会保留失败 section 和 `error_message`

## Enriched Schema

### `image.enriched.jsonl`

每条记录至少包含：

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

当前实现里：

- `relative_path` 来自 Stage 1 的 `image_relpath`
- `created_at` 和 `month` 通过 `memo.raw.jsonl` 关联得到
- `status` 支持 `success / skipped / failed`

## Raw Schema

### `memo.raw.jsonl`

每条 memo 至少包含：

- `memo_id`
- `created_at`
- `body_md`
- `image_count`
- `source_relpath`
- `batch_label`
- `ordinal`

### `image.raw.jsonl`

每条 image 至少包含：

- `image_id`
- `memo_id`
- `image_relpath`
- `source_relpath`
- `ordinal`

### `missing_image.raw.jsonl`

每条 missing image 记录包含：

- `image_id`
- `memo_id`
- `source_relpath`
- `ordinal`
- `reason`

## 使用方式

先安装依赖：

```bash
pip install -e .[dev]
```

从 `raw/` 构建 raw truth layer：

```bash
python scripts/extract_raw.py --raw-root raw --store-root store
```

校验 `store/`：

```bash
python scripts/validate_store.py --store-root store
```

如果 `raw` 不在默认位置，可以显式传入：

```bash
python scripts/validate_store.py --store-root store --raw-root /path/to/raw
```

也可以直接用 `make`：

```bash
make extract
make validate
make enrich
make enrich-lmstudio
make probe-lmstudio IMAGE=store/images/2025/2025-12/example.png
make validate-enrich
make merge-monthly
make validate-monthly
make build-chunks
make validate-chunks
make build-reports
make build-reports-lmstudio
make validate-reports
make pipeline
make pipeline-lmstudio
make probe-lmstudio-sh IMAGE=store/images/2025/2025-12/example.png
make stage2-lmstudio-sh MONTH=2025-12
make stage3-4-sh MONTH=2025-12
make test
```

### Stage 2-4 便捷脚本

如果目标只是把图片增强结果合并成外部 LLM 可读的 chunk，不需要手动逐条敲命令。

模型参与的脚本单独放在 Stage 2：

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="google/gemma-4-e4b:2"
export FLOMO_VLM_TIMEOUT_SECONDS="180"

scripts/00_probe_lmstudio_image.sh store/images/2025/2025-12/example.png
scripts/10_stage2_enrich_lmstudio.sh 2025-12
```

纯本地派生处理放在另一个脚本：

```bash
scripts/20_stage3_4_build_context.sh 2025-12
```

执行顺序固定是：

```text
10_stage2_enrich_lmstudio.sh
-> 20_stage3_4_build_context.sh
-> llm_chunks/YYYY-MM/*.json
```

`20_stage3_4_build_context.sh` 会依次执行：

- `validate_enriched_images`
- `merge_monthly`
- `validate_monthly`
- `build_chunks --overwrite`
- `validate_chunks`

常用环境变量：

- `MONTH=2025-12`：目标月份，也可以作为第一个参数传入
- `STORE_ROOT=store`
- `MONTHLY_ROOT=monthly`
- `CHUNKS_ROOT=llm_chunks`
- `OVERWRITE_ENRICH=1`：强制重跑已有成功图片
- `OVERWRITE_CHUNKS=0`：不覆盖已有 chunk

### Windows `.bat` 脚本

Windows 下有对应的 `.bat` 文件，适合在 CMD 或 PowerShell 里调用。
项目脚本本身不直接控制 GPU；32GB 内存 + RTX 4070 Laptop 8GB 的配置主要在
LM Studio 里选择合适模型和 offload 参数，脚本只负责调用本地 OpenAI-compatible
server。

先设置 LM Studio VLM 环境变量：

```bat
set FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1
set FLOMO_VLM_MODEL=google/gemma-4-e4b:2
set FLOMO_VLM_TIMEOUT_SECONDS=180
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

如果确认要从 Stage 2 到 Stage 4 一次跑完，也可以用总入口：

```bat
scripts\30_stage2_4_prepare_context.bat 2025-12
```

Windows 常用变量：

```bat
set OVERWRITE_ENRICH=1
set OVERWRITE_CHUNKS=1
set STORE_ROOT=store
set MONTHLY_ROOT=monthly
set CHUNKS_ROOT=llm_chunks
```

输出给外部 OpenRouter 模型读取的位置仍然是：

```text
llm_chunks\YYYY-MM\*.json
```

生成增强层：

```bash
python scripts/enrich_images.py --store-root store --provider mock
```

`enrich_images.py` 会先完整处理一轮目标图片。若本轮出现 `failed` 记录，
脚本会在首轮结束后只重试失败项，最多重试 3 轮；仍失败的记录会保留
`status=failed` 和最终 `error_message`，并在终端 summary 中报告重试次数和
仍失败数量。

当前也支持通过 LM Studio 的 OpenAI-compatible 接口调用真实本地视觉模型：

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="<your-local-vision-model>"
export FLOMO_VLM_TIMEOUT_SECONDS="60"
python scripts/enrich_images.py --store-root store --provider lmstudio
```

如果 LM Studio 需要 API key，再设置：

```bash
export FLOMO_VLM_API_KEY="<key>"
```

先用单图 probe 确认本地模型接口可用：

```bash
python scripts/probe_lmstudio_vlm.py --image store/images/2025/2025-12/example.png
```

按月份处理：

```bash
python scripts/enrich_images.py --store-root store --provider mock --month 2026-01
python scripts/enrich_images.py --store-root store --provider lmstudio --month 2025-12
```

覆盖已成功结果：

```bash
python scripts/enrich_images.py --store-root store --provider mock --overwrite
python scripts/enrich_images.py --store-root store --provider lmstudio --month 2025-12 --overwrite
```

校验增强层：

```bash
python scripts/validate_enriched_images.py --store-root store
```

生成 monthly 视图：

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly
```

只重建某一个月：

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly --month 2025-12
```

校验 monthly 视图：

```bash
python scripts/validate_monthly.py --store-root store --monthly-root monthly
```

生成 chunk：

```bash
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks
```

只构建一个月：

```bash
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12
```

调整 pack 阈值：

```bash
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --target-tokens 1200 --hard-max-tokens 1600 --overwrite
```

校验 chunk：

```bash
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --summary
```

生成 report：

```bash
python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider mock
```

用 LM Studio 生成 report：

```bash
export FLOMO_LLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_LLM_MODEL="<your-local-text-model>"
export FLOMO_LLM_TIMEOUT_SECONDS="120"
python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider lmstudio --month 2025-12 --overwrite
```

如果 LM Studio 需要 API key，再设置：

```bash
export FLOMO_LLM_API_KEY="<key>"
```

校验 report：

```bash
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports --month 2025-12 --summary
```

一键刷新派生层：

```bash
python scripts/run_pipeline.py --month 2025-12 --report-provider mock
python scripts/run_pipeline.py --month 2025-12 --report-provider lmstudio
```

如果要连 Stage 2 的 LM Studio enrich 一起跑：

```bash
python scripts/run_pipeline.py --month 2025-12 --enrich-provider lmstudio --report-provider lmstudio
```

## 校验规则

当前 raw 层保留的核心校验包括：

- `memo_id` / `image_id` 唯一性
- `memo_id` 引用完整性
- `image_count` 对账
- 路径必须是相对路径
- 输出图片文件存在性检查
- source 文件存在性检查
- `created_at` 必须符合 `YYYY-MM-DDTHH:MM:SS`
- `body_md` 不允许带 frontmatter

当前 enrich 层保留的核心校验包括：

- `image_id` 唯一
- 每条 enriched 记录都能在 `image.raw.jsonl` 找到
- `memo_id` 必须与 raw 层一致
- `relative_path` / `source_relpath` 必须是相对路径
- `status` 必须是允许枚举值之一
- `success` 记录至少要有 `ocr_text` 或 `visual_description`
- `failed` 记录必须有 `error_message`

当前 monthly 层保留的核心校验包括：

- 每个月文件内 `memo_id` 唯一
- 每条 monthly 记录的 `month` 必须和文件名一致
- 每条 monthly 记录都必须对应 `memo.raw.jsonl` 里的真实 memo
- nested image 记录必须对应 `image.enriched.jsonl` 里的真实 `image_id`
- `images` 字段必须存在且必须是数组
- 路径字段必须保持相对路径
- 记录顺序必须稳定为 `created_at + memo_id`

当前 chunk 层保留的核心校验包括：

- `chunk_id` 全局唯一
- `month` 必须匹配目录和 source month
- `source_memo_ids` 必须都能在对应 monthly source 找到
- `source_count` 必须等于 `source_memo_ids` 长度
- `token_estimate` 必须是正整数
- 成功 chunk 的 `text` 必须非空
- `chunk_index` 在月内必须唯一且连续
- 每个月的 memo 不能在 chunk 层丢失或重复
- `created_at_range` 必须和实际 source memo 时间一致
- 所有输出路径字段必须保持相对路径

当前 report 层保留的核心校验包括：

- 每个月有对应的 `YYYY-MM.report.json` 和 `YYYY-MM.report.md`
- report 的 `month` 必须匹配 source chunk 目录
- `source_chunk_ids` 必须和 chunk 文件一致
- `source_count` 必须等于 `source_chunk_ids` 长度
- `status` 必须是 `success / failed`
- `success` report 必须有非空 `report_md`
- `failed` report 必须有 `error_message`
- 每个 section 必须对应真实 chunk
- Markdown 文件内容必须和 JSON 里的 `report_md` 一致

## Stage 2 当前行为

当前只处理静态图片：

- `.png`
- `.jpg`
- `.jpeg`

当前会明确跳过：

- `.mov`
- `.mp4`
- `.m4a`
- 其他非静态图片类型

当前 provider 支持：

- `mock`：测试和占位 provider，不调用外部模型
- `lmstudio`：调用 LM Studio OpenAI-compatible `/chat/completions` 接口

`lmstudio` provider 读取这些环境变量：

- `FLOMO_VLM_BASE_URL`：OpenAI-compatible base URL，例如 `http://127.0.0.1:1234/v1`
- `FLOMO_VLM_MODEL`：本地视觉模型名
- `FLOMO_VLM_API_KEY`：可选；设置后会作为 Bearer token 发送
- `FLOMO_VLM_TIMEOUT_SECONDS`：可选；默认 `60`

`lmstudio` 请求会把本地图片转成 `image_url` data URL，要求模型只返回：

```json
{"ocr_text":"...", "visual_description":"..."}
```

如果 HTTP 失败、超时、返回结构异常、内容不是合法 JSON，或者两个字段都为空，该图片会写成 `status=failed` 并保留 `error_message`。这一步仍然只处理 `.png / .jpg / .jpeg`，不处理视频、音频或 Stage 5 的 LLM 报告。

每次 enrich 首轮完成后会自动重试本轮失败项，最多 3 轮。重试成功的图片会写成
`status=success`；重试 3 轮后仍失败的图片会保留最终失败原因。已有
`status=success` 的历史记录在未传 `--overwrite` 时仍按幂等规则跳过，不参与重试。

## Stage 3 当前行为

当前 monthly merge 的行为是：

- 只读取 `memo.raw.jsonl` 和 `image.enriched.jsonl`
- 按 `created_at[:7]` 分组写成 `monthly/YYYY-MM.enriched.jsonl`
- 每条 monthly 记录都以 memo 为中心
- 零图 memo 仍然保留，`images` 是空数组
- `failed` / `skipped` 的 enriched image 不会被丢掉，会保留在所属 memo 的 `images` 里
- 重新运行会从 upstream 重新生成月文件，不把 monthly 当成新的 truth layer

## Stage 4 当前行为

当前 chunking 的策略是：

- 以 memo 为原子单位，不在 v1 中拆开单条 memo
- 按月内时间顺序顺次装箱
- 使用简单 token heuristic 做大小估计：`max(ceil(words * 1.3), ceil(chars / 4))`
- 默认目标大小是 `1200` tokens，默认参数里也保留 `1600` 的 hard max 配置位

当前 `text` 构造规则是：

- 保留 memo id、created_at、原始 memo_text
- 对图片只把 `success` 项写入 `text`
- `skipped` / `failed` 图片不会伪造文字内容，但会保留在 `source_items` 结构里

当前重跑策略是：

- 默认安全模式：如果某个月已经有 chunk 文件，就整月跳过
- 只有传 `--overwrite` 才会重建该月 chunk
- 不会删除不在本次目标范围内的其他月份输出

## Stage 5 当前行为

当前 report generation 的行为是：

- 只读取 `llm_chunks/YYYY-MM/*.json`
- 默认写入 `reports/YYYY-MM.report.json` 和 `reports/YYYY-MM.report.md`
- 支持 `mock` provider 和 `lmstudio` provider
- `mock` 只用于测试和管线占位
- `lmstudio` 调用 OpenAI-compatible `/chat/completions`，但只发送文本 chunk，不发送图片二进制
- 每个 chunk 单独生成一个 section，再组合成月度 Markdown
- 默认安全模式：已有 report 时跳过，传 `--overwrite` 才重建

`lmstudio` report provider 读取这些环境变量：

- `FLOMO_LLM_BASE_URL`：OpenAI-compatible base URL，例如 `http://127.0.0.1:1234/v1`
- `FLOMO_LLM_MODEL`：本地文本模型名
- `FLOMO_LLM_API_KEY`：可选；设置后会作为 Bearer token 发送
- `FLOMO_LLM_TIMEOUT_SECONDS`：可选；默认 `120`

Stage 5 当前不做：

- 跨月综合
- embeddings / retrieval
- preview/UI
- 数据库或 web 服务
- 对 Stage 1-4 产物做反向修改

## 测试

```bash
python -m pytest
```

## Open Source Safety

真实 Flomo 导出和所有派生结果默认不应进入公开仓库。发布前运行：

```bash
python scripts/check_open_source_readiness.py
```

这个检查会扫描当前准备发布的文件，确认没有把 `raw/`、`store/`、
`monthly/`、`llm_chunks/`、`reports/`、`preview/` 中的真实数据加入 Git。

当前 private 工作仓库的旧 Git history 不适合作为 public history 直接公开。
公开发布应使用 clean orphan branch 或全新的 public repo。
