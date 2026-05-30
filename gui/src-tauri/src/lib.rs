use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};
#[cfg(debug_assertions)]
use std::{
    io::{BufRead, BufReader},
    process::Stdio,
    thread,
};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const ENV_KEYS: [&str; 5] = [
    "FLOMO_VLM_BASE_URL",
    "FLOMO_VLM_MODEL",
    "FLOMO_VLM_RETRY_MODEL",
    "FLOMO_VLM_TIMEOUT_SECONDS",
    "FLOMO_VLM_MAX_TOKENS",
];

#[derive(Default)]
struct WorkflowState {
    active: Option<ActiveWorkflow>,
}

struct ActiveWorkflow {
    task_id: String,
    process: Option<ActiveProcess>,
    cancelling: bool,
}

enum ActiveProcess {
    Sidecar(CommandChild),
    #[cfg(debug_assertions)]
    Local { pid: u32 },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AppSettings {
    project_root: String,
    env_file: String,
    raw_root: String,
    store_root: String,
    monthly_root: String,
    chunks_root: String,
    vlm_base_url: String,
    vlm_model: String,
    vlm_retry_model: String,
    vlm_timeout_seconds: String,
    vlm_max_tokens: String,
    env_exists: bool,
    runtime_mode: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct WorkflowRequest {
    action: String,
    provider: String,
    month: Option<String>,
    raw_root: String,
    store_root: String,
    monthly_root: String,
    chunks_root: String,
    env_file: String,
    image: Option<String>,
    rounds: u32,
}

#[derive(Debug, Clone, Serialize)]
struct WorkflowStarted {
    task_id: String,
    command: String,
}

#[derive(Debug, Clone, Serialize)]
struct WorkflowOutput {
    task_id: String,
    stream: String,
    line: String,
}

#[derive(Debug, Clone, Serialize)]
struct WorkflowCompleted {
    task_id: String,
    status: String,
    code: Option<i32>,
}

#[tauri::command]
fn read_settings(app: AppHandle) -> Result<AppSettings, String> {
    let project_root = workspace_root(&app)?;
    let env_file = project_root.join(".env");
    let env = read_env_map(&env_file)?;

    Ok(AppSettings {
        project_root: project_root.to_string_lossy().into_owned(),
        env_file: env_file.to_string_lossy().into_owned(),
        raw_root: project_root.join("raw").to_string_lossy().into_owned(),
        store_root: project_root.join("store").to_string_lossy().into_owned(),
        monthly_root: project_root.join("monthly").to_string_lossy().into_owned(),
        chunks_root: project_root.join("llm_chunks").to_string_lossy().into_owned(),
        vlm_base_url: env
            .get("FLOMO_VLM_BASE_URL")
            .cloned()
            .unwrap_or_else(|| "http://127.0.0.1:1234/v1".to_string()),
        vlm_model: env.get("FLOMO_VLM_MODEL").cloned().unwrap_or_default(),
        vlm_retry_model: env
            .get("FLOMO_VLM_RETRY_MODEL")
            .cloned()
            .unwrap_or_default(),
        vlm_timeout_seconds: env
            .get("FLOMO_VLM_TIMEOUT_SECONDS")
            .cloned()
            .unwrap_or_else(|| "180".to_string()),
        vlm_max_tokens: env
            .get("FLOMO_VLM_MAX_TOKENS")
            .cloned()
            .unwrap_or_else(|| "4096".to_string()),
        env_exists: env_file.exists(),
        runtime_mode: runtime_mode(&app),
    })
}

#[tauri::command]
fn save_settings(app: AppHandle, settings: AppSettings) -> Result<(), String> {
    let env_file = normalize_env_file(&app, &settings.env_file)?;
    let updates = env_updates_from_settings(&settings);
    write_env_file(&env_file, &updates)
}

#[tauri::command]
fn run_workflow(
    app: AppHandle,
    state: State<'_, Mutex<WorkflowState>>,
    request: WorkflowRequest,
) -> Result<WorkflowStarted, String> {
    let mut guarded = state
        .lock()
        .map_err(|_| "无法读取当前任务状态。".to_string())?;
    if guarded.active.is_some() {
        return Err("已有任务正在运行。".to_string());
    }

    validate_request(&request)?;
    let project_root = workspace_root(&app)?;
    let sidecar_args = build_sidecar_args(&request, &project_root);
    let command_text = display_command("flomo-sidecar", &sidecar_args);

    if let Ok(sidecar_command) = app.shell().sidecar("flomo-sidecar") {
        let (mut rx, child) = sidecar_command
            .args(sidecar_args)
            .spawn()
            .map_err(|error| format!("无法启动内置处理程序：{error}"))?;

        let task_id = new_task_id();
        guarded.active = Some(ActiveWorkflow {
            task_id: task_id.clone(),
            process: Some(ActiveProcess::Sidecar(child)),
            cancelling: false,
        });
        drop(guarded);

        let wait_app = app.clone();
        let wait_task_id = task_id.clone();
        tauri::async_runtime::spawn(async move {
            let mut code: Option<i32> = None;
            let mut status = "failed".to_string();
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        emit_output(&wait_app, &wait_task_id, "stdout", &line);
                    }
                    CommandEvent::Stderr(line) => {
                        emit_output(&wait_app, &wait_task_id, "stderr", &line);
                    }
                    CommandEvent::Error(error) => {
                        let _ = wait_app.emit(
                            "workflow-output",
                            WorkflowOutput {
                                task_id: wait_task_id.clone(),
                                stream: "stderr".to_string(),
                                line: error,
                            },
                        );
                    }
                    CommandEvent::Terminated(payload) => {
                        code = payload.code;
                        status = if code == Some(0) { "success" } else { "failed" }.to_string();
                        break;
                    }
                    _ => {}
                }
            }

            finish_workflow(wait_app, wait_task_id, status, code);
        });

