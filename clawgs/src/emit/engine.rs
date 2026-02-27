use std::collections::{hash_map::DefaultHasher, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::path::Path;

use chrono::{DateTime, Utc};

use crate::{extract, resolve_input, ExtractOptions, Snapshot, ToolSelection};

use super::model_client::ModelClient;
use super::protocol::{
    BubblePrecedence, SessionSnapshot, SessionState, SyncMetrics, SyncRequest, SyncResultMessage,
    ThoughtConfig, ThoughtSource, ThoughtState, ThoughtUpdate,
};

const SUMMARY_HISTORY_CAP: usize = 10;
const TERMINAL_CONTEXT_CHARS: usize = 800;
const TERMINAL_MIN_MEANINGFUL_DELTA_CHARS: usize = 100;
const MAX_THOUGHT_CHARS: usize = 120;
const STATIC_SLEEPING_THOUGHT: &str = "Sleeping.";
const SLEEPING_AFTER_MS: i64 = 60_000;

pub const DEFAULT_AGENT_PREAMBLE: &str =
    "You are a status reporter for a coding agent session.";
pub const DEFAULT_TERMINAL_PREAMBLE: &str = "Terminal session status reporter.";

struct SessionRuntimeState {
    summary_history: Vec<String>,
    last_terminal_context: Option<String>,
    last_call_at: Option<DateTime<Utc>>,
    last_emitted_thought: Option<String>,
    sleeping_emitted: bool,
    thought_state: ThoughtState,
    thought_source: ThoughtSource,
    objective_fingerprint: Option<String>,
    objective_stable_since: DateTime<Utc>,
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
            objective_fingerprint: session.objective_fingerprint.clone(),
            objective_stable_since: thought_updated_at,
        }
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
}

impl EmitEngine {
    pub fn new(model_client: Box<dyn ModelClient>) -> Self {
        Self {
            model_client,
            per_session: HashMap::new(),
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
            return SyncResultMessage::new(request.id.clone(), updates, metrics);
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

            if is_sleeping_session(session, request.now) {
                let should_emit_sleeping = state.thought_state != ThoughtState::Sleeping
                    || !state.sleeping_emitted
                    || !is_sleeping_text(state.last_emitted_thought.as_deref());

                if should_emit_sleeping {
                    let update = ThoughtUpdate {
                        session_id: session.session_id.clone(),
                        thought: Some(STATIC_SLEEPING_THOUGHT.to_string()),
                        token_count: session.token_count,
                        context_limit: session.context_limit,
                        thought_state: ThoughtState::Sleeping,
                        thought_source: ThoughtSource::StaticSleeping,
                        objective_changed: false,
                        bubble_precedence: BubblePrecedence::ThoughtFirst,
                        at: request.now,
                        objective_fingerprint: Some("sleeping".to_string()),
                    };
                    updates.push(update);
                } else {
                    metrics.suppressed += 1;
                }

                state.sleeping_emitted = true;
                state.thought_state = ThoughtState::Sleeping;
                state.thought_source = ThoughtSource::StaticSleeping;
                state.last_emitted_thought = Some(STATIC_SLEEPING_THOUGHT.to_string());
                state.last_call_at = Some(request.now);
                state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
                continue;
            }

            if state.thought_state == ThoughtState::Sleeping {
                updates.push(clear_thought_update(session, request.now));
                state.thought_state = ThoughtState::Holding;
                state.thought_source = ThoughtSource::CarryForward;
                state.sleeping_emitted = false;
                state.last_emitted_thought = None;
                state.last_call_at = Some(request.now);
            }

            let context_snapshot = context_snapshot_for_session(session);
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

            updates.push(ThoughtUpdate {
                session_id: session.session_id.clone(),
                thought: Some(thought.clone()),
                token_count,
                context_limit: session.context_limit,
                thought_state: next_state,
                thought_source: ThoughtSource::Llm,
                objective_changed,
                bubble_precedence: BubblePrecedence::ThoughtFirst,
                at: request.now,
                objective_fingerprint: Some(objective_fingerprint.clone()),
            });

            state.last_emitted_thought = Some(thought.clone());
            state.summary_history.push(thought);
            if state.summary_history.len() > SUMMARY_HISTORY_CAP {
                let start = state.summary_history.len() - SUMMARY_HISTORY_CAP;
                state.summary_history = state.summary_history.split_off(start);
            }
            state.thought_state = next_state;
            state.thought_source = ThoughtSource::Llm;
            state.sleeping_emitted = false;
            state.last_terminal_context = Some(trim_terminal_context(&session.replay_text));
            metrics.llm_calls += 1;
        }

        SyncResultMessage::new(request.id.clone(), updates, metrics)
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

            let needs_clear = state.last_emitted_thought.is_some()
                || session.thought.is_some()
                || state.thought_state != ThoughtState::Holding;

            if needs_clear {
                updates.push(clear_thought_update(session, request.now));
                state.last_emitted_thought = None;
                state.thought_state = ThoughtState::Holding;
                state.thought_source = ThoughtSource::CarryForward;
                state.sleeping_emitted = false;
                state.last_call_at = Some(request.now);
            } else {
                metrics.suppressed += 1;
            }
        }
    }
}

fn clear_thought_update(session: &SessionSnapshot, now: DateTime<Utc>) -> ThoughtUpdate {
    ThoughtUpdate {
        session_id: session.session_id.clone(),
        thought: None,
        token_count: session.token_count,
        context_limit: session.context_limit,
        thought_state: ThoughtState::Holding,
        thought_source: ThoughtSource::CarryForward,
        objective_changed: false,
        bubble_precedence: BubblePrecedence::ThoughtFirst,
        at: now,
        objective_fingerprint: None,
    }
}

fn is_sleeping_session(session: &SessionSnapshot, now: DateTime<Utc>) -> bool {
    if session.state != SessionState::Idle {
        return false;
    }
    let idle_ms = (now - session.last_activity_at).num_milliseconds().max(0);
    idle_ms >= SLEEPING_AFTER_MS
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

fn context_snapshot_for_session(session: &SessionSnapshot) -> Option<Snapshot> {
    let selection = tool_selection_for_session(session.tool.as_deref())?;
    let cwd = Path::new(&session.cwd);
    let resolved = resolve_input(selection, cwd, None).ok()?;
    let output = extract(
        resolved.tool,
        &resolved.path,
        cwd,
        resolved.discovered,
        &ExtractOptions::default(),
    )
    .ok()?;
    Some(output.snapshot)
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
    use chrono::Duration;

    use super::*;
    use crate::emit::model_client::ModelClient;
    use crate::emit::protocol::{SessionSnapshot, SessionState, SyncRequest, ThoughtConfig};

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
            replay_text: "cargo test --all".to_string(),
            thought: None,
            thought_state: ThoughtState::Holding,
            thought_source: ThoughtSource::CarryForward,
            objective_fingerprint: None,
            thought_updated_at: None,
            token_count: 1000,
            context_limit: 192_000,
            last_activity_at: now,
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
        assert_eq!(
            result.updates[0].thought.as_deref(),
            Some("investigating failing auth tests")
        );
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
    fn idle_session_emits_sleeping() {
        let now = Utc::now();
        let mut engine = EmitEngine::new(Box::new(MockModelClient {
            response: "unused".to_string(),
        }));

        let mut session = sample_session(now);
        session.state = SessionState::Idle;
        session.last_activity_at = now - Duration::milliseconds(61_000);

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
}
