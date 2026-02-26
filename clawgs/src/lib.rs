pub mod emit;
pub mod parsers;

use std::fs;
use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use anyhow::{anyhow, Context, Result};
use chrono::Utc;
use serde::Serialize;
use serde_json::Value;

use parsers::ParseSnapshot;

const SCHEMA_VERSION: &str = "clawgs.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentTool {
    Claude,
    Codex,
}

impl AgentTool {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolSelection {
    Auto,
    Claude,
    Codex,
}

#[derive(Debug, Clone)]
pub struct ExtractOptions {
    pub max_actions: usize,
    pub max_task_chars: usize,
    pub max_detail_chars: usize,
    pub include_raw: bool,
}

impl Default for ExtractOptions {
    fn default() -> Self {
        Self {
            max_actions: 10,
            max_task_chars: 300,
            max_detail_chars: 100,
            include_raw: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Action {
    pub tool: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ts: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_task: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_tool: Option<Action>,
    pub token_count: u64,
    pub recent_actions: Vec<Action>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Source {
    pub tool: String,
    pub path: String,
    pub discovered: bool,
    pub cwd: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Stats {
    pub events_seen: u64,
    pub malformed_lines_skipped: u64,
    pub bytes_read: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExtractOutput {
    pub schema_version: String,
    pub source: Source,
    pub snapshot: Snapshot,
    pub stats: Stats,
    pub generated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw_events: Option<Vec<Value>>,
}

#[derive(Debug, Clone)]
pub struct ResolvedInput {
    pub tool: AgentTool,
    pub path: PathBuf,
    pub discovered: bool,
}

pub fn resolve_input(
    selection: ToolSelection,
    cwd: &Path,
    input: Option<&Path>,
) -> Result<ResolvedInput> {
    if let Some(path) = input {
        let tool = match selection {
            ToolSelection::Auto => infer_tool_from_file(path)?,
            ToolSelection::Claude => AgentTool::Claude,
            ToolSelection::Codex => AgentTool::Codex,
        };

        return Ok(ResolvedInput {
            tool,
            path: path.to_path_buf(),
            discovered: false,
        });
    }

    let resolved = match selection {
        ToolSelection::Auto => discover_auto(cwd),
        ToolSelection::Claude => discover_for_tool(cwd, AgentTool::Claude),
        ToolSelection::Codex => discover_for_tool(cwd, AgentTool::Codex),
    }?;

    Ok(resolved)
}

pub fn extract(
    tool: AgentTool,
    path: &Path,
    cwd: &Path,
    discovered: bool,
    options: &ExtractOptions,
) -> Result<ExtractOutput> {
    let parsed: ParseSnapshot = match tool {
        AgentTool::Claude => parsers::claude::parse(path, options)?,
        AgentTool::Codex => parsers::codex::parse(path, options)?,
    };

    Ok(ExtractOutput {
        schema_version: SCHEMA_VERSION.to_string(),
        source: Source {
            tool: tool.as_str().to_string(),
            path: path.display().to_string(),
            discovered,
            cwd: cwd.display().to_string(),
        },
        snapshot: Snapshot {
            user_task: parsed.user_task,
            current_tool: parsed.current_tool,
            token_count: parsed.token_count,
            recent_actions: parsed.recent_actions,
        },
        stats: Stats {
            events_seen: parsed.events_seen,
            malformed_lines_skipped: parsed.malformed_lines_skipped,
            bytes_read: parsed.bytes_read,
        },
        generated_at: Utc::now().to_rfc3339(),
        raw_events: parsed.raw_events,
    })
}

pub fn infer_tool_from_file(path: &Path) -> Result<AgentTool> {
    let file = fs::File::open(path).with_context(|| {
        format!(
            "failed to open input file for tool inference: {}",
            path.display()
        )
    })?;
    let reader = std::io::BufReader::new(file);

    for line in reader.lines().take(40) {
        let line = line?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let value: Value = match serde_json::from_str(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };

        let entry_type = value.get("type").and_then(Value::as_str).unwrap_or("");

        if entry_type == "session_meta"
            || entry_type == "response"
            || entry_type == "response_item"
            || entry_type == "event_msg"
        {
            return Ok(AgentTool::Codex);
        }

        if entry_type == "assistant" || entry_type == "user" || value.get("message").is_some() {
            return Ok(AgentTool::Claude);
        }

        if value.get("payload").is_some() {
            return Ok(AgentTool::Codex);
        }
    }

    Err(anyhow!(
        "could not infer tool format from {}. Pass --tool claude or --tool codex",
        path.display()
    ))
}

pub fn discover_for_tool(cwd: &Path, tool: AgentTool) -> Result<ResolvedInput> {
    let path = match tool {
        AgentTool::Claude => discover_claude_path(cwd),
        AgentTool::Codex => discover_codex_path(cwd),
    }
    .ok_or_else(|| {
        anyhow!(
            "no {} transcript JSONL found for cwd {}",
            tool.as_str(),
            cwd.display()
        )
    })?;

    Ok(ResolvedInput {
        tool,
        path,
        discovered: true,
    })
}

pub fn discover_auto(cwd: &Path) -> Result<ResolvedInput> {
    let claude_path = discover_claude_path(cwd);
    let codex_path = discover_codex_path(cwd);

    match (claude_path, codex_path) {
        (Some(path), None) => Ok(ResolvedInput {
            tool: AgentTool::Claude,
            path,
            discovered: true,
        }),
        (None, Some(path)) => Ok(ResolvedInput {
            tool: AgentTool::Codex,
            path,
            discovered: true,
        }),
        (Some(claude), Some(codex)) => {
            let claude_time = modified_or_epoch(&claude);
            let codex_time = modified_or_epoch(&codex);
            if codex_time > claude_time {
                Ok(ResolvedInput {
                    tool: AgentTool::Codex,
                    path: codex,
                    discovered: true,
                })
            } else {
                Ok(ResolvedInput {
                    tool: AgentTool::Claude,
                    path: claude,
                    discovered: true,
                })
            }
        }
        (None, None) => Err(anyhow!(
            "no Claude or Codex transcript JSONL found for cwd {}",
            cwd.display()
        )),
    }
}

pub fn discover_claude_path(cwd: &Path) -> Option<PathBuf> {
    let home = home_dir()?;
    let cwd_slug = cwd.display().to_string().replace('/', "-");
    let project_dir = home.join(".claude").join("projects").join(cwd_slug);

    let mut files: Vec<(PathBuf, SystemTime)> = fs::read_dir(project_dir)
        .ok()?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("jsonl"))
        .filter_map(|path| {
            let modified = fs::metadata(&path).ok()?.modified().ok()?;
            Some((path, modified))
        })
        .collect();

    files.sort_by(|a, b| b.1.cmp(&a.1));
    files.into_iter().next().map(|(path, _)| path)
}

pub fn discover_codex_path(cwd: &Path) -> Option<PathBuf> {
    let home = home_dir()?;
    let sessions_dir = home.join(".codex").join("sessions");

    for year in sorted_numeric_subdirs_reverse(&sessions_dir, 4) {
        for month in sorted_numeric_subdirs_reverse(&year, 2) {
            for day in sorted_numeric_subdirs_reverse(&month, 2) {
                let mut rollout_files: Vec<PathBuf> = fs::read_dir(&day)
                    .ok()?
                    .filter_map(|entry| entry.ok())
                    .map(|entry| entry.path())
                    .filter(|path| {
                        let name = path
                            .file_name()
                            .and_then(|n| n.to_str())
                            .unwrap_or_default();
                        name.starts_with("rollout-") && name.ends_with(".jsonl")
                    })
                    .collect();

                rollout_files.sort();
                rollout_files.reverse();

                for file_path in rollout_files {
                    if codex_file_matches_cwd(&file_path, cwd) {
                        return Some(file_path);
                    }
                }
            }
        }
    }

    None
}

fn codex_file_matches_cwd(path: &Path, cwd: &Path) -> bool {
    let cwd_str = cwd.display().to_string();
    let file = match fs::File::open(path) {
        Ok(file) => file,
        Err(_) => return false,
    };
    let mut lines = std::io::BufReader::new(file).lines();
    let first_line = match lines.next() {
        Some(Ok(line)) => line,
        _ => return false,
    };

    let value: Value = match serde_json::from_str(&first_line) {
        Ok(value) => value,
        Err(_) => return false,
    };

    if value.get("type").and_then(Value::as_str) != Some("session_meta") {
        return false;
    }

    value
        .get("payload")
        .and_then(|payload| payload.get("cwd"))
        .and_then(Value::as_str)
        .map(|entry_cwd| entry_cwd == cwd_str)
        .unwrap_or(false)
}

fn sorted_numeric_subdirs_reverse(dir: &Path, width: usize) -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = match fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|entry| entry.ok())
            .filter(|entry| {
                entry
                    .file_type()
                    .ok()
                    .map(|ft| ft.is_dir())
                    .unwrap_or(false)
            })
            .filter(|entry| {
                entry
                    .file_name()
                    .to_str()
                    .map(|name| name.len() == width && name.chars().all(|ch| ch.is_ascii_digit()))
                    .unwrap_or(false)
            })
            .map(|entry| entry.path())
            .collect(),
        Err(_) => Vec::new(),
    };

    dirs.sort();
    dirs.reverse();
    dirs
}

fn modified_or_epoch(path: &Path) -> SystemTime {
    fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .unwrap_or(SystemTime::UNIX_EPOCH)
}

fn home_dir() -> Option<PathBuf> {
    std::env::var("HOME").ok().map(PathBuf::from)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn infer_codex_tool_from_response_item() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\"}}\n",
        )
        .expect("write file");

        let tool = infer_tool_from_file(file.path()).expect("infer tool");
        assert_eq!(tool, AgentTool::Codex);
    }

    #[test]
    fn infer_claude_tool_from_assistant_message() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\"}}\n",
        )
        .expect("write file");

        let tool = infer_tool_from_file(file.path()).expect("infer tool");
        assert_eq!(tool, AgentTool::Claude);
    }
}
