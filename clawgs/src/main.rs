use std::io::{self, BufRead, Write};
use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand, ValueEnum};
use serde::Serialize;
use serde_json::Value;

use clawgs::emit::engine::{EmitEngine, DEFAULT_AGENT_PREAMBLE, DEFAULT_TERMINAL_PREAMBLE};
use clawgs::emit::model_client::{thought_models, OpenRouterModelClient};
use clawgs::emit::protocol::{ErrorMessage, HelloMessage, SyncRequest};
use clawgs::tmux::scan_sessions;
use clawgs::{extract, resolve_input, ExtractOptions, ToolSelection};

#[derive(Debug, Parser)]
#[command(name = "clawgs")]
#[command(about = "Extract structured JSON snapshots from Claude/Codex JSONL transcripts")]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    Extract(ExtractArgs),
    Emit(EmitArgs),
    TmuxEmit(TmuxEmitArgs),
    TmuxNotify(TmuxNotifyArgs),
    /// Print resolved daemon defaults as JSON.
    Defaults,
}

#[derive(Debug, Args)]
struct ExtractArgs {
    #[arg(long, value_enum, default_value_t = ToolArg::Auto)]
    tool: ToolArg,

    #[arg(long)]
    cwd: Option<PathBuf>,

    #[arg(long)]
    input: Option<PathBuf>,

    #[arg(long)]
    pretty: bool,

    #[arg(long, default_value_t = 10)]
    max_actions: usize,

    #[arg(long, default_value_t = 300)]
    max_task_chars: usize,

    #[arg(long, default_value_t = 100)]
    max_detail_chars: usize,

    #[arg(long)]
    include_raw: bool,
}

#[derive(Debug, Args)]
struct EmitArgs {
    #[arg(long)]
    stdio: bool,
}

#[derive(Debug, Args)]
struct TmuxEmitArgs {
    #[arg(long, default_value_t = 15_000)]
    interval_ms: u64,

    #[arg(long, default_value_t = 200)]
    max_capture_lines: usize,

    #[arg(long)]
    once: bool,

    #[arg(long, default_value = "")]
    model: String,

    #[arg(long)]
    config_json: Option<String>,

    #[arg(long)]
    socket: Option<PathBuf>,
}

#[derive(Debug, Args)]
struct TmuxNotifyArgs {
    #[arg(long)]
    socket: Option<PathBuf>,

    #[arg(long, default_value = "tmux-event")]
    event: String,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum ToolArg {
    Auto,
    Claude,
    Codex,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Extract(args) => run_extract(args),
        Commands::Emit(args) => run_emit(args),
        Commands::TmuxEmit(args) => run_tmux_emit(args),
        Commands::TmuxNotify(args) => run_tmux_notify(args),
        Commands::Defaults => run_defaults(),
    }
}

fn run_extract(args: ExtractArgs) -> Result<()> {
    if args.max_actions == 0 {
        anyhow::bail!("--max-actions must be greater than 0");
    }
    if args.max_task_chars == 0 {
        anyhow::bail!("--max-task-chars must be greater than 0");
    }
    if args.max_detail_chars == 0 {
        anyhow::bail!("--max-detail-chars must be greater than 0");
    }

    let cwd = match args.cwd {
        Some(path) => path,
        None => std::env::current_dir().context("failed to resolve current directory")?,
    };

    let selection = match args.tool {
        ToolArg::Auto => ToolSelection::Auto,
        ToolArg::Claude => ToolSelection::Claude,
        ToolArg::Codex => ToolSelection::Codex,
    };

    let resolved = resolve_input(selection, &cwd, args.input.as_deref())?;

    let options = ExtractOptions {
        max_actions: args.max_actions,
        max_task_chars: args.max_task_chars,
        max_detail_chars: args.max_detail_chars,
        include_raw: args.include_raw,
    };

    let output = extract(
        resolved.tool,
        &resolved.path,
        &cwd,
        resolved.discovered,
        &options,
    )?;

    if args.pretty {
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        println!("{}", serde_json::to_string(&output)?);
    }

    Ok(())
}

