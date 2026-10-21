# gpt-6-luna compatibility check

- Model: `gpt-6-luna`
- Run at: 2026-10-15T14:02:34+00:00
- Overall: **PASS**
- Pricing: user-supplied; no price assumed.

| Check | Result | Detail |
|---|---|---|
| models.retrieve | PASS | HTTP 200 {
  "id": "gpt-6-luna",
  "object": "model",
  "created": 1789406102,
  "owned_by": "system",
  "shutdown_date": null
} |
| chat.completions (max_completion_tokens) | PASS | HTTP 200; text=True; finish=stop; usage={'prompt_tokens': 10, 'completion_tokens': 4, 'total_tokens': 14, 'prompt_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0, 'audio_tokens': 0}, 'completion_tokens_details': {'reasoning_tokens': 0, 'audio_tokens': 0, 'accepted_prediction_tokens': 0, 'rejected_prediction_tokens': 0}} |
| param: max_tokens | UNSUPPORTED (informational) | HTTP 400 {
  "error": {
    "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
    "type": "invalid_request_error",
    "param": "max_tokens",
    "code": "unsupported_parameter"
  }
} |
| param: temperature=0 | UNSUPPORTED (informational) | HTTP 400 {
  "error": {
    "message": "Unsupported value: 'temperature' does not support 0 with this model. Only the default (1) value is supported.",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "unsupported_value"
  }
} |
| param: seed | PASS | HTTP 200  |
| autogen OpenAIChatCompletionClient | PASS | usage=RequestUsage(prompt_tokens=11, completion_tokens=4) |
