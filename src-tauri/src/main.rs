#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Deserialize;
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
use std::{
    io::{BufRead, BufReader, Read},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use tauri::{path::BaseDirectory, Manager, RunEvent};

const DESKTOP_PORT: u16 = 18080;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

type DesktopResult<T> = Result<T, Box<dyn std::error::Error + Send + Sync>>;

const BOOTSTRAP_HTML: &str = r##"<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lang Drill Agent</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
      background: #f5f7fb;
      color: #172033;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at 20% 10%, rgba(68, 130, 255, 0.16), transparent 32rem),
        radial-gradient(circle at 80% 0%, rgba(34, 197, 94, 0.14), transparent 26rem),
        linear-gradient(145deg, #f8fbff 0%, #eef3f8 100%);
    }
    .shell {
      width: min(680px, calc(100vw - 48px));
      padding: 36px;
      border: 1px solid rgba(104, 119, 147, 0.18);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.82);
      box-shadow: 0 24px 70px rgba(31, 41, 55, 0.14);
      backdrop-filter: blur(18px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 26px;
    }
    .mark {
      width: 44px;
      height: 44px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: #244d9a;
      color: white;
      font-weight: 700;
    }
    h1, h2, p { margin: 0; }
    h1 {
      font-size: 22px;
      font-weight: 720;
    }
    .subtitle {
      margin-top: 4px;
      color: #5b6578;
      font-size: 14px;
    }
    .bar {
      width: 100%;
      height: 10px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(100, 116, 139, 0.16);
    }
    #bar-fill {
      width: 6%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #244d9a, #16a085);
      transition: width 220ms ease;
    }
    #status {
      margin-top: 22px;
      font-size: 18px;
      font-weight: 680;
    }
    #detail {
      margin-top: 8px;
      color: #536174;
      line-height: 1.6;
      word-break: break-word;
    }
    #log {
      margin: 20px 0 0;
      padding: 14px 16px;
      max-height: 180px;
      overflow: auto;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.055);
      color: #43506a;
      font-size: 13px;
      line-height: 1.55;
      list-style-position: inside;
    }
    #hint {
      margin-top: 18px;
      color: #69758a;
      font-size: 13px;
      line-height: 1.6;
    }
    body.error #bar-fill {
      background: linear-gradient(90deg, #b42318, #f59e0b);
    }
    body.error #status {
      color: #b42318;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        background: #121820;
        color: #eef3ff;
      }
      body {
        background:
          radial-gradient(circle at 20% 10%, rgba(86, 140, 255, 0.2), transparent 32rem),
          radial-gradient(circle at 80% 0%, rgba(45, 212, 191, 0.14), transparent 26rem),
          linear-gradient(145deg, #111827 0%, #172033 100%);
      }
      .shell {
        border-color: rgba(148, 163, 184, 0.16);
        background: rgba(17, 24, 39, 0.82);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
      }
      .subtitle, #detail, #hint {
        color: #a8b3c7;
      }
      #log {
        background: rgba(255, 255, 255, 0.06);
        color: #c8d1e1;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="brand" aria-label="Lang Drill Agent">
      <div class="mark">LD</div>
      <div>
        <h1>Lang Drill Agent</h1>
        <p class="subtitle">正在准备本地学习环境</p>
      </div>
    </section>
    <div class="bar" aria-hidden="true"><div id="bar-fill"></div></div>
    <h2 id="status">正在启动桌面应用...</h2>
    <p id="detail">首次启动会检测 Python 运行时、选择可用依赖源并准备本地后端。</p>
    <ol id="log"></ol>
    <p id="hint">如果网络较慢，首次启动可能需要几分钟；后续会复用本机缓存。</p>
  </main>
  <script>
    const logs = [];
    window.__langdrillSetStatus = function (payload) {
      const data = payload || {};
      const status = document.getElementById("status");
      const detail = document.getElementById("detail");
      const fill = document.getElementById("bar-fill");
      const log = document.getElementById("log");
      if (data.stage === "error") {
        document.body.classList.add("error");
      }
      if (typeof data.message === "string" && data.message) {
        status.textContent = data.message;
        logs.push(data.message);
      }
      if (typeof data.detail === "string") {
        detail.textContent = data.detail;
      }
      const percent = Number(data.percent);
      if (Number.isFinite(percent) && percent >= 0) {
        fill.style.width = Math.max(4, Math.min(100, percent)) + "%";
      }
      const recent = logs.slice(-7);
      log.replaceChildren(...recent.map((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        return li;
      }));
    };
  </script>
</body>
</html>"##;

#[derive(Debug, Default)]
struct BackendProcessState {
    pid: Mutex<Option<u32>>,
    owned: Mutex<bool>,
}