fn run_emit(args: EmitArgs) -> Result<()> {
    if !args.stdio {
        anyhow::bail!("emit requires --stdio");
    }

    let model_client = OpenRouterModelClient::new()
        .map_err(|error| anyhow::anyhow!("failed to initialize model client: {error}"))?;
    let mut engine = EmitEngine::new(Box::new(model_client));

    let stdin = io::stdin();
    let mut stdout = io::stdout().lock();

    write_json_line(&mut stdout, &HelloMessage::new())?;

    for line in stdin.lock().lines() {
        let line = line.context("failed to read stdin line")?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let value: Value = match serde_json::from_str(trimmed) {
            Ok(value) => value,
            Err(error) => {
                write_json_line(
                    &mut stdout,
                    &ErrorMessage::new(None, "invalid_json", format!("invalid JSON: {error}")),
                )?;
                continue;
            }
        };

        let request_id = value
            .get("id")
            .and_then(Value::as_str)
            .map(|value| value.to_string());
        let msg_type = value
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or_default();

        if msg_type != "sync" {
            write_json_line(
                &mut stdout,
                &ErrorMessage::new(
                    request_id,
                    "unknown_message_type",
                    format!("unsupported message type: {msg_type}"),
                ),
            )?;
            continue;
        }

        let request: SyncRequest = match serde_json::from_value(value) {
            Ok(request) => request,
            Err(error) => {
                write_json_line(
                    &mut stdout,
                    &ErrorMessage::new(
                        request_id,
                        "invalid_request",
                        format!("invalid sync request shape: {error}"),
                    ),
                )?;
                continue;
            }
        };

        if let Err(error) = request.config.validate() {
            write_json_line(
                &mut stdout,
                &ErrorMessage::new(Some(request.id), "invalid_config", error),
            )?;
            continue;
        }

        let response = engine.sync(&request);
        write_json_line(&mut stdout, &response)?;
    }

    Ok(())
}

fn run_defaults() -> Result<()> {
    let models = thought_models(None);
    let model = models.first().cloned().unwrap_or_default();

    #[derive(Serialize)]
    struct Defaults {
        model: String,
        agent_prompt: &'static str,
        terminal_prompt: &'static str,
    }

    let defaults = Defaults {
        model,
        agent_prompt: DEFAULT_AGENT_PREAMBLE,
        terminal_prompt: DEFAULT_TERMINAL_PREAMBLE,
    };

    println!("{}", serde_json::to_string(&defaults)?);
    Ok(())
}

fn run_tmux_emit(args: TmuxEmitArgs) -> Result<()> {
    let model_client = OpenRouterModelClient::new()
        .map_err(|error| anyhow::anyhow!("failed to initialize model client: {error}"))?;
    let mut engine = EmitEngine::new(Box::new(model_client));
    let mut stdout = io::stdout().lock();
    let mut seq = 0u64;
    let tmux_config = tmux_emit_config(&args)?;
    let socket_path = args.socket.unwrap_or_else(default_tmux_socket_path);
    let mut socket_guard = None;

    write_json_line(&mut stdout, &HelloMessage::new())?;

    if !args.once {
        socket_guard = Some(bind_tmux_socket(&socket_path)?);
    }

    emit_tmux_scan(
        &mut stdout,
        &mut engine,
        &mut seq,
        args.max_capture_lines,
        &tmux_config,
    )?;

    if args.once {
        return Ok(());
    }

    let socket = socket_guard
        .as_ref()
        .expect("socket guard must exist when not once");
    run_tmux_emit_loop(
        &mut stdout,
        &mut engine,
        &mut seq,
        args.max_capture_lines,
        args.interval_ms,
        &tmux_config,
        &socket.reader,
    )
}

fn run_tmux_emit_loop<W: Write>(
    stdout: &mut W,
    engine: &mut EmitEngine,
    seq: &mut u64,
    max_capture_lines: usize,
    interval_ms: u64,
    tmux_config: &clawgs::emit::protocol::ThoughtConfig,
    socket: &UnixDatagram,
) -> Result<()> {
    let mut next_reconcile_at = Instant::now() + Duration::from_millis(interval_ms);
    let mut buf = [0u8; 512];

    loop {
        let timeout = next_reconcile_at
            .saturating_duration_since(Instant::now())
            .min(Duration::from_millis(1_000));
        socket
            .set_read_timeout(Some(timeout))
            .context("failed to set tmux socket timeout")?;

        let mut should_scan = false;
        match socket.recv(&mut buf) {
            Ok(_) => {
                drain_tmux_socket(socket, &mut buf)?;
                should_scan = true;
            }
            Err(error)
                if error.kind() == io::ErrorKind::WouldBlock
                    || error.kind() == io::ErrorKind::TimedOut =>
            {
                if Instant::now() >= next_reconcile_at {
                    should_scan = true;
                }
            }
            Err(error) => return Err(error).context("failed to read tmux notify socket"),
        }

        if !should_scan {
            continue;
        }

        emit_tmux_scan(stdout, engine, seq, max_capture_lines, tmux_config)?;
        next_reconcile_at = Instant::now() + Duration::from_millis(interval_ms);
    }
}

