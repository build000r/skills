use std::ffi::OsString;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const OPENROUTER_TIMEOUT: Duration = Duration::from_secs(15);
const CODEX_EXEC_TIMEOUT: Duration = Duration::from_secs(30);
const CLAUDE_CLI_TIMEOUT: Duration = Duration::from_secs(30);
const DEFAULT_CODEX_CLI_MODEL: &str = "gpt-5.1-codex-mini";
const DEFAULT_CODEX_CLI_REASONING: &str = "low";
const DEFAULT_CODEX_CLI_VERBOSITY: &str = "low";
const DEFAULT_CLAUDE_CLI_MODEL: &str = "haiku";
const DEFAULT_CLAUDE_CLI_MAX_BUDGET: &str = "0.02";
const MODEL_BACKEND_ENV: &str = "CLAWGS_MODEL_BACKEND";
const CODEX_BIN_ENV: &str = "CLAWGS_CODEX_BIN";
const CODEX_REASONING_ENV: &str = "CLAWGS_CODEX_REASONING_EFFORT";
const CODEX_VERBOSITY_ENV: &str = "CLAWGS_CODEX_VERBOSITY";
const CODEX_WORKDIR_ENV: &str = "CLAWGS_CODEX_WORKDIR";
const CODEX_RUNTIME_DIR: &str = "clawgs-codex-exec";
const CLAUDE_BIN_ENV: &str = "CLAWGS_CLAUDE_BIN";
const CLAUDE_MAX_BUDGET_ENV: &str = "CLAWGS_CLAUDE_MAX_BUDGET";
const MODEL_ENV_KEYS: [&str; 3] = [
    "SWIMMERS_THOUGHT_MODEL",
    "SWIMMERS_THOUGHT_MODEL_2",
    "SWIMMERS_THOUGHT_MODEL_3",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ModelBackend {
    OpenRouter,
    CodexCli,
    ClaudeCli,
}

impl ModelBackend {
    pub fn from_env_value(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "openrouter" => Some(Self::OpenRouter),
            "codex" | "codex_cli" | "codex-cli" => Some(Self::CodexCli),
            "claude" | "claude_cli" | "claude-cli" => Some(Self::ClaudeCli),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::OpenRouter => "openrouter",
            Self::CodexCli => "codex",
            Self::ClaudeCli => "claude",
        }
    }
}

pub trait ModelClient: Send + Sync {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String>;
}

pub fn build_model_client() -> Result<Box<dyn ModelClient>, String> {
    build_model_client_for(resolve_model_backend())
}

pub fn build_model_client_for(backend: ModelBackend) -> Result<Box<dyn ModelClient>, String> {
    match backend {
        ModelBackend::OpenRouter => {
            OpenRouterModelClient::new().map(|client| Box::new(client) as Box<dyn ModelClient>)
        }
        ModelBackend::CodexCli => Ok(Box::new(CodexCliModelClient::new())),
        ModelBackend::ClaudeCli => Ok(Box::new(ClaudeCliModelClient::new())),
    }
}

pub fn validate_backend_credentials(backend: ModelBackend) -> Result<(), String> {
    match backend {
        ModelBackend::OpenRouter => {
            if nonempty_env_var("OPENROUTER_API_KEY").is_none() {
                return Err(format!("{}: OPENROUTER_API_KEY not set", backend.as_str()));
            }
            Ok(())
        }
        ModelBackend::CodexCli => {
            if !codex_command_available() {
                return Err(format!("{}: codex binary not found", backend.as_str()));
            }
            Ok(())
        }
        ModelBackend::ClaudeCli => {
            if !claude_command_available() {
                return Err(format!("{}: claude binary not found", backend.as_str()));
            }
            Ok(())
        }
    }
}

pub fn resolve_model_backend() -> ModelBackend {
    nonempty_env_var(MODEL_BACKEND_ENV)
        .and_then(|value| ModelBackend::from_env_value(&value))
        .unwrap_or_else(auto_detect_model_backend)
}

pub fn default_model_for_backend(backend: ModelBackend) -> String {
    thought_models(None, backend).into_iter().next().unwrap_or_default()
}

