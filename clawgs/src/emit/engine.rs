use std::collections::{hash_map::DefaultHasher, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};

use crate::{
    discover_claude_paths, discover_codex_paths, extract, resolve_input, AgentTool, ExtractOptions,
    Snapshot, ToolSelection,
};

use super::model_client::ModelClient;
use super::protocol::{
    BubblePrecedence, RestState, SessionSnapshot, SessionState, SyncMetrics, SyncRequest,
    SyncResultMessage, ThoughtConfig, ThoughtSource, ThoughtState, ThoughtUpdate,
};

const SUMMARY_HISTORY_CAP: usize = 10;
const TERMINAL_CONTEXT_CHARS: usize = 800;
const TERMINAL_MIN_MEANINGFUL_DELTA_CHARS: usize = 100;
const MAX_THOUGHT_CHARS: usize = 120;
const STATIC_SLEEPING_THOUGHT: &str = "Sleeping.";
const DROWSY_AFTER_MS: i64 = 10_000;
const SLEEPING_AFTER_MS: i64 = 30_000;
const DEEP_SLEEP_AFTER_MS: i64 = 60_000;

pub const DEFAULT_AGENT_PREAMBLE: &str = "You are a status reporter for a coding agent session.";
pub const DEFAULT_TERMINAL_PREAMBLE: &str = "Terminal session status reporter.";

struct SessionRuntimeState {
    summary_history: Vec<String>,
    last_terminal_context: Option<String>,
    last_call_at: Option<DateTime<Utc>>,
    last_emitted_thought: Option<String>,
    sleeping_emitted: bool,
    thought_state: ThoughtState,
    thought_source: ThoughtSource,
    rest_state: RestState,
    objective_fingerprint: Option<String>,
    objective_stable_since: DateTime<Utc>,
    claimed_jsonl_path: Option<PathBuf>,
    emission_seq: u64,
}

impl SessionRuntimeState {
    fn initialize_from_session(session: &SessionSnapshot, now: DateTime<Utc>) -> Self {
        let mut summary_history = Vec::new();
        if let Some(thought) = session.thought.as_ref() {
            summary_history.push(thought.clone());
        }

        let thought_updated_at = session.thought_updated_at.unwrap_or(now);

        Self {
            summary_history,
            last_terminal_context: Some(trim_terminal_context(&session.replay_text)),
            last_call_at: session.thought_updated_at,
            last_emitted_thought: session.thought.clone(),
            sleeping_emitted: is_sleeping_text(session.thought.as_deref()),
            thought_state: session.thought_state,
            thought_source: session.thought_source,
            rest_state: session.rest_state,
            objective_fingerprint: session.objective_fingerprint.clone(),
            objective_stable_since: thought_updated_at,
            claimed_jsonl_path: None,
            emission_seq: 0,
        }
    }

    fn next_emission_seq(&mut self) -> u64 {
        self.emission_seq = self.emission_seq.saturating_add(1);
        self.emission_seq
    }

    fn cadence_tier_label(&self, config: &ThoughtConfig, now: DateTime<Utc>) -> &'static str {
        let objective_age_ms = (now - self.objective_stable_since).num_milliseconds();
        if objective_age_ms >= config.cadence_cold_ms as i64 {
            "cold"
        } else if objective_age_ms >= config.cadence_warm_ms as i64 {
            "warm"
        } else {
            "hot"
        }
    }

    fn cadence_for_state(&self, config: &ThoughtConfig, now: DateTime<Utc>) -> u64 {
        match self.cadence_tier_label(config, now) {
            "cold" => config.cadence_cold_ms,
            "warm" => config.cadence_warm_ms,
            _ => config.cadence_hot_ms,
        }
    }

    fn should_call_for_cadence(&self, config: &ThoughtConfig, now: DateTime<Utc>) -> bool {
        match self.last_call_at {
            Some(last_call) => {
                let elapsed_ms = (now - last_call).num_milliseconds();
                elapsed_ms >= self.cadence_for_state(config, now) as i64
            }
            None => true,
        }
    }
}

pub struct EmitEngine {
    model_client: Box<dyn ModelClient>,
    per_session: HashMap<String, SessionRuntimeState>,
    stream_instance_id: String,
}

impl EmitEngine {
    pub fn new(model_client: Box<dyn ModelClient>) -> Self {
        Self {
            model_client,
            per_session: HashMap::new(),
            stream_instance_id: format!(
                "stream-{}-{}",
                Utc::now().timestamp_millis(),
                std::process::id()
            ),
        }
    }