        return Ok(WorkflowStarted {
            task_id,
            command: command_text,
        });
    }

    #[cfg(not(debug_assertions))]
    {
        return Err("内置处理程序缺失，请重新安装应用。".to_string());
    }

    #[cfg(debug_assertions)]
    {
        let (program, args) = build_local_python_command(&request, &project_root);
        let command_text = display_command(&program, &args);
        let mut child = Command::new(&program)
            .args(&args)
            .current_dir(&project_root)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("无法启动本机 Python：{error}"))?;

        let task_id = new_task_id();
        let pid = child.id();
        guarded.active = Some(ActiveWorkflow {
            task_id: task_id.clone(),
            process: Some(ActiveProcess::Local { pid }),
            cancelling: false,
        });
        drop(guarded);

        if let Some(stdout) = child.stdout.take() {
            spawn_output_reader(app.clone(), task_id.clone(), "stdout", stdout);
        }
        if let Some(stderr) = child.stderr.take() {
            spawn_output_reader(app.clone(), task_id.clone(), "stderr", stderr);
        }

        let wait_app = app.clone();
        let wait_task_id = task_id.clone();
        thread::spawn(move || {
            let code = child.wait().ok().and_then(|status| status.code());
            let status = if code == Some(0) { "success" } else { "failed" }.to_string();
            finish_workflow(wait_app, wait_task_id, status, code);
        });

        Ok(WorkflowStarted {
            task_id,
            command: command_text,
        })
    }
}

#[tauri::command(rename_all = "camelCase")]
fn cancel_workflow(
    state: State<'_, Mutex<WorkflowState>>,
    task_id: String,
) -> Result<(), String> {
    let process = {
        let mut guarded = state
            .lock()
            .map_err(|_| "无法读取当前任务状态。".to_string())?;
        let active = guarded
            .active
            .as_mut()
            .ok_or_else(|| "没有正在运行的任务。".to_string())?;
        if active.task_id != task_id {
            return Err("任务已经变化，无法停止。".to_string());
        }
        active.cancelling = true;
        active.process.take()
    };

    match process {
        Some(ActiveProcess::Sidecar(child)) => child
            .kill()
            .map_err(|error| format!("停止任务失败：{error}")),
        #[cfg(debug_assertions)]
        Some(ActiveProcess::Local { pid }) => kill_process(pid),
        None => Ok(()),
    }
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    let target = PathBuf::from(path);
    if !target.exists() {
        return Err("路径不存在。".to_string());
    }

    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("explorer");
        command.arg(&target);
        command
    };

    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(&target);
        command
    };

    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(&target);
        command
    };

    command
        .spawn()
        .map_err(|error| format!("无法打开路径：{error}"))?;
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(WorkflowState::default()))
        .invoke_handler(tauri::generate_handler![
            read_settings,
            save_settings,
            run_workflow,
            cancel_workflow,
            open_path
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(debug_assertions)]
fn dev_project_root() -> Result<PathBuf, String> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法定位项目根目录。".to_string())
}