pub fn thought_models(model_override: Option<&str>, backend: ModelBackend) -> Vec<String> {
    candidate_models(model_override, backend)
}

pub struct OpenRouterModelClient {
    client: reqwest::blocking::Client,
}

impl OpenRouterModelClient {
    pub fn new() -> Result<Self, String> {
        let client = reqwest::blocking::Client::builder()
            .timeout(OPENROUTER_TIMEOUT)
            .build()
            .map_err(|error| format!("failed to build HTTP client: {error}"))?;
        Ok(Self { client })
    }
}

impl ModelClient for OpenRouterModelClient {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String> {
        let api_key = std::env::var("OPENROUTER_API_KEY")
            .map_err(|_| "OPENROUTER_API_KEY not set".to_string())?;
        complete_with_models(&candidate_models(model_override, ModelBackend::OpenRouter), |model| {
            nonempty_openrouter_response(&self.client, prompt, model, &api_key)
        })
    }
}

pub struct CodexCliModelClient {
    bin: String,
    runtime_dir: PathBuf,
    workdir: PathBuf,
    reasoning_effort: String,
    verbosity: String,
}

impl CodexCliModelClient {
    pub fn new() -> Self {
        Self {
            bin: codex_bin(),
            runtime_dir: std::env::temp_dir().join(CODEX_RUNTIME_DIR),
            workdir: nonempty_env_var(CODEX_WORKDIR_ENV)
                .map(PathBuf::from)
                .unwrap_or_else(std::env::temp_dir),
            reasoning_effort: nonempty_env_var(CODEX_REASONING_ENV)
                .unwrap_or_else(|| DEFAULT_CODEX_CLI_REASONING.to_string()),
            verbosity: nonempty_env_var(CODEX_VERBOSITY_ENV)
                .unwrap_or_else(|| DEFAULT_CODEX_CLI_VERBOSITY.to_string()),
        }
    }
}

impl ModelClient for CodexCliModelClient {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String> {
        let model = candidate_models(model_override, ModelBackend::CodexCli)
            .into_iter()
            .next()
            .ok_or_else(|| "no models configured".to_string())?;

        fs::create_dir_all(&self.runtime_dir)
            .map_err(|error| format!("failed to create {}: {error}", self.runtime_dir.display()))?;

        let stamp = format!(
            "{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        let output_path = self.runtime_dir.join(format!("{stamp}.last.txt"));
        let stdout_path = self.runtime_dir.join(format!("{stamp}.stdout.log"));
        let stderr_path = self.runtime_dir.join(format!("{stamp}.stderr.log"));

        let stdout_file = File::create(&stdout_path)
            .map_err(|error| format!("failed to create {}: {error}", stdout_path.display()))?;
        let stderr_file = File::create(&stderr_path)
            .map_err(|error| format!("failed to create {}: {error}", stderr_path.display()))?;

        let mut command = Command::new(&self.bin);
        command.args(build_codex_exec_args(
            &model,
            &output_path,
            &self.workdir,
            &self.reasoning_effort,
            &self.verbosity,
        ));
        command.stdin(Stdio::piped());
        command.stdout(Stdio::from(stdout_file));
        command.stderr(Stdio::from(stderr_file));

        let mut child = command
            .spawn()
            .map_err(|error| format!("failed to spawn codex exec: {error}"))?;

        {
            let Some(stdin) = child.stdin.as_mut() else {
                return Err("codex exec missing stdin pipe".to_string());
            };
            stdin
                .write_all(prompt.as_bytes())
                .map_err(|error| format!("failed to write codex exec prompt: {error}"))?;
        }
        drop(child.stdin.take());

        let started = Instant::now();
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if started.elapsed() < CODEX_EXEC_TIMEOUT => {
                    thread::sleep(Duration::from_millis(50));
                }
                Ok(None) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(format!(
                        "codex exec timed out after {}s",
                        CODEX_EXEC_TIMEOUT.as_secs()
                    ));
                }
                Err(error) => {
                    return Err(format!("failed to wait for codex exec: {error}"));
                }
            }
        };

        let stdout = fs::read_to_string(&stdout_path).unwrap_or_default();
        let stderr = fs::read_to_string(&stderr_path).unwrap_or_default();
        if !status.success() {
            return Err(format!(
                "codex exec failed: {}",
                failure_preview(&stderr, &stdout)
            ));
        }

        let content = fs::read_to_string(&output_path).map_err(|error| {
            format!(
                "codex exec succeeded but {} was missing: {error}",
                output_path.display()
            )
        })?;
        let trimmed = content.trim();
        if trimmed.is_empty() {
            return Err("codex exec returned an empty final message".to_string());
        }
        Ok(trimmed.to_string())
    }
}