fn tmux_emit_config(args: &TmuxEmitArgs) -> Result<clawgs::emit::protocol::ThoughtConfig> {
    let mut config = match args.config_json.as_deref() {
        Some(raw) => {
            serde_json::from_str(raw).context("failed to parse --config-json for tmux-emit")?
        }
        None => clawgs::emit::protocol::ThoughtConfig::default(),
    };

    if !args.model.trim().is_empty() {
        config.model = args.model.clone();
    }

    config
        .validate()
        .map_err(|error| anyhow::anyhow!("invalid tmux emit config: {error}"))?;
    Ok(config)
}

fn write_json_line<W: Write, T: Serialize>(writer: &mut W, value: &T) -> Result<()> {
    serde_json::to_writer(&mut *writer, value).context("failed to write JSON response")?;
    writer.write_all(b"\n").context("failed to write newline")?;
    writer.flush().context("failed to flush output")?;
    Ok(())
}

fn run_tmux_notify(args: TmuxNotifyArgs) -> Result<()> {
    let socket_path = args.socket.unwrap_or_else(default_tmux_socket_path);
    let sender = UnixDatagram::unbound().context("failed to create tmux notify socket")?;

    // Hooks should be safe to install even before the daemon is running.
    let _ = sender.send_to(args.event.as_bytes(), &socket_path);
    Ok(())
}

fn emit_tmux_scan<W: Write>(
    stdout: &mut W,
    engine: &mut EmitEngine,
    seq: &mut u64,
    max_capture_lines: usize,
    config: &clawgs::emit::protocol::ThoughtConfig,
) -> Result<()> {
    *seq += 1;
    let now = chrono::Utc::now();
    let sessions = scan_sessions(now, max_capture_lines)?;

    let result = engine.sync(&SyncRequest {
        id: format!("tmux-{}", *seq),
        now,
        config: config.clone(),
        sessions,
    });

    write_json_line(stdout, &result)
}

fn default_tmux_socket_path() -> PathBuf {
    if let Ok(value) = std::env::var("CLAWGS_TMUX_SOCKET") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }

    let username = std::env::var("USER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "default".to_string());

    std::env::temp_dir().join(format!("clawgs-tmux-{username}.sock"))
}

struct TmuxSocketGuard {
    path: PathBuf,
    reader: UnixDatagram,
}

impl Drop for TmuxSocketGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

fn bind_tmux_socket(path: &PathBuf) -> Result<TmuxSocketGuard> {
    if path.exists() {
        std::fs::remove_file(path).with_context(|| {
            format!(
                "failed to remove existing tmux socket at {}",
                path.display()
            )
        })?;
    }

    let socket = UnixDatagram::bind(path)
        .with_context(|| format!("failed to bind tmux notify socket at {}", path.display()))?;

    Ok(TmuxSocketGuard {
        path: path.clone(),
        reader: socket,
    })
}

fn drain_tmux_socket(socket: &UnixDatagram, buf: &mut [u8]) -> Result<()> {
    socket
        .set_nonblocking(true)
        .context("failed to set tmux socket nonblocking")?;

    loop {
        match socket.recv(buf) {
            Ok(_) => continue,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => break,
            Err(error) => {
                socket
                    .set_nonblocking(false)
                    .context("failed to restore tmux socket blocking mode")?;
                return Err(error).context("failed while draining tmux socket");
            }
        }
    }

    socket
        .set_nonblocking(false)
        .context("failed to restore tmux socket blocking mode")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use clawgs::emit::model_client::ModelClient;

    use super::*;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    struct DummyModelClient;

    impl ModelClient for DummyModelClient {
        fn complete(&self, _prompt: &str, _model_override: Option<&str>) -> Result<String, String> {
            Ok("unused".to_string())
        }
    }

    #[test]
    fn run_tmux_emit_loop_surfaces_scan_errors_after_socket_event() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        let previous_tmux_bin = std::env::var("CLAWGS_TMUX_BIN").ok();
        std::env::set_var("CLAWGS_TMUX_BIN", "/definitely/missing-tmux");

        let (sender, receiver) = UnixDatagram::pair().expect("socket pair");
        sender.send(b"tick").expect("send tick");

        let mut stdout = Vec::new();
        let mut engine = EmitEngine::new(Box::new(DummyModelClient));
        let mut seq = 0u64;
        let config = clawgs::emit::protocol::ThoughtConfig::default();

        let error = run_tmux_emit_loop(
            &mut stdout,
            &mut engine,
            &mut seq,
            50,
            1_000,
            &config,
            &receiver,
        )
        .expect_err("scan failure");

        assert!(error
            .to_string()
            .contains("failed to run /definitely/missing-tmux list-panes"));

        if let Some(value) = previous_tmux_bin {
            std::env::set_var("CLAWGS_TMUX_BIN", value);
        } else {
            std::env::remove_var("CLAWGS_TMUX_BIN");
        }
    }
}