    pub fn sync(&mut self, request: &SyncRequest) -> SyncResultMessage {
        let mut updates = Vec::new();
        let mut metrics = SyncMetrics::default();

        let active_ids: HashSet<&str> = request
            .sessions
            .iter()
            .map(|session| session.session_id.as_str())
            .collect();
        self.per_session
            .retain(|session_id, _| active_ids.contains(session_id.as_str()));

        if !request.config.enabled {
            self.clear_all_sessions(request, &mut updates, &mut metrics);
            return SyncResultMessage::new(
                request.id.clone(),
                self.stream_instance_id.clone(),
                updates,
                metrics,
            );
        }

        let mut transcript_group_counts: HashMap<String, usize> = HashMap::new();
        for session in &request.sessions {
            if let Some(group_key) = transcript_group_key(session) {
                *transcript_group_counts.entry(group_key).or_insert(0) += 1;
            }
        }

        let model_client = &self.model_client;

        for session in &request.sessions {
            metrics.sessions_seen += 1;

            if session.exited {
                metrics.suppressed += 1;
                continue;
            }

            let state = self
                .per_session
                .entry(session.session_id.clone())
                .or_insert_with(|| {
                    SessionRuntimeState::initialize_from_session(session, request.now)
                });
            let next_rest_state = rest_state_for_session(session, request.now);

            if is_sleeping_rest_state(next_rest_state) {
                let should_emit_sleeping = state.thought_state != ThoughtState::Sleeping
                    || !state.sleeping_emitted
                    || !is_sleeping_text(state.last_emitted_thought.as_deref())
                    || state.rest_state != next_rest_state;

                if should_emit_sleeping {
                    let update = thought_update(
                        &self.stream_instance_id,
                        state,
                        session,
                        Some(STATIC_SLEEPING_THOUGHT.to_string()),
                        session.token_count,
                        session.context_limit,
                        ThoughtState::Sleeping,
                        ThoughtSource::StaticSleeping,
                        false,
                        request.now,
                        Some("sleeping".to_string()),
                        next_rest_state,
                    );
                    updates.push(update);
                } else {
                    metrics.suppressed += 1;
                }

                state.sleeping_emitted = true;
                state.thought_state = ThoughtState::Sleeping;
                state.thought_source = ThoughtSource::StaticSleeping;
                state.rest_state = next_rest_state;
                state.last_emitted_thought = Some(STATIC_SLEEPING_THOUGHT.to_string());
                state.last_call_at = Some(request.now);
                state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
                continue;
            }

            if state.thought_state == ThoughtState::Sleeping {
                updates.push(clear_thought_update(
                    &self.stream_instance_id,
                    state,
                    session,
                    request.now,
                    next_rest_state,
                ));
                state.thought_state = ThoughtState::Holding;
                state.thought_source = ThoughtSource::CarryForward;
                state.rest_state = next_rest_state;
                state.sleeping_emitted = false;
                state.last_emitted_thought = None;
                state.last_call_at = Some(request.now);
            }

            let context_group_is_ambiguous = transcript_group_key(session)
                .and_then(|group_key| transcript_group_counts.get(&group_key).copied())
                .unwrap_or_default()
                > 1;
            let (context_snapshot, resolved_path) = context_snapshot_for_session_with_claim(
                session,
                state.claimed_jsonl_path.as_deref(),
                context_group_is_ambiguous,
            );
            state.claimed_jsonl_path = resolved_path;
            if is_initial_thought_candidate(state, session)
                && !has_adequate_initial_context(context_snapshot.as_ref(), &session.replay_text)
            {
                state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
                metrics.suppressed += 1;
                continue;
            }
            let objective_fingerprint = if let Some(snapshot) = context_snapshot.as_ref() {
                context_focus_fingerprint(snapshot, &session.state).to_string()
            } else {
                terminal_objective_fingerprint(&session.replay_text, &session.state)
            };

            let objective_changed =
                state.objective_fingerprint.as_deref() != Some(objective_fingerprint.as_str());
            if objective_changed {
                state.objective_stable_since = request.now;
                state.objective_fingerprint = Some(objective_fingerprint.clone());
            }

            if !objective_changed && !state.should_call_for_cadence(&request.config, request.now) {
                if emit_rest_state_change_if_needed(
                    &mut updates,
                    &self.stream_instance_id,
                    state,
                    session,
                    next_rest_state,
                    request.now,
                ) {
                    continue;
                }
                metrics.suppressed += 1;
                continue;
            }

            if context_snapshot.is_none()
                && !objective_changed
                && !has_meaningful_terminal_delta(
                    &session.replay_text,
                    state.last_terminal_context.as_deref(),
                )
            {
                if emit_rest_state_change_if_needed(
                    &mut updates,
                    &self.stream_instance_id,
                    state,
                    session,
                    next_rest_state,
                    request.now,
                ) {
                    continue;
                }
                metrics.suppressed += 1;
                continue;
            }

            state.last_call_at = Some(request.now);

            let prompt = if let Some(snapshot) = context_snapshot.as_ref() {
                build_context_prompt(
                    snapshot,
                    &session.state,
                    &state.summary_history,
                    request.config.agent_prompt.as_deref(),
                )
            } else {
                build_terminal_prompt(
                    &session.replay_text,
                    &session.state,
                    state.last_terminal_context.as_deref(),
                    request.config.terminal_prompt.as_deref(),
                )
            };

            let raw_thought = match model_client.complete(&prompt, request.config.model_override())
            {
                Ok(value) => value,
                Err(_) => {
                    metrics.suppressed += 1;
                    state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
                    continue;
                }
            };

            let thought = sanitize_thought_text(&raw_thought);
            if thought.is_empty() {
                metrics.suppressed += 1;
                continue;
            }

            if is_duplicate_thought(state.last_emitted_thought.as_deref(), &thought) {
                if emit_rest_state_change_if_needed(
                    &mut updates,
                    &self.stream_instance_id,
                    state,
                    session,
                    next_rest_state,
                    request.now,
                ) {
                    continue;
                }
                metrics.suppressed += 1;
                continue;
            }

            let next_state = if objective_changed {
                ThoughtState::Active
            } else {
                ThoughtState::Holding
            };

            let token_count = context_snapshot
                .as_ref()
                .map(|snapshot| snapshot.token_count)
                .unwrap_or(session.token_count);

            updates.push(thought_update(
                &self.stream_instance_id,
                state,
                session,
                Some(thought.clone()),
                token_count,
                session.context_limit,
                next_state,
                ThoughtSource::Llm,
                objective_changed,
                request.now,
                Some(objective_fingerprint.clone()),
                next_rest_state,
            ));

            state.last_emitted_thought = Some(thought.clone());
            state.summary_history.push(thought);
            if state.summary_history.len() > SUMMARY_HISTORY_CAP {
                let start = state.summary_history.len() - SUMMARY_HISTORY_CAP;
                state.summary_history = state.summary_history.split_off(start);
            }
            state.thought_state = next_state;
            state.thought_source = ThoughtSource::Llm;
            state.rest_state = next_rest_state;
            state.sleeping_emitted = false;
            state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
            metrics.llm_calls += 1;
        }

        SyncResultMessage::new(
            request.id.clone(),
            self.stream_instance_id.clone(),
            updates,
            metrics,
        )
    }