pub struct ClaudeCliModelClient {
    bin: String,
    max_budget: String,
}

impl ClaudeCliModelClient {
    pub fn new() -> Self {
        Self {
            bin: claude_bin(),
            max_budget: nonempty_env_var(CLAUDE_MAX_BUDGET_ENV)
                .unwrap_or_else(|| DEFAULT_CLAUDE_CLI_MAX_BUDGET.to_string()),
        }
    }
}

impl ModelClient for ClaudeCliModelClient {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String> {
        let model = model_override
            .map(|m| m.to_string())
            .or_else(|| {
                candidate_models(None, ModelBackend::ClaudeCli)
                    .into_iter()
                    .next()
            })
            .unwrap_or_else(|| DEFAULT_CLAUDE_CLI_MODEL.to_string());

        let mut command = Command::new(&self.bin);
        command.args([
            "--print",
            "--model",
            &model,
            "--bare",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--max-budget-usd",
            &self.max_budget,
        ]);
        command.stdin(Stdio::piped());
        command.stdout(Stdio::piped());
        command.stderr(Stdio::piped());

        let mut child = command
            .spawn()
            .map_err(|error| format!("failed to spawn claude: {error}"))?;

        {
            let Some(stdin) = child.stdin.as_mut() else {
                return Err("claude missing stdin pipe".to_string());
            };
            stdin
                .write_all(prompt.as_bytes())
                .map_err(|error| format!("failed to write claude prompt: {error}"))?;
        }
        drop(child.stdin.take());

        let started = Instant::now();
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if started.elapsed() < CLAUDE_CLI_TIMEOUT => {
                    thread::sleep(Duration::from_millis(50));
                }
                Ok(None) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(format!(
                        "claude exec timed out after {}s",
                        CLAUDE_CLI_TIMEOUT.as_secs()
                    ));
                }
                Err(error) => {
                    return Err(format!("failed to wait for claude: {error}"));
                }
            }
        };

        let stdout = child
            .stdout
            .take()
            .map(|mut out| {
                let mut buf = String::new();
                use std::io::Read;
                let _ = out.read_to_string(&mut buf);
                buf
            })
            .unwrap_or_default();
        let stderr = child
            .stderr
            .take()
            .map(|mut err| {
                let mut buf = String::new();
                use std::io::Read;
                let _ = err.read_to_string(&mut buf);
                buf
            })
            .unwrap_or_default();

        if !status.success() {
            return Err(format!(
                "claude exec failed: {}",
                failure_preview(&stderr, &stdout)
            ));
        }

        let trimmed = stdout.trim();
        if trimmed.is_empty() {
            return Err("claude exec returned empty output".to_string());
        }
        Ok(trimmed.to_string())
    }
}

fn auto_detect_model_backend() -> ModelBackend {
    if nonempty_env_var("OPENROUTER_API_KEY").is_some() {
        ModelBackend::OpenRouter
    } else if claude_command_available() {
        ModelBackend::ClaudeCli
    } else if codex_command_available() {
        ModelBackend::CodexCli
    } else {
        ModelBackend::OpenRouter
    }
}

fn codex_command_available() -> bool {
    Command::new(codex_bin())
        .arg("--version")
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false)
}

fn claude_command_available() -> bool {
    Command::new(claude_bin())
        .arg("--version")
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false)
}

fn codex_bin() -> String {
    nonempty_env_var(CODEX_BIN_ENV).unwrap_or_else(|| "codex".to_string())
}

fn claude_bin() -> String {
    nonempty_env_var(CLAUDE_BIN_ENV).unwrap_or_else(|| "claude".to_string())
}

fn candidate_models(model_override: Option<&str>, backend: ModelBackend) -> Vec<String> {
    model_override
        .map(|model| vec![model.to_string()])
        .unwrap_or_else(|| configured_models(backend))
}

