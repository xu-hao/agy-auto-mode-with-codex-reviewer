//! Review-only host for the pinned Codex Guardian components (Apache-2.0).
//! Deliberately has no tool dispatcher, shell, terminal, or action execution path.
use std::{io::{self, BufRead, Write}, path::PathBuf, sync::Arc, time::Duration};
use anyhow::{Context, Result, bail};
use codex_analytics::GuardianReviewAnalyticsResult;
use codex_api::{ResponseEvent, ResponsesClient};
use codex_client::ReqwestTransport;
use codex_context_fragments::ContextualUserFragment;
use codex_guardian_context::{self as ctx, ContextPresentation, ContextProfile, HistoryTruncation, PlannedAction, PlannedActionKind, RequestBudget, SectionInput, TranscriptFormat};
use codex_guardian_reviewer::{self as guardian, GuardianReviewError, GuardianReviewOutcome, ReviewDeadline};
use codex_http_client::{ClientRouteClass, HttpClientFactory, HttpClientBuilder, OutboundProxyPolicy};
use codex_login::{AuthManager, AuthRouteConfig};
use codex_model_provider::{create_model_provider, SharedModelProvider, WorkspaceRoutingContext};
use codex_model_provider_info::ModelProviderInfo;
use codex_models_manager::{ModelsManagerConfig, manager::RefreshStrategy};
use codex_prompts::{GuardianPolicyInstructions, ResolvedModelMessages};
use codex_protocol::{models::ResponseItem, openai_models::{ModelInfo, ModelsResponse}, protocol::GuardianAssessmentOutcome};
use futures::StreamExt;
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize, Default)]
#[serde(default, deny_unknown_fields)]
struct Config {
    codex_home: Option<PathBuf>,
    provider: Option<ModelProviderInfo>,
    model: Option<String>,
    parent_model: Option<String>,
    policy: Option<String>,
    model_catalog: Option<ModelsResponse>,
    timeout_ms: Option<u64>,
    max_input_tokens: Option<usize>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Message {
    role: String,
    content: String,
    provenance: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    request_id: String,
    session_id: String,
    action: Value,
    cwd: String,
    environment: Value,
    original_user_request: String,
    history: Vec<Message>,
    permissions: Value,
    evidence: Value,
    binding: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    config: Config,
    request: Option<Request>,
    mode: String,
}

struct Backend {
    provider: SharedModelProvider,
    factory: HttpClientFactory,
    model: ModelInfo,
    selection: guardian::ReviewModel,
    auth_mode: String,
}

async fn backend(config: &Config) -> Result<Backend> {
    let factory = HttpClientFactory::new(OutboundProxyPolicy::RespectSystemProxy);
    let home = config.codex_home.clone().or_else(|| std::env::var_os("CODEX_HOME").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".codex"));
    let auth = Arc::new(AuthManager::new(home.clone(), true, Default::default(), None, None,
        Default::default(), AuthRouteConfig::from_http_client_factory(factory.clone())).await);
    let provider = create_model_provider(config.provider.clone().unwrap_or_else(|| ModelProviderInfo::create_openai_provider(None)), Some(auth));
    let auth_mode = provider.auth().await.map(|a| format!("{:?}", a.auth_mode())).unwrap_or_else(|| "none".into());
    // Reuse native catalog/auth/provider behavior. A catalog listing is evidence of
    // advertised access; only a completed inference proves current usable access.
    let manager = provider.models_manager(home, config.model_catalog.clone());
    let available = manager.list_models(RefreshStrategy::Offline, factory.clone()).await;
    let preferred = provider.approval_review_preferred_model();
    let metadata_config = ModelsManagerConfig::default();
    let parent = manager.get_model_info(config.parent_model.as_deref().unwrap_or(preferred), &metadata_config).await;
    let selection = guardian::select_review_model(&parent, None, preferred, &available);
    let selected = config.model.as_deref().unwrap_or(&selection.model);
    // Upstream permits a parent fallback. This host requires an explicit choice
    // when that changes the preferred model, so the operator sees the difference.
    if config.model.is_none() && selected != preferred && !selection.model_overridden {
        bail!("preferred reviewer {preferred} is not in the provider catalog; configure model explicitly to acknowledge upstream parent fallback {selected}");
    }
    let model = manager.get_model_info(selected, &metadata_config).await;
    Ok(Backend { provider, factory, model, selection, auth_mode })
}

