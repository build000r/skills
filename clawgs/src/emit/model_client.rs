use std::time::Duration;

const CODEX_TIMEOUT: Duration = Duration::from_secs(15);
const DEFAULT_THOUGHT_MODEL: &str = "openrouter/aurora-alpha";
const MODEL_ENV_KEYS: [&str; 3] = [
    "THRONGTERM_THOUGHT_MODEL",
    "THRONGTERM_THOUGHT_MODEL_2",
    "THRONGTERM_THOUGHT_MODEL_3",
];

pub trait ModelClient: Send + Sync {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String>;
}

pub struct OpenRouterModelClient {
    client: reqwest::blocking::Client,
}

impl OpenRouterModelClient {
    pub fn new() -> Result<Self, String> {
        let client = reqwest::blocking::Client::builder()
            .timeout(CODEX_TIMEOUT)
            .build()
            .map_err(|error| format!("failed to build HTTP client: {error}"))?;
        Ok(Self { client })
    }
}

impl ModelClient for OpenRouterModelClient {
    fn complete(&self, prompt: &str, model_override: Option<&str>) -> Result<String, String> {
        let api_key = std::env::var("OPENROUTER_API_KEY")
            .map_err(|_| "OPENROUTER_API_KEY not set".to_string())?;
        complete_with_models(&thought_models(model_override), |model| {
            nonempty_openrouter_response(&self.client, prompt, model, &api_key)
        })
    }
}

pub fn thought_models(model_override: Option<&str>) -> Vec<String> {
    model_override
        .map(|model| vec![model.to_string()])
        .unwrap_or_else(default_thought_models)
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

fn default_thought_models() -> Vec<String> {
    let models: Vec<String> = MODEL_ENV_KEYS.iter().filter_map(nonempty_env_var).collect();
    if models.is_empty() {
        vec![DEFAULT_THOUGHT_MODEL.to_string()]
    } else {
        models
    }
}

fn nonempty_env_var(key: &&str) -> Option<String> {
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
    use std::sync::Mutex;

    use super::thought_models;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn thought_models_prefers_override() {
        let models = thought_models(Some("custom/model"));
        assert_eq!(models, vec!["custom/model".to_string()]);
    }

    #[test]
    fn thought_models_collects_nonempty_env_overrides_in_order() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::set_var("THRONGTERM_THOUGHT_MODEL", "openrouter/one");
        std::env::set_var("THRONGTERM_THOUGHT_MODEL_2", "   ");
        std::env::set_var("THRONGTERM_THOUGHT_MODEL_3", "openrouter/three");

        let models = thought_models(None);

        assert_eq!(
            models,
            vec!["openrouter/one".to_string(), "openrouter/three".to_string()]
        );

        std::env::remove_var("THRONGTERM_THOUGHT_MODEL");
        std::env::remove_var("THRONGTERM_THOUGHT_MODEL_2");
        std::env::remove_var("THRONGTERM_THOUGHT_MODEL_3");
    }

    #[test]
    fn thought_models_falls_back_to_default_model() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        std::env::remove_var("THRONGTERM_THOUGHT_MODEL");
        std::env::remove_var("THRONGTERM_THOUGHT_MODEL_2");
        std::env::remove_var("THRONGTERM_THOUGHT_MODEL_3");

        let models = thought_models(None);

        assert_eq!(models, vec!["openrouter/aurora-alpha".to_string()]);
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
}