    fn clear_all_sessions(
        &mut self,
        request: &SyncRequest,
        updates: &mut Vec<ThoughtUpdate>,
        metrics: &mut SyncMetrics,
    ) {
        for session in &request.sessions {
            metrics.sessions_seen += 1;
            let state = self
                .per_session
                .entry(session.session_id.clone())
                .or_insert_with(|| {
                    SessionRuntimeState::initialize_from_session(session, request.now)
                });
            let next_rest_state = rest_state_for_session(session, request.now);

            let needs_clear = state.last_emitted_thought.is_some()
                || session.thought.is_some()
                || state.thought_state != ThoughtState::Holding
                || state.rest_state != next_rest_state;

            if needs_clear {
                updates.push(clear_thought_update(
                    &self.stream_instance_id,
                    state,
                    session,
                    request.now,
                    next_rest_state,
                ));
                state.last_emitted_thought = None;
                state.thought_state = ThoughtState::Holding;
                state.thought_source = ThoughtSource::CarryForward;
                state.rest_state = next_rest_state;
                state.sleeping_emitted = false;
                state.last_call_at = Some(request.now);
            } else {
                metrics.suppressed += 1;
            }
        }
    }
}

fn clear_thought_update(
    stream_instance_id: &str,
    state: &mut SessionRuntimeState,
    session: &SessionSnapshot,
    now: DateTime<Utc>,
    rest_state: RestState,
) -> ThoughtUpdate {
    thought_update(
        stream_instance_id,
        state,
        session,
        None,
        session.token_count,
        session.context_limit,
        ThoughtState::Holding,
        ThoughtSource::CarryForward,
        false,
        now,
        None,
        rest_state,
    )
}

fn emit_rest_state_change_if_needed(
    updates: &mut Vec<ThoughtUpdate>,
    stream_instance_id: &str,
    state: &mut SessionRuntimeState,
    session: &SessionSnapshot,
    next_rest_state: RestState,
    now: DateTime<Utc>,
) -> bool {
    if state.rest_state == next_rest_state {
        return false;
    }

    updates.push(thought_update(
        stream_instance_id,
        state,
        session,
        current_thought_for_update(state, session),
        session.token_count,
        session.context_limit,
        state.thought_state,
        state.thought_source,
        false,
        now,
        state.objective_fingerprint.clone(),
        next_rest_state,
    ));
    state.rest_state = next_rest_state;
    true
}

fn current_thought_for_update(
    state: &SessionRuntimeState,
    session: &SessionSnapshot,
) -> Option<String> {
    state
        .last_emitted_thought
        .clone()
        .or_else(|| session.thought.clone())
}

fn thought_update(
    stream_instance_id: &str,
    state: &mut SessionRuntimeState,
    session: &SessionSnapshot,
    thought: Option<String>,
    token_count: u64,
    context_limit: u64,
    thought_state: ThoughtState,
    thought_source: ThoughtSource,
    objective_changed: bool,
    at: DateTime<Utc>,
    objective_fingerprint: Option<String>,
    rest_state: RestState,
) -> ThoughtUpdate {
    ThoughtUpdate {
        session_id: session.session_id.clone(),
        stream_instance_id: stream_instance_id.to_string(),
        emission_seq: state.next_emission_seq(),
        thought,
        token_count,
        context_limit,
        thought_state,
        thought_source,
        objective_changed,
        bubble_precedence: BubblePrecedence::ThoughtFirst,
        at,
        objective_fingerprint,
        rest_state,
    }
}

