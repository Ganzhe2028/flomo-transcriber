# 外部模型识别结果写回流程

将外部模型识别结果写回 `store/image.enriched.jsonl`，按 `image_id` 找到原来失败的那一行，**只修改增强字段**，不改动 `store/image.raw.jsonl`。

## 字段对应关系

| 内容             | 写入字段                   |
| ---------------- | -------------------------- |
| 图片里的文字     | `ocr_text`                 |
| 图片画面说明     | `visual_description`       |
| 外部模型名称     | `model_name`               |
| 本次人工补录标记 | `prompt_version`, `run_id` |
| 识别成功         | `status: "success"`        |
| 清空失败原因     | `error_message: null`      |

## 外部模型返回模板

```json
{
  "ocr_text": "图片中能直接读到的文字。没有文字就填空字符串。",
  "visual_description": "图片的主要内容、场景、结构、图表、截图界面、人物、物品等说明。不要编造看不清的信息。"
}
```

## 写回 `store/image.enriched.jsonl` 的模板

```json
{
  "image_id": "保留原值",
  "memo_id": "保留原值",
  "created_at": "保留原值",
  "month": "保留原值",
  "relative_path": "保留原值",
  "source_relpath": "保留原值",
  "media_type": "保留原值",
  "ocr_text": "外部模型识别出的文字",
  "visual_description": "外部模型识别出的图片说明",
  "model_name": "external-web-manual:模型名",
  "prompt_version": "manual-external-v1",
  "run_id": "manual-2026-04-28",
  "status": "success",
  "error_message": null
}
```

## 修改后重新生成下游文件

e.g.

```bash
python scripts/validate_enriched_images.py --store-root store
python scripts/merge_monthly.py --store-root store --monthly-root monthly --month 2025-04
python scripts/validate_monthly.py --store-root store --monthly-root monthly --month 2025-04
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-04 --overwrite
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-04
```
