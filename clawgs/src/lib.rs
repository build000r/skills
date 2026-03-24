pub mod emit;
pub mod parsers;
pub mod tmux;

use std::collections::HashSet;
use std::fs;
use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use anyhow::{anyhow, Context, Result};
use chrono::Utc;
use serde::Serialize;
use serde_json::Value;

use parsers::ParseSnapshot;

const SCHEMA_VERSION: &str = "clawgs.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentTool {
    Claude,
    Codex,
}

impl AgentTool {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolSelection {
    Auto,
    Claude,
    Codex,
}

#[derive(Debug, Clone)]
pub struct ExtractOptions {
    pub max_actions: usize,
    pub max_task_chars: usize,
    pub max_detail_chars: usize,
    pub include_raw: bool,
}

impl Default for ExtractOptions {
    fn default() -> Self {
        Self {
            max_actions: 10,
            max_task_chars: 300,
            max_detail_chars: 100,
            include_raw: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Action {
    pub tool: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ts: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, PartialEq, Eq)]
pub struct CommitSignal {
    pub candidate: bool,
    pub edited: bool,
    pub validated: bool,
    pub dirty_checked: bool,
    pub commit_seen: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_task: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_tool: Option<Action>,
    pub token_count: u64,
    pub recent_actions: Vec<Action>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub commit_signal: Option<CommitSignal>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Source {
    pub tool: String,
    pub path: String,
    pub discovered: bool,
    pub cwd: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Stats {
    pub events_seen: u64,
    pub malformed_lines_skipped: u64,
    pub bytes_read: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExtractOutput {
    pub schema_version: String,
    pub source: Source,
    pub snapshot: Snapshot,
    pub stats: Stats,
    pub generated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw_events: Option<Vec<Value>>,
}

#[derive(Debug, Clone)]
pub struct ResolvedInput {
    pub tool: AgentTool,
    pub path: PathBuf,
    pub discovered: bool,
}

pub fn resolve_input(
    selection: ToolSelection,
    cwd: &Path,
    input: Option<&Path>,
) -> Result<ResolvedInput> {
    if let Some(path) = input {
        let tool = match selection {
            ToolSelection::Auto => infer_tool_from_file(path)?,
            ToolSelection::Claude => AgentTool::Claude,
            ToolSelection::Codex => AgentTool::Codex,
        };

        return Ok(ResolvedInput {
            tool,
            path: path.to_path_buf(),
            discovered: false,
        });
    }

    let resolved = match selection {
        ToolSelection::Auto => discover_auto(cwd),
        ToolSelection::Claude => discover_for_tool(cwd, AgentTool::Claude),
        ToolSelection::Codex => discover_for_tool(cwd, AgentTool::Codex),
    }?;

    Ok(resolved)
}

pub fn extract(
    tool: AgentTool,
    path: &Path,
    cwd: &Path,
    discovered: bool,
    options: &ExtractOptions,
) -> Result<ExtractOutput> {
    let parsed: ParseSnapshot = match tool {
        AgentTool::Claude => parsers::claude::parse(path, options)?,
        AgentTool::Codex => parsers::codex::parse(path, options)?,
    };

    Ok(ExtractOutput {
        schema_version: SCHEMA_VERSION.to_string(),
        source: Source {
            tool: tool.as_str().to_string(),
            path: path.display().to_string(),
            discovered,
            cwd: cwd.display().to_string(),
        },
        snapshot: Snapshot {
            user_task: parsed.user_task,
            current_tool: parsed.current_tool,
            token_count: parsed.token_count,
            recent_actions: parsed.recent_actions,
            commit_signal: parsed.commit_signal,
        },
        stats: Stats {
            events_seen: parsed.events_seen,
            malformed_lines_skipped: parsed.malformed_lines_skipped,
            bytes_read: parsed.bytes_read,
        },
        generated_at: Utc::now().to_rfc3339(),
        raw_events: parsed.raw_events,
    })
}

pub fn infer_tool_from_file(path: &Path) -> Result<AgentTool> {
    let file = fs::File::open(path).with_context(|| {
        format!(
            "failed to open input file for tool inference: {}",
            path.display()
        )
    })?;
    let reader = std::io::BufReader::new(file);

    for line in reader.lines().take(40) {
        let line = line?;
        if let Some(tool) = parsed_line_value(&line).and_then(|value| infer_tool_from_entry(&value))
        {
            return Ok(tool);
        }
    }

    Err(anyhow!(
        "could not infer tool format from {}. Pass --tool claude or --tool codex",
        path.display()
    ))
}

pub fn discover_for_tool(cwd: &Path, tool: AgentTool) -> Result<ResolvedInput> {
    discovered_path_for_tool(cwd, tool)
        .map(|path| discovered_input(tool, path))
        .ok_or_else(|| {
            anyhow!(
                "no {} transcript JSONL found for cwd {}",
                tool.as_str(),
                cwd.display()
            )
        })
}

pub fn discover_auto(cwd: &Path) -> Result<ResolvedInput> {
    match (discover_claude_path(cwd), discover_codex_path(cwd)) {
        (Some(path), None) => Ok(discovered_input(AgentTool::Claude, path)),
        (None, Some(path)) => Ok(discovered_input(AgentTool::Codex, path)),
        (Some(claude), Some(codex)) => Ok(newer_discovered_input(claude, codex)),
        (None, None) => Err(anyhow!(
            "no Claude or Codex transcript JSONL found for cwd {}",
            cwd.display()
        )),
    }
}

pub fn discover_claude_path(cwd: &Path) -> Option<PathBuf> {
    discover_claude_paths(cwd).into_iter().next()
}

pub fn discover_claude_paths(cwd: &Path) -> Vec<PathBuf> {
    let Some(home) = home_dir() else {
        return Vec::new();
    };
    let cwd_slug = cwd.display().to_string().replace('/', "-");
    let project_dir = home.join(".claude").join("projects").join(cwd_slug);

    let mut files: Vec<(PathBuf, SystemTime)> = match fs::read_dir(project_dir) {
        Ok(entries) => entries
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("jsonl"))
            .filter(|path| claude_file_matches_cwd(path, cwd))
            .filter_map(|path| {
                let modified = fs::metadata(&path).ok()?.modified().ok()?;
                Some((path, modified))
            })
            .collect(),
        Err(_) => return Vec::new(),
    };

    files.sort_by(|a, b| b.1.cmp(&a.1));
    files.into_iter().map(|(path, _)| path).collect()
}

pub fn discover_codex_path(cwd: &Path) -> Option<PathBuf> {
    discover_codex_paths(cwd).into_iter().next()
}

pub fn discover_codex_paths(cwd: &Path) -> Vec<PathBuf> {
    let Some(home) = home_dir() else {
        return Vec::new();
    };
    let sessions_dir = home.join(".codex").join("sessions");
    sorted_numeric_subdirs_reverse(&sessions_dir, 4)
        .into_iter()
        .flat_map(|year| codex_paths_in_year(&year, cwd))
        .collect()
}

pub fn discover_claude_path_excluding(cwd: &Path, excluded: &HashSet<PathBuf>) -> Option<PathBuf> {
    discover_claude_paths(cwd)
        .into_iter()
        .find(|path| !excluded.contains(path))
}

fn claude_file_matches_cwd(path: &Path, cwd: &Path) -> bool {
    fs::File::open(path)
        .ok()
        .map(std::io::BufReader::new)
        .is_some_and(|reader| reader_matches_or_lacks_cwd(reader, &cwd.display().to_string()))
}

pub fn discover_codex_path_excluding(cwd: &Path, excluded: &HashSet<PathBuf>) -> Option<PathBuf> {
    discover_codex_paths(cwd)
        .into_iter()
        .find(|path| !excluded.contains(path))
}

fn codex_file_matches_cwd(path: &Path, cwd: &Path) -> bool {
    let cwd_str = cwd.display().to_string();
    let file = match fs::File::open(path) {
        Ok(file) => file,
        Err(_) => return false,
    };
    let mut lines = std::io::BufReader::new(file).lines();
    let first_line = match lines.next() {
        Some(Ok(line)) => line,
        _ => return false,
    };

    let value: Value = match serde_json::from_str(&first_line) {
        Ok(value) => value,
        Err(_) => return false,
    };

    if value.get("type").and_then(Value::as_str) != Some("session_meta") {
        return false;
    }

    value
        .get("payload")
        .and_then(|payload| payload.get("cwd"))
        .and_then(Value::as_str)
        .map(|entry_cwd| entry_cwd == cwd_str)
        .unwrap_or(false)
}

fn sorted_numeric_subdirs_reverse(dir: &Path, width: usize) -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = match fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|entry| entry.ok())
            .filter(|entry| {
                entry
                    .file_type()
                    .ok()
                    .map(|ft| ft.is_dir())
                    .unwrap_or(false)
            })
            .filter(|entry| {
                entry
                    .file_name()
                    .to_str()
                    .map(|name| name.len() == width && name.chars().all(|ch| ch.is_ascii_digit()))
                    .unwrap_or(false)
            })
            .map(|entry| entry.path())
            .collect(),
        Err(_) => Vec::new(),
    };

    dirs.sort();
    dirs.reverse();
    dirs
}

fn modified_or_epoch(path: &Path) -> SystemTime {
    fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .unwrap_or(SystemTime::UNIX_EPOCH)
}

fn home_dir() -> Option<PathBuf> {
    std::env::var("HOME").ok().map(PathBuf::from)
}

fn parsed_line_value(line: &str) -> Option<Value> {
    let trimmed = line.trim();
    (!trimmed.is_empty())
        .then_some(trimmed)
        .and_then(|trimmed| serde_json::from_str(trimmed).ok())
}

fn infer_tool_from_entry(value: &Value) -> Option<AgentTool> {
    let entry_type = value
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default();
    codex_entry_tool(entry_type)
        .or_else(|| claude_entry_tool(value, entry_type))
        .or_else(|| value.get("payload").map(|_| AgentTool::Codex))
}

fn codex_entry_tool(entry_type: &str) -> Option<AgentTool> {
    matches!(
        entry_type,
        "session_meta" | "response" | "response_item" | "event_msg"
    )
    .then_some(AgentTool::Codex)
}

fn claude_entry_tool(value: &Value, entry_type: &str) -> Option<AgentTool> {
    matches!(entry_type, "assistant" | "user")
        .then_some(AgentTool::Claude)
        .or_else(|| value.get("message").map(|_| AgentTool::Claude))
}

fn discovered_path_for_tool(cwd: &Path, tool: AgentTool) -> Option<PathBuf> {
    match tool {
        AgentTool::Claude => discover_claude_path(cwd),
        AgentTool::Codex => discover_codex_path(cwd),
    }
}

fn discovered_input(tool: AgentTool, path: PathBuf) -> ResolvedInput {
    ResolvedInput {
        tool,
        path,
        discovered: true,
    }
}

fn newer_discovered_input(claude: PathBuf, codex: PathBuf) -> ResolvedInput {
    if modified_or_epoch(&codex) > modified_or_epoch(&claude) {
        discovered_input(AgentTool::Codex, codex)
    } else {
        discovered_input(AgentTool::Claude, claude)
    }
}

fn codex_paths_in_year(year: &Path, cwd: &Path) -> Vec<PathBuf> {
    sorted_numeric_subdirs_reverse(year, 2)
        .into_iter()
        .flat_map(|month| codex_paths_in_month(&month, cwd))
        .collect()
}

fn codex_paths_in_month(month: &Path, cwd: &Path) -> Vec<PathBuf> {
    sorted_numeric_subdirs_reverse(month, 2)
        .into_iter()
        .flat_map(|day| matching_codex_rollouts(&day, cwd))
        .collect()
}

fn matching_codex_rollouts(day: &Path, cwd: &Path) -> Vec<PathBuf> {
    codex_rollout_files(day)
        .into_iter()
        .filter(|path| codex_file_matches_cwd(path, cwd))
        .collect()
}

fn codex_rollout_files(day: &Path) -> Vec<PathBuf> {
    let mut rollout_files: Vec<PathBuf> = match fs::read_dir(day) {
        Ok(entries) => entries
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| {
                let name = path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or_default();
                name.starts_with("rollout-") && name.ends_with(".jsonl")
            })
            .collect(),
        Err(_) => return Vec::new(),
    };

