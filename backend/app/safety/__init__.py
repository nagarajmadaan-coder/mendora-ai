"""
Safety assessment engine (Step 6) — rule-based, deterministic, works without any AI key.

    rules.py   all hazard rules, clarifying questions and safety advice (plain data)
    engine.py  assess(): turns a repair report into a risk level and advice

Every path to AI diagnosis or DIY guidance goes through this engine first (see services/safety_workflow.py).
Import from the submodules, e.g. `from app.safety.engine import assess`.
"""
