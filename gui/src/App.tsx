import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Activity,
  CheckCircle2,
  FileImage,
  FolderOpen,
  PauseCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type WorkflowAction = "first" | "daily" | "probe" | "retry";
type Provider = "lmstudio" | "mock";
type RunStatus = "idle" | "running" | "success" | "failed" | "cancelled";

type AppSettings = {
  project_root: string;
  env_file: string;
  raw_root: string;
  store_root: string;
  monthly_root: string;
  chunks_root: string;
  vlm_base_url: string;
  vlm_model: string;
  vlm_retry_model: string;
  vlm_timeout_seconds: string;
  vlm_max_tokens: string;
  env_exists: boolean;
  runtime_mode: string;
};

type WorkflowRequest = {
  action: WorkflowAction;
  provider: Provider;
  month?: string;
  raw_root: string;
  store_root: string;
  monthly_root: string;
  chunks_root: string;
  env_file: string;
  image?: string;
  rounds: number;
};

type WorkflowStarted = {
  task_id: string;
  command: string;
};

type WorkflowOutput = {
  task_id: string;
  stream: "stdout" | "stderr";
  line: string;
};

type WorkflowCompleted = {
  task_id: string;
  status: "success" | "failed" | "cancelled";
  code: number | null;
};

type LogLine = {
  id: number;
  stream: "system" | "stdout" | "stderr";
  text: string;
};

const defaultSettings: AppSettings = {
  project_root: "",
  env_file: "",
  raw_root: "raw",
  store_root: "store",
  monthly_root: "monthly",
  chunks_root: "llm_chunks",
  vlm_base_url: "http://127.0.0.1:1234/v1",
  vlm_model: "",
  vlm_retry_model: "",
  vlm_timeout_seconds: "180",
  vlm_max_tokens: "4096",
  env_exists: false,
  runtime_mode: "",
};

const actionMeta: Record<
  WorkflowAction,
  { label: string; description: string; icon: typeof Play }
> = {
  first: {
    label: "首次生成",
    description: "从 raw/ 生成可交给外部 LLM 的 chunks。",
    icon: Play,
  },
  daily: {
    label: "日常更新",
    description: "更新 raw/ 后重新生成 chunks，已成功图片会跳过。",
    icon: RefreshCw,
  },
  probe: {
    label: "探测图片",
    description: "用 LM Studio 检查一张图片是否可读。",
    icon: Search,
  },
  retry: {
    label: "重试失败",
    description: "只重试已经失败的图片记录。",
    icon: RotateCcw,
  },
};

