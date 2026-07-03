#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Deserialize;
use std::{
    path::{Path, PathBuf},
    process::Command,
    sync::Mutex,
};
use tauri::{path::BaseDirectory, Manager, RunEvent};

const DESKTOP_PORT: u16 = 18080;

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

fn main() {
    tauri::Builder::default()
        .manage(BackendProcessState::default())
        .setup(|app| {
            set_main_window_title(app.app_handle(), "Lang Drill Agent - preparing backend");
            let backend = start_backend(app)?;
            if !backend.ok {
                return Err("Desktop backend bootstrap returned ok=false".into());
            }
            let state = app.state::<BackendProcessState>();
            if let Some(pid) = backend.pid {
                *state.pid.lock().map_err(|_| "backend pid lock poisoned")? = Some(pid);
            }
            *state
                .owned
                .lock()
                .map_err(|_| "backend ownership lock poisoned")? = backend.owned;
            let title = match backend.url.as_deref() {
                Some(url) => format!("Lang Drill Agent - {}", url),
                None => "Lang Drill Agent".to_string(),
            };
            set_main_window_title(app.app_handle(), &title);
            if let Some(env_path) = backend.env {
                eprintln!("[langdrill-desktop] environment file: {env_path}");
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

fn set_main_window_title(app: &tauri::AppHandle, title: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(title);
    }
}

fn start_backend(app: &mut tauri::App) -> Result<BackendStartResult, Box<dyn std::error::Error>> {
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

    let output = Command::new("powershell.exe")
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(script)
        .arg("-ProjectRoot")
        .arg(project_root)
        .arg("-AppDataDir")
        .arg(app_data_dir)
        .arg("-LocalAppDataDir")
        .arg(local_app_data_dir)
        .arg("-Port")
        .arg(DESKTOP_PORT.to_string())
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        return Err(format!(
            "Desktop backend bootstrap failed.\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
        )
        .into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let json_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'))
        .ok_or("Desktop backend bootstrap did not return JSON status.")?;
    Ok(serde_json::from_str(json_line)?)
}

fn resource_or_dev_path(
    app: &tauri::AppHandle,
    resource_path: &str,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
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

fn windows_known_dir(
    env_key: &str,
    app_folder: &str,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
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
