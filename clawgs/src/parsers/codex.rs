use std::path::Path;

use anyhow::Result;
use serde_json::Value;

use super::{extract_timestamp, push_action, read_jsonl, truncate, ParseSnapshot};
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
        let payload = entry.get("payload").unwrap_or(&Value::Null);
        let ts = extract_timestamp(entry);

        if entry_type == "response_item"
            && payload.get("role").and_then(Value::as_str) == Some("user")
        {
            if let Some(text) = extract_user_input_text(payload) {
                if text.len() < 1000 && !text.starts_with('<') {
                    user_task = Some(truncate(&text, options.max_task_chars));
                }
            }
        }

        if entry_type == "event_msg"
            && payload.get("type").and_then(Value::as_str) == Some("user_message")
        {
            if let Some(message) = payload.get("message").and_then(Value::as_str) {
                let trimmed = message.trim();
                if !trimmed.is_empty() {
                    user_task = Some(truncate(trimmed, options.max_task_chars));
                }
            }
        }

        if entry_type == "response" {
            if let Some(input_tokens) = payload
                .get("usage")
                .and_then(|usage| usage.get("input_tokens"))
                .and_then(Value::as_u64)
            {
                token_count = input_tokens;
            }
        }

        if entry_type == "response_item"
            && payload.get("type").and_then(Value::as_str) == Some("function_call")
        {
            let action =
                Action {
                    tool: payload
                        .get("name")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_string(),
                    detail: payload.get("arguments").and_then(Value::as_str).and_then(
                        |arguments| function_call_detail(arguments, options.max_detail_chars),
                    ),
                    kind: "function_call".to_string(),
                    ts: ts.clone(),
                };

            push_action(&mut recent_actions, action.clone(), options.max_actions);
            current_tool = Some(action);
        }

        if entry_type == "event_msg"
            && payload.get("type").and_then(Value::as_str) == Some("agent_reasoning")
        {
            if let Some(text) = payload.get("text").and_then(Value::as_str) {
                let action = Action {
                    tool: "thinking".to_string(),
                    detail: Some(truncate(text, options.max_detail_chars)),
                    kind: "thinking".to_string(),
                    ts: ts.clone(),
                };
                push_action(&mut recent_actions, action.clone(), options.max_actions);
                current_tool = Some(action);
            }
        }

        if entry_type == "response_item"
            && payload.get("type").and_then(Value::as_str) == Some("reasoning")
        {
            if let Some(summary_items) = payload.get("summary").and_then(Value::as_array) {
                for summary in summary_items {
                    if summary.get("type").and_then(Value::as_str) == Some("summary_text") {
                        if let Some(text) = summary.get("text").and_then(Value::as_str) {
                            let action = Action {
                                tool: "thinking".to_string(),
                                detail: Some(truncate(text, options.max_detail_chars)),
                                kind: "thinking".to_string(),
                                ts: ts.clone(),
                            };
                            push_action(&mut recent_actions, action.clone(), options.max_actions);
                            current_tool = Some(action);
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

fn extract_user_input_text(payload: &Value) -> Option<String> {
    let blocks = payload.get("content")?.as_array()?;
    for block in blocks {
        if block.get("type").and_then(Value::as_str) == Some("input_text") {
            if let Some(text) = block.get("text").and_then(Value::as_str) {
                let trimmed = text.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
        }
    }
    None
}

fn function_call_detail(arguments: &str, max_chars: usize) -> Option<String> {
    let parsed: Value = serde_json::from_str(arguments).ok()?;
    if let Some(command) = parsed.get("command").and_then(Value::as_str) {
        return Some(truncate(command, max_chars));
    }
    if let Some(file_path) = parsed.get("file_path").and_then(Value::as_str) {
        return Some(
            file_path
                .rsplit('/')
                .next()
                .unwrap_or(file_path)
                .to_string(),
        );
    }
    if let Some(pattern) = parsed.get("pattern").and_then(Value::as_str) {
        return Some(truncate(pattern, max_chars));
    }
    None
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn parse_codex_extracts_task_function_call_and_tokens() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Build parser\"}}\n",
                "{\"type\":\"response\",\"payload\":{\"usage\":{\"input_tokens\":456}}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"command\\\":\\\"ls -la\\\"}\"}}\n"
            ),
        )
        .expect("write fixture");

        let options = ExtractOptions::default();
        let snapshot = parse(file.path(), &options).expect("parse");

        assert_eq!(snapshot.user_task.as_deref(), Some("Build parser"));
        assert_eq!(snapshot.token_count, 456);
        assert_eq!(snapshot.recent_actions.len(), 1);
        assert_eq!(snapshot.recent_actions[0].tool, "exec_command");
        assert_eq!(snapshot.recent_actions[0].kind, "function_call");
        assert_eq!(
            snapshot.current_tool.as_ref().map(|a| a.tool.as_str()),
            Some("exec_command")
        );
    }

    #[test]
    fn extract_user_input_text_returns_first_nonempty_input_block() {
        let payload = serde_json::json!({
            "content": [
                {"type": "text", "text": "ignore"},
                {"type": "input_text", "text": "  inspect parser branches  "},
                {"type": "input_text", "text": "later"}
            ]
        });

        assert_eq!(
            extract_user_input_text(&payload).as_deref(),
            Some("inspect parser branches")
        );
    }

    #[test]
    fn extract_user_input_text_skips_empty_or_missing_blocks() {
        let empty_payload = serde_json::json!({
            "content": [
                {"type": "input_text", "text": "   "},
                {"type": "text", "text": "ignore"}
            ]
        });
        let missing_payload = serde_json::json!({"content": "not-an-array"});

        assert_eq!(extract_user_input_text(&empty_payload), None);
        assert_eq!(extract_user_input_text(&missing_payload), None);
    }

    #[test]
    fn parse_codex_collects_reasoning_actions_and_file_details() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"response_item\",\"payload\":{\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"Review parser output\"}]}}\n",
                "{\"type\":\"response\",\"payload\":{\"usage\":{\"input_tokens\":77}}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"read_file\",\"arguments\":\"{\\\"file_path\\\":\\\"/tmp/demo.txt\\\"}\"}}\n",
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_reasoning\",\"text\":\"checking transcript details\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"reasoning\",\"summary\":[{\"type\":\"summary_text\",\"text\":\"looking at fallback handling\"},{\"type\":\"other\",\"text\":\"ignored\"}]}}\n"
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert_eq!(snapshot.user_task.as_deref(), Some("Review parser output"));
        assert_eq!(snapshot.token_count, 77);
        assert_eq!(snapshot.recent_actions.len(), 3);
        assert_eq!(snapshot.recent_actions[0].tool, "read_file");
        assert_eq!(
            snapshot.recent_actions[0].detail.as_deref(),
            Some("demo.txt")
        );
        assert_eq!(snapshot.recent_actions[1].tool, "thinking");
        assert_eq!(
            snapshot.recent_actions[1].detail.as_deref(),
            Some("checking transcript details")
        );
        assert_eq!(snapshot.recent_actions[2].tool, "thinking");
        assert_eq!(
            snapshot.recent_actions[2].detail.as_deref(),
            Some("looking at fallback handling")
        );
        assert_eq!(
            snapshot
                .current_tool
                .as_ref()
                .map(|action| action.tool.as_str()),
            Some("thinking")
        );
    }

    #[test]
    fn parse_codex_ignores_markup_and_oversized_user_inputs() {
        let file = NamedTempFile::new().expect("temp file");
        let oversized = "a".repeat(1001);
        fs::write(
            file.path(),
            format!(
                concat!(
                    "{{\"type\":\"response_item\",\"payload\":{{\"role\":\"user\",\"content\":[{{\"type\":\"input_text\",\"text\":\"<system>\"}}]}}}}\n",
                    "{{\"type\":\"response_item\",\"payload\":{{\"role\":\"user\",\"content\":[{{\"type\":\"input_text\",\"text\":\"{oversized}\"}}]}}}}\n",
                    "{{\"type\":\"event_msg\",\"payload\":{{\"type\":\"user_message\",\"message\":\"   \"}}}}\n",
                    "{{\"type\":\"event_msg\",\"payload\":{{\"type\":\"user_message\",\"message\":\"Use the fallback task\"}}}}\n"
                ),
                oversized = oversized
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert_eq!(snapshot.user_task.as_deref(), Some("Use the fallback task"));
    }
}
