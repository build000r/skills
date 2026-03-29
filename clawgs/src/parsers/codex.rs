use std::collections::HashMap;
use std::path::Path;

use anyhow::Result;
use serde_json::Value;

use super::{extract_timestamp, push_action, read_jsonl, truncate, ParseSnapshot};
use crate::{Action, CommitSignal, ExtractOptions};

struct ToolCallObservation {
    action: Action,
    call_id: Option<String>,
    command: Option<String>,
    session_id: Option<String>,
    marks_edit: bool,
}

pub(crate) fn parse(path: &Path, options: &ExtractOptions) -> Result<ParseSnapshot> {
    let parsed = read_jsonl(path, options.include_raw)?;

    let mut user_task: Option<String> = None;
    let mut recent_actions: Vec<Action> = Vec::new();
    let mut current_tool: Option<Action> = None;
    let mut token_count = 0u64;
    let mut pending_validation_commands: HashMap<String, String> = HashMap::new();
    let mut pending_validation_sessions: HashMap<String, String> = HashMap::new();
    let mut commit_signal = CommitSignal::default();

    for entry in &parsed.entries {
        let ts = extract_timestamp(entry);
        update_user_task(entry, options, &mut user_task);
        update_token_count(entry, &mut token_count);

        if let Some(observation) = function_call_observation(entry, options, &ts) {
            observe_tool_call(
                &observation,
                &mut pending_validation_commands,
                &mut pending_validation_sessions,
                &mut commit_signal,
            );
            record_action(
                &mut recent_actions,
                &mut current_tool,
                observation.action,
                options.max_actions,
            );
        }

        if let Some(observation) = custom_tool_call_observation(entry, options, &ts) {
            observe_tool_call(
                &observation,
                &mut pending_validation_commands,
                &mut pending_validation_sessions,
                &mut commit_signal,
            );
            record_action(
                &mut recent_actions,
                &mut current_tool,
                observation.action,
                options.max_actions,
            );
        }

        update_validation_signal(
            entry,
            &mut pending_validation_commands,
            &mut pending_validation_sessions,
            &mut commit_signal,
        );

        if let Some(action) = reasoning_event_action(entry, options, &ts) {
            record_action(
                &mut recent_actions,
                &mut current_tool,
                action,
                options.max_actions,
            );
        }

        record_actions(
            &mut recent_actions,
            &mut current_tool,
            reasoning_summary_actions(entry, options, &ts),
            options.max_actions,
        );
    }

    commit_signal.candidate = commit_signal.edited
        && commit_signal.validated
        && commit_signal.dirty_checked
        && !commit_signal.commit_seen;

    Ok(ParseSnapshot {
        user_task,
        recent_actions,
        current_tool,
        token_count,
        commit_signal: Some(commit_signal),
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

fn payload<'a>(entry: &'a Value) -> &'a Value {
    entry.get("payload").unwrap_or(&Value::Null)
}

fn update_user_task(entry: &Value, options: &ExtractOptions, user_task: &mut Option<String>) {
    user_task_text(entry)
        .filter(|text| !internal_warning_text(text))
        .map(|text| truncate(&text, options.max_task_chars))
        .map(|text| *user_task = Some(text));
}

fn user_task_text(entry: &Value) -> Option<String> {
    match entry_type(entry) {
        "response_item" => user_response_item_text(payload(entry)),
        "event_msg" => user_event_message_text(payload(entry)),
        _ => None,
    }
}

fn user_response_item_text(payload: &Value) -> Option<String> {
    payload
        .get("role")
        .and_then(Value::as_str)
        .filter(|role| *role == "user")
        .and_then(|_| extract_user_input_text(payload))
        .filter(|text| text.len() < 1000 && !text.starts_with('<'))
}

fn user_event_message_text(payload: &Value) -> Option<String> {
    payload
        .get("type")
        .and_then(Value::as_str)
        .filter(|value| *value == "user_message")
        .and_then(|_| payload.get("message").and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn internal_warning_text(text: &str) -> bool {
    text.trim_start().starts_with("Warning:")
}

fn update_token_count(entry: &Value, token_count: &mut u64) {
    token_count_from_entry(entry).map(|value| *token_count = value);
}

fn token_count_from_entry(entry: &Value) -> Option<u64> {
    response_token_count(entry).or_else(|| event_token_count(entry))
}

fn response_token_count(entry: &Value) -> Option<u64> {
    (entry_type(entry) == "response")
        .then_some(payload(entry))
        .and_then(|payload| payload.get("usage"))
        .and_then(|usage| usage.get("input_tokens"))
        .and_then(Value::as_u64)
}

fn event_token_count(entry: &Value) -> Option<u64> {
    event_payload(entry, "token_count")
        .and_then(|payload| payload.get("info"))
        .and_then(|info| {
            info.get("last_token_usage")
                .and_then(|usage| usage.get("input_tokens"))
                .and_then(Value::as_u64)
                .or_else(|| {
                    info.get("total_token_usage")
                        .and_then(|usage| usage.get("input_tokens"))
                        .and_then(Value::as_u64)
                })
        })
}

fn function_call_observation(
    entry: &Value,
    options: &ExtractOptions,
    ts: &Option<String>,
) -> Option<ToolCallObservation> {
    response_item_payload(entry, "function_call").map(|payload| {
        let parsed_arguments = payload.get("arguments").and_then(parse_tool_arguments);
        ToolCallObservation {
            action: Action {
                tool: payload
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
                    .to_string(),
                detail: parsed_arguments
                    .as_ref()
                    .and_then(|arguments| argument_detail(arguments, options.max_detail_chars)),
                kind: "function_call".to_string(),
                ts: ts.clone(),
            },
            call_id: payload
                .get("call_id")
                .and_then(Value::as_str)
                .map(ToString::to_string),
            command: parsed_arguments.as_ref().and_then(command_from_arguments),
            session_id: parsed_arguments
                .as_ref()
                .and_then(session_id_from_arguments),
            marks_edit: false,
        }
    })
}

fn custom_tool_call_observation(
    entry: &Value,
    options: &ExtractOptions,
    ts: &Option<String>,
) -> Option<ToolCallObservation> {
    response_item_payload(entry, "custom_tool_call").map(|payload| {
        let tool_name = payload
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
            .to_string();
        let detail = custom_tool_call_detail(
            tool_name.as_str(),
            payload.get("input"),
            options.max_detail_chars,
        );

        ToolCallObservation {
            action: Action {
                tool: tool_name.clone(),
                detail,
                kind: "function_call".to_string(),
                ts: ts.clone(),
            },
            call_id: payload
                .get("call_id")
                .and_then(Value::as_str)
                .map(ToString::to_string),
            command: None,
            session_id: None,
            marks_edit: tool_name == "apply_patch"
                && payload.get("status").and_then(Value::as_str) == Some("completed"),
        }
    })
}

fn reasoning_event_action(
    entry: &Value,
    options: &ExtractOptions,
    ts: &Option<String>,
) -> Option<Action> {
    event_payload(entry, "agent_reasoning")
        .and_then(|payload| payload.get("text").and_then(Value::as_str))
        .map(|text| thinking_action(text, options.max_detail_chars, ts))
}

fn reasoning_summary_actions(
    entry: &Value,
    options: &ExtractOptions,
    ts: &Option<String>,
) -> Vec<Action> {
    response_item_payload(entry, "reasoning")
        .and_then(|payload| payload.get("summary").and_then(Value::as_array))
        .map(|items| {
            items
                .iter()
                .filter_map(|summary| summary_text_action(summary, options.max_detail_chars, ts))
                .collect()
        })
        .unwrap_or_default()
}

fn response_item_payload<'a>(entry: &'a Value, expected_type: &str) -> Option<&'a Value> {
    (entry_type(entry) == "response_item")
        .then_some(payload(entry))
        .filter(|payload| payload.get("type").and_then(Value::as_str) == Some(expected_type))
}

fn event_payload<'a>(entry: &'a Value, expected_type: &str) -> Option<&'a Value> {
    (entry_type(entry) == "event_msg")
        .then_some(payload(entry))
        .filter(|payload| payload.get("type").and_then(Value::as_str) == Some(expected_type))
}