    rollout_files.sort();
    rollout_files.reverse();
    rollout_files
}

fn reader_matches_or_lacks_cwd<R: BufRead>(reader: R, cwd_str: &str) -> bool {
    let matches: Vec<bool> = reader
        .lines()
        .take(64)
        .filter_map(|line| line.ok())
        .filter_map(|line| parsed_line_value(&line))
        .filter_map(|value| {
            value
                .get("cwd")
                .and_then(Value::as_str)
                .map(|entry| entry == cwd_str)
        })
        .collect();

    matches.is_empty() || matches.into_iter().any(|matched| matched)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use std::thread;
    use std::time::Duration;
    use tempfile::NamedTempFile;

    /// Tests that modify $HOME must hold this lock to avoid racing each other.
    static HOME_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn infer_codex_tool_from_response_item() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\"}}\n",
        )
        .expect("write file");

        let tool = infer_tool_from_file(file.path()).expect("infer tool");
        assert_eq!(tool, AgentTool::Codex);
    }

    #[test]
    fn infer_claude_tool_from_assistant_message() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(
            file.path(),
            "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\"}}\n",
        )
        .expect("write file");

        let tool = infer_tool_from_file(file.path()).expect("infer tool");
        assert_eq!(tool, AgentTool::Claude);
    }

    #[test]
    fn infer_codex_tool_from_payload_marker() {
        let file = NamedTempFile::new().expect("temp file");
        fs::write(file.path(), "{\"payload\":{\"cwd\":\"/tmp/project\"}}\n").expect("write file");

        let tool = infer_tool_from_file(file.path()).expect("infer tool");
        assert_eq!(tool, AgentTool::Codex);
    }

    /// Helper: create a fake Claude project dir under a temp HOME with JSONL files.
    /// Returns (temp_dir, cwd, vec of created file paths sorted oldest-first).
    fn setup_claude_project_dir(
        cwd_path: &str,
        file_count: usize,
    ) -> (tempfile::TempDir, PathBuf, Vec<PathBuf>) {
        let tmp = tempfile::tempdir().expect("tempdir");
        let cwd = PathBuf::from(cwd_path);
        let cwd_slug = cwd.display().to_string().replace('/', "-");
        let project_dir = tmp.path().join(".claude").join("projects").join(cwd_slug);
        fs::create_dir_all(&project_dir).expect("mkdir");

        let mut paths = Vec::new();
        for i in 0..file_count {
            let file_path = project_dir.join(format!("session-{i}.jsonl"));
            let line = format!(
                "{{\"type\":\"assistant\",\"cwd\":\"{}\",\"message\":{{\"role\":\"assistant\"}}}}\n",
                cwd.display()
            );
            fs::write(&file_path, line).expect("write");
            paths.push(file_path);
            // Ensure distinct mtime ordering
            thread::sleep(Duration::from_millis(50));
        }
        (tmp, cwd, paths)
    }

    #[test]
    fn excluding_empty_set_returns_newest() {
        let _lock = HOME_LOCK.lock().unwrap();
        let (tmp, cwd, paths) = setup_claude_project_dir("/tmp/project", 2);
        std::env::set_var("HOME", tmp.path());
        let result = discover_claude_path_excluding(&cwd, &HashSet::new());
        assert_eq!(result, Some(paths[1].clone()), "should return newest file");
    }

    #[test]
    fn excluding_newest_returns_second() {
        let _lock = HOME_LOCK.lock().unwrap();
        let (tmp, cwd, paths) = setup_claude_project_dir("/tmp/project-a", 2);
        std::env::set_var("HOME", tmp.path());
        let mut excluded = HashSet::new();
        excluded.insert(paths[1].clone());
        let result = discover_claude_path_excluding(&cwd, &excluded);
        assert_eq!(
            result,
            Some(paths[0].clone()),
            "should return second-newest when newest excluded"
        );
    }

    #[test]
    fn excluding_all_returns_none() {
        let _lock = HOME_LOCK.lock().unwrap();
        let (tmp, cwd, paths) = setup_claude_project_dir("/tmp/project-b", 1);
        std::env::set_var("HOME", tmp.path());
        let mut excluded = HashSet::new();
        excluded.insert(paths[0].clone());
        let result = discover_claude_path_excluding(&cwd, &excluded);
        assert_eq!(result, None, "should return None when all files excluded");
    }

    #[test]
    fn exclusion_does_not_cross_cwd_boundaries() {
        let _lock = HOME_LOCK.lock().unwrap();
        let (tmp, _cwd_a, paths_a) = setup_claude_project_dir("/tmp/project-c", 1);
        // Create a second project dir under the same HOME
        let cwd_b = PathBuf::from("/tmp/project-d");
        let slug_b = cwd_b.display().to_string().replace('/', "-");
        let dir_b = tmp.path().join(".claude").join("projects").join(slug_b);
        fs::create_dir_all(&dir_b).expect("mkdir");
        let file_b = dir_b.join("session-0.jsonl");
        fs::write(
            &file_b,
            "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\"}}\n",
        )
        .expect("write");

        std::env::set_var("HOME", tmp.path());

        // Exclude a path from project A
        let mut excluded = HashSet::new();
        excluded.insert(paths_a[0].clone());

        // Project B should still find its file unaffected
        let result = discover_claude_path_excluding(&cwd_b, &excluded);
        assert_eq!(
            result,
            Some(file_b),
            "exclusion from different CWD should not affect discovery"
        );
    }

    #[test]
    fn claude_discovery_filters_colliding_slug_by_exact_cwd() {
        let _lock = HOME_LOCK.lock().unwrap();
        let tmp = tempfile::tempdir().expect("tempdir");

        let cwd_a = PathBuf::from("/tmp/a-b/c");
        let cwd_b = PathBuf::from("/tmp/a/b-c");
        let slug_a = cwd_a.display().to_string().replace('/', "-");
        let slug_b = cwd_b.display().to_string().replace('/', "-");
        assert_eq!(slug_a, slug_b, "test requires slug collision");

        let project_dir = tmp.path().join(".claude").join("projects").join(&slug_a);
        fs::create_dir_all(&project_dir).expect("mkdir");

        // Older file for cwd_a
        let file_a = project_dir.join("session-a.jsonl");
        fs::write(
            &file_a,
            format!(
                "{{\"type\":\"user\",\"cwd\":\"{}\",\"message\":{{\"role\":\"user\",\"content\":\"TASK_A\"}}}}\n",
                cwd_a.display()
            ),
        )
        .expect("write");
        thread::sleep(Duration::from_millis(50));

        // Newer file for cwd_b (same slug dir due collision)
        let file_b = project_dir.join("session-b.jsonl");
        fs::write(
            &file_b,
            format!(
                "{{\"type\":\"user\",\"cwd\":\"{}\",\"message\":{{\"role\":\"user\",\"content\":\"TASK_B\"}}}}\n",
                cwd_b.display()
            ),
        )
        .expect("write");

        std::env::set_var("HOME", tmp.path());

        let found_plain = discover_claude_path(&cwd_a);
        assert_eq!(
            found_plain,
            Some(file_a.clone()),
            "plain discovery should ignore newer mismatched-cwd file"
        );

        let found_excluding = discover_claude_path_excluding(&cwd_a, &HashSet::new());
        assert_eq!(
            found_excluding,
            Some(file_a),
            "excluding discovery should ignore newer mismatched-cwd file"
        );
    }

    #[test]
    fn claude_discovery_exclusion_isolates_same_cwd_sessions() {
        let _lock = HOME_LOCK.lock().unwrap();
        let (tmp, cwd, paths) = setup_claude_project_dir("/tmp/shared-cwd", 2);
        std::env::set_var("HOME", tmp.path());

        let first = discover_claude_path_excluding(&cwd, &HashSet::new())
            .expect("first discovery should find newest file");
        let mut excluded = HashSet::new();
        excluded.insert(first.clone());
        let second = discover_claude_path_excluding(&cwd, &excluded)
            .expect("second discovery should find non-excluded file");

        assert_ne!(first, second, "same-cwd sessions must not claim same file");
        assert_eq!(first, paths[1], "first claim should be newest file");
        assert_eq!(second, paths[0], "second claim should be next newest file");
    }

    #[test]
    fn discover_for_tool_finds_codex_rollout() {
        let _lock = HOME_LOCK.lock().unwrap();
        let tmp = tempfile::tempdir().expect("tempdir");
        let cwd = PathBuf::from("/tmp/codex-project");
        let codex_day = tmp
            .path()
            .join(".codex")
            .join("sessions")
            .join("2026")
            .join("03")
            .join("16");
        fs::create_dir_all(&codex_day).expect("mkdir");
        let rollout = codex_day.join("rollout-a.jsonl");
        fs::write(
            &rollout,
            format!(
                "{{\"type\":\"session_meta\",\"payload\":{{\"cwd\":\"{}\"}}}}\n",
                cwd.display()
            ),
        )
        .expect("write");
        std::env::set_var("HOME", tmp.path());

        let resolved = discover_for_tool(&cwd, AgentTool::Codex).expect("discover codex");

        assert_eq!(resolved.tool, AgentTool::Codex);
        assert_eq!(resolved.path, rollout);
        assert!(resolved.discovered);
    }

    #[test]
    fn discover_auto_prefers_newer_codex_rollout() {
        let _lock = HOME_LOCK.lock().unwrap();
        let tmp = tempfile::tempdir().expect("tempdir");
        let cwd = PathBuf::from("/tmp/mixed-project");
        std::env::set_var("HOME", tmp.path());

        let cwd_slug = cwd.display().to_string().replace('/', "-");
        let claude_dir = tmp.path().join(".claude").join("projects").join(cwd_slug);
        fs::create_dir_all(&claude_dir).expect("mkdir");
        let claude_file = claude_dir.join("session-a.jsonl");
        fs::write(
            &claude_file,
            format!(
                "{{\"type\":\"assistant\",\"cwd\":\"{}\",\"message\":{{\"role\":\"assistant\"}}}}\n",
                cwd.display()
            ),
        )
        .expect("write");
        thread::sleep(Duration::from_millis(50));

        let codex_day = tmp
            .path()
            .join(".codex")
            .join("sessions")
            .join("2026")
            .join("03")
            .join("16");
        fs::create_dir_all(&codex_day).expect("mkdir");
        let codex_file = codex_day.join("rollout-z.jsonl");
        fs::write(
            &codex_file,
            format!(
                "{{\"type\":\"session_meta\",\"payload\":{{\"cwd\":\"{}\"}}}}\n",
                cwd.display()
            ),
        )
        .expect("write");

        let resolved = discover_auto(&cwd).expect("discover newest");

        assert_eq!(resolved.tool, AgentTool::Codex);
        assert_eq!(resolved.path, codex_file);
    }
}
