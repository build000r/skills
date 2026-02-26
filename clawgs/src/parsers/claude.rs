use std::path::Path;

use anyhow::Result;
use serde_json::Value;

use super::{
    extract_timestamp, extract_tool_detail, push_action, read_jsonl, truncate, ParseSnapshot,
};
use crate::{Action, ExtractOptions};

pub(crate) fn parse(path: &Path, options: &ExtractOptions) -> Result<ParseSnapshot> {
    let parsed = read_jsonl(path, options.include_raw)?;

    let mut user_task: Option<String> = None;
    let mut recent_actions: Vec<Action> = Vec::new();
    let mut current_tool: Option<Action> = None;
    let mut token_count = 0u64;

    for entry in &parsed.entries {
        let entry_type = entry
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let message = entry.get("message");
        let ts = extract_timestamp(entry);

        if entry_type == "user" {
            if let Some(text) = extract_user_text(message) {
                user_task = Some(truncate(&text, options.max_task_chars));
            }
            continue;
        }

        if entry_type != "assistant" {
            continue;
        }

        let Some(message) = message else {
            continue;
        };

        if message.get("role").and_then(Value::as_str) != Some("assistant") {
            continue;
        }

        if let Some(input_tokens) = message
            .get("usage")
            .and_then(|usage| usage.get("input_tokens"))
            .and_then(Value::as_u64)
        {
            token_count = input_tokens;
        }

        if let Some(blocks) = message.get("content").and_then(Value::as_array) {
            for block in blocks {
                let block_type = block
                    .get("type")
                    .and_then(Value::as_str)
                    .unwrap_or_default();

                if block_type == "tool_use" {
                    let action = Action {
                        tool: block
                            .get("name")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown")
                            .to_string(),
                        detail: block
                            .get("input")
                            .and_then(|input| extract_tool_detail(input, options)),
                        kind: "tool_use".to_string(),
                        ts: ts.clone(),
                    };
                    push_action(&mut recent_actions, action.clone(), options.max_actions);
                    current_tool = Some(action);
                    continue;
                }

                if block_type == "text" {
                    if let Some(text) = block.get("text").and_then(Value::as_str) {
                        let trimmed = text.trim();
                        if trimmed.len() > 5 {
                            let action = Action {
                                tool: "said".to_string(),
                                detail: Some(truncate(trimmed, options.max_detail_chars)),
                                kind: "text".to_string(),
                                ts: ts.clone(),
                            };
                            push_action(&mut recent_actions, action, options.max_actions);
                        }
                    }
                }
            }
        }
    }

    Ok(ParseSnapshot {
        user_task,
        recent_actions,
        current_tool,
        token_count,
        events_seen: parsed.entries.len() as u64,
        malformed_lines_skipped: parsed.malformed_lines_skipped,
        bytes_read: parsed.bytes_read,
        raw_events: parsed.raw_events,
    })
}

fn extract_user_text(message: Option<&Value>) -> Option<String> {
    let message = message?;
    if message.get("role").and_then(Value::as_str) != Some("user") {
        return None;
    }

    let content = message.get("content")?;
    if let Some(text) = content.as_str() {
        let trimmed = text.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }

    if let Some(blocks) = content.as_array() {
        for block in blocks {
            if block.get("type").and_then(Value::as_str) == Some("text") {
                if let Some(text) = block.get("text").and_then(Value::as_str) {
                    let trimmed = text.trim();
                    if !trimmed.is_empty() {
                        return Some(trimmed.to_string());
                    }
                }
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn parse_claude_extracts_task_tool_and_tokens() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"Summarize logs\"}}\n",
                "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"usage\":{\"input_tokens\":88},\"content\":[{\"type\":\"tool_use\",\"name\":\"read_file\",\"input\":{\"file_path\":\"/tmp/demo.txt\"}}]}}\n"
            ),
        )
        .expect("write fixture");

        let options = ExtractOptions::default();
        let snapshot = parse(file.path(), &options).expect("parse");

        assert_eq!(snapshot.user_task.as_deref(), Some("Summarize logs"));
        assert_eq!(snapshot.token_count, 88);
        assert_eq!(snapshot.recent_actions.len(), 1);
        assert_eq!(snapshot.recent_actions[0].tool, "read_file");
        assert_eq!(
            snapshot.current_tool.as_ref().map(|a| a.tool.as_str()),
            Some("read_file")
        );
    }
}