fn workspace_root(_app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(debug_assertions)]
    {
        return dev_project_root();
    }

    #[cfg(not(debug_assertions))]
    {
        let root = _app
            .path()
            .app_data_dir()
            .map_err(|error| format!("无法定位应用数据目录：{error}"))?;
        fs::create_dir_all(&root).map_err(|error| format!("无法创建应用数据目录：{error}"))?;
        Ok(root)
    }
}

fn runtime_mode(app: &AppHandle) -> String {
    if app.shell().sidecar("flomo-sidecar").is_ok() {
        "内置 sidecar".to_string()
    } else if cfg!(debug_assertions) {
        "开发模式：本机 Python".to_string()
    } else {
        "sidecar 缺失".to_string()
    }
}

fn normalize_env_file(app: &AppHandle, path: &str) -> Result<PathBuf, String> {
    let requested = PathBuf::from(path);
    if requested.is_absolute() {
        return Ok(requested);
    }
    Ok(workspace_root(app)?.join(requested))
}

fn read_env_map(path: &Path) -> Result<HashMap<String, String>, String> {
    let mut values = HashMap::new();
    if !path.exists() {
        return Ok(values);
    }

    let content = fs::read_to_string(path).map_err(|error| format!("无法读取 .env：{error}"))?;
    for line in content.lines() {
        if let Some((key, value)) = parse_env_line(line) {
            values.insert(key, value);
        }
    }
    Ok(values)
}

fn parse_env_line(line: &str) -> Option<(String, String)> {
    let trimmed = line.trim();
    if trimmed.is_empty() || trimmed.starts_with('#') {
        return None;
    }
    let assignment = trimmed.strip_prefix("export ").unwrap_or(trimmed);
    let (raw_key, raw_value) = assignment.split_once('=')?;
    let key = raw_key.trim();
    if key.is_empty() {
        return None;
    }
    Some((key.to_string(), unquote_env_value(raw_value.trim())))
}

fn unquote_env_value(value: &str) -> String {
    if value.len() >= 2 {
        let bytes = value.as_bytes();
        if (bytes[0] == b'"' && bytes[value.len() - 1] == b'"')
            || (bytes[0] == b'\'' && bytes[value.len() - 1] == b'\'')
        {
            return value[1..value.len() - 1].to_string();
        }
    }
    value.to_string()
}

fn env_updates_from_settings(settings: &AppSettings) -> HashMap<String, String> {
    let pairs = [
        ("FLOMO_VLM_BASE_URL", settings.vlm_base_url.trim()),
        ("FLOMO_VLM_MODEL", settings.vlm_model.trim()),
        ("FLOMO_VLM_RETRY_MODEL", settings.vlm_retry_model.trim()),
        (
            "FLOMO_VLM_TIMEOUT_SECONDS",
            settings.vlm_timeout_seconds.trim(),
        ),
        ("FLOMO_VLM_MAX_TOKENS", settings.vlm_max_tokens.trim()),
    ];

    pairs
        .into_iter()
        .filter(|(_, value)| !value.is_empty())
        .map(|(key, value)| (key.to_string(), value.to_string()))
        .collect()
}

fn write_env_file(path: &Path, updates: &HashMap<String, String>) -> Result<(), String> {
    let original = if path.exists() {
        fs::read_to_string(path).map_err(|error| format!("无法读取 .env：{error}"))?
    } else {
        String::new()
    };

    let mut seen: HashMap<String, bool> = ENV_KEYS
        .iter()
        .map(|key| ((*key).to_string(), false))
        .collect();
    let mut lines = Vec::new();

    for line in original.lines() {
        if let Some((key, _)) = parse_env_line(line) {
            if ENV_KEYS.contains(&key.as_str()) {
                if let Some(value) = updates.get(&key) {
                    lines.push(format!("{key}={value}"));
                    seen.insert(key, true);
                }
                continue;
            }
        }
        lines.push(line.to_string());
    }

    for key in ENV_KEYS {
        if !seen.get(key).copied().unwrap_or(false) {
            if let Some(value) = updates.get(key) {
                lines.push(format!("{key}={value}"));
            }
        }
    }

    let mut content = lines.join("\n");
    if !content.is_empty() {
        content.push('\n');
    }
    fs::write(path, content).map_err(|error| format!("无法写入 .env：{error}"))
}

