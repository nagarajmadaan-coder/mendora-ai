"""
Payments (Step 10) — SANDBOX ONLY.

providers.py  the provider interface + the simulated SandboxProvider (no real money, no card data)
service.py    the business rules: ownership, amount checks against the stored booking price,
              duplicate prevention, refunds when a paid booking is cancelled.

To add a real gateway later, implement PaymentProvider in providers.py and select it in get_provider().
"""
