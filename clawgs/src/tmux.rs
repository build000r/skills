use std::process::Command;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};

use crate::emit::protocol::{
    RestState, SessionSnapshot, SessionState, ThoughtSource, ThoughtState,
};

const FIELD_SEP: char = '\u{1f}';

pub fn tmux_bin() -> String {
    std::env::var("CLAWGS_TMUX_BIN").unwrap_or_else(|_| "tmux".to_string())
}

pub fn scan_sessions(now: DateTime<Utc>, max_capture_lines: usize) -> Result<Vec<SessionSnapshot>> {
    scan_sessions_with_bin(now, max_capture_lines, &tmux_bin())
}

pub fn scan_sessions_with_bin(
    now: DateTime<Utc>,
    max_capture_lines: usize,
    tmux_bin: &str,
) -> Result<Vec<SessionSnapshot>> {
    let stdout = list_tmux_panes(tmux_bin)?;
    Ok(stdout
        .lines()
        .filter_map(parse_pane_meta_line)
        .filter_map(|meta| pane_meta_to_session(now, max_capture_lines, tmux_bin, meta))
        .collect())
}

fn list_tmux_panes(tmux_bin: &str) -> Result<String> {
    let format = format!(
        "#{{session_name}}{sep}#{{window_index}}{sep}#{{pane_index}}{sep}#{{pane_id}}{sep}#{{pane_current_path}}{sep}#{{pane_current_command}}{sep}#{{?pane_active,1,0}}{sep}#{{?pane_dead,1,0}}",
        sep = FIELD_SEP
    );

    let output = Command::new(tmux_bin)
        .args(["list-panes", "-a", "-F", &format])
        .output()
        .with_context(|| format!("failed to run {tmux_bin} list-panes"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        if tmux_server_missing(&stderr) {
            return Ok(String::new());
        }

        anyhow::bail!(
            "{tmux_bin} list-panes failed: {}",
            stderr.trim().replace('\n', " ")
        );
    }

    String::from_utf8(output.stdout).context("tmux list-panes output was not UTF-8")
}

#[derive(Debug, PartialEq, Eq)]
struct PaneMeta {
    session_name: String,
    window_index: String,
    pane_index: String,
    pane_id: String,
    current_path: String,
    current_command: String,
    active: bool,
    dead: bool,
}

fn parse_pane_line(line: &str) -> Option<PaneMeta> {
    let mut parts = line.split(FIELD_SEP);

    Some(PaneMeta {
        session_name: parts.next()?.to_string(),
        window_index: parts.next()?.to_string(),
        pane_index: parts.next()?.to_string(),
        pane_id: parts.next()?.to_string(),
        current_path: parts.next()?.to_string(),
        current_command: parts.next()?.to_string(),
        active: parts.next()? == "1",
        dead: parts.next()? == "1",
    })
}

fn parse_pane_meta_line(line: &str) -> Option<PaneMeta> {
    let trimmed = line.trim_end();
    (!trimmed.is_empty())
        .then(|| parse_pane_line(trimmed))
        .flatten()
}

fn pane_meta_to_session(
    now: DateTime<Utc>,
    max_capture_lines: usize,
    tmux_bin: &str,
    meta: PaneMeta,
) -> Option<SessionSnapshot> {
    (!meta.dead).then(|| build_session_snapshot(now, max_capture_lines, tmux_bin, meta))
}

fn build_session_snapshot(
    now: DateTime<Utc>,
    max_capture_lines: usize,
    tmux_bin: &str,
    meta: PaneMeta,
) -> SessionSnapshot {
    let replay_text =
        capture_pane_text(tmux_bin, &meta.pane_id, max_capture_lines).unwrap_or_default();
    let state = if meta.active {
        SessionState::Busy
    } else {
        SessionState::Idle
    };

    SessionSnapshot {
        session_id: format!(
            "tmux:{}:{}.{}:{}",
            meta.session_name, meta.window_index, meta.pane_index, meta.pane_id
        ),
        state,
        exited: false,
        tool: infer_tool(&meta.current_command),
        cwd: meta.current_path,
        replay_text,
        thought: None,
        thought_state: ThoughtState::Holding,
        thought_source: ThoughtSource::CarryForward,
        objective_fingerprint: None,
        thought_updated_at: None,
        token_count: 0,
        context_limit: 0,
        last_activity_at: now,
        rest_state: RestState::Active,
    }
}

fn capture_pane_text(tmux_bin: &str, pane_id: &str, max_capture_lines: usize) -> Result<String> {
    let start = capture_start(max_capture_lines);
    let output = Command::new(tmux_bin)
        .args(["capture-pane", "-p", "-t", pane_id, "-S", &start])
        .output()
        .with_context(|| format!("failed to run {tmux_bin} capture-pane for {pane_id}"))?;

    if !output.status.success() {
        return Ok(String::new());
    }

    let stdout =
        String::from_utf8(output.stdout).context("tmux capture-pane output was not UTF-8")?;
    Ok(stdout.trim().to_string())
}

fn capture_start(max_capture_lines: usize) -> String {
    let lines = max_capture_lines.max(1);
    format!("-{}", lines.saturating_sub(1))
}

fn infer_tool(current_command: &str) -> Option<String> {
    let normalized = current_command.trim().to_lowercase();
    ["claude", "codex"]
        .into_iter()
        .find(|tool| normalized.contains(tool))
        .map(|tool| tool.to_string())
}

fn tmux_server_missing(stderr: &str) -> bool {
    let lower = stderr.to_lowercase();
    [
        "no server running",
        "failed to connect to server",
        "no sessions",
    ]
    .iter()
    .any(|fragment| lower.contains(fragment))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_pane_line_decodes_tmux_fields() {
        let line = "work\u{1f}1\u{1f}0\u{1f}%3\u{1f}/tmp/project\u{1f}codex\u{1f}1\u{1f}0";
        let parsed = parse_pane_line(line).expect("pane meta");

        assert_eq!(
            parsed,
            PaneMeta {
                session_name: "work".to_string(),
                window_index: "1".to_string(),
                pane_index: "0".to_string(),
                pane_id: "%3".to_string(),
                current_path: "/tmp/project".to_string(),
                current_command: "codex".to_string(),
                active: true,
                dead: false,
            }
        );
    }

    #[test]
    fn capture_start_keeps_one_line_minimum() {
        assert_eq!(capture_start(0), "-0");
        assert_eq!(capture_start(1), "-0");
        assert_eq!(capture_start(200), "-199");
    }

    #[test]
    fn tmux_server_missing_recognizes_expected_errors() {
        assert!(tmux_server_missing("No server running on /tmp/tmux"));
        assert!(tmux_server_missing("failed to connect to server"));
        assert!(tmux_server_missing("no sessions"));
        assert!(!tmux_server_missing("permission denied"));
    }

    #[test]
    fn infer_tool_matches_supported_agents() {
        assert_eq!(infer_tool("  Claude  ").as_deref(), Some("claude"));
        assert_eq!(
            infer_tool("/usr/bin/codex --json").as_deref(),
            Some("codex")
        );
        assert_eq!(infer_tool("vim"), None);
    }
}