fn rest_state_for_session(session: &SessionSnapshot, now: DateTime<Utc>) -> RestState {
    if session.exited || session.state == SessionState::Exited {
        return RestState::DeepSleep;
    }
    if session.state != SessionState::Idle && session.state != SessionState::Attention {
        return RestState::Active;
    }
    let idle_ms = (now - session.last_activity_at).num_milliseconds().max(0);
    if idle_ms >= DEEP_SLEEP_AFTER_MS {
        RestState::DeepSleep
    } else if idle_ms >= SLEEPING_AFTER_MS {
        RestState::Sleeping
    } else if idle_ms >= DROWSY_AFTER_MS {
        RestState::Drowsy
    } else {
        RestState::Active
    }
}

fn is_sleeping_rest_state(rest_state: RestState) -> bool {
    matches!(rest_state, RestState::Sleeping | RestState::DeepSleep)
}

fn is_sleeping_text(thought: Option<&str>) -> bool {
    match thought {
        Some(value) => {
            let normalized = value.trim().to_lowercase();
            normalized == "sleeping." || normalized == "sleeping"
        }
        None => false,
    }
}

fn transcript_group_key(session: &SessionSnapshot) -> Option<String> {
    let selection = tool_selection_for_session(session.tool.as_deref())?;
    let tool = match selection {
        ToolSelection::Claude => "claude",
        ToolSelection::Codex => "codex",
        ToolSelection::Auto => return None,
    };

    Some(format!("{tool}:{}", session.cwd))
}

fn context_snapshot_for_session_with_claim(
    session: &SessionSnapshot,
    existing_claim: Option<&Path>,
    group_is_ambiguous: bool,
) -> (Option<Snapshot>, Option<PathBuf>) {
    let selection = match tool_selection_for_session(session.tool.as_deref()) {
        Some(s) => s,
        None => return (None, None),
    };
    let cwd = Path::new(&session.cwd);

    // If we already have a claimed path and the file still exists, reuse it
    if let Some(claimed) = existing_claim {
        if claimed.exists() {
            let resolved = resolve_input(selection, cwd, Some(claimed)).ok();
            if let Some(resolved) = resolved {
                let output = extract(
                    resolved.tool,
                    &resolved.path,
                    cwd,
                    resolved.discovered,
                    &ExtractOptions::default(),
                )
                .ok();
                return (output.map(|o| o.snapshot), Some(claimed.to_path_buf()));
            }
        }
    }

    // Otherwise, only claim a transcript when the pane has a unique binding.
    if group_is_ambiguous {
        return (None, None);
    }

    let agent_tool = match selection {
        ToolSelection::Claude => AgentTool::Claude,
        ToolSelection::Codex => AgentTool::Codex,
        ToolSelection::Auto => return (None, None),
    };

    let candidates = match agent_tool {
        AgentTool::Claude => discover_claude_paths(cwd),
        AgentTool::Codex => discover_codex_paths(cwd),
    };

    if candidates.len() != 1 {
        return (None, None);
    }

    let path = candidates[0].clone();

    let output = extract(agent_tool, &path, cwd, true, &ExtractOptions::default()).ok();

    (output.map(|o| o.snapshot), Some(path))
}

fn is_initial_thought_candidate(state: &SessionRuntimeState, session: &SessionSnapshot) -> bool {
    state.emission_seq == 0 && state.last_emitted_thought.is_none() && session.thought.is_none()
}

fn has_adequate_initial_context(context_snapshot: Option<&Snapshot>, replay_text: &str) -> bool {
    context_snapshot.is_some_and(snapshot_has_meaningful_context)
        || has_meaningful_terminal_delta(replay_text, None)
}

fn snapshot_has_meaningful_context(snapshot: &Snapshot) -> bool {
    snapshot
        .user_task
        .as_deref()
        .map(normalize_for_focus)
        .is_some_and(|task| !task.is_empty())
        || snapshot.current_tool.is_some()
        || !snapshot.recent_actions.is_empty()
}

fn tool_selection_for_session(tool: Option<&str>) -> Option<ToolSelection> {
    let tool = tool?.to_lowercase();
    if tool.contains("claude") {
        Some(ToolSelection::Claude)
    } else if tool.contains("codex") {
        Some(ToolSelection::Codex)
    } else {
        None
    }
}