fn validate_request(request: &WorkflowRequest) -> Result<(), String> {
    if !matches!(
        request.action.as_str(),
        "first" | "daily" | "probe" | "retry"
    ) {
        return Err("未知操作。".to_string());
    }
    if !matches!(request.provider.as_str(), "lmstudio" | "mock") {
        return Err("图片处理方式必须是 lmstudio 或 mock。".to_string());
    }
    if request.action == "probe" && request.image.as_deref().unwrap_or("").trim().is_empty() {
        return Err("探测图片需要先选择图片。".to_string());
    }
    if request.action == "retry" && request.rounds == 0 {
        return Err("重试轮数必须大于 0。".to_string());
    }
    Ok(())
}

fn build_sidecar_args(request: &WorkflowRequest, project_root: &Path) -> Vec<String> {
    let mut args = vec![
        "--action".to_string(),
        request.action.clone(),
        "--project-root".to_string(),
        project_root.to_string_lossy().into_owned(),
        "--env-file".to_string(),
        request.env_file.clone(),
    ];

    if matches!(request.action.as_str(), "first" | "daily" | "retry") {
        args.extend(["--provider".to_string(), request.provider.clone()]);
    }

    args.extend([
        "--raw-root".to_string(),
        request.raw_root.clone(),
        "--store-root".to_string(),
        request.store_root.clone(),
        "--monthly-root".to_string(),
        request.monthly_root.clone(),
        "--chunks-root".to_string(),
        request.chunks_root.clone(),
    ]);

    if let Some(month) = request
        .month
        .as_ref()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    {
        args.extend(["--month".to_string(), month.to_string()]);
    }

    if request.action == "probe" {
        if let Some(image) = request.image.as_ref() {
            args.extend(["--image".to_string(), image.clone()]);
        }
    }

    if request.action == "retry" {
        args.extend(["--rounds".to_string(), request.rounds.to_string()]);
    }

    args
}

#[cfg(debug_assertions)]
fn build_local_python_command(request: &WorkflowRequest, project_root: &Path) -> (String, Vec<String>) {
    let mut args = vec![
        "scripts/guide.py".to_string(),
        "--action".to_string(),
        request.action.clone(),
        "--env-file".to_string(),
        request.env_file.clone(),
    ];

    if matches!(request.action.as_str(), "first" | "daily" | "retry") {
        args.extend(["--provider".to_string(), request.provider.clone()]);
    }

    args.extend([
        "--raw-root".to_string(),
        request.raw_root.clone(),
        "--store-root".to_string(),
        request.store_root.clone(),
        "--monthly-root".to_string(),
        request.monthly_root.clone(),
        "--chunks-root".to_string(),
        request.chunks_root.clone(),
    ]);

    if let Some(month) = request
        .month
        .as_ref()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    {
        args.extend(["--month".to_string(), month.to_string()]);
    }

    if request.action == "probe" {
        if let Some(image) = request.image.as_ref() {
            args.extend(["--image".to_string(), image.clone()]);
        }
    }

    if request.action == "retry" {
        args.extend(["--rounds".to_string(), request.rounds.to_string()]);
    }

    let program = std::env::var("PYTHON").unwrap_or_else(|_| "python".to_string());
    let guide_path = project_root.join("scripts").join("guide.py");
    if guide_path.exists() {
        args[0] = guide_path.to_string_lossy().into_owned();
    }
    (program, args)
}

