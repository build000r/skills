use std::error::Error;
use std::fmt::{Display, Formatter};

use chrono::{DateTime, Utc};
use serde::ser::SerializeStruct;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

pub const HELLO_MESSAGE_TYPE: &str = "hello";
pub const SYNC_MESSAGE_TYPE: &str = "sync";
pub const SYNC_RESULT_MESSAGE_TYPE: &str = "sync_result";
pub const SYNC_RESPONSE_MESSAGE_TYPE: &str = SYNC_RESULT_MESSAGE_TYPE;
pub const EMIT_PROTOCOL_V1: &str = "clawgs.emit.v1";

pub const CADENCE_HOT_MIN_MS: u64 = 5_000;
pub const CADENCE_HOT_MAX_MS: u64 = 300_000;
pub const CADENCE_WARM_MAX_MS: u64 = 600_000;
pub const CADENCE_COLD_MAX_MS: u64 = 1_800_000;
pub const MODEL_MAX_CHARS: usize = 200;
pub const PROMPT_MAX_CHARS: usize = 4_000;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    Idle,
    Busy,
    Error,
    Attention,
    Exited,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ThoughtState {
    Active,
    Holding,
    Sleeping,
}

impl Default for ThoughtState {
    fn default() -> Self {
        Self::Holding
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ThoughtSource {
    CarryForward,
    Llm,
    StaticSleeping,
}

impl Default for ThoughtSource {
    fn default() -> Self {
        Self::CarryForward
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RestState {
    Active,
    Drowsy,
    Sleeping,
    DeepSleep,
}

impl Default for RestState {
    fn default() -> Self {
        Self::Active
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BubblePrecedence {
    ThoughtFirst,
}

impl Default for BubblePrecedence {
    fn default() -> Self {
        Self::ThoughtFirst
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ThoughtConfig {
    #[serde(default = "default_enabled")]
    pub enabled: bool,
    #[serde(default)]
    pub model: String,
    #[serde(default = "default_cadence_hot_ms")]
    pub cadence_hot_ms: u64,
    #[serde(default = "default_cadence_warm_ms")]
    pub cadence_warm_ms: u64,
    #[serde(default = "default_cadence_cold_ms")]
    pub cadence_cold_ms: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_prompt: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub terminal_prompt: Option<String>,
}

impl Default for ThoughtConfig {
    fn default() -> Self {
        Self {
            enabled: default_enabled(),
            model: String::new(),
            cadence_hot_ms: default_cadence_hot_ms(),
            cadence_warm_ms: default_cadence_warm_ms(),
            cadence_cold_ms: default_cadence_cold_ms(),
            agent_prompt: None,
            terminal_prompt: None,
        }
    }
}

impl ThoughtConfig {
    pub fn normalize(&mut self) {
        self.model = self.model.trim().to_string();
        self.agent_prompt = normalize_optional_prompt(self.agent_prompt.take());
        self.terminal_prompt = normalize_optional_prompt(self.terminal_prompt.take());
    }

    pub fn validate(&self) -> Result<(), ThoughtConfigValidationError> {
        if self.model.chars().count() > MODEL_MAX_CHARS {
            return Err(ThoughtConfigValidationError::new(
                "model",
                format!("must be <= {MODEL_MAX_CHARS} characters"),
            ));
        }

        if !(CADENCE_HOT_MIN_MS..=CADENCE_HOT_MAX_MS).contains(&self.cadence_hot_ms) {
            return Err(ThoughtConfigValidationError::new(
                "cadence_hot_ms",
                format!(
                    "must be between {CADENCE_HOT_MIN_MS} and {CADENCE_HOT_MAX_MS} (inclusive)"
                ),
            ));
        }

        if self.cadence_warm_ms < self.cadence_hot_ms || self.cadence_warm_ms > CADENCE_WARM_MAX_MS
        {
            return Err(ThoughtConfigValidationError::new(
                "cadence_warm_ms",
                format!(
                    "must be between cadence_hot_ms ({}) and {} (inclusive)",
                    self.cadence_hot_ms, CADENCE_WARM_MAX_MS
                ),
            ));
        }

        if self.cadence_cold_ms < self.cadence_warm_ms || self.cadence_cold_ms > CADENCE_COLD_MAX_MS
        {
            return Err(ThoughtConfigValidationError::new(
                "cadence_cold_ms",
                format!(
                    "must be between cadence_warm_ms ({}) and {} (inclusive)",
                    self.cadence_warm_ms, CADENCE_COLD_MAX_MS
                ),
            ));
        }

        validate_optional_len("agent_prompt", self.agent_prompt.as_deref())?;
        validate_optional_len("terminal_prompt", self.terminal_prompt.as_deref())?;

        Ok(())
    }

    pub fn normalize_and_validate(mut self) -> Result<Self, ThoughtConfigValidationError> {
        self.normalize();
        self.validate()?;
        Ok(self)
    }

    pub fn model_override(&self) -> Option<&str> {
        let trimmed = self.model.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed)
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThoughtConfigValidationError {
    pub field: &'static str,
    pub message: String,
}

impl ThoughtConfigValidationError {
    fn new(field: &'static str, message: String) -> Self {
        Self { field, message }
    }
}

impl Display for ThoughtConfigValidationError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} {}", self.field, self.message)
    }
}

impl Error for ThoughtConfigValidationError {}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SessionSnapshot {
    pub session_id: String,
    pub state: SessionState,
    pub exited: bool,
    pub tool: Option<String>,
    pub cwd: String,
    pub replay_text: String,
    pub thought: Option<String>,
    #[serde(default)]
    pub thought_state: ThoughtState,
    #[serde(default)]
    pub thought_source: ThoughtSource,
    pub objective_fingerprint: Option<String>,
    pub thought_updated_at: Option<DateTime<Utc>>,
    pub token_count: u64,
    pub context_limit: u64,
    pub last_activity_at: DateTime<Utc>,
    #[serde(default)]
    pub rest_state: RestState,
    #[serde(default)]
    pub commit_candidate: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SyncRequest {
    pub id: String,
    pub now: DateTime<Utc>,
    pub config: ThoughtConfig,
    pub sessions: Vec<SessionSnapshot>,
}

impl SyncRequest {
    pub fn new(
        id: impl Into<String>,
        now: DateTime<Utc>,
        config: ThoughtConfig,
        sessions: Vec<SessionSnapshot>,
    ) -> Self {
        Self {
            id: id.into(),
            now,
            config,
            sessions,
        }
    }

    pub fn with_generated_now(
        id: impl Into<String>,
        config: ThoughtConfig,
        sessions: Vec<SessionSnapshot>,
    ) -> Self {
        Self::new(id, Utc::now(), config, sessions)
    }
}

impl Serialize for SyncRequest {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut state = serializer.serialize_struct("SyncRequest", 5)?;
        state.serialize_field("type", SYNC_MESSAGE_TYPE)?;
        state.serialize_field("id", &self.id)?;
        state.serialize_field("now", &self.now)?;
        state.serialize_field("config", &SyncRequestConfigWireRef::from(&self.config))?;
        state.serialize_field("sessions", &self.sessions)?;
        state.end()
    }
}

impl<'de> Deserialize<'de> for SyncRequest {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = SyncRequestWire::deserialize(deserializer)?;
        Ok(Self {
            id: wire.id,
            now: wire.now,
            config: wire.config.into_runtime_config(),
            sessions: wire.sessions,
        })
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
struct SyncRequestWire {
    #[serde(default = "default_sync_message_type", rename = "type")]
    _message_type: String,
    id: String,
    now: DateTime<Utc>,
    config: SyncRequestConfigWire,
    #[serde(default)]
    sessions: Vec<SessionSnapshot>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
struct SyncRequestConfigWire {
    enabled: bool,
    model: String,
    cadence_hot_ms: u64,
    cadence_warm_ms: u64,
    cadence_cold_ms: u64,
    #[serde(default, deserialize_with = "deserialize_wire_prompt_string")]
    agent_prompt: String,
    #[serde(default, deserialize_with = "deserialize_wire_prompt_string")]
    terminal_prompt: String,
}

impl SyncRequestConfigWire {
    fn into_runtime_config(self) -> ThoughtConfig {
        let mut config = ThoughtConfig {
            enabled: self.enabled,
            model: self.model,
            cadence_hot_ms: self.cadence_hot_ms,
            cadence_warm_ms: self.cadence_warm_ms,
            cadence_cold_ms: self.cadence_cold_ms,
            agent_prompt: string_to_optional_prompt(self.agent_prompt),
            terminal_prompt: string_to_optional_prompt(self.terminal_prompt),
        };
        config.normalize();
        config
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
struct SyncRequestConfigWireRef<'a> {
    enabled: bool,
    model: &'a str,
    cadence_hot_ms: u64,
    cadence_warm_ms: u64,
    cadence_cold_ms: u64,
    agent_prompt: &'a str,
    terminal_prompt: &'a str,
}

impl<'a> From<&'a ThoughtConfig> for SyncRequestConfigWireRef<'a> {
    fn from(value: &'a ThoughtConfig) -> Self {
        Self {
            enabled: value.enabled,
            model: value.model.as_str(),
            cadence_hot_ms: value.cadence_hot_ms,
            cadence_warm_ms: value.cadence_warm_ms,
            cadence_cold_ms: value.cadence_cold_ms,
            agent_prompt: value.agent_prompt.as_deref().unwrap_or_default(),
            terminal_prompt: value.terminal_prompt.as_deref().unwrap_or_default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SyncUpdate {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stream_instance_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub emission_seq: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thought: Option<String>,
    pub token_count: u64,
    pub context_limit: u64,
    #[serde(default)]
    pub thought_state: ThoughtState,
    #[serde(default)]
    pub thought_source: ThoughtSource,
    #[serde(default)]
    pub objective_changed: bool,
    #[serde(default)]
    pub bubble_precedence: BubblePrecedence,
    pub at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub objective_fingerprint: Option<String>,
    #[serde(default)]
    pub rest_state: RestState,
    #[serde(default)]
    pub commit_candidate: bool,
}

pub type ThoughtUpdate = SyncUpdate;

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncMetrics {
    pub sessions_seen: u64,
    pub llm_calls: u64,
    pub suppressed: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HelloMessage {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub protocol: String,
    pub engine_version: String,
}

impl HelloMessage {
    pub fn new() -> Self {
        Self {
            msg_type: HELLO_MESSAGE_TYPE.to_string(),
            protocol: EMIT_PROTOCOL_V1.to_string(),
            engine_version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SyncResultMessage {
    #[serde(rename = "type")]
    pub msg_type: &'static str,
    pub id: String,
    pub stream_instance_id: String,
    pub updates: Vec<ThoughtUpdate>,
    pub metrics: SyncMetrics,
}

impl SyncResultMessage {
    pub fn new(
        id: impl Into<String>,
        stream_instance_id: impl Into<String>,
        updates: Vec<ThoughtUpdate>,
        metrics: SyncMetrics,
    ) -> Self {
        Self {
            msg_type: SYNC_RESULT_MESSAGE_TYPE,
            id: id.into(),
            stream_instance_id: stream_instance_id.into(),
            updates,
            metrics,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ErrorMessage {
    #[serde(rename = "type")]
    pub msg_type: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    pub code: String,
    pub message: String,
}

impl ErrorMessage {
    pub fn new(id: Option<String>, code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            msg_type: "error",
            id,
            code: code.into(),
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SyncResponse {
    pub request_id: String,
    pub stream_instance_id: Option<String>,
    pub updates: Vec<SyncUpdate>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(untagged)]
enum WireRequestId {
    Numeric(u64),
    Stringy(String),
}

fn parse_wire_request_id(value: WireRequestId) -> String {
    match value {
        WireRequestId::Numeric(v) => v.to_string(),
        WireRequestId::Stringy(v) => v,
    }
}

fn deserialize_request_id<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = WireRequestId::deserialize(deserializer)?;
    Ok(parse_wire_request_id(raw))
}

fn deserialize_optional_request_id<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<WireRequestId>::deserialize(deserializer)?;
    Ok(raw.map(parse_wire_request_id))
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum DaemonInboundMessage {
    Hello {
        protocol: String,
    },
    #[serde(rename = "sync_result", alias = "sync_response", alias = "sync")]
    SyncResponse {
        #[serde(
            rename = "id",
            alias = "request_id",
            deserialize_with = "deserialize_request_id"
        )]
        request_id: String,
        #[serde(default)]
        stream_instance_id: Option<String>,
        #[serde(default)]
        updates: Vec<SyncUpdate>,
    },
    Error {
        code: String,
        message: String,
        #[serde(
            default,
            rename = "id",
            alias = "request_id",
            deserialize_with = "deserialize_optional_request_id"
        )]
        request_id: Option<String>,
    },
}

impl DaemonInboundMessage {
    pub fn message_type(&self) -> &'static str {
        match self {
            Self::Hello { .. } => HELLO_MESSAGE_TYPE,
            Self::SyncResponse { .. } => SYNC_RESPONSE_MESSAGE_TYPE,
            Self::Error { .. } => "error",
        }
    }
}

fn validate_optional_len(
    field: &'static str,
    value: Option<&str>,
) -> Result<(), ThoughtConfigValidationError> {
    if value.map(|value| value.chars().count()).unwrap_or_default() > PROMPT_MAX_CHARS {
        return Err(ThoughtConfigValidationError::new(
            field,
            format!("must be <= {PROMPT_MAX_CHARS} characters"),
        ));
    }
    Ok(())
}

fn normalize_optional_prompt(value: Option<String>) -> Option<String> {
    match value {
        Some(value) if value.is_empty() => None,
        _ => value,
    }
}

fn string_to_optional_prompt(value: String) -> Option<String> {
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}

fn deserialize_wire_prompt_string<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(Option::<String>::deserialize(deserializer)?.unwrap_or_default())
}

fn default_sync_message_type() -> String {
    SYNC_MESSAGE_TYPE.to_string()
}

const fn default_enabled() -> bool {
    true
}

const fn default_cadence_hot_ms() -> u64 {
    15_000
}

const fn default_cadence_warm_ms() -> u64 {
    45_000
}

const fn default_cadence_cold_ms() -> u64 {
    120_000
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_session() -> SessionSnapshot {
        let now = Utc::now();
        SessionSnapshot {
            session_id: "sess-1".to_string(),
            state: SessionState::Busy,
            exited: false,
            tool: Some("Codex".to_string()),
            cwd: "/tmp".to_string(),
            replay_text: "cargo test".to_string(),
            thought: Some("Running tests".to_string()),
            thought_state: ThoughtState::Holding,
            thought_source: ThoughtSource::CarryForward,
            rest_state: RestState::Drowsy,
            objective_fingerprint: Some("obj-1".to_string()),
            thought_updated_at: Some(now),
            token_count: 12,
            context_limit: 100,
            last_activity_at: now,
            commit_candidate: false,
        }
    }

    #[test]
    fn config_validation_accepts_defaults() {
        let cfg = ThoughtConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn normalize_converts_empty_prompts_to_none() {
        let mut cfg = ThoughtConfig {
            agent_prompt: Some(String::new()),
            terminal_prompt: Some(String::new()),
            ..ThoughtConfig::default()
        };

        cfg.normalize();
        assert!(cfg.agent_prompt.is_none());
        assert!(cfg.terminal_prompt.is_none());
    }

    #[test]
    fn hot_cadence_must_be_in_range() {
        let mut cfg = ThoughtConfig::default();
        cfg.cadence_hot_ms = CADENCE_HOT_MIN_MS - 1;

        let err = cfg
            .validate()
            .expect_err("hot cadence below range should fail");
        assert_eq!(err.field, "cadence_hot_ms");
    }

    #[test]
    fn warm_cadence_must_be_at_least_hot() {
        let mut cfg = ThoughtConfig::default();
        cfg.cadence_hot_ms = 10_000;
        cfg.cadence_warm_ms = 9_999;

        let err = cfg
            .validate()
            .expect_err("warm cadence below hot cadence should fail");
        assert_eq!(err.field, "cadence_warm_ms");
    }

    #[test]
    fn cold_cadence_must_be_at_least_warm() {
        let mut cfg = ThoughtConfig::default();
        cfg.cadence_warm_ms = 50_000;
        cfg.cadence_cold_ms = 49_000;

        let err = cfg
            .validate()
            .expect_err("cold cadence below warm cadence should fail");
        assert_eq!(err.field, "cadence_cold_ms");
    }

    #[test]
    fn sync_request_serializes_expected_wire_shape() {
        let request =
            SyncRequest::with_generated_now("7", ThoughtConfig::default(), vec![sample_session()]);
        let json = serde_json::to_value(&request).expect("request should serialize");

        assert_eq!(json["type"], SYNC_MESSAGE_TYPE);
        assert_eq!(json["id"], "7");
        assert!(chrono::DateTime::parse_from_rfc3339(
            json["now"]
                .as_str()
                .expect("now should be an RFC3339 string")
        )
        .is_ok());
        assert_eq!(json["config"]["enabled"], true);
        assert_eq!(json["config"]["model"], "");
        assert_eq!(json["config"]["cadence_hot_ms"], 15_000);
        assert_eq!(json["config"]["cadence_warm_ms"], 45_000);
        assert_eq!(json["config"]["cadence_cold_ms"], 120_000);
        assert_eq!(json["config"]["agent_prompt"], "");
        assert_eq!(json["config"]["terminal_prompt"], "");
        assert_eq!(json["sessions"].as_array().map(|v| v.len()), Some(1));
        assert_eq!(json["sessions"][0]["session_id"], "sess-1");
        assert_eq!(json["sessions"][0]["state"], "busy");
    }

    #[test]
    fn sync_request_deserializes_null_prompt_fields_to_none() {
        let raw = serde_json::json!({
            "type": "sync",
            "id": "req-1",
            "now": "2026-02-26T21:00:00Z",
            "config": {
                "enabled": true,
                "model": "",
                "cadence_hot_ms": 15000,
                "cadence_warm_ms": 45000,
                "cadence_cold_ms": 120000,
                "agent_prompt": null,
                "terminal_prompt": null
            },
            "sessions": []
        })
        .to_string();

        let request: SyncRequest = serde_json::from_str(&raw).expect("sync request should parse");
        assert_eq!(request.id, "req-1");
        assert!(request.config.agent_prompt.is_none());
        assert!(request.config.terminal_prompt.is_none());
    }

    #[test]
    fn inbound_message_deserializes_legacy_sync_response_alias() {
        let raw = r#"{
            "type": "sync_response",
            "request_id": 17,
            "updates": []
        }"#;
        let message: DaemonInboundMessage =
            serde_json::from_str(raw).expect("legacy sync_response alias should deserialize");

        match message {
            DaemonInboundMessage::SyncResponse {
                request_id,
                stream_instance_id,
                updates,
            } => {
                assert_eq!(request_id, "17");
                assert_eq!(stream_instance_id.as_deref(), None);
                assert!(updates.is_empty());
                assert_eq!(SYNC_RESPONSE_MESSAGE_TYPE, "sync_result");
            }
            other => panic!("unexpected message variant: {other:?}"),
        }
    }

    #[test]
    fn hello_roundtrip_is_stable() {
        let hello = HelloMessage::new();
        let encoded = serde_json::to_string(&hello).expect("hello should serialize");
        let decoded: HelloMessage = serde_json::from_str(&encoded).expect("hello should parse");
        assert_eq!(decoded, hello);
    }
}