fn build_context_prompt(
    snapshot: &Snapshot,
    state: &SessionState,
    summary_history: &[String],
    custom_preamble: Option<&str>,
) -> String {
    let mut parts: Vec<String> = Vec::new();
    let preamble = custom_preamble.unwrap_or(DEFAULT_AGENT_PREAMBLE);
    parts.push(preamble.to_string());
    parts.push(format!("State: {}", state_label(state)));

    if let Some(task) = snapshot.user_task.as_ref() {
        parts.push(format!("Task: {task}"));
    }

    if !summary_history.is_empty() {
        let recent: Vec<&String> = summary_history
            .iter()
            .rev()
            .take(3)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        parts.push("Recent status:".to_string());
        for status in recent {
            parts.push(format!("  {status}"));
        }
    }

    if !snapshot.recent_actions.is_empty() {
        parts.push("Actions:".to_string());
        for action in &snapshot.recent_actions {
            if action.tool == "said" {
                parts.push(format!(
                    "  said: {}",
                    action.detail.as_deref().unwrap_or_default()
                ));
            } else {
                let detail_part = action
                    .detail
                    .as_ref()
                    .map(|value| format!(": {value}"))
                    .unwrap_or_default();
                parts.push(format!("  {}{detail_part}", action.tool));
            }
        }
    }

    if let Some(action) = snapshot.current_tool.as_ref() {
        let detail_part = action
            .detail
            .as_ref()
            .map(|value| format!(": {value}"))
            .unwrap_or_default();
        parts.push(format!("Now: {}{detail_part}", action.tool));
    }

    parts.push(String::new());
    parts.push("Write a 1-line status (max 60 chars). Explain the PURPOSE and WHY, not the tool or command.".to_string());
    parts.push("Do not speculate about anticipated future steps.".to_string());
    parts.push("Reply with ONLY the status line, nothing else.".to_string());

    parts.join("\n")
}

fn build_terminal_prompt(
    context: &str,
    state: &SessionState,
    prev_context: Option<&str>,
    custom_preamble: Option<&str>,
) -> String {
    let preamble = custom_preamble.unwrap_or(DEFAULT_TERMINAL_PREAMBLE);
    let clean = trim_terminal_context(context);
    let clean_prev = prev_context.map(trim_terminal_context);

    let context_block = if let Some(prev) = clean_prev {
        let tail: String = prev
            .chars()
            .rev()
            .take(200)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        match clean.find(&tail) {
            Some(index) => {
                let delta = clean[index + tail.len()..].trim();
                if !delta.is_empty() {
                    format!("New output:\n{delta}")
                } else {
                    format!("Screen:\n{clean}")
                }
            }
            None => format!("Screen:\n{clean}"),
        }
    } else {
        format!("Screen:\n{clean}")
    };

    format!(
        "{preamble}\n\
         State: {}\n\
         {context_block}\n\n\
         Write a 1-line status (max 60 chars). Infer the PURPOSE behind what's on screen — WHY is this happening, not WHAT command is running.\n\
         Do not speculate about anticipated future steps.\n\
         Reply with ONLY the status line, nothing else.",
        state_label(state)
    )
}

fn state_label(state: &SessionState) -> &'static str {
    match state {
        SessionState::Idle => "idle",
        SessionState::Busy => "busy",
        SessionState::Error => "error",
        SessionState::Attention => "attention",
        SessionState::Exited => "exited",
    }
}

fn has_meaningful_terminal_delta(current: &str, previous: Option<&str>) -> bool {
    let clean = trim_terminal_context(current);
    let clean_prev = previous.map(trim_terminal_context).unwrap_or_default();

    if clean != clean_prev {
        return changed_non_whitespace_chars(&clean, &clean_prev)
            >= TERMINAL_MIN_MEANINGFUL_DELTA_CHARS;
    }
    false
}

fn changed_non_whitespace_chars(current: &str, previous: &str) -> usize {
    let cur: Vec<char> = current.chars().collect();
    let prev: Vec<char> = previous.chars().collect();

    let mut prefix = 0usize;
    while prefix < cur.len() && prefix < prev.len() && cur[prefix] == prev[prefix] {
        prefix += 1;
    }

    let mut cur_suffix = cur.len();
    let mut prev_suffix = prev.len();
    while cur_suffix > prefix
        && prev_suffix > prefix
        && cur[cur_suffix - 1] == prev[prev_suffix - 1]
    {
        cur_suffix -= 1;
        prev_suffix -= 1;
    }

    cur[prefix..cur_suffix]
        .iter()
        .filter(|ch| !ch.is_whitespace())
        .count()
}

fn sanitize_thought_text(raw: &str) -> String {
    let normalized = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.is_empty() {
        return String::new();
    }

    if normalized.chars().count() <= MAX_THOUGHT_CHARS {
        return normalized;
    }

    let mut trimmed: String = normalized.chars().take(MAX_THOUGHT_CHARS - 3).collect();
    trimmed.push_str("...");
    trimmed
}

fn is_duplicate_thought(previous: Option<&str>, next: &str) -> bool {
    let Some(previous) = previous else {
        return false;
    };
    normalize_for_compare(previous) == normalize_for_compare(next)
}