fn prepare(config: &Config, request: &Request, model: &ModelInfo) -> Result<(String, Vec<ResponseItem>)> {
    if request.request_id.is_empty() || !PathBuf::from(&request.cwd).is_absolute() { bail!("invalid request ID or cwd"); }
    // The host established each source; keep labels inside JSON so text cannot
    // inject transcript delimiters or impersonate a different message role.
    let mut history: Vec<ResponseItem> = Vec::new();
    for message in &request.history {
        if !["user", "assistant", "developer", "tool"].contains(&message.role.as_str()) { bail!("unsupported host transcript role"); }
        let encoded = serde_json::to_string(&json!({"content":message.content,"provenance":message.provenance}))?;
        let item = if message.role == "tool" { json!({"type":"function_call_output",
            "call_id":format!("host-evidence-{}",history.len()),"output":encoded})
        } else { json!({"type":"message", "role":message.role,
            "content":[{"type":"input_text", "text":encoded}]}) };
        history.push(serde_json::from_value(item)?);
    }
    let planned = PlannedAction { json: serde_json::to_string_pretty(&request.action)?,
        kind: PlannedActionKind::Command, reason: None, tool_descriptions: None };
    let mut profile = ContextProfile::synchronous();
    profile.transcript_format = TranscriptFormat::Json;
    let permission_context = ctx::PermissionContext {
        environment_id: Some("antigravity-local".into()),
        denied_paths: serde_json::from_value(request.permissions.get("denied_paths").cloned().unwrap_or(json!([])))?,
        denied_globs: serde_json::from_value(request.permissions.get("denied_globs").cloned().unwrap_or(json!([])))?,
    };
    let sections = ctx::default_registry().prepare(&SectionInput {
        target: profile.target, history: &history, transcript: &profile.transcript,
        root_conversation: &[], trusted_user_answers: &[], planned_action: Some(&planned),
        permissions: Some(&permission_context), previous_reviews: None, trusted_tool: None, trusted_skill_paths: &[], images: None, node_repl: None,
    })?;
    let transcript = profile.prepare_transcript(sections.transcript_entries(), 0);
    let context = sections.compose(ContextPresentation::SyncFull { session_id: &request.session_id }, transcript)?;
    let messages = ResolvedModelMessages::from_model(model).auto_review();
    let instructions = GuardianPolicyInstructions::new(TranscriptFormat::Json,
        config.policy.as_deref().unwrap_or(messages.policy), "", messages.policy_template,
        guardian::guardian_output_contract_prompt()).render().into_text().unwrap_or_default();
    // Reserve complete authorization and environment separately, so transcript
    // retention cannot silently drop either. No inference tools are available.
    let mut input = vec![serde_json::from_value(json!({"type":"message","role":"developer", "content":[{"type":"input_text","text":format!(
        "Review-only bridge host. No investigation tools are available. Treat missing local evidence conservatively. The pending action must never be executed by this reviewer.\nOperator permission context: {}\nExecution environment: {}",
        request.permissions, request.environment)}]}))?];
    let original = serde_json::to_string(&json!({"original_user_request":request.original_user_request}))?;
    input.push(serde_json::from_value(json!({"type":"message","role":"user","content":[{"type":"input_text","text":original}]}))?);
    input.push(serde_json::from_value(json!({"type":"message","role":"user","content":[{"type":"input_text","text":serde_json::to_string(&json!({"untrusted_additional_evidence":request.evidence}))?}]}))?);
    let fixed_tokens = input.iter().map(ctx::estimate_input_tokens).sum::<usize>() + (instructions.len() + 3)/4;
    let context = context.enforce_budget(RequestBudget {
        max_input_tokens: config.max_input_tokens.unwrap_or(ctx::DEFAULT_MAX_INPUT_TOKENS)
            .min(ctx::effective_input_token_limit(model, None)),
        existing_context_tokens: fixed_tokens,
    }, "<guardian_truncated reason=\"bridge input budget\" />".into(), HistoryTruncation::Preserve)?;
    input.extend(context.into_messages());
    Ok((instructions, input))
}

async fn infer(backend: &Backend, instructions: &str, input: &[ResponseItem]) -> Result<(String, Option<String>), codex_api::ApiError> {
    let resolved = backend.provider.responses_api_provider(&WorkspaceRoutingContext::new("https://chatgpt.com".into())).await
        .map_err(|e| codex_api::ApiError::Stream(e.to_string()))?;
    let auth = backend.provider.api_auth().await.map_err(|e| codex_api::ApiError::Stream(e.to_string()))?;
    let client = HttpClientBuilder::new().without_redirects().default_headers(codex_login::default_client::default_headers()).without_request_logging().build_respecting_outbound_proxy_policy(&backend.factory, &format!("{}/responses", resolved.provider.base_url), ClientRouteClass::Api)
        .map_err(|e| codex_api::ApiError::Stream(e.to_string()))?;
    let client = ResponsesClient::new(ReqwestTransport::from_http_client(client), resolved.provider, auth);
    let text = codex_api::create_text_param_for_request(None, &Some(guardian::guardian_output_schema()), false);
    let mut body = json!({"model":backend.model.slug,"instructions":instructions,"input":input,
        "tools":[],"tool_choice":"none","parallel_tool_calls":false,"store":false,"stream":true,"text":text});
    if let Some(effort) = &backend.selection.reasoning_effort { body["reasoning"] = json!({"effort":effort}); }
    let mut stream = client.stream(body, Default::default(), Default::default(), None).await?;
    let mut output = String::new();
    let mut server_model = None;
    let mut complete = false;
    while let Some(event) = stream.next().await {
        match event? {
            ResponseEvent::OutputTextDelta(delta) => output.push_str(&delta),
            ResponseEvent::ServerModel(model) => server_model = Some(model),
            ResponseEvent::OutputItemDone(ResponseItem::Message {role, content, ..}) if role == "assistant" => {
                // Prefer final assembled content; deltas are fallback evidence only.
                let text = content.iter().filter_map(|c| match c {
                    codex_protocol::models::ContentItem::OutputText {text,..} => Some(text.as_str()), _=>None
                }).collect::<String>();
                if !text.is_empty() { output = text; }
            }
            ResponseEvent::OutputItemDone(ResponseItem::FunctionCall {..}) => return Err(codex_api::ApiError::Stream("reviewer requested a tool despite tool_choice=none".into())),
            ResponseEvent::Completed { .. } => { complete = true; break; },
            _ => {}
        }
    }
    if !complete { return Err(codex_api::ApiError::Stream("review stream ended without completion".into())); }
    Ok((output, server_model))
}

