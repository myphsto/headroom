# Plan: Migrate Gemini Handler to Rust Proxy

## Context
The project is migrating its proxy logic from Python to Rust. The Gemini handler currently resides in Python (`headroom/proxy/handlers/gemini.py`) and needs to be ported to the Rust `headroom-proxy` binary.

## Technical Analysis
Gemini's API structure differs significantly from OpenAI/Anthropic:
- **Input Structure**: Uses a nested `contents` list containing `parts`. Each part can be text, image data (`inlineData`), file references (`fileData`), or function call/response.
- **System Instruction**: Handled via a separate `systemInstruction` field rather than a system message in the chat history.
- **Optimization Challenge**: The proxy applies compression to the conversation history. Since only text parts are compressible, the Rust implementation must:
    1. Identify and "preserve" non-text parts (indices of entries with images/tools).
    2. Convert the remaining text into a flat internal message format for the optimization pipeline.
    3. After optimization, interleave the preserved original non-text entries back into their correct relative positions in the final Gemini request body.

## Implementation Steps

### 1. Define Rust Data Models
- Create `serde` compatible structs in `crates/headroom-proxy/src/` to represent Gemini requests and responses.
- Implement a polymorphic `GeminiPart` enum to handle `text`, `inlineData`, `fileData`, `functionCall`, and `functionResponse`.

### 2. Implementation of Conversion Layer
- **`gemini_to_internal`**: 
    - Convert `contents` $\rightarrow$ flat internal messages for the optimizer.
    - Return a map/set of indices that must be preserved (non-text entries).
- **`internal_to_gemini`**: 
    - Map roles back (`assistant` $\rightarrow$ `model`).
    - Use the preservation map to interleave original non-text parts with optimized text parts.

### 3. Update Proxy Routing & Dispatch
- Add Gemini endpoints to the `CompressibleEndpoint` enum and update `classify_compressible_path`.
- Implement a new dispatcher in `crates/headroom-proxy/src/compression/live_zone_gemini.rs` that:
    - Parses the incoming JSON into Gemini models.
    - Runs the conversion $\rightarrow$ optimization $\rightarrow$ re-conversion cycle.
    - Forwards the request to the upstream Gemini API.

### 4. Handle Special Routing (Cloud Code Assist / Antigravity)
- Port the logic for detecting "antigravity" requests via User-Agent and body fields.
- Implement base URL resolution (`DEFAULT_CLOUDCODE_API_URL` vs `ANTIGRAVITY_DAILY_API_URL`).

### 5. Verification & Testing
- **Parity Tests**: Use a set of Gemini request payloads (text-only, mixed media, function calls).
- **Shadowing**: Verify that the Rust output body matches the Python handler's output for the same input.
- **Integration**: Test end-to-end connectivity with `alt=sse` streaming.

## Success Criteria
- All Gemini requests are handled by the Rust proxy.
- Non-text parts are preserved exactly in their original positions after compression.
- Performance parity or improvement over the Python implementation.
- Zero regressions in Cloud Code Assist routing.
