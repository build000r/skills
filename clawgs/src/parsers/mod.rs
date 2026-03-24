pub mod claude;
pub mod codex;

use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use serde_json::Value;

use crate::{Action, CommitSignal, ExtractOptions};

pub(crate) struct ParseSnapshot {
    pub user_task: Option<String>,
    pub recent_actions: Vec<Action>,
    pub current_tool: Option<Action>,
    pub token_count: u64,
    pub commit_signal: Option<CommitSignal>,
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
    string_field(input, "file_path")
        .map(|file_path| basename(file_path).to_string())
        .or_else(|| {
            string_field(input, "command")
                .map(|command| truncate(command, options.max_detail_chars))
        })
        .or_else(|| {
            string_field(input, "pattern")
                .map(|pattern| truncate(pattern, options.max_detail_chars))
        })
}

pub(crate) fn extract_timestamp(entry: &Value) -> Option<String> {
    timestamp_from_value(entry).or_else(|| entry.get("payload").and_then(timestamp_from_value))
}

fn scalar_to_string(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.clone()),
        Value::Number(_) | Value::Bool(_) => Some(value.to_string()),
        _ => None,
    }
}

fn basename(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

fn string_field<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(Value::as_str)
}

fn timestamp_from_value(value: &Value) -> Option<String> {
    ["timestamp", "created_at", "time", "ts"]
        .into_iter()
        .find_map(|key| value.get(key).and_then(scalar_to_string))
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

    #[test]
    fn extract_tool_detail_prefers_file_path_then_command_then_pattern() {
        let options = ExtractOptions::default();
        let file_input = serde_json::json!({"file_path": "/tmp/demo.txt", "command": "ignored"});
        let command_input = serde_json::json!({"command": "cargo test --all"});
        let pattern_input = serde_json::json!({"pattern": "extract timestamp"});

        assert_eq!(
            extract_tool_detail(&file_input, &options).as_deref(),
            Some("demo.txt")
        );
        assert_eq!(
            extract_tool_detail(&command_input, &options).as_deref(),
            Some("cargo test --all")
        );
        assert_eq!(
            extract_tool_detail(&pattern_input, &options).as_deref(),
            Some("extract timestamp")
        );
    }

    #[test]
    fn extract_timestamp_uses_entry_then_payload_scalars() {
        let top_level = serde_json::json!({"timestamp": 12345});
        let payload = serde_json::json!({"payload": {"created_at": true}});

        assert_eq!(extract_timestamp(&top_level).as_deref(), Some("12345"));
        assert_eq!(extract_timestamp(&payload).as_deref(), Some("true"));
    }
}