fn configured_models(backend: ModelBackend) -> Vec<String> {
    let configured: Vec<String> = MODEL_ENV_KEYS.iter().filter_map(|key| nonempty_env_var(key)).collect();
    if !configured.is_empty() {
        configured
    } else {
        backend_default_model(backend)
            .map(|model| vec![model.to_string()])
            .unwrap_or_default()
    }
}

fn backend_default_model(backend: ModelBackend) -> Option<&'static str> {
    match backend {
        ModelBackend::OpenRouter => None,
        ModelBackend::CodexCli => Some(DEFAULT_CODEX_CLI_MODEL),
        ModelBackend::ClaudeCli => Some(DEFAULT_CLAUDE_CLI_MODEL),
    }
}

fn build_codex_exec_args(
    model: &str,
    output_path: &Path,
    workdir: &Path,
    reasoning_effort: &str,
    verbosity: &str,
) -> Vec<OsString> {
    vec![
        OsString::from("exec"),
        OsString::from("-m"),
        OsString::from(model),
        OsString::from("-C"),
        workdir.as_os_str().to_os_string(),
        OsString::from("--skip-git-repo-check"),
        OsString::from("--ephemeral"),
        OsString::from("--output-last-message"),
        output_path.as_os_str().to_os_string(),
        OsString::from("-c"),
        OsString::from(format!("model_reasoning_effort={reasoning_effort:?}")),
        OsString::from("-c"),
        OsString::from(format!("model_verbosity={verbosity:?}")),
        OsString::from("-c"),
        OsString::from("model_reasoning_summary=\"none\""),
        OsString::from("-"),
    ]
}

fn failure_preview(stderr: &str, stdout: &str) -> String {
    let merged = if stderr.trim().is_empty() { stdout } else { stderr };
    let trimmed = merged.trim();
    if trimmed.is_empty() {
        "process exited without output".to_string()
    } else {
        trimmed.chars().take(500).collect()
    }
}

