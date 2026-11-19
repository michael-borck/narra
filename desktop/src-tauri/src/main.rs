// Narra desktop: a thin Tauri shell around the Python core.
//
// On first launch it bootstraps a private Python runtime with uv (downloaded
// if absent), installs narra[serve] into an app-data venv, then runs
// `narra serve` as a localhost sidecar and shows its UI in the webview.
// Settings write the user's ~/.narra.yaml — bring your own writer + voice;
// nothing ever leaves the machine except requests to those providers.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

/// The narra release the runtime installs; bump together with PyPI releases.
const NARRA_VERSION: &str = "0.4.0";

struct Sidecar(Mutex<Option<Child>>);

#[derive(Serialize, Deserialize, Default, Clone)]
struct Settings {
    writer: String,
    voice: String,
    gemini_key: String,
    openai_url: String,
    openai_key: String,
    openai_writer_model: String,
    openai_voice_model: String,
    ollama_url: String,
    ollama_model: String,
    piper_voice: String,
    kokoro_voice: String,
}

fn status(app: &AppHandle, message: &str) {
    let _ = app.emit("status", message.to_string());
}

fn config_path() -> Result<PathBuf, String> {
    dirs::home_dir()
        .map(|home| home.join(".narra.yaml"))
        .ok_or_else(|| "Could not determine home directory".into())
}

fn yaml_str(value: &serde_yaml::Value, key: &str) -> String {
    value
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string()
}

fn yaml_str_path(value: &serde_yaml::Value, path: &[&str]) -> String {
    let mut current = value;
    for key in path {
        match current.get(*key) {
            Some(next) => current = next,
            None => return String::new(),
        }
    }
    current.as_str().unwrap_or_default().to_string()
}

/// First non-empty value along the given fallback paths.
fn yaml_str_any(value: &serde_yaml::Value, paths: &[&[&str]]) -> String {
    for path in paths {
        let found = yaml_str_path(value, path);
        if !found.is_empty() {
            return found;
        }
    }
    String::new()
}

fn set_str(map: &mut serde_yaml::Mapping, key: &str, value: &str) {
    let trimmed = value.trim();
    let value_key = serde_yaml::Value::String(key.to_string());
    if trimmed.is_empty() {
        map.remove(&value_key);
    } else {
        map.insert(value_key, trimmed.to_string().into());
    }
}

/// Get (or create) a nested mapping block at `parent[key]`.
fn block_mut<'a>(
    parent: &'a mut serde_yaml::Mapping,
    key: &str,
) -> &'a mut serde_yaml::Mapping {
    let entry = parent
        .entry(key.into())
        .or_insert(serde_yaml::Value::Mapping(Default::default()));
    if !matches!(entry, serde_yaml::Value::Mapping(_)) {
        *entry = serde_yaml::Value::Mapping(Default::default());
    }
    match entry {
        serde_yaml::Value::Mapping(map) => map,
        _ => unreachable!(),
    }
}

#[tauri::command]
fn get_settings() -> Settings {
    let Ok(path) = config_path() else {
        return Settings::default();
    };
    let Ok(text) = fs::read_to_string(&path) else {
        return Settings::default();
    };
    let Ok(root) = serde_yaml::from_str::<serde_yaml::Value>(&text) else {
        return Settings::default();
    };

    let writer = {
        let value = yaml_str(&root, "writer");
        if value.is_empty() { "gemini".into() } else { value }
    };
    let voice = {
        let value = yaml_str(&root, "voice");
        if value.is_empty() { "edge".into() } else { value }
    };
    let openai_writer_model = {
        let value = yaml_str_any(
            &root,
            &[
                &["writers", "openai-compatible", "model"],
                &["voices", "openai-compatible", "model"],
            ],
        );
        if value.is_empty() { "gpt-4o-mini".into() } else { value }
    };

    Settings {
        writer,
        voice,
        gemini_key: yaml_str_any(&root, &[&["writers", "gemini", "api_key"], &["voices", "gemini", "api_key"]]),
        openai_url: yaml_str_path(&root, &["writers", "openai-compatible", "base_url"]),
        openai_key: yaml_str_path(&root, &["writers", "openai-compatible", "api_key"]),
        openai_writer_model,
        openai_voice_model: {
            let value = yaml_str_path(&root, &["voices", "openai-compatible", "model"]);
            if value.is_empty() { "gpt-4o-mini-tts".into() } else { value }
        },
        ollama_url: {
            let value = yaml_str_path(&root, &["writers", "ollama", "base_url"]);
            if value.is_empty() { "http://127.0.0.1:11434".into() } else { value }
        },
        ollama_model: {
            let value = yaml_str_path(&root, &["writers", "ollama", "model"]);
            if value.is_empty() { "qwen3.5:4b".into() } else { value }
        },
        piper_voice: {
            let value = yaml_str_path(&root, &["voices", "piper", "voice"]);
            if value.is_empty() { "en_US-amy-low".into() } else { value }
        },
        kokoro_voice: {
            let value = yaml_str_path(&root, &["voices", "kokoro", "voice"]);
            if value.is_empty() { "af_sarah".into() } else { value }
        },
    }
}