#[derive(Debug, Deserialize)]
struct BackendStartResult {
    ok: bool,
    owned: bool,
    pid: Option<u32>,
    url: Option<String>,
    env: Option<String>,
}

#[derive(Debug, Clone)]
struct DesktopBootstrapContext {
    script: PathBuf,
    project_root: PathBuf,
    app_data_dir: PathBuf,
    local_app_data_dir: PathBuf,
}

#[derive(Debug, Deserialize)]
struct ProgressLine {
    stage: Option<String>,
    message: Option<String>,
    percent: Option<i32>,
    detail: Option<String>,
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcessState::default())
        .setup(|app| {
            let app_handle = app.app_handle().clone();
            install_bootstrap_page(&app_handle);
            set_main_window_title(&app_handle, "Lang Drill Agent - preparing runtime");

            match prepare_bootstrap_context(app) {
                Ok(context) => {
                    push_bootstrap_status(
                        &app_handle,
                        "startup",
                        "正在准备桌面运行环境...",
                        3,
                        "",
                    );
                    start_backend_in_background(app_handle, context);
                }
                Err(error) => {
                    show_bootstrap_error(
                        &app_handle,
                        "桌面运行环境准备失败",
                        &error.to_string(),
                    );
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Tauri application")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                stop_owned_backend(app_handle);
            }
        });
}

fn prepare_bootstrap_context(app: &mut tauri::App) -> DesktopResult<DesktopBootstrapContext> {
    if !cfg!(target_os = "windows") {
        return Err("The desktop backend bootstrap is currently implemented for Windows.".into());
    }

    let app_handle = app.app_handle();
    let script = resource_or_dev_path(app_handle, "desktop-runtime/start-backend.ps1")?;
    let project_root = resource_or_dev_path(app_handle, "app/pyproject.toml")?
        .parent()
        .ok_or("invalid bundled app resource path")?
        .to_path_buf();
    let app_data_dir = windows_known_dir("APPDATA", "Lang Drill Agent")?;
    let local_app_data_dir = windows_known_dir("LOCALAPPDATA", "Lang Drill Agent")?;

    std::fs::create_dir_all(&app_data_dir)?;
    std::fs::create_dir_all(&local_app_data_dir)?;

    Ok(DesktopBootstrapContext {
        script,
        project_root,
        app_data_dir,
        local_app_data_dir,
    })
}

fn start_backend_in_background(app_handle: tauri::AppHandle, context: DesktopBootstrapContext) {
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(250));
        install_bootstrap_page(&app_handle);
        push_bootstrap_status(&app_handle, "startup", "正在准备桌面运行环境...", 3, "");

        match start_backend(&context, &app_handle) {
            Ok(backend) => {
                if !backend.ok {
                    show_bootstrap_error(
                        &app_handle,
                        "本地后端启动失败",
                        "Desktop backend bootstrap returned ok=false",
                    );
                    return;
                }
                record_backend_state(&app_handle, &backend);
                let title = match backend.url.as_deref() {
                    Some(url) => format!("Lang Drill Agent - {}", url),
                    None => "Lang Drill Agent".to_string(),
                };
                set_main_window_title(&app_handle, &title);
                let detail = backend
                    .env
                    .as_deref()
                    .map(|env_path| format!("配置文件: {env_path}"))
                    .unwrap_or_else(|| "正在进入学习工作台...".to_string());
                push_bootstrap_status(&app_handle, "ready", "本地后端已就绪", 100, &detail);
                thread::sleep(Duration::from_millis(600));
                reload_main_window(&app_handle);
            }
            Err(error) => {
                show_bootstrap_error(&app_handle, "启动失败", &error.to_string());
            }
        }
    });
}

fn record_backend_state(app: &tauri::AppHandle, backend: &BackendStartResult) {
    let state = app.state::<BackendProcessState>();
    if let Some(pid) = backend.pid {
        if let Ok(mut value) = state.pid.lock() {
            *value = Some(pid);
        }
    }
    if let Ok(mut owned) = state.owned.lock() {
        *owned = backend.owned;
    };
}

fn set_main_window_title(app: &tauri::AppHandle, title: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(title);
    }
}

fn install_bootstrap_page(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let html = serde_json::to_string(BOOTSTRAP_HTML).unwrap_or_else(|_| "\"\"".to_string());
        let script = format!("document.open(); document.write({html}); document.close();");
        let _ = window.eval(script);
    }
}

fn reload_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.reload();
    }
}

fn show_bootstrap_error(app: &tauri::AppHandle, message: &str, detail: &str) {
    set_main_window_title(app, "Lang Drill Agent - startup failed");
    push_bootstrap_status(app, "error", message, 100, detail);
}