function App() {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [action, setAction] = useState<WorkflowAction>("first");
  const [provider, setProvider] = useState<Provider>("lmstudio");
  const [month, setMonth] = useState("");
  const [image, setImage] = useState("");
  const [rounds, setRounds] = useState(3);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeCommand, setActiveCommand] = useState("");
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [lastOutputPath, setLastOutputPath] = useState("");

  const lmstudioReady =
    settings.vlm_base_url.trim().length > 0 && settings.vlm_model.trim().length > 0;
  const canRun =
    status !== "running" &&
    (provider === "mock" && action !== "probe" ? true : lmstudioReady) &&
    (action !== "probe" || image.trim().length > 0);

  const configState = useMemo(() => {
    if (provider === "mock" && action !== "probe") {
      return { label: "mock 流程", tone: "neutral" };
    }
    if (lmstudioReady) {
      return { label: "LM Studio 已配置", tone: "good" };
    }
    return { label: "LM Studio 未完整配置", tone: "warn" };
  }, [action, lmstudioReady, provider]);

  useEffect(() => {
    void loadSettings();

    const unlistenOutput = listen<WorkflowOutput>("workflow-output", (event) => {
      setLogs((current) => [
        ...current,
        {
          id: current.length + 1,
          stream: event.payload.stream,
          text: event.payload.line,
        },
      ]);
    });

    const unlistenCompleted = listen<WorkflowCompleted>("workflow-completed", (event) => {
      setStatus(event.payload.status);
      setActiveTaskId(null);
      const suffix =
        event.payload.code === null ? "" : `，退出码 ${event.payload.code.toString()}`;
      pushSystemLog(`任务${statusLabel(event.payload.status)}${suffix}`);
    });

    return () => {
      void unlistenOutput.then((dispose) => dispose());
      void unlistenCompleted.then((dispose) => dispose());
    };
  }, []);

  useEffect(() => {
    if (action === "probe") {
      setProvider("lmstudio");
    }
  }, [action]);

  async function loadSettings() {
    const next = await invoke<AppSettings>("read_settings");
    setSettings(next);
  }

  function updateSettings<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function pushSystemLog(text: string) {
    setLogs((current) => [
      ...current,
      {
        id: current.length + 1,
        stream: "system",
        text,
      },
    ]);
  }

  async function saveSettings() {
    await invoke("save_settings", { settings });
    setSettings((current) => ({ ...current, env_exists: true }));
    pushSystemLog("配置已保存到 .env");
  }

  async function chooseDirectory(field: "raw_root" | "store_root" | "monthly_root" | "chunks_root") {
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath: settings[field],
    });
    if (typeof selected === "string") {
      updateSettings(field, selected);
    }
  }

  async function chooseImage() {
    const selected = await open({
      directory: false,
      multiple: false,
      filters: [
        {
          name: "图片",
          extensions: ["png", "jpg", "jpeg", "webp", "bmp", "gif"],
        },
      ],
    });
    if (typeof selected === "string") {
      setImage(selected);
    }
  }

  async function runWorkflow() {
    setLogs([]);
    setStatus("running");
    setLastOutputPath("");
    try {
      await invoke("save_settings", { settings });
      const request: WorkflowRequest = {
        action,
        provider,
        month: month.trim() || undefined,
        raw_root: settings.raw_root,
        store_root: settings.store_root,
        monthly_root: settings.monthly_root,
        chunks_root: settings.chunks_root,
        env_file: settings.env_file,
        image: image.trim() || undefined,
        rounds,
      };
      const started = await invoke<WorkflowStarted>("run_workflow", { request });
      setActiveTaskId(started.task_id);
      setActiveCommand(started.command);
      pushSystemLog(`已启动：${started.command}`);
      if (action === "first" || action === "daily") {
        setLastOutputPath(
          month.trim() ? `${settings.chunks_root}/${month.trim()}` : settings.chunks_root,
        );
      }
    } catch (error) {
      setStatus("failed");
      setActiveTaskId(null);
      pushSystemLog(String(error));
    }
  }

  async function cancelWorkflow() {
    if (!activeTaskId) {
      return;
    }
    await invoke("cancel_workflow", { taskId: activeTaskId });
    pushSystemLog("已请求停止当前任务");
  }

  async function openOutputPath() {
    if (lastOutputPath) {
      await invoke("open_path", { path: lastOutputPath });
    }
  }

  const selectedAction = actionMeta[action];
  const SelectedIcon = selectedAction.icon;

  return (
    <main className="shell">
      <section className="workspace">
        <aside className="sidebar" aria-label="工作流">
          <div className="brand">
            <div className="brandMark">ft</div>
            <div>
              <h1>flomo-transcriber</h1>
              <p>{settings.project_root || "本地资料处理工具"}</p>
            </div>
          </div>

          <nav className="actionList">
            {(Object.keys(actionMeta) as WorkflowAction[]).map((key) => {
              const meta = actionMeta[key];
              const Icon = meta.icon;
              return (
                <button
                  key={key}
                  className={key === action ? "actionButton active" : "actionButton"}
                  disabled={status === "running"}
                  onClick={() => setAction(key)}
                  type="button"
                >
                  <Icon size={18} aria-hidden="true" />
                  <span>{meta.label}</span>
                </button>
              );
            })}
          </nav>

          <div className={`statusPill ${configState.tone}`}>
            <Activity size={16} aria-hidden="true" />
            <span>{configState.label}</span>
          </div>
          <div className="runtimeInfo">
            <span>运行环境</span>
            <strong>{settings.runtime_mode || "检测中"}</strong>
          </div>
        </aside>

        <section className="controlPane">
          <header className="paneHeader">
            <div>
              <h2>
                <SelectedIcon size={22} aria-hidden="true" />
                {selectedAction.label}
              </h2>
              <p>{selectedAction.description}</p>
            </div>
            <div className={`runState ${status}`}>
              {statusIcon(status)}
              <span>{statusLabel(status)}</span>
            </div>
          </header>

          <section className="sectionBlock">
            <div className="sectionTitle">
              <FolderOpen size={18} aria-hidden="true" />
              <h3>路径</h3>
            </div>
            <PathInput
              label="raw"
              value={settings.raw_root}
              onChange={(value) => updateSettings("raw_root", value)}
              onPick={() => void chooseDirectory("raw_root")}
              disabled={status === "running"}
            />
            <PathInput
              label="store"
              value={settings.store_root}
              onChange={(value) => updateSettings("store_root", value)}
              onPick={() => void chooseDirectory("store_root")}
              disabled={status === "running"}
            />
            <PathInput
              label="monthly"
              value={settings.monthly_root}
              onChange={(value) => updateSettings("monthly_root", value)}
              onPick={() => void chooseDirectory("monthly_root")}
              disabled={status === "running"}
            />
            <PathInput
              label="llm_chunks"
              value={settings.chunks_root}
              onChange={(value) => updateSettings("chunks_root", value)}
              onPick={() => void chooseDirectory("chunks_root")}
              disabled={status === "running"}
            />
          </section>

          <section className="sectionBlock">
            <div className="sectionTitle">
              <Settings size={18} aria-hidden="true" />
              <h3>运行设置</h3>
            </div>
            <div className="fieldGrid">
              <label className="field">
                <span>月份</span>
                <input
                  value={month}
                  disabled={status === "running"}
                  onChange={(event) => setMonth(event.target.value)}
                  placeholder="全部月份"
                />
              </label>
              <label className="field">
                <span>图片处理</span>
                <select
                  value={provider}
                  disabled={status === "running" || action === "probe"}
                  onChange={(event) => setProvider(event.target.value as Provider)}
                >
                  <option value="lmstudio">LM Studio</option>
                  <option value="mock">mock</option>
                </select>
              </label>
              {action === "retry" && (
                <label className="field">
                  <span>重试轮数</span>
                  <input
                    min={1}
                    max={20}
                    type="number"
                    value={rounds}
                    disabled={status === "running"}
                    onChange={(event) => setRounds(Number(event.target.value))}
                  />
                </label>
              )}
              {action === "probe" && (
                <label className="field wide">
                  <span>图片</span>
                  <div className="inlinePicker">
                    <input
                      value={image}
                      disabled={status === "running"}
                      onChange={(event) => setImage(event.target.value)}
                      placeholder="选择一张图片"
                    />
                    <button
                      className="iconButton"
                      title="选择图片"
                      type="button"
                      disabled={status === "running"}
                      onClick={() => void chooseImage()}
                    >
                      <FileImage size={18} aria-hidden="true" />
                    </button>
                  </div>
                </label>
              )}
            </div>
          </section>

          <section className="sectionBlock">
            <div className="sectionTitle">
              <Settings size={18} aria-hidden="true" />
              <h3>LM Studio</h3>
            </div>
            <div className="fieldGrid">
              <label className="field wide">
                <span>Base URL</span>
                <input
                  value={settings.vlm_base_url}
                  disabled={status === "running"}
                  onChange={(event) => updateSettings("vlm_base_url", event.target.value)}
                />
              </label>
              <label className="field">
                <span>视觉模型</span>
                <input
                  value={settings.vlm_model}
                  disabled={status === "running"}
                  onChange={(event) => updateSettings("vlm_model", event.target.value)}
                  placeholder="必填"
                />
              </label>
              <label className="field">
                <span>重试模型</span>
                <input
                  value={settings.vlm_retry_model}
                  disabled={status === "running"}
                  onChange={(event) => updateSettings("vlm_retry_model", event.target.value)}
                  placeholder="可选"
                />
              </label>
              <label className="field">
                <span>超时秒数</span>
                <input
                  value={settings.vlm_timeout_seconds}
                  disabled={status === "running"}
                  onChange={(event) => updateSettings("vlm_timeout_seconds", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Max tokens</span>
                <input
                  value={settings.vlm_max_tokens}
                  disabled={status === "running"}
                  onChange={(event) => updateSettings("vlm_max_tokens", event.target.value)}
                />
              </label>
            </div>
          </section>

          <footer className="commandBar">
            <button
              className="secondaryButton"
              type="button"
              disabled={status === "running"}
              onClick={() => void saveSettings()}
            >
              <Save size={18} aria-hidden="true" />
              保存配置
            </button>
            {status === "running" ? (
              <button className="dangerButton" type="button" onClick={() => void cancelWorkflow()}>
                <PauseCircle size={18} aria-hidden="true" />
                停止
              </button>
            ) : (
              <button
                className="primaryButton"
                type="button"
                disabled={!canRun}
                onClick={() => void runWorkflow()}
              >
                <Play size={18} aria-hidden="true" />
                开始
              </button>
            )}
          </footer>
        </section>

        <section className="logPane">
          <header className="logHeader">
            <div>
              <h2>运行日志</h2>
              <p>{activeCommand || "等待任务开始"}</p>
            </div>
            <button
              className="secondaryButton compact"
              type="button"
              disabled={!lastOutputPath || status === "running"}
              onClick={() => void openOutputPath()}
            >
              <FolderOpen size={16} aria-hidden="true" />
              打开结果
            </button>
          </header>
          <div className="logOutput" aria-live="polite">
            {logs.length === 0 ? (
              <p className="emptyLog">日志会显示在这里。</p>
            ) : (
              logs.map((line) => (
                <div key={line.id} className={`logLine ${line.stream}`}>
                  <span>{line.stream}</span>
                  <pre>{line.text}</pre>
                </div>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

function PathInput({
  label,
  value,
  disabled,
  onChange,
  onPick,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onPick: () => void;
}) {
  return (
    <label className="pathField">
      <span>{label}</span>
      <input value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      <button
        className="iconButton"
        title={`选择 ${label} 目录`}
        type="button"
        disabled={disabled}
        onClick={onPick}
      >
        <FolderOpen size={18} aria-hidden="true" />
      </button>
    </label>
  );
}

function statusLabel(status: RunStatus | WorkflowCompleted["status"]) {
  const labels: Record<RunStatus, string> = {
    idle: "待运行",
    running: "运行中",
    success: "已完成",
    failed: "失败",
    cancelled: "已停止",
  };
  return labels[status];
}

function statusIcon(status: RunStatus) {
  if (status === "success") {
    return <CheckCircle2 size={17} aria-hidden="true" />;
  }
  if (status === "failed") {
    return <XCircle size={17} aria-hidden="true" />;
  }
  if (status === "cancelled") {
    return <PauseCircle size={17} aria-hidden="true" />;
  }
  return <Activity size={17} aria-hidden="true" />;
}

export default App;
