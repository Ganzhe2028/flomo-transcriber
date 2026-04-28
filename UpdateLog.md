# UpdateLog

本文件记录项目的重要更新。之后凡是达到 `a.b.c` 中 `b` 级别及以上的变化，必须主动更新本文件。

版本级别约定：

- `a`：架构变化，例如数据流、核心目录结构、主要模块边界调整。
- `b`：重要功能、处理流程升级、版本更新换代。
- `c`：小功能、日常修正、文档或脚本微调。

## 2026-04-28 - 0.2.0 级别更新

覆盖范围：2026-04-27 至 2026-04-28，约 4 天内的本地更新。

### 本次更新内容

- 增加长图切片识别能力：长截图、窄截图或压缩严重截图在整图识别失败后，可以切成纵向 clip 逐段识别。
- 增加强制切片模式：确认整图识别效果差时，可以直接跳过整图识别，按切片结果生成图片增强文本。
- 切片识别结果仍写回原图片对应的同一条 `image_id`，不会改变 `store/image.enriched.jsonl`、`monthly/*.enriched.jsonl` 或 `llm_chunks/**/*.json` 的结构。
- 增加切片参数：`--slice-height`、`--slice-overlap`、`--slice-upscale`。
- 增加失败图片重试流程：支持只重试 `status=failed` 的图片记录，并保留已成功记录。
- 完善 Windows 脚本：补充 Stage 2 到 Stage 4 的准备流程和失败图片重试入口。
- 调整 LM Studio 默认示例模型说明，便于 Windows 环境直接使用。
- 更新中英文 README 和 `.env.example`，补充长图切片、失败重试和相关环境变量。

### 使用方式

长图整图识别失败后自动切片重试：

```powershell
python scripts\enrich_images.py --store-root store --provider lmstudio --month 2025-04 --slice-long-images
```

确认长图整图识别效果差，直接切片识别：

```powershell
python scripts\enrich_images.py --store-root store --provider lmstudio --month 2025-04 --force-slice-long-images
```

只重试失败图片：

```powershell
scripts\40_retry_failed_images_lmstudio.bat 2025-04
```

### 验证结果

- 完整测试集：58 passed。
- `store/image.enriched.jsonl` 校验通过。
- `monthly/*.enriched.jsonl` 校验通过。
- `llm_chunks/**/*.json` 校验通过。

### 相关提交

- `8436e74` win update
- `9f492a9` 手动修复，没问题版本
- `6c2f2ff` windows update failed image
- `aa9940b` 默认e2b
- `7790fd8` 默认e2b模型
- `48aebda` win update
