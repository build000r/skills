use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand, ValueEnum};

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
