//! Conversion layer between Gemini API and internal proxy representation.
//!
//! This module allows the proxy to treat Gemini requests as a sequence of messages,
//! enabling the use of standard compression pipelines while preserving complex
//! content (images, files, function calls) that cannot be compressed.

use crate::gemini::models::*;
use serde_json::{json, Value};

/// Result of converting Gemini contents to an internal format.
pub struct ConversionResult {
    /// The flattened list of messages in a form compatible with OpenAI/Anthropic.
    pub messages: Vec<Value>,
    /// Indices of the original `GeminiContent` entries that contain non-text parts.
    /// These indices are used to re-inject original content after compression.
    pub preserved_indices: Vec<usize>,
}

/// Converts a Gemini request into an internal message format for optimization.
///
/// Non-text parts (images, files, function calls) make the content "uncompressible".
/// We mark these indices as `preserved` and only pass the text components to the optimizer.
pub fn gemini_to_internal(req: &GeminiRequest) -> ConversionResult {
    let mut messages = Vec::new();
    let mut preserved_indices = Vec::new();

    // 1. Handle System Instruction
    if let Some(sys) = &req.system_instruction {
        let text = extract_text(&sys.parts);
        if !text.is_empty() {
            messages.push(json!({ "role": "system", "content": text }));
        }
    }

    // 2. Handle Conversation Contents
    for (idx, content) in req.contents.iter().enumerate() {
        if has_non_text_parts(&content.parts) {
            preserved_indices.push(idx);
        }

        let text = extract_text(&content.parts);
        if !text.is_empty() {
            // Map Gemini role "model" -> internal "assistant"
            let role = if content.role == "model" {
                "assistant"
            } else {
                &content.role
            };
            messages.push(json!({ "role": role, "content": text }));
        }
    }

    ConversionResult {
        messages,
        preserved_indices,
    }
}

/// Rebuilds the Gemini request body using optimized internal messages and
/// interleaved original preserved content.
pub fn internal_to_gemini(
    optimized_messages: Vec<Value>,
    original_req: &GeminiRequest,
    preserved_indices: &[usize],
) -> Vec<GeminiContent> {
    let mut final_contents = Vec::new();
    let mut current_msg_idx = 0;

    // Note: System instructions are usually handled separately or kept as-is.
    // This logic focuses on the `contents` array.

    // Filter out system messages from optimized list for content reconstruction
    let user_assistant_msgs: Vec<Value> = optimized_messages
        .into_iter()
        .filter(|m| m["role"] != "system")
        .collect();

    for (idx, original) in original_req.contents.iter().enumerate() {
        if preserved_indices.contains(&idx) {
            // Restore the full complex content
            final_contents.push(original.clone());
        } else if current_msg_idx < user_assistant_msgs.len() {
            // Use optimized text content
            let msg = &user_assistant_msgs[current_msg_idx];
            let role = if msg["role"] == "assistant" {
                "model"
            } else {
                msg["role"].as_str().unwrap_or("user")
            };
            let text = msg["content"].as_str().unwrap_or("");

            final_contents.push(GeminiContent {
                role: role.to_string(),
                parts: vec![GeminiPart::Text {
                    text: text.to_string(),
                }],
            });
            current_msg_idx += 1;
        } else {
            // Fallback to original if we ran out of optimized messages (shouldn't happen)
            final_contents.push(original.clone());
        }
    }

    final_contents
}

fn extract_text(parts: &[GeminiPart]) -> String {
    parts
        .iter()
        .filter_map(|p| {
            if let GeminiPart::Text { text } = p {
                Some(text)
            } else {
                None
            }
        })
        .cloned()
        .collect::<Vec<_>>()
        .join(" ")
}

fn has_non_text_parts(parts: &[GeminiPart]) -> bool {
    parts.iter().any(|p| !matches!(p, GeminiPart::Text { .. }))
}
