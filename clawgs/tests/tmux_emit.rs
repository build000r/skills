use std::fs;
use std::io::{BufRead, BufReader};
use std::os::unix::fs::PermissionsExt;
use std::process::Command;
use std::sync::mpsc;
use std::time::Duration;

use chrono::Utc;
use clawgs::tmux::scan_sessions_with_bin;
use serde_json::Value;
use tempfile::TempDir;

fn fake_tmux_script(temp_dir: &TempDir) -> std::path::PathBuf {
    let script_path = temp_dir.path().join("fake-tmux");
    fs::write(
        &script_path,
        r#"#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true

if [[ "$cmd" == "list-panes" ]]; then
  printf 'work\x1f1\x1f0\x1f%%1\x1f/tmp/project-a\x1fclaude\x1f1\x1f0\n'
  printf 'ops\x1f2\x1f1\x1f%%2\x1f/tmp/project-b\x1fzsh\x1f0\x1f0\n'
  exit 0
fi

if [[ "$cmd" == "capture-pane" ]]; then
  target=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-t" ]]; then
      target="${2:-}"
      break
    fi
    shift
  done

  if [[ "$target" == "%1" ]]; then
    printf 'claude is extracting session context\n'
  elif [[ "$target" == "%2" ]]; then
    printf 'tail -f logs/app.log\n'
  fi
  exit 0
fi

echo "unexpected command: $cmd" >&2
exit 1
"#,
    )
    .expect("write fake tmux");

    let mut permissions = fs::metadata(&script_path)
        .expect("script metadata")
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).expect("chmod");

    script_path
}

#[test]
fn scan_sessions_maps_tmux_panes_to_session_snapshots() {
    let temp_dir = TempDir::new().expect("temp dir");
    let fake_tmux = fake_tmux_script(&temp_dir);

    let sessions = scan_sessions_with_bin(Utc::now(), 200, fake_tmux.to_str().expect("path str"))
        .expect("scan sessions");

    assert_eq!(sessions.len(), 2);

    assert_eq!(sessions[0].session_id, "tmux:work:1.0:%1");
    assert_eq!(sessions[0].cwd, "/tmp/project-a");
    assert_eq!(sessions[0].tool.as_deref(), Some("claude"));
    assert!(sessions[0]
        .replay_text
        .contains("extracting session context"));

    assert_eq!(sessions[1].session_id, "tmux:ops:2.1:%2");
    assert_eq!(sessions[1].tool, None);
    assert_eq!(
        sessions[1].state,
        clawgs::emit::protocol::SessionState::Idle
    );
}

#[test]
fn tmux_emit_once_writes_hello_and_sync_result() {
    let temp_dir = TempDir::new().expect("temp dir");
    let fake_tmux = fake_tmux_script(&temp_dir);
    let socket_path = temp_dir.path().join("tmux.sock");

    let child = Command::new(env!("CARGO_BIN_EXE_clawgs"))
        .arg("tmux-emit")
        .arg("--once")
        .arg("--socket")
        .arg(&socket_path)
        .env("CLAWGS_TMUX_BIN", fake_tmux)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("spawn tmux emit");

    let output = child.wait_with_output().expect("wait for child");
    assert!(
        output.status.success(),
        "process failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("stdout utf8");
    let mut lines = stdout.lines();

    let hello: Value = serde_json::from_str(lines.next().expect("hello line")).expect("hello json");
    assert_eq!(hello["type"], "hello");
    assert_eq!(hello["protocol"], "clawgs.emit.v1");

    let result: Value =
        serde_json::from_str(lines.next().expect("sync result line")).expect("result json");
    assert_eq!(result["type"], "sync_result");
    assert_eq!(result["id"], "tmux-1");
    assert!(result["stream_instance_id"].as_str().is_some());
    assert_eq!(result["metrics"]["sessions_seen"], 2);
    assert!(result["updates"].is_array());
}

#[test]
fn tmux_notify_triggers_immediate_rescan() {
    let temp_dir = TempDir::new().expect("temp dir");
    let fake_tmux = fake_tmux_script(&temp_dir);
    let socket_path = temp_dir.path().join("tmux.sock");

    let mut child = Command::new(env!("CARGO_BIN_EXE_clawgs"))
        .arg("tmux-emit")
        .arg("--interval-ms")
        .arg("60000")
        .arg("--socket")
        .arg(&socket_path)
        .env("CLAWGS_TMUX_BIN", fake_tmux)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("spawn tmux emit");

    let stdout = child.stdout.take().expect("stdout");
    let mut reader = BufReader::new(stdout);

    let mut hello_line = String::new();
    reader.read_line(&mut hello_line).expect("read hello");
    let hello: Value = serde_json::from_str(hello_line.trim()).expect("hello json");
    assert_eq!(hello["type"], "hello");

    let mut first_result_line = String::new();
    reader
        .read_line(&mut first_result_line)
        .expect("read first sync_result");
    let first: Value = serde_json::from_str(first_result_line.trim()).expect("first result json");
    assert_eq!(first["type"], "sync_result");
    assert_eq!(first["id"], "tmux-1");
    let stream_instance_id = first["stream_instance_id"]
        .as_str()
        .expect("stream instance id")
        .to_string();

    let notify = Command::new(env!("CARGO_BIN_EXE_clawgs"))
        .arg("tmux-notify")
        .arg("--socket")
        .arg(&socket_path)
        .arg("--event")
        .arg("session-created")
        .output()
        .expect("run tmux notify");
    assert!(
        notify.status.success(),
        "tmux-notify failed: {}",
        String::from_utf8_lossy(&notify.stderr)
    );

    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let _ = reader.read_line(&mut line);
        let _ = tx.send(line);
    });

    let line = rx
        .recv_timeout(Duration::from_secs(2))
        .expect("expected immediate rescan after notify");
    let second: Value = serde_json::from_str(line.trim()).expect("second result json");
    assert_eq!(second["type"], "sync_result");
    assert_eq!(second["id"], "tmux-2");
    assert_eq!(second["stream_instance_id"], stream_instance_id);

    child.kill().expect("kill tmux emit");
    child.wait().expect("wait for tmux emit");
}