fn display_command(program: &str, args: &[String]) -> String {
    std::iter::once(program.to_string())
        .chain(args.iter().cloned())
        .map(|part| {
            if part.contains(' ') {
                format!("\"{}\"", part.replace('"', "\\\""))
            } else {
                part
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn emit_output(app: &AppHandle, task_id: &str, stream: &str, bytes: &[u8]) {
    let line = String::from_utf8_lossy(bytes).trim_end().to_string();
    let _ = app.emit(
        "workflow-output",
        WorkflowOutput {
            task_id: task_id.to_string(),
            stream: stream.to_string(),
            line,
        },
    );
}

fn finish_workflow(
    app: AppHandle,
    task_id: String,
    mut status: String,
    code: Option<i32>,
) {
    let state = app.state::<Mutex<WorkflowState>>();
    if let Ok(mut guarded) = state.lock() {
        if let Some(active) = &guarded.active {
            if active.task_id == task_id && active.cancelling {
                status = "cancelled".to_string();
            }
        }
        if guarded
            .active
            .as_ref()
            .is_some_and(|active| active.task_id == task_id)
        {
            guarded.active = None;
        }
    }

    let _ = app.emit(
        "workflow-completed",
        WorkflowCompleted {
            task_id,
            status,
            code,
        },
    );
}

#[cfg(debug_assertions)]
fn spawn_output_reader<R>(app: AppHandle, task_id: String, stream: &'static str, reader: R)
where
    R: std::io::Read + Send + 'static,
{
    thread::spawn(move || {
        let buffered = BufReader::new(reader);
        for line in buffered.lines().map_while(Result::ok) {
            let _ = app.emit(
                "workflow-output",
                WorkflowOutput {
                    task_id: task_id.clone(),
                    stream: stream.to_string(),
                    line,
                },
            );
        }
    });
}

fn new_task_id() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    format!("workflow-{millis}")
}

#[cfg(debug_assertions)]
fn kill_process(pid: u32) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    let status = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .status();

    #[cfg(not(target_os = "windows"))]
    let status = Command::new("kill").args(["-TERM", &pid.to_string()]).status();

    match status {
        Ok(status) if status.success() => Ok(()),
        Ok(status) => Err(format!("停止任务失败，退出码：{status}")),
        Err(error) => Err(format!("停止任务失败：{error}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_settings(env_file: &Path) -> AppSettings {
        AppSettings {
            project_root: "project".to_string(),
            env_file: env_file.to_string_lossy().into_owned(),
            raw_root: "raw".to_string(),
            store_root: "store".to_string(),
            monthly_root: "monthly".to_string(),
            chunks_root: "llm_chunks".to_string(),
            vlm_base_url: "http://127.0.0.1:1234/v1".to_string(),
            vlm_model: "local-vlm".to_string(),
            vlm_retry_model: String::new(),
            vlm_timeout_seconds: "180".to_string(),
            vlm_max_tokens: "4096".to_string(),
            env_exists: true,
            runtime_mode: "test".to_string(),
        }
    }

    #[test]
    fn env_writer_preserves_comments_and_unrelated_values() {
        let dir = std::env::temp_dir().join(new_task_id());
        fs::create_dir_all(&dir).unwrap();
        let env_file = dir.join(".env");
        fs::write(
            &env_file,
            "# keep\nOTHER=value\nFLOMO_VLM_MODEL=old\nFLOMO_VLM_RETRY_MODEL=old-retry\n",
        )
        .unwrap();

        let updates = env_updates_from_settings(&sample_settings(&env_file));
        write_env_file(&env_file, &updates).unwrap();
        let content = fs::read_to_string(&env_file).unwrap();

        assert!(content.contains("# keep"));
        assert!(content.contains("OTHER=value"));
        assert!(content.contains("FLOMO_VLM_MODEL=local-vlm"));
        assert!(!content.contains("old-retry"));
    }

    #[test]
    fn command_builder_maps_main_actions_to_guide() {
        let request = WorkflowRequest {
            action: "first".to_string(),
            provider: "mock".to_string(),
            month: Some("2026-05".to_string()),
            raw_root: "raw".to_string(),
            store_root: "store".to_string(),
            monthly_root: "monthly".to_string(),
            chunks_root: "llm_chunks".to_string(),
            env_file: ".env".to_string(),
            image: None,
            rounds: 3,
        };

        let args = build_sidecar_args(&request, Path::new("project"));
        assert!(has_arg_pair(&args, "--action", "first"));
        assert!(has_arg_pair(&args, "--provider", "mock"));
        assert!(has_arg_pair(&args, "--month", "2026-05"));
    }

    #[test]
    fn command_builder_maps_probe_image() {
        let request = WorkflowRequest {
            action: "probe".to_string(),
            provider: "lmstudio".to_string(),
            month: None,
            raw_root: "raw".to_string(),
            store_root: "store".to_string(),
            monthly_root: "monthly".to_string(),
            chunks_root: "llm_chunks".to_string(),
            env_file: ".env".to_string(),
            image: Some("store/images/example.png".to_string()),
            rounds: 3,
        };

        let args = build_sidecar_args(&request, Path::new("project"));
        assert!(has_arg_pair(&args, "--action", "probe"));
        assert!(has_arg_pair(&args, "--image", "store/images/example.png"));
        assert!(!args.iter().any(|arg| arg == "--provider"));
    }

    fn has_arg_pair(args: &[String], key: &str, value: &str) -> bool {
        args.windows(2)
            .any(|pair| pair[0] == key && pair[1] == value)
    }
}