fn push_bootstrap_status(
    app: &tauri::AppHandle,
    stage: &str,
    message: &str,
    percent: i32,
    detail: &str,
) {
    let payload = serde_json::json!({
        "stage": stage,
        "message": message,
        "percent": percent,
        "detail": detail,
    });
    let script = format!(
        "window.__langdrillSetStatus && window.__langdrillSetStatus({});",
        payload
    );
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.eval(script);
    }
}

fn start_backend(
    context: &DesktopBootstrapContext,
    app_handle: &tauri::AppHandle,
) -> DesktopResult<BackendStartResult> {
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-WindowStyle")
        .arg("Hidden")
        .arg("-File")
        .arg(path_for_powershell(&context.script))
        .arg("-ProjectRoot")
        .arg(path_for_powershell(&context.project_root))
        .arg("-AppDataDir")
        .arg(path_for_powershell(&context.app_data_dir))
        .arg("-LocalAppDataDir")
        .arg(path_for_powershell(&context.local_app_data_dir))
        .arg("-Port")
        .arg(DESKTOP_PORT.to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command.spawn()?;
    let stdout_lines = Arc::new(Mutex::new(Vec::new()));
    let stderr_lines = Arc::new(Mutex::new(Vec::new()));

    let stdout_reader = child
        .stdout
        .take()
        .ok_or("Desktop backend bootstrap did not provide stdout.")?;
    let stderr_reader = child
        .stderr
        .take()
        .ok_or("Desktop backend bootstrap did not provide stderr.")?;

    let stdout_handle = spawn_output_reader(stdout_reader, stdout_lines.clone(), None);
    let stderr_handle = spawn_output_reader(
        stderr_reader,
        stderr_lines.clone(),
        Some(app_handle.clone()),
    );

    let status = child.wait()?;
    let _ = stdout_handle.join();
    let _ = stderr_handle.join();

    let stdout = join_lines(&stdout_lines);
    let stderr = join_lines(&stderr_lines);

    if !status.success() {
        return Err(format!(
            "Desktop backend bootstrap failed.\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
        )
        .into());
    }

    let json_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'))
        .ok_or("Desktop backend bootstrap did not return JSON status.")?;
    Ok(serde_json::from_str(json_line)?)
}

fn spawn_output_reader<R: Read + Send + 'static>(
    reader: R,
    lines: Arc<Mutex<Vec<String>>>,
    app_handle: Option<tauri::AppHandle>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let reader = BufReader::new(reader);
        for line in reader.lines().map_while(Result::ok) {
            if let Ok(mut collected) = lines.lock() {
                collected.push(line.clone());
                if collected.len() > 240 {
                    collected.remove(0);
                }
            }
            if let Some(app) = app_handle.as_ref() {
                handle_bootstrap_output_line(app, &line);
            }
        }
    })
}

fn handle_bootstrap_output_line(app: &tauri::AppHandle, line: &str) {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return;
    }
    if let Some(json_text) = trimmed.strip_prefix("[langdrill-progress] ") {
        if let Ok(progress) = serde_json::from_str::<ProgressLine>(json_text) {
            let message = localize_progress_message(
                progress.message.as_deref().unwrap_or("Starting..."),
            );
            push_bootstrap_status(
                app,
                progress.stage.as_deref().unwrap_or("running"),
                &message,
                progress.percent.unwrap_or(-1),
                progress.detail.as_deref().unwrap_or(""),
            );
            return;
        }
    }
    push_bootstrap_status(app, "running", trimmed, -1, "");
}

