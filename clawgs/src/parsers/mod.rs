pub mod claude;
pub mod codex;

use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use serde_json::Value;

use crate::{Action, ExtractOptions};

pub(crate) struct ParseSnapshot {
    pub user_task: Option<String>,
    pub recent_actions: Vec<Action>,
    pub current_tool: Option<Action>,
    pub token_count: u64,
    pub events_seen: u64,
    pub malformed_lines_skipped: u64,
    pub bytes_read: u64,
    pub raw_events: Option<Vec<Value>>,
}

pub(crate) struct ParsedLines {
    pub entries: Vec<Value>,
    pub malformed_lines_skipped: u64,
    pub bytes_read: u64,
    pub raw_events: Option<Vec<Value>>,
}

pub(crate) fn read_jsonl(path: &Path, include_raw: bool) -> Result<ParsedLines> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    let bytes_read = bytes.len() as u64;

    let mut entries = Vec::new();
    let mut malformed_lines_skipped = 0;
    let mut raw_events: Vec<Value> = Vec::new();

    for line in String::from_utf8_lossy(&bytes)
        .lines()
        .filter(|line| !line.trim().is_empty())
    {
        match serde_json::from_str::<Value>(line) {
            Ok(value) => {
                if include_raw {
                    raw_events.push(value.clone());
                    if raw_events.len() > 20 {
                        let to_remove = raw_events.len() - 20;
                        raw_events.drain(0..to_remove);
                    }
                }
                entries.push(value);
            }
            Err(_) => malformed_lines_skipped += 1,
        }
    }

    Ok(ParsedLines {
        entries,
        malformed_lines_skipped,
        bytes_read,
        raw_events: if include_raw { Some(raw_events) } else { None },
    })
}

pub(crate) fn truncate(value: &str, max_chars: usize) -> String {
    if value.chars().count() <= max_chars {
        value.to_string()
    } else {
        value.chars().take(max_chars).collect()
    }
}

pub(crate) fn push_action(actions: &mut Vec<Action>, action: Action, max_actions: usize) {
    actions.push(action);
    if actions.len() > max_actions {
        let to_remove = actions.len() - max_actions;
        actions.drain(0..to_remove);
    }
}

pub(crate) fn extract_tool_detail(input: &Value, options: &ExtractOptions) -> Option<String> {
    if let Some(file_path) = input.get("file_path").and_then(Value::as_str) {
        return Some(basename(file_path).to_string());
    }
    if let Some(command) = input.get("command").and_then(Value::as_str) {
        return Some(truncate(command, options.max_detail_chars));
    }
    if let Some(pattern) = input.get("pattern").and_then(Value::as_str) {
        return Some(truncate(pattern, options.max_detail_chars));
    }
    None
}

pub(crate) fn extract_timestamp(entry: &Value) -> Option<String> {
    for key in ["timestamp", "created_at", "time", "ts"] {
        if let Some(value) = entry.get(key) {
            if let Some(value) = scalar_to_string(value) {
                return Some(value);
            }
        }
    }

    let payload = entry.get("payload")?;
    for key in ["timestamp", "created_at", "time", "ts"] {
        if let Some(value) = payload.get(key) {
            if let Some(value) = scalar_to_string(value) {
                return Some(value);
            }
        }
    }

    None
}

fn scalar_to_string(value: &Value) -> Option<String> {
    if let Some(value) = value.as_str() {
        return Some(value.to_string());
    }
    if value.is_number() || value.is_boolean() {
        return Some(value.to_string());
    }
    None
}

fn basename(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn read_jsonl_skips_bad_lines() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            "{\"type\":\"a\"}\nnot-json\n{\"type\":\"b\"}\n",
        )
        .expect("write");

        let parsed = read_jsonl(file.path(), false).expect("read jsonl");
        assert_eq!(parsed.entries.len(), 2);
        assert_eq!(parsed.malformed_lines_skipped, 1);
    }

    #[test]
    fn truncate_limits_chars() {
        assert_eq!(truncate("hello", 3), "hel");
        assert_eq!(truncate("hi", 10), "hi");
    }
}
