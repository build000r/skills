use std::fs;
use std::path::PathBuf;
use std::process::Command;

use serde_json::Value;
use tempfile::NamedTempFile;

fn fixture_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!("tests/fixtures/{name}"))
}

fn run_extract(input: &std::path::Path, pretty: bool) -> std::process::Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_clawgs"));
    command
        .arg("extract")
        .arg("--tool")
        .arg("codex")
        .arg("--input")
        .arg(input);

    if pretty {
        command.arg("--pretty");
    }

    command.output().expect("failed to run clawgs")
}

#[test]
fn extract_codex_fixture_emits_schema_v1() {
    let fixture = fixture_path("codex-sample.jsonl");
    let output = run_extract(&fixture, false);

    assert!(
        output.status.success(),
        "command failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let json: Value = serde_json::from_slice(&output.stdout).expect("stdout should be json");
    assert_eq!(json["schema_version"], "clawgs.v1");
    assert_eq!(json["source"]["tool"], "codex");
    assert_eq!(json["snapshot"]["token_count"], 1212);

    let actions = json["snapshot"]["recent_actions"]
        .as_array()
        .expect("recent_actions should be array");
    assert_eq!(actions.len(), 1);
    assert_eq!(actions[0]["tool"], "exec_command");
    assert_eq!(actions[0]["detail"], "ls -la");
    assert_eq!(
        json["snapshot"]["commit_signal"],
        serde_json::json!({
            "candidate": false,
            "edited": false,
            "validated": false,
            "dirty_checked": false,
            "commit_seen": false
        })
    );
}

#[test]
fn pretty_flag_outputs_multiline_json() {
    let fixture = fixture_path("codex-sample.jsonl");
    let output = run_extract(&fixture, true);

    assert!(output.status.success());

    let stdout = String::from_utf8(output.stdout).expect("utf8");
    assert!(stdout.contains('\n'));
    assert!(stdout.contains("\"schema_version\": \"clawgs.v1\""));

    let json: Value = serde_json::from_str(&stdout).expect("pretty output should be json");
    assert_eq!(json["snapshot"]["token_count"], 1212);
    assert_eq!(json["snapshot"]["recent_actions"][0]["detail"], "ls -la");
}

#[test]
fn extract_current_codex_fixture_normalizes_actions_and_commit_signal() {
    let fixture = fixture_path("codex-current.jsonl");
    let output = run_extract(&fixture, false);

    assert!(
        output.status.success(),
        "command failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let json: Value = serde_json::from_slice(&output.stdout).expect("stdout should be json");
    let actions = json["snapshot"]["recent_actions"]
        .as_array()
        .expect("recent_actions should be array");

    assert_eq!(json["schema_version"], "clawgs.v1");
    assert_eq!(
        json["snapshot"]["user_task"],
        "Ship preview-first widget fix"
    );
    assert_eq!(json["snapshot"]["token_count"], 144379);
    assert!(
        actions.iter().any(|action| {
            action["tool"] == "exec_command" && action["detail"] == "git status --short"
        }),
        "expected git status action in {actions:?}"
    );
    assert!(
        actions
            .iter()
            .any(|action| action["tool"] == "apply_patch" && action["detail"] == "widget.tsx"),
        "expected apply_patch action in {actions:?}"
    );
    assert_ne!(
        json["snapshot"]["user_task"],
        "Warning: apply_patch was requested via exec_command. Use the apply_patch tool instead of exec_command."
    );
    assert_eq!(
        json["snapshot"]["commit_signal"],
        serde_json::json!({
            "candidate": true,
            "edited": true,
            "validated": true,
            "dirty_checked": true,
            "commit_seen": false
        })
    );
}

#[test]
fn extract_temp_codex_fixture_without_validation_is_not_commit_candidate() {
    let file = NamedTempFile::new().expect("temp file");
    fs::write(
        file.path(),
        concat!(
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Ship preview-first widget fix\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git status --short\\\"}\",\"call_id\":\"call_status\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"status\":\"completed\",\"name\":\"apply_patch\",\"call_id\":\"call_patch\",\"input\":\"*** Begin Patch\\n*** Update File: /tmp/project/src/widget.tsx\\n@@\\n-old\\n+new\\n*** End Patch\\n\"}}\n"
        ),
    )
    .expect("write fixture");

    let output = run_extract(file.path(), false);
    assert!(output.status.success());

    let json: Value = serde_json::from_slice(&output.stdout).expect("stdout should be json");
    assert_eq!(
        json["snapshot"]["commit_signal"],
        serde_json::json!({
            "candidate": false,
            "edited": true,
            "validated": false,
            "dirty_checked": true,
            "commit_seen": false
        })
    );
}

#[test]
fn extract_temp_codex_fixture_commit_seen_suppresses_candidate() {
    let file = NamedTempFile::new().expect("temp file");
    fs::write(
        file.path(),
        concat!(
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Ship parser parity\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git status --short\\\"}\",\"call_id\":\"call_status\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"status\":\"completed\",\"name\":\"apply_patch\",\"call_id\":\"call_patch\",\"input\":\"*** Begin Patch\\n*** Update File: /tmp/project/src/widget.tsx\\n@@\\n-old\\n+new\\n*** End Patch\\n\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"cargo test --manifest-path clawgs/Cargo.toml codex -- --nocapture\\\"}\",\"call_id\":\"call_validate\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_validate\",\"output\":\"Chunk ID: abc123\\nWall time: 0.0100 seconds\\nProcess exited with code 0\\nOriginal token count: 12\\nOutput:\\n\\nvalidation passed\\n\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"git commit -m \\\\\\\"ship parser parity\\\\\\\"\\\"}\",\"call_id\":\"call_commit\"}}\n"
        ),
    )
    .expect("write fixture");

    let output = run_extract(file.path(), false);
    assert!(output.status.success());

    let json: Value = serde_json::from_slice(&output.stdout).expect("stdout should be json");
    assert_eq!(
        json["snapshot"]["commit_signal"],
        serde_json::json!({
            "candidate": false,
            "edited": true,
            "validated": true,
            "dirty_checked": true,
            "commit_seen": true
        })
    );
}
