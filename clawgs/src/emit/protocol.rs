use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThoughtConfig {
    pub enabled: bool,
    pub model: String,
    pub cadence_hot_ms: u64,
    pub cadence_warm_ms: u64,
    pub cadence_cold_ms: u64,
    pub agent_prompt: Option<String>,
    pub terminal_prompt: Option<String>,
}

impl Default for ThoughtConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            model: String::new(),
            cadence_hot_ms: 15_000,
            cadence_warm_ms: 45_000,
            cadence_cold_ms: 120_000,
            agent_prompt: None,
            terminal_prompt: None,
        }
    }
}

impl ThoughtConfig {
    pub fn validate(&self) -> Result<(), String> {
        validate_hot_cadence(self.cadence_hot_ms)?;
        validate_warm_cadence(self.cadence_hot_ms, self.cadence_warm_ms)?;
        validate_cold_cadence(self.cadence_warm_ms, self.cadence_cold_ms)?;
        validate_model_length(&self.model)?;
        validate_prompt_length(self.agent_prompt.as_deref(), "agent_prompt")?;
        validate_prompt_length(self.terminal_prompt.as_deref(), "terminal_prompt")?;
        Ok(())
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

fn validate_hot_cadence(cadence_hot_ms: u64) -> Result<(), String> {
    if !(5_000..=300_000).contains(&cadence_hot_ms) {
        Err("cadence_hot_ms must be between 5000 and 300000".to_string())
    } else {
        Ok(())
    }
}

fn validate_warm_cadence(cadence_hot_ms: u64, cadence_warm_ms: u64) -> Result<(), String> {
    if cadence_warm_ms < cadence_hot_ms || cadence_warm_ms > 600_000 {
        Err("cadence_warm_ms must be >= hot and <= 600000".to_string())
    } else {
        Ok(())
    }
}

fn validate_cold_cadence(cadence_warm_ms: u64, cadence_cold_ms: u64) -> Result<(), String> {
    if cadence_cold_ms < cadence_warm_ms || cadence_cold_ms > 1_800_000 {
        Err("cadence_cold_ms must be >= warm and <= 1800000".to_string())
    } else {
        Ok(())
    }
}

fn validate_model_length(model: &str) -> Result<(), String> {
    if model.chars().count() > 200 {
        Err("model must be <= 200 chars".to_string())
    } else {
        Ok(())
    }
}

fn validate_prompt_length(prompt: Option<&str>, field_name: &str) -> Result<(), String> {
    if prompt.is_some_and(|prompt| prompt.chars().count() > 4_000) {
        Err(format!("{field_name} must be <= 4000 chars"))
    } else {
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncRequest {
    pub id: String,
    pub now: DateTime<Utc>,
    pub config: ThoughtConfig,
    #[serde(default)]
    pub sessions: Vec<SessionSnapshot>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThoughtUpdate {
    pub session_id: String,
    pub stream_instance_id: String,
    pub emission_seq: u64,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub objective_fingerprint: Option<String>,
    #[serde(default)]
    pub rest_state: RestState,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SyncMetrics {
    pub sessions_seen: u64,
    pub llm_calls: u64,
    pub suppressed: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct HelloMessage {
    #[serde(rename = "type")]
    pub msg_type: &'static str,
    pub protocol: &'static str,
    pub engine_version: &'static str,
}

impl HelloMessage {
    pub fn new() -> Self {
        Self {
            msg_type: "hello",
            protocol: "clawgs.emit.v1",
            engine_version: env!("CARGO_PKG_VERSION"),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
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
            msg_type: "sync_result",
            id: id.into(),
            stream_instance_id: stream_instance_id.into(),
            updates,
            metrics,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
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

#[cfg(test)]
mod tests {
    use super::ThoughtConfig;

    #[test]
    fn config_validation_accepts_defaults() {
        let cfg = ThoughtConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn config_validation_rejects_bad_cadence_ordering() {
        let mut cfg = ThoughtConfig::default();
        cfg.cadence_warm_ms = 10_000;
        cfg.cadence_hot_ms = 20_000;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn config_validation_rejects_long_model() {
        let mut cfg = ThoughtConfig::default();
        cfg.model = "m".repeat(201);
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn config_validation_rejects_long_agent_prompt() {
        let mut cfg = ThoughtConfig::default();
        cfg.agent_prompt = Some("a".repeat(4_001));
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn config_validation_rejects_long_terminal_prompt() {
        let mut cfg = ThoughtConfig::default();
        cfg.terminal_prompt = Some("t".repeat(4_001));
        assert!(cfg.validate().is_err());
    }
}