fn localize_progress_message(message: &str) -> String {
    match message {
        "Preparing desktop runtime folders..." => "正在准备桌面运行目录...".to_string(),
        "Checking local backend port..." => "正在检查本地后端端口...".to_string(),
        "Preparing user configuration..." => "正在准备用户配置...".to_string(),
        "Syncing bundled backend files..." => "正在同步内置后端文件...".to_string(),
        "Checking local Python 3.11+ runtime..." => {
            "正在检查本机 Python 3.11+ 运行时...".to_string()
        }
        "Using existing Python runtime." => "已复用本机 Python 运行时。".to_string(),
        "Using cached Python runtime." => "已复用缓存 Python 运行时。".to_string(),
        "Choosing Python download source..." => "正在选择 Python 下载源...".to_string(),
        "Using cached Python installer." => "已复用缓存 Python 安装器。".to_string(),
        "Creating desktop virtual environment..." => "正在创建桌面虚拟环境...".to_string(),
        "Preparing Python package index..." => "正在准备 Python 依赖源...".to_string(),
        "Initializing local learning database..." => {
            "正在初始化本地学习数据库...".to_string()
        }
        "Starting local backend service..." => "正在启动本地后端服务...".to_string(),
        "Waiting for backend health check..." => "正在等待后端健康检查...".to_string(),
        "Local backend is ready." => "本地后端已就绪。".to_string(),
        "Reusing already running Lang Drill Agent backend." => {
            "已复用正在运行的 Lang Drill Agent 后端。".to_string()
        }
        _ => {
            if let Some(source) = message.strip_prefix("Testing Python runtime: ") {
                format!("正在检测 Python 运行时下载源：{source}")
            } else if let Some(source) = message.strip_prefix("Testing Python package index: ") {
                format!("正在检测 Python 依赖源：{source}")
            } else if let Some(source) = message
                .strip_prefix("Downloading from ")
                .and_then(|value| value.strip_suffix("..."))
            {
                format!("正在从 {source} 下载...")
            } else if let Some(source) = message
                .strip_prefix("Downloaded from ")
                .and_then(|value| value.strip_suffix("."))
            {
                format!("已从 {source} 下载完成。")
            } else if let Some(source) = message
                .strip_prefix("Download failed from ")
                .and_then(|value| value.strip_suffix(", trying next source..."))
            {
                format!("从 {source} 下载失败，正在尝试下一个源...")
            } else if let Some(source) = message
                .strip_prefix("Installing dependencies via ")
                .and_then(|value| value.strip_suffix("..."))
            {
                format!("正在通过 {source} 安装依赖...")
            } else if let Some(source) = message
                .strip_prefix("Dependency step completed via ")
                .and_then(|value| value.strip_suffix("."))
            {
                format!("依赖步骤已通过 {source} 完成。")
            } else if let Some(source) = message
                .strip_prefix("Dependency install failed via ")
                .and_then(|value| value.strip_suffix(", trying next source..."))
            {
                format!("通过 {source} 安装依赖失败，正在尝试下一个源...")
            } else if message.starts_with("Installing Python ") {
                message
                    .replace("Installing", "正在安装")
                    .replace("runtime into user cache...", "到用户缓存...")
            } else {
                message.to_string()
            }
        }
    }
}

fn join_lines(lines: &Arc<Mutex<Vec<String>>>) -> String {
    lines
        .lock()
        .map(|value| value.join("\n"))
        .unwrap_or_else(|_| String::new())
}

#[cfg(target_os = "windows")]
fn path_for_powershell(path: &Path) -> String {
    let value = path.display().to_string();
    if let Some(stripped) = value.strip_prefix(r"\\?\UNC\") {
        return format!(r"\\{stripped}");
    }
    if let Some(stripped) = value.strip_prefix(r"\\?\") {
        return stripped.to_string();
    }
    value
}

#[cfg(not(target_os = "windows"))]
fn path_for_powershell(path: &Path) -> String {
    path.display().to_string()
}

fn resource_or_dev_path(
    app: &tauri::AppHandle,
    resource_path: &str,
) -> DesktopResult<PathBuf> {
    let bundled = app.path().resolve(resource_path, BaseDirectory::Resource)?;
    if bundled.exists() {
        return Ok(bundled);
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let project_root = manifest_dir
        .parent()
        .ok_or("CARGO_MANIFEST_DIR has no parent project root")?;
    let dev_path = match resource_path {
        "desktop-runtime/start-backend.ps1" => {
            project_root.join("scripts/desktop/start-backend.ps1")
        }
        "app/pyproject.toml" => project_root.join("pyproject.toml"),
        other => project_root.join(other),
    };
    if dev_path.exists() {
        return Ok(dev_path);
    }

    Err(format!("Required desktop resource was not found: {resource_path}").into())
}

fn windows_known_dir(env_key: &str, app_folder: &str) -> DesktopResult<PathBuf> {
    let root = std::env::var_os(env_key).ok_or_else(|| format!("{env_key} is not set"))?;
    Ok(Path::new(&root).join(app_folder))
}

fn stop_owned_backend(app: &tauri::AppHandle) {
    let state = app.state::<BackendProcessState>();
    let owned = state.owned.lock().map(|value| *value).unwrap_or(false);
    if !owned {
        return;
    }
    let pid = state.pid.lock().ok().and_then(|value| *value);
    if let Some(pid) = pid {
        #[cfg(target_os = "windows")]
        {
            let _ = Command::new("taskkill")
                .arg("/PID")
                .arg(pid.to_string())
                .arg("/T")
                .arg("/F")
                .output();
        }
        #[cfg(not(target_os = "windows"))]
        {
            let _ = Command::new("kill").arg(pid.to_string()).output();
        }
    }
}
