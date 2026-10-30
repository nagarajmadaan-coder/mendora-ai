"""
Minimal JSON-over-HTTPS helper using only Python's standard library (no extra dependency).

Providers receive a `Transport` function. In production it's `urllib_transport`;
tests pass a fake one that returns canned responses, so tests never call a real API.
"""

import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import AIProviderError, AITimeout


@dataclass
class HttpResponse:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)


Transport = Callable[[str, dict[str, str], bytes, float], HttpResponse]


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https URLs)
            return HttpResponse(response.status, response.read().decode("utf-8", errors="replace"), dict(response.headers))
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a useful body
        body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return HttpResponse(exc.code, body_text, dict(exc.headers or {}))
    except (TimeoutError, socket.timeout) as exc:
        raise AITimeout(f"Request to {url} timed out after {timeout}s") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AITimeout(f"Request to {url} timed out after {timeout}s") from exc
        raise AIProviderError(f"Could not reach {url}: {exc.reason}") from exc
