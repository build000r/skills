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
            return Ok(Vec::new());
        }

        anyhow::bail!(
            "{tmux_bin} list-panes failed: {}",
            stderr.trim().replace('\n', " ")
        );
    }

    let stdout =
        String::from_utf8(output.stdout).context("tmux list-panes output was not UTF-8")?;
    let mut sessions = Vec::new();

    for line in stdout.lines() {
        let trimmed = line.trim_end();
        if trimmed.is_empty() {
            continue;
        }

        let Some(meta) = parse_pane_line(trimmed) else {
            continue;
        };

        if meta.dead {
            continue;
        }

        let replay_text =
            capture_pane_text(tmux_bin, &meta.pane_id, max_capture_lines).unwrap_or_default();

        let tool = infer_tool(&meta.current_command);
        let state = if meta.active {
            SessionState::Busy
        } else {
            SessionState::Idle
        };

        sessions.push(SessionSnapshot {
            session_id: format!(
                "tmux:{}:{}.{}:{}",
                meta.session_name, meta.window_index, meta.pane_index, meta.pane_id
            ),
            state,
            exited: false,
            tool,
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
        });
    }

    Ok(sessions)
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

    if normalized.contains("claude") {
        Some("claude".to_string())
    } else if normalized.contains("codex") {
        Some("codex".to_string())
    } else {
        None
    }
}

fn tmux_server_missing(stderr: &str) -> bool {
    let lower = stderr.to_lowercase();
    lower.contains("no server running")
        || lower.contains("failed to connect to server")
        || lower.contains("no sessions")
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
}