#[tauri::command]
fn save_settings(settings: Settings) -> Result<(), String> {
    let writer = if settings.writer.trim().is_empty() {
        "gemini".to_string()
    } else {
        settings.writer.trim().to_string()
    };
    if !["gemini", "openai-compatible", "ollama"].contains(&writer.as_str()) {
        return Err("Pick a writer: gemini, openai-compatible, or ollama".into());
    }
    let voice = if settings.voice.trim().is_empty() {
        "edge".to_string()
    } else {
        settings.voice.trim().to_string()
    };
    if !["edge", "openai", "openai-compatible", "gemini", "piper", "kokoro"]
        .contains(&voice.as_str())
    {
        return Err("Pick a voice: edge, openai-compatible, gemini, piper, or kokoro".into());
    }

    let path = config_path()?;

    // Preserve an existing config's other keys; only update what we own.
    let mut root = fs::read_to_string(&path)
        .ok()
        .and_then(|t| serde_yaml::from_str::<serde_yaml::Value>(&t).ok())
        .unwrap_or(serde_yaml::Value::Mapping(Default::default()));
    let serde_yaml::Value::Mapping(map) = &mut root else {
        return Err(format!(
            "{} is not a YAML mapping; edit it by hand",
            path.display()
        ));
    };

    map.insert("writer".into(), writer.into());
    map.insert("voice".into(), voice.into());

    let writers = block_mut(map, "writers");
    let gemini = block_mut(writers, "gemini");
    set_str(gemini, "api_key", &settings.gemini_key);

    let openai_w = block_mut(writers, "openai-compatible");
    set_str(openai_w, "base_url", &settings.openai_url);
    set_str(openai_w, "api_key", &settings.openai_key);
    set_str(openai_w, "model", &settings.openai_writer_model);

    let ollama = block_mut(writers, "ollama");
    set_str(ollama, "base_url", &settings.ollama_url);
    set_str(ollama, "model", &settings.ollama_model);

    let voices = block_mut(map, "voices");
    let openai_v = block_mut(voices, "openai-compatible");
    set_str(openai_v, "base_url", &settings.openai_url);
    set_str(openai_v, "api_key", &settings.openai_key);
    set_str(openai_v, "model", &settings.openai_voice_model);

    let gemini_v = block_mut(voices, "gemini");
    set_str(gemini_v, "api_key", &settings.gemini_key);

    let piper = block_mut(voices, "piper");
    set_str(piper, "voice", &settings.piper_voice);

    let kokoro = block_mut(voices, "kokoro");
    set_str(kokoro, "voice", &settings.kokoro_voice);

    let text = serde_yaml::to_string(&root).map_err(|e| e.to_string())?;
    fs::write(&path, text).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o600));
    }
    Ok(())
}

fn command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let cmd = Command::new(program);
    #[cfg(windows)]
    let cmd = {
        use std::os::windows::process::CommandExt;
        let mut c = cmd;
        c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        c
    };
    cmd
}

fn run_ok(cmd: &mut Command) -> Result<(), String> {
    let output = cmd.output().map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

fn find_uv() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".local/bin/uv"));
        candidates.push(home.join(".cargo/bin/uv"));
    }
    candidates.push("/opt/homebrew/bin/uv".into());
    candidates.push("/usr/local/bin/uv".into());
    #[cfg(windows)]
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".local\\bin\\uv.exe"));
    }
    for path in candidates {
        if path.exists() {
            return Some(path);
        }
    }
    let probe = command("uv").arg("--version").output();
    if matches!(probe, Ok(ref o) if o.status.success()) {
        return Some("uv".into());
    }
    None
}

