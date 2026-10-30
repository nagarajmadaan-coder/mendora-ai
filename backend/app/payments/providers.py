"""
Payment providers.

Only a SANDBOX provider exists. It simulates an outcome chosen by the person testing (success, a declined
card, …). It never sees card numbers, never contacts a bank, and moves no money.

A real gateway (e.g. Razorpay or Stripe) would implement the same PaymentProvider interface — typically by
creating a payment on the gateway, then confirming it from the gateway's server-side webhook. That is NOT done here.
"""

import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

SandboxScenario = Literal["success", "card_declined", "insufficient_funds", "processing_error"]

SCENARIO_FAILURES: dict[str, tuple[str, str]] = {
    "card_declined": ("card_declined", "The simulated card was declined. No money was taken."),
    "insufficient_funds": ("insufficient_funds", "The simulated account has insufficient funds. No money was taken."),
    "processing_error": ("processing_error", "The simulated payment provider had a temporary problem. No money was taken; you can try again."),
}


@dataclass(frozen=True)
class ChargeResult:
    succeeded: bool
    transaction_ref: str | None
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class RefundResult:
    succeeded: bool
    refund_ref: str | None


class PaymentProvider(Protocol):
    name: str
    is_sandbox: bool

    def charge(self, *, amount: int, currency: str, reference: str, scenario: SandboxScenario) -> ChargeResult: ...

    def refund(self, *, transaction_ref: str, amount: int, currency: str) -> RefundResult: ...


class SandboxProvider:
    """Simulates a payment. The outcome is the scenario the tester picked; nothing real happens."""

    name = "sandbox"
    is_sandbox = True

    def charge(self, *, amount: int, currency: str, reference: str, scenario: SandboxScenario) -> ChargeResult:
        ref = f"sbx_txn_{secrets.token_hex(8)}"  # random and meaningless outside MENDORA
        if scenario == "success":
            return ChargeResult(True, ref)
        code, message = SCENARIO_FAILURES[scenario]
        return ChargeResult(False, ref, code, message)

    def refund(self, *, transaction_ref: str, amount: int, currency: str) -> RefundResult:
        return RefundResult(True, f"sbx_ref_{secrets.token_hex(8)}")


def get_provider(name: str) -> PaymentProvider | None:
    if name == "sandbox":
        return SandboxProvider()
    return None  # "none" = payments switched off
