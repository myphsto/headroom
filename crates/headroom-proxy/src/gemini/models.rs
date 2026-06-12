//! Gemini API data models for request/response serialization.
//!
//! These structs map to the Google Gemini v1beta native API shape.
//! We use `camelCase` renaming as required by the upstream wire format.

use serde::{Deserialize, Serialize};

/// Root envelope for a Gemini generateContent request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiRequest {
    pub contents: Vec<GeminiContent>,
    pub system_instruction: Option<GeminiSystemInstruction>,
}

/// A single turn in the conversation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiContent {
    pub role: String,
    pub parts: Vec<GeminiPart>,
}

/// Polymorphic part of a content entry.
///
/// We use `untagged` because Google's API distinguishes types by the presence
/// of specific keys (e.g., if "text" is present, it's a text part).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum GeminiPart {
    Text {
        text: String,
    },
    InlineData {
        #[serde(rename = "inlineData")]
        blob: GeminiBlob,
    },
    FileData {
        #[serde(rename = "fileData")]
        file: GeminiFile,
    },
    FunctionCall {
        #[serde(rename = "functionCall")]
        call: GeminiFunctionCall,
    },
    FunctionResponse {
        #[serde(rename = "functionResponse")]
        response: GeminiFunctionResponse,
    },
}

/// Base64 encoded media data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiBlob {
    pub mime_type: String,
    pub data: String,
}

/// Reference to a file uploaded to Google's File API.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiFile {
    pub mime_type: String,
    pub file_uri: String,
}

/// A model-generated function call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiFunctionCall {
    pub name: String,
    pub args: serde_json::Value,
}

/// A user-provided response to a function call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiFunctionResponse {
    pub name: String,
    pub response: serde_json::Value,
}

/// The system instruction envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiSystemInstruction {
    pub parts: Vec<GeminiPart>,
}

/// Root envelope for a Gemini generateContent response.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiResponse {
    pub candidates: Vec<GeminiCandidate>,
    pub usage_metadata: Option<GeminiUsageMetadata>,
}

/// A candidate response from the model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeminiCandidate {
    pub content: GeminiContent,
    pub finish_reason: String,
}

/// Token usage metrics for a request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiUsageMetadata {
    pub prompt_token_count: u64,
    pub candidates_token_count: u64,
    pub cached_content_token_count: Option<u64>,
}