fn install_uv(app: &AppHandle) -> Result<PathBuf, String> {
    status(app, "Downloading uv (one-time)…");
    #[cfg(not(windows))]
    run_ok(command("sh").args([
        "-c",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
    ]))?;
    #[cfg(windows)]
    run_ok(command("powershell").args([
        "-NoProfile",
        "-ExecutionPolicy",
        "ByPass",
        "-Command",
        "irm https://astral.sh/uv/install.ps1 | iex",
    ]))?;
    find_uv().ok_or_else(|| "uv installed but not found".into())
}

fn narra_bin(venv: &Path) -> PathBuf {
    #[cfg(windows)]
    return venv.join("Scripts").join("narra.exe");
    #[cfg(not(windows))]
    venv.join("bin").join("narra")
}

fn venv_python(venv: &Path) -> PathBuf {
    #[cfg(windows)]
    return venv.join("Scripts").join("python.exe");
    #[cfg(not(windows))]
    venv.join("bin").join("python")
}

/// First run: create the app's private venv and install narra[serve].
///
/// For development before a PyPI release, set NARRA_DEV_PATH to the repo root
/// and the editable package is installed instead.
fn ensure_runtime(app: &AppHandle, force_update: bool) -> Result<PathBuf, String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;
    let venv = data_dir.join("runtime");
    let bin = narra_bin(&venv);

    let marker = venv.join("narra-version");
    let installed = fs::read_to_string(&marker).unwrap_or_default();
    if bin.exists() && installed.trim() == NARRA_VERSION && !force_update {
        return Ok(bin);
    }

    let uv = match find_uv() {
        Some(uv) => uv,
        None => install_uv(app)?,
    };

    if !venv.exists() {
        status(app, "Setting up Python runtime (one-time, ~a minute)…");
        run_ok(command(&uv).args(["venv", "--python", "3.12"]).arg(&venv))?;
    }

    let dev_path = std::env::var("NARRA_DEV_PATH")
        .ok()
        .filter(|path| !path.trim().is_empty());
    if let Some(path) = dev_path {
        status(app, "Installing Narra from source…");
        run_ok(
            command(&uv)
                .args(["pip", "install", "--upgrade", "--python"])
                .arg(venv_python(&venv))
                .arg("-e")
                .arg(path),
        )?;
    } else {
        status(app, "Installing Narra…");
        run_ok(
            command(&uv)
                .args(["pip", "install", "--upgrade", "--python"])
                .arg(venv_python(&venv))
                .arg(format!("narra[serve]=={NARRA_VERSION}")),
        )?;
    }
    let _ = fs::write(&marker, NARRA_VERSION);
    Ok(bin)
}

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    Ok(listener.local_addr().map_err(|e| e.to_string())?.port())
}

fn kill_sidecar(sidecar: &Sidecar) {
    if let Ok(mut guard) = sidecar.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn spawn_sidecar(app: &AppHandle, bin: &Path) -> Result<u16, String> {
    let port = free_port()?;
    let out_dir = dirs::home_dir()
        .unwrap_or_else(|| ".".into())
        .join("Podcasts")
        .join("Narra");

    status(app, "Starting Narra…");
    let child = command(bin)
        .args([
            "serve",
            "--no-browser",
            "--desktop",
            "--host",
            "127.0.0.1",
            "--port",
        ])
        .arg(port.to_string())
        .arg("--out-dir")
        .arg(&out_dir)
        .spawn()
        .map_err(|e| format!("Could not start narra: {e}"))?;

    let sidecar: State<Sidecar> = app.state();
    kill_sidecar(&sidecar);
    *sidecar.0.lock().unwrap() = Some(child);

    let deadline = Instant::now() + Duration::from_secs(30);
    let addr = format!("127.0.0.1:{port}");
    loop {
        if TcpStream::connect(&addr).is_ok() {
            std::thread::sleep(Duration::from_millis(300));
            return Ok(port);
        }
        if Instant::now() > deadline {
            return Err("Narra server did not come up within 30s".into());
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

#[tauri::command]
async fn start_server(app: AppHandle, update: bool) -> Result<u16, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let bin = ensure_runtime(&app, update)?;
        spawn_sidecar(&app, &bin)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn restart_server(app: AppHandle) -> Result<u16, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let bin = ensure_runtime(&app, false)?;
        spawn_sidecar(&app, &bin)
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
    tauri::Builder::default()
        .manage(Sidecar(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            start_server,
            restart_server
        ])
        .build(tauri::generate_context!())
        .expect("error while building Narra")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                kill_sidecar(&app.state::<Sidecar>());
            }
        });
}