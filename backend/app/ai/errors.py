"""
Errors the AI service can raise. Each maps to an HTTP status and a safe, user-facing message.
Internal details (provider error bodies, keys) are logged on the server, never sent to the client.
"""


class AIError(Exception):
    status_code = 502
    code = "ai_error"
    public_message = "The AI diagnosis service failed. No diagnosis was generated."

    def __init__(self, internal_detail: str = "") -> None:
        super().__init__(internal_detail or self.public_message)
        self.internal_detail = internal_detail


class AINotConfigured(AIError):
    status_code = 503
    code = "ai_not_configured"
    public_message = (
        "AI diagnosis is not configured on this server yet, so no diagnosis was generated. "
        "Your request has been saved."
    )


class AITimeout(AIError):
    status_code = 504
    code = "ai_timeout"
    public_message = "The AI service took too long to respond. No diagnosis was generated. Please try again."


class AIRateLimited(AIError):
    status_code = 503
    code = "ai_rate_limited"
    public_message = "The AI service is busy right now. No diagnosis was generated. Please try again in a minute."


class AIProviderError(AIError):
    status_code = 502
    code = "ai_provider_error"
    public_message = "The AI service returned an error. No diagnosis was generated. Please try again later."


class AIInvalidResponse(AIError):
    status_code = 502
    code = "ai_invalid_response"
    public_message = (
        "The AI service returned a response MENDORA couldn't use. No diagnosis was generated. Please try again."
    )
