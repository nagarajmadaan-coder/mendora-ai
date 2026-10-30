"""
Removes obvious personal contact details before text is sent to the AI provider.
The model never receives the user's name, email, account ID or request ID — only the
trade, the problem description, and follow-up answers, with emails/phone numbers masked.
"""

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# 8+ digits, allowing spaces, dashes, dots, brackets and a leading + (phone-number shapes).
_PHONE = re.compile(r"(?<![\w(])[+(]?\d[\d\s().-]{6,}\d(?!\w)")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email removed]", text)

    def _phone(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        return "[phone removed]" if len(digits) >= 8 else match.group()

    return _PHONE.sub(_phone, text)