fn summary_text_action(
    summary: &Value,
    max_detail_chars: usize,
    ts: &Option<String>,
) -> Option<Action> {
    summary
        .get("type")
        .and_then(Value::as_str)
        .filter(|value| *value == "summary_text")
        .and_then(|_| summary.get("text").and_then(Value::as_str))
        .map(|text| thinking_action(text, max_detail_chars, ts))
}

fn thinking_action(text: &str, max_detail_chars: usize, ts: &Option<String>) -> Action {
    Action {
        tool: "thinking".to_string(),
        detail: Some(truncate(text, max_detail_chars)),
        kind: "thinking".to_string(),
        ts: ts.clone(),
    }
}

fn record_action(
    recent_actions: &mut Vec<Action>,
    current_tool: &mut Option<Action>,
    action: Action,
    max_actions: usize,
) {
    push_action(recent_actions, action.clone(), max_actions);
    *current_tool = Some(action);
}

fn record_actions(
    recent_actions: &mut Vec<Action>,
    current_tool: &mut Option<Action>,
    actions: Vec<Action>,
    max_actions: usize,
) {
    for action in actions {
        record_action(recent_actions, current_tool, action, max_actions);
    }
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

fn observe_tool_call(
    observation: &ToolCallObservation,
    pending_validation_commands: &mut HashMap<String, String>,
    pending_validation_sessions: &mut HashMap<String, String>,
    commit_signal: &mut CommitSignal,
) {
    if observation.marks_edit {
        commit_signal.edited = true;
    }

    if observation.action.tool == "write_stdin" {
        let Some(call_id) = observation.call_id.as_deref() else {
            return;
        };
        let Some(session_id) = observation.session_id.as_deref() else {
            return;
        };
        let Some(command) = pending_validation_sessions.get(session_id) else {
            return;
        };
        pending_validation_commands.insert(call_id.to_string(), command.clone());
        return;
    }

    if observation.action.tool != "exec_command" {
        return;
    }

    let Some(command) = observation.command.as_deref() else {
        return;
    };

    if dirty_check_command(command) {
        commit_signal.dirty_checked = true;
    }

    if commit_command(command) {
        commit_signal.commit_seen = true;
    }

    if validation_command(command) {
        if let Some(call_id) = observation.call_id.as_deref() {
            pending_validation_commands.insert(call_id.to_string(), command.to_string());
        }
    }
}

fn update_validation_signal(
    entry: &Value,
    pending_validation_commands: &mut HashMap<String, String>,
    pending_validation_sessions: &mut HashMap<String, String>,
    commit_signal: &mut CommitSignal,
) {
    let Some(payload) = response_item_payload(entry, "function_call_output") else {
        return;
    };
    let Some(call_id) = payload.get("call_id").and_then(Value::as_str) else {
        return;
    };
    let Some(command) = pending_validation_commands.remove(call_id) else {
        return;
    };
    let output = payload
        .get("output")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if validation_command(&command) && successful_command_output(output) {
        commit_signal.validated = true;
    } else if let Some(session_id) = running_session_id_from_output(output) {
        pending_validation_sessions.insert(session_id, command);
    }
}

fn parse_tool_arguments(arguments: &Value) -> Option<Value> {
    match arguments {
        Value::String(value) => serde_json::from_str(value).ok(),
        Value::Object(_) => Some(arguments.clone()),
        _ => None,
    }
}

fn argument_detail(arguments: &Value, max_chars: usize) -> Option<String> {
    if let Some(command) = command_from_arguments(arguments) {
        return Some(truncate(&command, max_chars));
    }
    if let Some(file_path) = arguments.get("file_path").and_then(Value::as_str) {
        return Some(path_basename(file_path));
    }
    if let Some(pattern) = arguments.get("pattern").and_then(Value::as_str) {
        return Some(truncate(pattern, max_chars));
    }
    None
}

fn command_from_arguments(arguments: &Value) -> Option<String> {
    arguments
        .get("cmd")
        .or_else(|| arguments.get("command"))
        .and_then(Value::as_str)
        .map(ToString::to_string)
}

fn session_id_from_arguments(arguments: &Value) -> Option<String> {
    arguments.get("session_id").and_then(|value| match value {
        Value::String(session_id) => Some(session_id.clone()),
        Value::Number(session_id) => Some(session_id.to_string()),
        _ => None,
    })
}

fn custom_tool_call_detail(
    tool_name: &str,
    input: Option<&Value>,
    max_chars: usize,
) -> Option<String> {
    let input = input?;
    if tool_name == "apply_patch" {
        return patch_target_detail(input);
    }

    input.as_str().map(|value| truncate(value, max_chars))
}

fn patch_target_detail(input: &Value) -> Option<String> {
    let patch = input.as_str()?;
    patch.lines().find_map(|line| {
        line.strip_prefix("*** Update File: ")
            .or_else(|| line.strip_prefix("*** Add File: "))
            .or_else(|| line.strip_prefix("*** Delete File: "))
            .or_else(|| line.strip_prefix("*** Move to: "))
            .map(path_basename)
    })
}

fn path_basename(path: &str) -> String {
    path.rsplit('/').next().unwrap_or(path).to_string()
}

fn dirty_check_command(command: &str) -> bool {
    let trimmed = command.trim();
    trimmed == "git status"
        || trimmed.starts_with("git status ")
        || trimmed.starts_with("git diff ")
}

fn commit_command(command: &str) -> bool {
    let trimmed = command.trim();
    trimmed == "git commit" || trimmed.starts_with("git commit ")
}

fn validation_command(command: &str) -> bool {
    let normalized = command.trim().to_lowercase();
    [
        "cargo test",
        "cargo build",
        "cargo nextest",
        "cargo clippy",
        "pytest",
        "vitest",
        "jest",
        "go test",
        "npm test",
        "npm run build",
        "npm run test",
        "npm run lint",
        "npm run type-check",
        "npm run typecheck",
        "pnpm build",
        "pnpm test",
        "pnpm lint",
        "pnpm type-check",
        "pnpm typecheck",
        "yarn build",
        "yarn test",
        "yarn lint",
        "yarn type-check",
        "yarn typecheck",
        "swift test",
        "swift build",
        "tsc --noemit",
        "eslint",
        "biome check",
        "ruff check",
        "mypy",
        "pyright",
    ]
    .iter()
    .any(|prefix| normalized.starts_with(prefix))
        || make_validation_command(&normalized)
        || xcodebuild_validation_command(&normalized)
}

fn make_validation_command(normalized: &str) -> bool {
    normalized
        .strip_prefix("make ")
        .map(|target| {
            [
                "test",
                "check",
                "build",
                "build-",
                "lint",
                "verify",
                "typecheck",
                "type-check",
            ]
            .iter()
            .any(|prefix| target.starts_with(prefix))
        })
        .unwrap_or(false)
}

fn xcodebuild_validation_command(normalized: &str) -> bool {
    normalized.starts_with("xcodebuild")
        && (normalized.contains(" test") || normalized.contains(" build"))
}

fn successful_command_output(output: &str) -> bool {
    output.contains("Process exited with code 0")
}

fn running_session_id_from_output(output: &str) -> Option<String> {
    output.lines().find_map(|line| {
        line.trim()
            .strip_prefix("Process running with session ID ")
            .map(ToString::to_string)
    })
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
            snapshot.commit_signal,
            Some(CommitSignal {
                candidate: false,
                edited: false,
                validated: false,
                dirty_checked: false,
                commit_seen: false,
            })
        );
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
    fn user_response_item_text_rejects_short_markup_input() {
        let payload = serde_json::json!({
            "role": "user",
            "content": [
                {"type": "input_text", "text": "<system>"}
            ]
        });

        assert_eq!(user_response_item_text(&payload), None);
    }

    #[test]
    fn user_response_item_text_rejects_exactly_1000_chars() {
        let payload = serde_json::json!({
            "role": "user",
            "content": [
                {"type": "input_text", "text": "a".repeat(1000)}
            ]
        });

        assert_eq!(user_response_item_text(&payload), None);
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

    #[test]
    fn parse_codex_ignores_empty_reasoning_entries() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"reasoning\",\"summary\":[{\"type\":\"other\",\"text\":\"ignored\"}]}}\n",
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_reasoning\"}}\n"
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert!(snapshot.recent_actions.is_empty());
        assert!(snapshot.current_tool.is_none());
    }

    #[test]
    fn parse_codex_current_shapes_preserve_task_and_commit_candidate() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Ship preview-first widget fix\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git status --short\\\"}\",\"call_id\":\"call_status\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"status\":\"completed\",\"name\":\"apply_patch\",\"call_id\":\"call_patch\",\"input\":\"*** Begin Patch\\n*** Update File: /tmp/project/src/widget.tsx\\n@@\\n-old\\n+new\\n*** End Patch\\n\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"cargo test --manifest-path clawgs/Cargo.toml codex -- --nocapture\\\"}\",\"call_id\":\"call_validate\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_validate\",\"output\":\"Chunk ID: abc123\\nWall time: 0.0100 seconds\\nProcess exited with code 0\\nOriginal token count: 12\\nOutput:\\n\\nvalidation passed\\n\"}}\n",
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"last_token_usage\":{\"input_tokens\":144379}}}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"Warning: apply_patch was requested via exec_command. Use the apply_patch tool instead of exec_command.\"}]}}\n"
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert_eq!(
            snapshot.user_task.as_deref(),
            Some("Ship preview-first widget fix")
        );
        assert_eq!(snapshot.token_count, 144379);
        assert_eq!(
            snapshot.recent_actions[0].detail.as_deref(),
            Some("git status --short")
        );
        assert_eq!(snapshot.recent_actions[1].tool, "apply_patch");
        assert_eq!(
            snapshot.recent_actions[1].detail.as_deref(),
            Some("widget.tsx")
        );
        assert_eq!(
            snapshot.commit_signal,
            Some(CommitSignal {
                candidate: true,
                edited: true,
                validated: true,
                dirty_checked: true,
                commit_seen: false,
            })
        );
    }

    #[test]
    fn validation_command_recognizes_make_swift_and_xcodebuild_flows() {
        assert!(validation_command("make test"));
        assert!(validation_command("make build-agent"));
        assert!(validation_command("swift test"));
        assert!(validation_command("swift build"));
        assert!(validation_command("xcodebuild -scheme Etcha test"));
        assert!(validation_command("xcodebuild -scheme Etcha build"));
        assert!(!validation_command("make docs"));
        assert!(!validation_command("xcodebuild -list"));
    }

    #[test]
    fn parse_codex_make_test_marks_commit_candidate_after_success() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Finish the tape save flow\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git status --short\\\"}\",\"call_id\":\"call_status\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"status\":\"completed\",\"name\":\"apply_patch\",\"call_id\":\"call_patch\",\"input\":\"*** Begin Patch\\n*** Update File: /tmp/project/Sources/App.swift\\n@@\\n-old\\n+new\\n*** End Patch\\n\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"make test\\\"}\",\"call_id\":\"call_validate\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_validate\",\"output\":\"Chunk ID: abc123\\nWall time: 0.0100 seconds\\nProcess exited with code 0\\nOriginal token count: 12\\nOutput:\\n\\nvalidation passed\\n\"}}\n"
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert_eq!(
            snapshot.commit_signal,
            Some(CommitSignal {
                candidate: true,
                edited: true,
                validated: true,
                dirty_checked: true,
                commit_seen: false,
            })
        );
    }

    #[test]
    fn parse_codex_write_stdin_validation_marks_commit_candidate() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            concat!(
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Finish the tape save flow\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git status --short\\\"}\",\"call_id\":\"call_status\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"status\":\"completed\",\"name\":\"apply_patch\",\"call_id\":\"call_patch\",\"input\":\"*** Begin Patch\\n*** Update File: /tmp/project/Sources/App.swift\\n@@\\n-old\\n+new\\n*** End Patch\\n\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"make test\\\"}\",\"call_id\":\"call_validate\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_validate\",\"output\":\"Chunk ID: abc123\\nWall time: 0.0100 seconds\\nProcess running with session ID 23259\\nOriginal token count: 12\\nOutput:\\n\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"write_stdin\",\"arguments\":\"{\\\"session_id\\\":23259,\\\"chars\\\":\\\"\\\",\\\"yield_time_ms\\\":1000}\",\"call_id\":\"call_poll\"}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_poll\",\"output\":\"Chunk ID: def456\\nWall time: 0.0100 seconds\\nProcess exited with code 0\\nOriginal token count: 12\\nOutput:\\n\\nvalidation passed\\n\"}}\n"
            ),
        )
        .expect("write fixture");

        let snapshot = parse(file.path(), &ExtractOptions::default()).expect("parse");

        assert_eq!(
            snapshot.commit_signal,
            Some(CommitSignal {
                candidate: true,
                edited: true,
                validated: true,
                dirty_checked: true,
                commit_seen: false,
            })
        );
    }
}
