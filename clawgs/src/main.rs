use std::io::{self, BufRead, Write};
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand, ValueEnum};
use serde::Serialize;
use serde_json::Value;

use clawgs::emit::engine::{
    EmitEngine, DEFAULT_AGENT_PREAMBLE, DEFAULT_TERMINAL_PREAMBLE,
};
use clawgs::emit::model_client::{thought_models, OpenRouterModelClient};
use clawgs::emit::protocol::{ErrorMessage, HelloMessage, SyncRequest};
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

fn write_json_line<W: Write, T: Serialize>(writer: &mut W, value: &T) -> Result<()> {
    serde_json::to_writer(&mut *writer, value).context("failed to write JSON response")?;
    writer.write_all(b"\n").context("failed to write newline")?;
    writer.flush().context("failed to flush output")?;
    Ok(())
}
