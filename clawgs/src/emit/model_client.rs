use std::time::Duration;

const CODEX_TIMEOUT: Duration = Duration::from_secs(15);

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

        let models = thought_models(model_override);
        let mut last_error = String::new();

        for model in &models {
            match call_openrouter(&self.client, prompt, model, &api_key) {
                Ok(content) if !content.is_empty() => return Ok(content),
                Ok(_) => {
                    last_error = format!("{model} returned empty");
                }
                Err(error) => {
                    last_error = format!("{model}: {error}");
                }
            }
        }

        Err(format!("all models failed, last: {last_error}"))
    }
}

pub fn thought_models(model_override: Option<&str>) -> Vec<String> {
    if let Some(model) = model_override {
        return vec![model.to_string()];
    }

    let mut models = Vec::new();
    for key in [
        "THRONGTERM_THOUGHT_MODEL",
        "THRONGTERM_THOUGHT_MODEL_2",
        "THRONGTERM_THOUGHT_MODEL_3",
    ] {
        if let Ok(model) = std::env::var(key) {
            if !model.trim().is_empty() {
                models.push(model);
            }
        }
    }

    if models.is_empty() {
        models.push("openrouter/aurora-alpha".to_string());
    }

    models
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

#[cfg(test)]
mod tests {
    use super::thought_models;

    #[test]
    fn thought_models_prefers_override() {
        let models = thought_models(Some("custom/model"));
        assert_eq!(models, vec!["custom/model".to_string()]);
    }
}
