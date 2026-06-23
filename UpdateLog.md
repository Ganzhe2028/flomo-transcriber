# UpdateLog

本文件记录项目的重要更新。之后凡是达到 `a.b.c` 中 `b` 级别及以上的变化，必须主动更新本文件。

版本级别约定：

- `a`：架构变化，例如数据流、核心目录结构、主要模块边界调整。
- `b`：重要功能、处理流程升级、版本更新换代。
- `c`：小功能、日常修正、文档或脚本微调。

## 2026-06-24 - 0.5.0 级别更新

### 本次更新内容

- **GUI 全面重设计**：`gui/src/styles.css`、`gui/src/App.tsx` 用 Agentic 设计系统重写，深海军蓝 `#0b1020` 底色 + 冷蓝 `#60a5fa` accent，8pt 严格网格间距体系，不再沿用旧版绿灰调。
- **新增亮色/暗色主题切换**：侧栏右上角 ☀️/🌙 图标按钮一键切换，偏好通过 `localStorage` 持久化。亮色主题使用 `#f8fafc` 底色 + `#3b82f6` accent 的浅色变体。
- **控制面板布局重排**：高频操作提权——运行设置（月份/provider/重试轮数/目标图片）置顶，48px 大号「开始运行」按钮紧随其后，路径配置和 LM Studio 配置分别用折叠菜单收起（默认折叠），低频的「保存配置」按钮弱化到底部。
- **日志面板增加终端风格**：日志行淡入动画，JetBrains Mono 等宽字体。移除 macOS 风格终端圆点装饰块。
- **按钮交互增强**：4 种按钮变体全部增加 `:active` 按压态（scale 压缩 + 颜色变暗）、`:focus-visible` 可见焦点环、`aria-current="true"` 当前操作标记，键盘可导航性显著提升。
- **表单无障碍改进**：所有 `<span>` 标签替换为语义化的 `<label for="...">`，屏幕阅读器可正确关联标签与输入框。
- **CSS 组件体系**：btn-primary / btn-secondary / btn-icon / btn-danger 四类按钮变体 + 统一状态（hover/active/disabled），collapsibleSection 折叠菜单组件，pulse/saveFlash 动画，全套 `--space-*` / `--radius-*` CSS 自定义属性。
- **所有现有 Tauri 逻辑零改动**：`invoke`、`listen`、`dialog`、`readTextFile`、`writeTextFile` 全部保留原样，仅组件布局和样式变更新。

### 验证结果

- `cd gui && npm run build` 通过：`tsc` 类型检查 + `vite build` 零错误。
- 四个操作（首次生成/日常更新/探测图片/重试失败）交互逻辑与原版完全一致。
- 侧栏操作切换、provider 切换触发状态胶囊更新，日志模拟输出 4 Stage 流程，功能不变。

### 2026-06-24 修正

- **修复日志面板撑爆窗口高度**：`html`、`body`、`.shell` 从 `min-height: 100vh` 改为 `height: 100vh` + `overflow: hidden`，彻底锁死视口高度，日志输出再多也不会把窗口撑高。
- **移除终端圆点装饰**：删除 `.terminalBar` 组件及红·黄·绿圆点，终端面板更简洁。
- **设计原型同步**：`flomo-redesign.html` 同步以上两项修正。
- **修复 `\u2028` Unicode 行分隔符导致 JSONL 校验失败**：Flomo HTML 导出中的部分 memo 包含 Unicode LINE SEPARATOR (`\u2028`) 字符。`json.dumps(ensure_ascii=False)` 不会转义该字符（JSON 规范允许），但 `str.splitlines()` 将其视为换行符，导致一条 JSONL 记录被拆为多行、校验阶段报 10 个 JSON 解析错误。修复方案：`write_jsonl` 写入前显式转义 `\u2028`/`\u2029` 为 `\\u2028`/`\\u2029`；`read_jsonl`、`load_jsonl_for_validation`、`_load_jsonl`、`load_env_file` 共 4 处 JSONL/配置读取改用 `split("\n")` + `rstrip("\r")` 替代 `splitlines()`。
- **修复 Sidecar 打包后每次运行弹出空终端窗口**：`build_gui_sidecar.py` 的 PyInstaller 命令增加 `--noconsole`，打包出的 exe 变为 Windows GUI 程序，不再显示空 cmd 窗口。
- **新增 `build.bat` 一键打包脚本**：放在项目根目录，串行执行 pip 安装、npm 安装、sidecar 构建和 NSIS 安装包构建共 4 步，任一步失败即停。
- **新增分层 AGENTS.md 知识库**（`/init-deep`）：根文件已有，新增 7 个子模块 AGENTS.md（`common/` `extract/` `enrich/` `merge/` `chunk/` `report/` `gui/` `scripts/`），每个子文件只记录该模块专属的边界、入口、约定和禁区，不重复根文件内容。
- **新增日志面板自动滚动切换按钮**：GUI 右侧日志面板标题栏增加切换按钮（`gui/src/App.tsx` + `gui/src/styles.css`），默认跟随最新行；向上滚动自动暂停，点击按钮手动切换。深蓝跟随态 / 灰色暂停态，用 `useRef` + `useEffect` + `onScroll` 实现。
- **修复 `build.bat` 中文编码问题**：去除 echo 中的中文字符，避免 cmd.exe 在 GBK 环境下将 UTF-8 中文解析为乱码命令。
- **修复 `--month` 参数非零填充月份导致所有 Stage 零记录 bug**：用户传入 `--month 2026-6`（无前导零）时，`created_at[:7]` 产出的 `2026-06` 无法匹配 `2026-6`，导致 Stage 2/3/4 全部选中 0 条记录，monthly validator 也因文件名不匹配报错。修复：新增 `_normalize_month()` 将用户输入的月份统一标准化为 `YYYY-MM`（零填充）格式，在 `flomo_sidecar.py` 和 `guide.py` 两处 CLI 入口调用。影响范围：仅 CLI 入口的参数预处理，不改变流水线内部逻辑或数据格式。

