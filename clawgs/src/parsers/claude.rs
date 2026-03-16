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
        let ts = extract_timestamp(entry);
        update_user_task(entry, options, &mut user_task);
        update_token_count(entry, &mut token_count);
        record_actions(
            &mut recent_actions,
            &mut current_tool,
            assistant_actions(entry, options, &ts),
            options.max_actions,
        );
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

fn entry_type(entry: &Value) -> &str {
    entry
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default()
}

fn message<'a>(entry: &'a Value) -> Option<&'a Value> {
    entry.get("message")
}

fn update_user_task(entry: &Value, options: &ExtractOptions, user_task: &mut Option<String>) {
    (entry_type(entry) == "user")
        .then_some(message(entry))
        .flatten()
        .and_then(|message| extract_user_text(Some(message)))
        .map(|text| truncate(&text, options.max_task_chars))
        .map(|text| *user_task = Some(text));
}

fn update_token_count(entry: &Value, token_count: &mut u64) {
    assistant_message(entry)
        .and_then(|message| message.get("usage"))
        .and_then(|usage| usage.get("input_tokens"))
        .and_then(Value::as_u64)
        .map(|value| *token_count = value);
}

fn assistant_actions(entry: &Value, options: &ExtractOptions, ts: &Option<String>) -> Vec<Action> {
    assistant_message(entry)
        .and_then(|message| message.get("content").and_then(Value::as_array))
        .map(|blocks| {
            blocks
                .iter()
                .filter_map(|block| block_action(block, options, ts))
                .collect()
        })
        .unwrap_or_default()
}

fn assistant_message(entry: &Value) -> Option<&Value> {
    (entry_type(entry) == "assistant")
        .then_some(message(entry))
        .flatten()
        .filter(|message| message.get("role").and_then(Value::as_str) == Some("assistant"))
}

fn block_action(block: &Value, options: &ExtractOptions, ts: &Option<String>) -> Option<Action> {
    match block
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default()
    {
        "tool_use" => Some(tool_use_action(block, options, ts)),
        "text" => text_action(block, options, ts),
        _ => None,
    }
}

fn tool_use_action(block: &Value, options: &ExtractOptions, ts: &Option<String>) -> Action {
    Action {
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
    }
}

fn text_action(block: &Value, options: &ExtractOptions, ts: &Option<String>) -> Option<Action> {
    block
        .get("text")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|text| text.len() > 5)
        .map(|text| Action {
            tool: "said".to_string(),
            detail: Some(truncate(text, options.max_detail_chars)),
            kind: "text".to_string(),
            ts: ts.clone(),
        })
}

fn record_actions(
    recent_actions: &mut Vec<Action>,
    current_tool: &mut Option<Action>,
    actions: Vec<Action>,
    max_actions: usize,
) {
    for action in actions {
        let is_tool_use = action.kind == "tool_use";
        push_action(recent_actions, action.clone(), max_actions);
        if is_tool_use {
            *current_tool = Some(action);
        }
    }
}

fn extract_user_text(message: Option<&Value>) -> Option<String> {
    let content = user_message(message)?.get("content")?;
    content_text(content).or_else(|| content_block_text(content))
}

fn user_message(message: Option<&Value>) -> Option<&Value> {
    message.filter(|message| message.get("role").and_then(Value::as_str) == Some("user"))
}

fn content_text(content: &Value) -> Option<String> {
    content
        .as_str()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(ToString::to_string)
}

fn content_block_text(content: &Value) -> Option<String> {
    content.as_array()?.iter().find_map(text_block_content)
}

fn text_block_content(block: &Value) -> Option<String> {
    block
        .get("type")
        .and_then(Value::as_str)
        .filter(|block_type| *block_type == "text")
        .and_then(|_| block.get("text").and_then(Value::as_str))
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(ToString::to_string)
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

    #[test]
    fn extract_user_text_supports_string_and_blocks() {
        let string_message = serde_json::json!({
            "role": "user",
            "content": "  summarize logs  "
        });
        let block_message = serde_json::json!({
            "role": "user",
            "content": [
                {"type": "text", "text": "  inspect parser  "}
            ]
        });

        assert_eq!(
            extract_user_text(Some(&string_message)).as_deref(),
            Some("summarize logs")
        );
        assert_eq!(
            extract_user_text(Some(&block_message)).as_deref(),
            Some("inspect parser")
        );
    }

    #[test]
    fn extract_user_text_rejects_non_user_messages() {
        let assistant_message = serde_json::json!({
            "role": "assistant",
            "content": "ignored"
        });

        assert_eq!(extract_user_text(Some(&assistant_message)), None);
        assert_eq!(extract_user_text(None), None);
    }
}
