"""
Repair knowledge base (Step 7).

    data/entries.json  the knowledge entries (plain data — edit to add or change entries)
    store.py           loads + validates entries at startup (unsafe wording is rejected)
    retrieval.py       search interface + the current keyword retriever (swappable later)
    service.py         safety-gated guidance: the Step 6 safety engine ALWAYS decides what is shown
"""