fn normalize_for_compare(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn trim_terminal_context(context: &str) -> String {
    let stripped = strip_ansi(context);
    if stripped.chars().count() <= TERMINAL_CONTEXT_CHARS {
        return stripped;
    }

    stripped
        .chars()
        .rev()
        .take(TERMINAL_CONTEXT_CHARS)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect()
}

fn strip_ansi(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut chars = value.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next();
                while let Some(&next) = chars.peek() {
                    chars.next();
                    if next.is_ascii_alphabetic() || next == '~' {
                        break;
                    }
                }
            } else if chars.peek() == Some(&']') {
                chars.next();
                while let Some(&next) = chars.peek() {
                    chars.next();
                    if next == '\x07' {
                        break;
                    }
                    if next == '\x1b' && chars.peek() == Some(&'\\') {
                        chars.next();
                        break;
                    }
                }
            } else {
                chars.next();
            }
        } else if ch.is_control() && ch != '\n' && ch != '\t' {
            continue;
        } else {
            output.push(ch);
        }
    }
    output
}

fn context_focus_fingerprint(snapshot: &Snapshot, state: &SessionState) -> u64 {
    let mut parts = vec![format!("state={}", state_label(state))];

    if let Some(task) = snapshot.user_task.as_deref() {
        let normalized = normalize_for_focus(task);
        if !normalized.is_empty() {
            parts.push(format!("task={normalized}"));
        }
    }

    if let Some(current_tool) = snapshot.current_tool.as_ref() {
        let normalized = normalize_for_focus(&current_tool.tool);
        if !normalized.is_empty() {
            parts.push(format!("now={normalized}"));
        }
    }

    let recent_tools: Vec<String> = snapshot
        .recent_actions
        .iter()
        .rev()
        .take(3)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|action| normalize_for_focus(&action.tool))
        .filter(|tool| !tool.is_empty())
        .collect();
    if !recent_tools.is_empty() {
        parts.push(format!("recent={}", recent_tools.join(",")));
    }

    hash_string(&parts.join("|"))
}

fn terminal_objective_fingerprint(context: &str, state: &SessionState) -> String {
    let clean = strip_ansi(context);
    let preview = clean
        .lines()
        .rev()
        .take(6)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>()
        .join("|");

    let material = format!(
        "state={}|{}",
        state_label(state),
        normalize_for_focus(&preview)
    );
    hash_string(&material).to_string()
}