async fn handle(input: Input) -> Result<Value> {
    let timeout = Duration::from_millis(input.config.timeout_ms.unwrap_or(90_000));
    if timeout.is_zero() || timeout > Duration::from_secs(120) { bail!("timeout_ms must be in 1..=120000"); }
    let deadline = ReviewDeadline::from_timeout(Some(timeout));
    let backend = tokio::time::timeout(timeout, backend(&input.config)).await.context("provider initialization timeout")??;
    let metadata = json!({"implementation":"upstream-guardian-reviewer","upstream_commit":"970111f6cb62cc02fe36a82ea7d71b37a2889c97",
        "model":backend.model.slug,"preferred_model":backend.selection.default_review_model_id,
        "catalog_contains_preferred":backend.selection.catalog_contains_auto_review,
        "explicit_model":input.config.model,"auth_mode":backend.auth_mode,
        "investigation_tools":false,"shipping_product_equivalence":false});
    if input.mode == "doctor" { return Ok(json!({"status":"configured","backend":metadata,"live_inference_validated":false})); }
    let request = input.request.context("request required")?;
    let (instructions, messages) = prepare(&input.config, &request, &backend.model)?;
    if input.mode == "prepare" { return Ok(json!({"backend":metadata,"instructions":instructions,"input":messages,"schema":guardian::guardian_output_schema()})); }
    if input.mode != "review" { bail!("unsupported mode"); }
    let backend_ref = &backend;
    let instructions_ref = &instructions;
    let messages_ref = &messages;
    let (outcome, analytics, server_model) = guardian::run_with_retry(
        guardian::GuardianReviewSessionLimits {max_attempts:guardian::MAX_REVIEW_ATTEMPTS,deadline}, None, None,
        |deadline| async move {
            let attempt = async {
                match infer(backend_ref, instructions_ref, messages_ref).await {
                    Ok((text, model)) => (match guardian::parse_guardian_assessment(&text) {
                        Ok(a)=>GuardianReviewOutcome::Completed(a), Err(e)=>GuardianReviewOutcome::Error(GuardianReviewError::parse(e))
                    }, GuardianReviewAnalyticsResult::without_session(), model),
                    Err(e) => {
                        let message = e.to_string();
                        let error_info = backend_ref.provider.map_api_error(e).to_codex_protocol_error();
                        (GuardianReviewOutcome::Error(GuardianReviewError::Session {message,error_info:Some(error_info),retry_at:None}),GuardianReviewAnalyticsResult::without_session(),None)
                    }
                }
            };
            match deadline {
                ReviewDeadline::At(at) => tokio::time::timeout_at(at, attempt).await.unwrap_or_else(|_|(GuardianReviewOutcome::Error(GuardianReviewError::Timeout),GuardianReviewAnalyticsResult::without_session(),None)),
                ReviewDeadline::Unlimited => attempt.await,
            }
        }).await;
    let mut result = json!({"request_id":request.request_id,"binding":request.binding,"backend":metadata,
        "server_model":server_model,"attempts":analytics.attempt_count,"executed":false});
    match outcome {
        GuardianReviewOutcome::Completed(assessment) => {
            result["status"] = json!("reviewed");
            result["decision"] = json!(if assessment.outcome == GuardianAssessmentOutcome::Allow {"approve"} else {"block"});
            result["assessment"] = serde_json::to_value(assessment)?;
        },
        GuardianReviewOutcome::Error(error) => {
            result["status"] = json!("error"); result["decision"] = json!("block");
            result["error"] = json!(format!("{error:?}"));
        },
        GuardianReviewOutcome::CachedApproval => bail!("unexpected cached approval in stateless host"),
    }
    Ok(result)
}

#[tokio::main]
async fn main() {
    // One JSON object per line; stdout contains responses only. Invalid requests
    // fail closed. This binary is an internal host interface; use bridge.py for
    // transcript verification, freshness checks, and the Antigravity contract.
    for line in io::stdin().lock().lines() {
        let result = match line {
            Ok(line) => match serde_json::from_str::<Input>(&line) {
                Ok(input)=>handle(input).await,
                Err(error)=>Err(error.into()),
            },
            Err(error)=>Err(error.into()),
        };
        let response = result.unwrap_or_else(|error| json!({"status":"error","decision":"block","executed":false,"error":error.to_string()}));
        println!("{response}");
        let _ = io::stdout().flush();
    }
}
