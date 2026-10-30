"""
AI diagnosis package — kept separate from the API routes so it can be tested and changed on its own.

    service.py    the entry point: safety gate → privacy redaction → provider call → validation → output screening
    providers.py  Anthropic (default) and OpenAI-compatible providers
    prompts.py    system prompt + the JSON structure the model must return
    privacy.py    removes emails/phone numbers before anything is sent to the provider
    http.py       tiny HTTP helper (swappable in tests, so no real API is called during tests)
    errors.py     clear error types: not configured, timeout, rate limited, provider error, invalid response
"""