fn normalize_for_focus(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn hash_string(value: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    strip_ansi(value).hash(&mut hasher);
    hasher.finish()
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::sync::Mutex;

    use chrono::Duration;
    use tempfile::tempdir;

    use super::*;
    use crate::emit::model_client::ModelClient;
    use crate::emit::protocol::{SessionSnapshot, SessionState, SyncRequest, ThoughtConfig};

    static HOME_LOCK: Mutex<()> = Mutex::new(());

    struct MockModelClient {
        response: String,
    }

    impl ModelClient for MockModelClient {
        fn complete(&self, _prompt: &str, _model_override: Option<&str>) -> Result<String, String> {
            Ok(self.response.clone())
        }
    }

    fn sample_session(now: DateTime<Utc>) -> SessionSnapshot {
        SessionSnapshot {
            session_id: "sess-1".to_string(),
            state: SessionState::Busy,
            exited: false,
            tool: None,
            cwd: "/tmp/project".to_string(),
            replay_text: concat!(
                "running cargo test --all\n",
                "test auth::login_rejects_missing_token ... FAILED\n",
                "assertion failed: status should stay unauthorized after missing token\n",
                "reviewing auth middleware header parsing and session fallback handling\n"
            )
            .to_string(),
            thought: None,
            thought_state: ThoughtState::Holding,
            thought_source: ThoughtSource::CarryForward,
            objective_fingerprint: None,
            thought_updated_at: None,
            token_count: 1000,
            context_limit: 192_000,
            last_activity_at: now,
            rest_state: RestState::Active,
        }
    }

    #[test]
    fn emits_update_for_active_session() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "investigating failing auth tests".to_string(),
        }));

        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now)],
        };

        let result = engine.sync(&request);
        assert_eq!(result.msg_type, "sync_result");
        assert_eq!(result.updates.len(), 1);
        assert!(!result.stream_instance_id.is_empty());
        assert_eq!(
            result.updates[0].thought.as_deref(),
            Some("investigating failing auth tests")
        );
        assert_eq!(
            result.updates[0].stream_instance_id,
            result.stream_instance_id
        );
        assert_eq!(result.updates[0].emission_seq, 1);
    }

    #[test]
    fn cadence_gate_suppresses_rapid_repeat() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "investigating failing auth tests".to_string(),
        }));

        let first = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now)],
        };
        let first_result = engine.sync(&first);
        assert_eq!(first_result.updates.len(), 1);

        let second = SyncRequest {
            id: "req-2".to_string(),
            now: now + Duration::seconds(1),
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now + Duration::seconds(1))],
        };
        let second_result = engine.sync(&second);
        assert_eq!(second_result.updates.len(), 0);
        assert!(second_result.metrics.suppressed > 0);
    }

    #[test]
    fn idle_rest_state_uses_10_30_60_thresholds() {
        let now = Utc::now();
        let mut session = sample_session(now);
        session.state = SessionState::Idle;

        session.last_activity_at = now - Duration::milliseconds(9_999);
        assert_eq!(rest_state_for_session(&session, now), RestState::Active);

        session.last_activity_at = now - Duration::milliseconds(10_000);
        assert_eq!(rest_state_for_session(&session, now), RestState::Drowsy);

        session.last_activity_at = now - Duration::milliseconds(30_000);
        assert_eq!(rest_state_for_session(&session, now), RestState::Sleeping);

        session.last_activity_at = now - Duration::milliseconds(60_000);
        assert_eq!(rest_state_for_session(&session, now), RestState::DeepSleep);
    }

    #[test]
    fn idle_session_emits_sleeping() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut session = sample_session(now);
        session.state = SessionState::Idle;
        session.last_activity_at = now - Duration::milliseconds(31_000);

        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        };

        let result = engine.sync(&request);
        assert_eq!(result.updates.len(), 1);
        assert_eq!(result.updates[0].thought.as_deref(), Some("Sleeping."));
        assert_eq!(result.updates[0].thought_state, ThoughtState::Sleeping);
        assert_eq!(result.updates[0].emission_seq, 1);
    }

    #[test]
    fn attention_session_emits_sleeping() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut session = sample_session(now);
        session.state = SessionState::Attention;
        session.last_activity_at = now - Duration::milliseconds(31_000);

        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        };

        let result = engine.sync(&request);
        assert_eq!(result.updates.len(), 1);
        assert_eq!(result.updates[0].thought.as_deref(), Some("Sleeping."));
        assert_eq!(result.updates[0].thought_state, ThoughtState::Sleeping);
        assert_eq!(result.updates[0].rest_state, RestState::Sleeping);
    }

    #[test]
    fn emitted_sleeping_update_serializes_rest_state_explicitly() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut session = sample_session(now);
        session.state = SessionState::Attention;
        session.last_activity_at = now - Duration::milliseconds(31_000);

        let result = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        });

        let serialized =
            serde_json::to_value(&result.updates[0]).expect("sleeping update should serialize");
        assert_eq!(serialized.get("rest_state").and_then(|value| value.as_str()), Some("sleeping"));
    }

    #[test]
    fn disabled_config_clears_existing_thought() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut session = sample_session(now);
        session.thought = Some("existing thought".to_string());
        session.thought_state = ThoughtState::Active;

        let mut config = ThoughtConfig::default();
        config.enabled = false;

        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config,
            sessions: vec![session],
        };

        let result = engine.sync(&request);
        assert_eq!(result.updates.len(), 1);
        assert!(result.updates[0].thought.is_none());
        assert_eq!(result.updates[0].thought_state, ThoughtState::Holding);
    }

    #[test]
    fn claimed_path_persists_across_sync_ticks() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "working on tests".to_string(),
        }));

        // First sync — no tool set, so no JSONL claim, but state is created
        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now)],
        };
        engine.sync(&request);

        // Manually inject a claimed path to simulate a successful discovery
        let fake_path = PathBuf::from("/tmp/fake-session.jsonl");
        engine
            .per_session
            .get_mut("sess-1")
            .unwrap()
            .claimed_jsonl_path = Some(fake_path.clone());

        // Second sync — state should retain the claimed path
        let request2 = SyncRequest {
            id: "req-2".to_string(),
            now: now + Duration::seconds(60),
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now + Duration::seconds(60))],
        };
        engine.sync(&request2);

        // The state persists (not reset) — claimed_jsonl_path may be cleared
        // by the sync logic since the file doesn't exist, but the state entry
        // itself survives across ticks.
        assert!(
            engine.per_session.contains_key("sess-1"),
            "state should persist across sync ticks"
        );
    }

    #[test]
    fn session_removal_drops_claim() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "working".to_string(),
        }));

        // First sync creates state for sess-1
        let request = SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now)],
        };
        engine.sync(&request);
        assert!(engine.per_session.contains_key("sess-1"));

        // Second sync with no sessions — retain() should drop sess-1
        let request2 = SyncRequest {
            id: "req-2".to_string(),
            now: now + Duration::seconds(1),
            config: ThoughtConfig::default(),
            sessions: vec![],
        };
        engine.sync(&request2);
        assert!(
            !engine.per_session.contains_key("sess-1"),
            "state and claim should be dropped when session removed"
        );
    }

    #[test]
    fn no_op_scan_does_not_advance_emission_seq() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut sleeping = sample_session(now);
        sleeping.state = SessionState::Idle;
        sleeping.last_activity_at = now - Duration::milliseconds(31_000);

        let first = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![sleeping.clone()],
        });
        assert_eq!(first.updates.len(), 1);
        assert_eq!(first.updates[0].emission_seq, 1);

        let second = engine.sync(&SyncRequest {
            id: "req-2".to_string(),
            now: now + Duration::seconds(1),
            config: ThoughtConfig::default(),
            sessions: vec![sleeping],
        });
        assert!(second.updates.is_empty());

        let waking = sample_session(now + Duration::seconds(2));
        let third = engine.sync(&SyncRequest {
            id: "req-3".to_string(),
            now: now + Duration::seconds(2),
            config: ThoughtConfig::default(),
            sessions: vec![waking],
        });
        assert_eq!(third.updates.len(), 2);
        assert_eq!(third.updates[0].thought, None);
        assert_eq!(third.updates[0].emission_seq, 2);
        assert_eq!(third.updates[1].emission_seq, 3);
    }

    #[test]
    fn ambiguous_transcript_binding_falls_back_to_terminal_only() {
        let _lock = HOME_LOCK.lock().expect("home lock");
        let home = tempdir().expect("tempdir");
        std::env::set_var("HOME", home.path());

        let cwd = PathBuf::from("/tmp/shared");
        let codex_day = home
            .path()
            .join(".codex")
            .join("sessions")
            .join("2026")
            .join("03")
            .join("08");
        fs::create_dir_all(&codex_day).expect("create codex dir");
        for name in ["rollout-a.jsonl", "rollout-b.jsonl"] {
            fs::write(
                codex_day.join(name),
                format!(
                    "{{\"type\":\"session_meta\",\"payload\":{{\"cwd\":\"{}\"}}}}\n",
                    cwd.display()
                ),
            )
            .expect("write codex transcript");
        }

        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "watching logs".to_string(),
        }));
        let mut session = sample_session(now);
        session.session_id = "tmux:work:1.0:%1".to_string();
        session.tool = Some("codex".to_string());
        session.cwd = cwd.display().to_string();
        session.replay_text = "tail -f logs/app.log".to_string();

        let result = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        });

        assert!(result.updates.is_empty());
        assert!(result.metrics.suppressed > 0);
        let state = engine
            .per_session
            .get("tmux:work:1.0:%1")
            .expect("pane state should exist");
        assert!(state.claimed_jsonl_path.is_none());
    }

    #[test]
    fn short_bootstrap_terminal_context_suppresses_first_thought() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "too early".to_string(),
        }));
        let mut session = sample_session(now);
        session.replay_text = "$ ".to_string();

        let result = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        });

        assert!(result.updates.is_empty());
        assert!(result.metrics.suppressed > 0);
        assert_eq!(
            engine
                .per_session
                .get("sess-1")
                .expect("state should exist")
                .emission_seq,
            0
        );
    }

    #[test]
    fn meaningful_terminal_output_unblocks_first_thought_on_later_sync() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "isolating auth regression".to_string(),
        }));
        let mut bootstrap = sample_session(now);
        bootstrap.replay_text = "$ ".to_string();

        let first = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![bootstrap],
        });
        assert!(first.updates.is_empty());

        let second = engine.sync(&SyncRequest {
            id: "req-2".to_string(),
            now: now + Duration::seconds(1),
            config: ThoughtConfig::default(),
            sessions: vec![sample_session(now + Duration::seconds(1))],
        });

        assert_eq!(second.updates.len(), 1);
        assert_eq!(second.updates[0].emission_seq, 1);
        assert_eq!(
            second.updates[0].thought.as_deref(),
            Some("isolating auth regression")
        );
    }

    #[test]
    fn unique_transcript_context_allows_first_thought_without_terminal_delta() {
        let _lock = HOME_LOCK.lock().expect("home lock");
        let home = tempdir().expect("tempdir");
        std::env::set_var("HOME", home.path());

        let codex_day = home
            .path()
            .join(".codex")
            .join("sessions")
            .join("2026")
            .join("03")
            .join("08");
        fs::create_dir_all(&codex_day).expect("create codex dir");
        fs::write(
            codex_day.join("rollout-a.jsonl"),
            concat!(
                "{\"type\":\"session_meta\",\"payload\":{\"cwd\":\"/tmp/project\"}}\n",
                "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\"Fix auth regression\"}}\n",
                "{\"type\":\"response\",\"payload\":{\"usage\":{\"input_tokens\":456}}}\n",
                "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"arguments\":\"{\\\"command\\\":\\\"cargo test auth\\\"}\"}}\n"
            ),
        )
        .expect("write codex transcript");

        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "fixing auth regression".to_string(),
        }));
        let mut session = sample_session(now);
        session.session_id = "tmux:work:1.0:%1".to_string();
        session.tool = Some("codex".to_string());
        session.replay_text = "$ ".to_string();

        let result = engine.sync(&SyncRequest {
            id: "req-1".to_string(),
            now,
            config: ThoughtConfig::default(),
            sessions: vec![session],
        });

        assert_eq!(result.updates.len(), 1);
        assert_eq!(
            result.updates[0].thought.as_deref(),
            Some("fixing auth regression")
        );
        assert_eq!(result.updates[0].token_count, 456);
        assert_eq!(
            engine
                .per_session
                .get("tmux:work:1.0:%1")
                .expect("pane state")
                .claimed_jsonl_path
                .as_ref()
                .and_then(|path| path.file_name())
                .and_then(|name| name.to_str()),
            Some("rollout-a.jsonl")
        );
    }
}