## 2026-05-01 - 0.4.0 级别更新

### 本次更新内容

- 新增跨平台引导脚本 `scripts/guide.py`，普通用户可以通过菜单完成首次生成、日常更新、单图探测和失败图片重试。
- 引导脚本会读取 `.env` 中的 LM Studio 配置；模型名缺失或仍是示例占位值时会直接停止并提示修正。
- Windows 直接执行 `scripts\guide.py` 时，如果当前 shell 已激活 `.venv`，引导脚本会用虚拟环境里的 Python 调用后续 stage 脚本。
- 新增 `FLOMO_VLM_RETRY_MODEL`，失败图片 retry 可以切换到更强的 LM Studio 视觉模型；未配置时沿用 `FLOMO_VLM_MODEL` 并提示，配置成相同模型时直接停止。
- Stage 2 内置 retry 和 `retry_failed_images.py` 都会记录实际 retry 模型名到 `store/image.enriched.jsonl` 的 `model_name`。
- 引导脚本复用现有 Stage 1-4 和失败重试脚本，不改变 JSONL schema、目录结构或下游产物。
- 重写中英文 README 的使用入口，区分“第一次使用”和“日常使用”，并把单阶段命令、长图切片、手动写回和本地 report 移到高级用法。
- 扩展测试，覆盖 `.env` 加载、mock provider 生成 chunks、缺少 LM Studio 配置时停止、retry 专用模型生效、retry 模型缺失时 fallback、retry 模型与普通模型相同时停止。
- 清理测试文件中已有 Ruff 格式项，让计划中的 `tests` 范围 Ruff 检查可以通过。

### 验证结果

- `python -m ruff check scripts\enrich_images.py scripts\retry_failed_images.py scripts\guide.py tests src\flomo_pipeline\enrich\runner.py src\flomo_pipeline\enrich\retry_config.py src\flomo_pipeline\enrich\providers\__init__.py` 通过。
- `python -m pytest` 通过：67 passed。
- `python -m mypy src` 通过。
- `python scripts\check_open_source_readiness.py` 通过；本地 `raw/`、`store/`、`monthly/`、`llm_chunks/` 中仍有被忽略的私人数据，不能直接打包工作树发布。

## 2026-04-28 - 0.3.0 级别更新

### 本次更新内容

- 梳理仓库结构，确认现有 stage 拆分仍合理，主要臃肿点是重复的校验和文件读写基础代码。
- 新增 `src/flomo_pipeline/common/io.py`，统一 JSON、JSONL 和文本写入读取。
- 新增 `src/flomo_pipeline/common/validation.py`，统一校验报告、违规项、严重级别和 JSON 解析错误格式。
- Stage 1-5 的 validator 继续保留各自业务规则，但共享同一套报告结构。
- Stage runner 和 writer 改用共享文件读写工具，减少重复实现。
- 删除无引用的 `src/flomo_pipeline/preview/` 空包和 `preview/.gitkeep` 占位文件；`.gitignore` 仍保护本地遗留的 `preview/` 输出。
- 删除独立的 `fail-image-handle-guidance.md`，将失败图片外部识别写回流程合并进中英文 README。
- 新增 `AGENTS.md`，记录 AI Agent 接手仓库时的边界、禁区和验证要求。
- 更新中英文 README 和 release checklist，说明当前目录边界、`common/` 用途和本地遗留 `preview/` 的处理方式。

### 验证结果

- 完整测试集：58 passed。
- 类型检查：`python -m mypy src` 通过。
- 本次改动范围 Ruff 检查通过。
- Open-source readiness 检查通过；本地 `raw/`、`store/`、`monthly/`、`llm_chunks/` 中仍有被忽略的私人数据，不能直接打包工作树发布。

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