fn call_openrouter(
    client: &reqwest::blocking::Client,
    prompt: &str,
    model: &str,
    api_key: &str,
) -> Result<String, String> {
    let body = serde_json::json!({
        "model": model,
        "max_tokens": 80,
        "messages": [
            { "role": "user", "content": prompt }
        ]
    });

    let response = client
        .post("https://openrouter.ai/api/v1/chat/completions")
        .header("Authorization", format!("Bearer {api_key}"))
        .json(&body)
        .send()
        .map_err(|error| format!("request failed: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let preview: String = response
            .text()
            .unwrap_or_default()
            .chars()
            .take(500)
            .collect();
        return Err(format!("{status}: {preview}"));
    }

    let body: serde_json::Value = response
        .json()
        .map_err(|error| format!("json parse failed: {error}"))?;

    Ok(body["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .trim()
        .to_string())
}

fn nonempty_env_var(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn complete_with_models<F>(models: &[String], mut attempt: F) -> Result<String, String>
where
    F: FnMut(&str) -> Result<String, String>,
{
    let mut last_error = "no models configured".to_string();
    models
        .iter()
        .find_map(|model| match attempt(model) {
            Ok(content) => Some(Ok(content)),
            Err(error) => {
                last_error = format!("{model}: {error}");
                None
            }
        })
        .map_or(
            Err(format!("all models failed, last: {last_error}")),
            |result| result,
        )
}

fn nonempty_openrouter_response(
    client: &reqwest::blocking::Client,
    prompt: &str,
    model: &str,
    api_key: &str,
) -> Result<String, String> {
    let content = call_openrouter(client, prompt, model, api_key)?;
    if content.is_empty() {
        Err("returned empty".to_string())
    } else {
        Ok(content)
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use std::sync::Mutex;

    use super::{
        build_codex_exec_args, default_model_for_backend, thought_models,
        validate_backend_credentials, ModelBackend,
    };

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn thought_models_prefers_override() {
        let models = thought_models(Some("custom/model"), ModelBackend::CodexCli);
        assert_eq!(models, vec!["custom/model".to_string()]);
    }

    #[test]
    fn thought_models_collects_nonempty_env_overrides_in_order() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::set_var("SWIMMERS_THOUGHT_MODEL", "openrouter/one");
        std::env::set_var("SWIMMERS_THOUGHT_MODEL_2", "   ");
        std::env::set_var("SWIMMERS_THOUGHT_MODEL_3", "openrouter/three");

        let models = thought_models(None, ModelBackend::OpenRouter);

        assert_eq!(
            models,
            vec!["openrouter/one".to_string(), "openrouter/three".to_string()]
        );

        std::env::remove_var("SWIMMERS_THOUGHT_MODEL");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_2");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_3");
    }

    #[test]
    fn codex_backend_falls_back_to_headless_codex_default_model() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_2");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_3");

        let model = default_model_for_backend(ModelBackend::CodexCli);

        assert_eq!(model, "gpt-5.1-codex-mini");
    }

    #[test]
    fn complete_with_models_returns_first_successful_result() {
        let models = vec!["first".to_string(), "second".to_string()];
        let result = super::complete_with_models(&models, |model| {
            if model == "first" {
                Err("boom".to_string())
            } else {
                Ok("done".to_string())
            }
        });

        assert_eq!(result.expect("successful fallback"), "done");
    }

    #[test]
    fn complete_with_models_reports_last_error() {
        let models = vec!["alpha".to_string(), "beta".to_string()];
        let error = super::complete_with_models(&models, |model| Err(format!("{model} failed")))
            .expect_err("expected failure");

        assert!(error.contains("beta: beta failed"));
    }

    #[test]
    fn build_codex_exec_args_pins_low_reasoning_and_low_verbosity() {
        let args = build_codex_exec_args(
            "gpt-5.1-codex-mini",
            Path::new("/tmp/last.txt"),
            Path::new("/tmp"),
            "low",
            "low",
        );
        let args: Vec<String> = args
            .into_iter()
            .map(|value| value.to_string_lossy().into_owned())
            .collect();

        assert!(args.contains(&"exec".to_string()));
        assert!(args.contains(&"gpt-5.1-codex-mini".to_string()));
        assert!(args.contains(&"model_reasoning_effort=\"low\"".to_string()));
        assert!(args.contains(&"model_verbosity=\"low\"".to_string()));
        assert!(args.contains(&"model_reasoning_summary=\"none\"".to_string()));
        assert!(args.contains(&"--ephemeral".to_string()));
    }

    #[test]
    fn claude_backend_falls_back_to_haiku_default_model() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_2");
        std::env::remove_var("SWIMMERS_THOUGHT_MODEL_3");

        let model = default_model_for_backend(ModelBackend::ClaudeCli);

        assert_eq!(model, "haiku");
    }

    #[test]
    fn model_backend_from_env_value_parses_claude_variants() {
        assert_eq!(
            ModelBackend::from_env_value("claude"),
            Some(ModelBackend::ClaudeCli)
        );
        assert_eq!(
            ModelBackend::from_env_value("claude_cli"),
            Some(ModelBackend::ClaudeCli)
        );
        assert_eq!(
            ModelBackend::from_env_value("claude-cli"),
            Some(ModelBackend::ClaudeCli)
        );
        assert_eq!(
            ModelBackend::from_env_value("CLAUDE"),
            Some(ModelBackend::ClaudeCli)
        );
    }

    #[test]
    fn model_backend_from_env_value_rejects_unknown() {
        assert_eq!(ModelBackend::from_env_value("gemini"), None);
        assert_eq!(ModelBackend::from_env_value(""), None);
    }

    #[test]
    fn model_backend_as_str_roundtrips() {
        assert_eq!(ModelBackend::OpenRouter.as_str(), "openrouter");
        assert_eq!(ModelBackend::CodexCli.as_str(), "codex");
        assert_eq!(ModelBackend::ClaudeCli.as_str(), "claude");
    }

    #[test]
    fn validate_backend_credentials_rejects_missing_openrouter_key() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::remove_var("OPENROUTER_API_KEY");

        let err = validate_backend_credentials(ModelBackend::OpenRouter)
            .expect_err("should fail without API key");
        assert!(err.starts_with("openrouter:"));
        assert!(err.contains("OPENROUTER_API_KEY"));
    }
}
