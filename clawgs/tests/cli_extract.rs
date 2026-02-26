use std::path::PathBuf;
use std::process::Command;

use serde_json::Value;

#[test]
fn extract_codex_fixture_emits_schema_v1() {
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/codex-sample.jsonl");

    let output = Command::new(env!("CARGO_BIN_EXE_clawgs"))
        .arg("extract")
        .arg("--tool")
        .arg("codex")
        .arg("--input")
        .arg(fixture)
        .output()
        .expect("failed to run clawgs");

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
}

#[test]
fn pretty_flag_outputs_multiline_json() {
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/codex-sample.jsonl");

    let output = Command::new(env!("CARGO_BIN_EXE_clawgs"))
        .arg("extract")
        .arg("--tool")
        .arg("codex")
        .arg("--input")
        .arg(fixture)
        .arg("--pretty")
        .output()
        .expect("failed to run clawgs");

    assert!(output.status.success());

    let stdout = String::from_utf8(output.stdout).expect("utf8");
    assert!(stdout.contains('\n'));
    assert!(stdout.contains("\"schema_version\": \"clawgs.v1\""));
}
