//! Gemini API request compression — live-zone dispatcher entry point.
//!
//! # Provider scope
//!
//! Sibling of [`super::live_zone_openai`] and [`super::live_zone_anthropic`].
//! This dispatcher handles requests to the Gemini API, extracting the conversation
//! history (`contents`) and applying compression via the `headroom-core` backend.
//!
//! Failure-mode contract: every error path returns the original body unchanged.

use bytes::Bytes;
use headroom_core::auth_mode::AuthMode as RequestAuthMode;
use headroom_core::transforms::live_zone::{compress_gemini_live_zone, DEFAULT_MODEL};
use headroom_core::transforms::{BlockAction, LiveZoneError, LiveZoneOutcome};
use serde_json::Value;

use crate::compression::{Outcome, PassthroughReason, PerStrategyTokens};
use crate::config::CompressionMode;

/// Gemini live-zone compression entry point.
///
/// # Behaviour
/// - `mode == Off` → [`Outcome::Passthrough { ModeOff }`].
/// - Body doesn't parse as JSON → `Passthrough { NotJson }`.
/// - `contents` array is missing → `Passthrough { NoMessages }`.
/// - Content in the live zone is large enough to compress → [`Outcome::Compressed`].
/// - Otherwise → [`Outcome::NoCompression`].
pub fn compress_gemini_request(
    body: &Bytes,
    mode: CompressionMode,
    auth_mode: RequestAuthMode,
    request_id: &str,
) -> Outcome {
    if matches!(mode, CompressionMode::Off) {
        tracing::info!(
            event = "compression_decision",
            request_id = %request_id,
            path = "/v1beta/models/{model}:generateContent",
            method = "POST",
            compression_mode = mode.as_str(),
            decision = "passthrough",
            reason = "mode_off",
            body_bytes = body.len(),
            "gemini compression decision"
        );
        return Outcome::Passthrough {
            reason: PassthroughReason::ModeOff,
        };
    }

    let parsed: Value = match serde_json::from_slice(body) {
        Ok(v) => v,
        Err(_) => {
            tracing::warn!(
                event = "compression_decision",
                request_id = %request_id,
                path = "/v1beta/models/{model}:generateContent",
                method = "POST",
                compression_mode = mode.as_str(),
                decision = "passthrough",
                reason = "not_json",
                body_bytes = body.len(),
                "gemini compression decision"
            );
            return Outcome::Passthrough {
                reason: PassthroughReason::NotJson,
            };
        }
    };

    if parsed.get("contents").and_then(Value::as_array).is_none() {
        tracing::info!(
            event = "compression_decision",
            request_id = %request_id,
            path = "/v1beta/models/{model}:generateContent",
            method = "POST",
            compression_mode = mode.as_str(),
            decision = "passthrough",
            reason = "no_messages",
            body_bytes = body.len(),
            "gemini compression decision"
        );
        return Outcome::Passthrough {
            reason: PassthroughReason::NoMessages,
        };
    }

    let model = parsed
        .get("model") // Note: In actual Gemini requests, the model is often in the URL. 
        .and_then(Value::as_str)
        .unwrap_or(DEFAULT_MODEL);

    match compress_gemini_live_zone(body, auth_mode.into(), model) {
        Ok(LiveZoneOutcome::NoChange { manifest }) => {
            tracing::info!(
                event = "compression_decision",
                request_id = %request_id,
                path = "/v1beta/models/{model}:generateContent",
                method = "POST",
                compression_mode = mode.as_str(),
                decision = "no_change",
                reason = "no_block_compressed",
                body_bytes = body.len(),
                messages_total = manifest.messages_total,
                latest_user_message_index = ?manifest.latest_user_message_index,
                live_zone_blocks = manifest.block_outcomes.len(),
                model = model,
                "gemini live-zone dispatch"
            );
            Outcome::NoCompression
        }
        Ok(LiveZoneOutcome::Modified { new_body, manifest }) => {
            let mut original_bytes_total: usize = 0;
            let mut compressed_bytes_total: usize = 0;
            let mut original_tokens_total: usize = 0;
            let mut compressed_tokens_total: usize = 0;
            let mut strategies: Vec<&'static str> = Vec::new();
            let mut per_strategy_tokens: Vec<PerStrategyTokens> = Vec::new();
            let mut had_compressor_error = false;

            for entry in &manifest.block_outcomes {
                match entry.action {
                    BlockAction::Compressed {
                        strategy,
                        original_bytes,
                        compressed_bytes,
                        original_tokens,
                        compressed_tokens,
                    } => {
                        original_bytes_total += original_bytes;
                        compressed_bytes_total += compressed_bytes;
                        original_tokens_total += original_tokens;
                        compressed_tokens_total += compressed_tokens;
                        if !strategies.contains(&strategy) {
                            strategies.push(strategy);
                        }
                        if let Some(slot) = per_strategy_tokens
                            .iter_mut()
                            .find(|s| s.strategy == strategy)
                        {
                            slot.original_tokens += original_tokens;
                            slot.compressed_tokens += compressed_tokens;
                        } else {
                            per_strategy_tokens.push(PerStrategyTokens {
                                strategy,
                                original_tokens,
                                compressed_tokens,
                            });
                        }
                    }
                    BlockAction::RejectedNotSmaller { strategy, .. } => {
                        crate::observability::record_compression_rejected_by_token_check(strategy);
                    }
                    BlockAction::CompressorError {
                        strategy,
                        ref error,
                    } => {
                        had_compressor_error = true;
                        tracing::error!(
                            event = "compression_error",
                            request_id = %request_id,
                            path = "/v1beta/models/{model}:generateContent",
                            strategy = strategy,
                            error = %error,
                            "gemini compressor error on a block; that block reverts to original"
                        );
                    }
                    _ => {}
                }
            }

            let body_bytes_in = body.len();
            let new_body_bytes = Bytes::copy_from_slice(new_body.get().as_bytes());
            let body_bytes_out = new_body_bytes.len();

            tracing::info!(
                event = "compression_decision",
                request_id = %request_id,
                path = "/v1beta/models/{model}:generateContent",
                method = "POST",
                compression_mode = mode.as_str(),
                decision = "compressed",
                reason = "live_zone_blocks_rewritten",
                body_bytes_in = body_bytes_in,
                body_bytes_out = body_bytes_out,
                bytes_freed = body_bytes_in.saturating_sub(body_bytes_out),
                messages_total = manifest.messages_total,
                latest_user_message_index = ?manifest.latest_user_message_index,
                live_zone_blocks = manifest.block_outcomes.len(),
                live_zone_strategies = ?strategies,
                live_zone_block_original_bytes = original_bytes_total,
                live_zone_block_compressed_bytes = compressed_bytes_total,
                live_zone_block_original_tokens = original_tokens_total,
                live_zone_block_compressed_tokens = compressed_tokens_total,
                had_compressor_error = had_compressor_error,
                model = model,
                "gemini live-zone dispatch"
            );

            Outcome::Compressed {
                body: new_body_bytes,
                tokens_before: original_tokens_total,
                tokens_after: compressed_tokens_total,
                strategies_applied: strategies,
                markers_inserted: Vec::new(),
                per_strategy_tokens,
            }
        }
        Err(LiveZoneError::BodyNotJson(_)) => {
            tracing::warn!(
                event = "compression_decision",
                request_id = %request_id,
                path = "/v1beta/models/{model}:generateContent",
                "gemini live-zone dispatcher rejected JSON body; falling back to passthrough"
            );
            Outcome::Passthrough {
                reason: PassthroughReason::NotJson,
            }
        }
        Err(LiveZoneError::NoMessagesArray) => {
            tracing::info!(
                event = "compression_decision",
                request_id = %request_id,
                path = "/v1beta/models/{model}:generateContent",
                method = "POST",
                compression_mode = mode.as_str(),
                decision = "passthrough",
                reason = "no_messages",
                body_bytes = body.len(),
                "gemini compression decision"
            );
            Outcome::Passthrough {
                reason: PassthroughReason::NoMessages,
            }
        }
    }
}
