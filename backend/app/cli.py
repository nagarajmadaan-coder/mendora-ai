"""
Command-line tools.

Create the first admin account (there is deliberately NO public admin sign-up):

    python -m app.cli create-admin --email admin@example.com --name "Site Admin"

You'll be asked to type the password twice. It is never shown, stored in plain text, or saved in any file.

Create clearly-labelled SAMPLE technicians for a local demo (Step 8):

    python -m app.cli seed-demo

You'll be asked for one password that all sample technician accounts will use, so you can sign in as them.
Samples are marked "Demo sample — not a real technician" everywhere and are never verified.

Check that the AI provider really works (one real request with a harmless sample problem):

    python -m app.cli check-ai
    python -m app.cli check-web-research     (Tavily AI web research)
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from .config import get_settings
from .db import create_tables, make_engine, make_session_factory
from .repositories import users as users_repo
from .schemas import AdminCreateUserRequest
from .security import hash_password


def create_admin(email: str, name: str, password: str) -> int:
    try:
        data = AdminCreateUserRequest(email=email, full_name=name, password=password, role="admin")
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Error ({err['loc'][0]}): {err['msg'].removeprefix('Value error, ')}", file=sys.stderr)
        return 1

    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_tables(engine)
    with make_session_factory(engine)() as db:
        if users_repo.get_by_email(db, data.email):
            print(f"Error: an account with {data.email} already exists.", file=sys.stderr)
            return 1
        user = users_repo.create(db, email=data.email, full_name=data.full_name, password_hash=hash_password(data.password), role="admin")
        print(f"Admin account created: {user.email} (id {user.id})")
    engine.dispose()
    return 0


# Clearly-labelled DEMO data. Not real people, businesses, rates, availability or qualifications.
# Each sample keeps the same login email across runs, so re-running the seed updates rather than duplicates.
SAMPLE_TECHNICIANS = [
    {"trade": "plumbing", "name": "Sample Plumber A (demo)", "areas": ["560001", "560038", "indiranagar", "bengaluru"],
     "skills": ["Leak repair", "Tap and toilet repairs"], "years": 6, "visit": 399, "consult": 199, "availability": "available"},
    {"trade": "plumbing", "name": "Sample Plumber B (demo)", "areas": ["600017", "t nagar", "chennai"],
     "skills": ["Drain unblocking", "Water heater checks"], "years": 3, "visit": 349, "consult": None, "availability": "busy"},
    {"trade": "electrical", "name": "Sample Electrician A (demo)", "areas": ["560001", "560034", "koramangala", "bengaluru"],
     "skills": ["Socket and switch repairs", "Fault finding"], "years": 8, "visit": 499, "consult": 249, "availability": "available"},
    {"trade": "electrical", "name": "Sample Electrician B (demo)", "areas": ["400053", "andheri", "mumbai"],
     "skills": ["Lighting", "Breaker faults"], "years": 4, "visit": 449, "consult": None, "availability": "available"},
    {"trade": "carpentry", "name": "Sample Carpenter A (demo)", "areas": ["560001", "560038", "indiranagar", "bengaluru"],
     "skills": ["Door and hinge repairs", "Furniture repair"], "years": 10, "visit": 349, "consult": 149, "availability": "available"},
    {"trade": "carpentry", "name": "Sample Carpenter B (demo)", "areas": ["110001", "connaught place", "delhi"],
     "skills": ["Cabinet fitting", "Drawer repairs"], "years": 2, "visit": 299, "consult": None, "availability": "unavailable"},
]
SAMPLE_BIO = "Sample profile for testing MENDORA. Not a real person or business."


def sample_email(index: int, trade: str) -> str:
    return f"sample.{trade}.{index}@demo.mendora.local"


def seed_demo(password: str) -> int:
    """Create or refresh the sample technicians. Safe to run again: nothing is duplicated."""
    from .models import TechnicianProfile

    if len(password) < 8:
        print("Error: the password must be at least 8 characters.", file=sys.stderr)
        return 1
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_tables(engine)
    created = skipped = 0
    with make_session_factory(engine)() as db:
        for i, row in enumerate(SAMPLE_TECHNICIANS, start=1):
            email = sample_email(i, row["trade"])
            user = users_repo.get_by_email(db, email)
            if user is None:
                user = users_repo.create(db, email=email, full_name=row["name"], password_hash=hash_password(password), role="technician")
                created += 1
            profile = db.query(TechnicianProfile).filter(TechnicianProfile.user_id == user.id).one_or_none()
            if profile is not None and not profile.is_sample:
                print(f"Skipped {email}: it has a non-sample profile, so it was left unchanged.", file=sys.stderr)
                skipped += 1
                continue
            if profile is None:
                profile = TechnicianProfile(user_id=user.id, is_sample=True)
                db.add(profile)
            profile.display_name = row["name"]
            profile.trade = row["trade"]
            profile.service_areas = row["areas"]
            profile.skills = row["skills"]
            profile.years_experience = row["years"]
            profile.bio = SAMPLE_BIO
            profile.visit_rate = row["visit"]
            profile.consultation_rate = row["consult"]
            profile.currency = settings.currency
            profile.availability_status = row["availability"]
            profile.verification_status = "unverified"  # samples are never verified
            profile.is_sample = True
            db.commit()
    engine.dispose()

    print(f"Done: {created} sample technician(s) created, {len(SAMPLE_TECHNICIANS) - created - skipped} refreshed. Nothing was duplicated.")
    if created < len(SAMPLE_TECHNICIANS):
        print("Existing sample accounts keep their old password.")
    print("\nSample technicians (DEMO DATA — not real people):")
    for i, row in enumerate(SAMPLE_TECHNICIANS, start=1):
        print(f"  {row['name']:<30} {row['trade']:<11} {row['availability']:<12} areas: {', '.join(row['areas'])}")
        print(f"  {'':<30} sign in: {sample_email(i, row['trade'])}")
    print("\nTry searching for an area above, e.g. 560001, Indiranagar, Bengaluru, Chennai, Mumbai or Delhi.")
    if not settings.demo_mode_enabled:
        print("Note: demo mode is OFF, so samples are hidden. Set MENDORA_DEMO_MODE=true in backend/.env to show them.")
    return 0


CHECK_AI_SAMPLE = "The kitchen sink drains very slowly and gurgles. It started two days ago."


def check_ai(transport=None) -> int:
    """
    Make ONE real AI diagnosis with a harmless sample problem (no personal data), through the same code the app uses,
    and report whether it worked. The API key is never printed.
    """
    from .ai.errors import AIError, AINotConfigured
    from .ai.service import ai_status, diagnose
    from .safety.engine import SafetyInput, assess

    from .config import env_file_path

    settings = get_settings()
    status = ai_status(settings)
    print(f"Settings file: {env_file_path()}")
    base = settings.ai_base_url or {"nebius": "https://api.tokenfactory.nebius.com/v1", "openai": "https://api.openai.com/v1", "tavily": "https://api.tavily.com/search"}.get(settings.ai_provider, "provider default")
    print(f"Provider: {status['provider']}   Model: {status['model']}   API address: {base}")
    print(f"API key: {'set' if settings.ai_api_key else 'NOT SET'} (never shown)")
    if not status["configured"]:
        print("Result: NOT CONFIGURED — set the provider, model and API key in backend/.env (see README).", file=sys.stderr)
        return 1
    safety = assess(SafetyInput(trade_id="plumbing", description=CHECK_AI_SAMPLE))
    print(f"Sample problem: “{CHECK_AI_SAMPLE}” (safety check: {safety.risk_level} risk)")
    print("Calling the AI provider… (this can take up to a minute)")
    try:
        outcome = diagnose(
            trade_id="plumbing", trade_name="Plumbing", description=CHECK_AI_SAMPLE,
            follow_up_answers=[], safety=safety, settings=settings, transport=transport,
        )
    except AINotConfigured as exc:
        print(f"Result: NOT CONFIGURED — {exc}", file=sys.stderr)
        return 1
    except AIError as exc:
        print(f"Result: FAILED ({type(exc).__name__}) — {exc}", file=sys.stderr)
        print("Check the API key, the model name (MENDORA_AI_MODEL) and your internet connection.", file=sys.stderr)
        return 1
    if outcome.diagnosis is None:
        print("Result: WORKING — the AI answered, but flagged possible danger (the app would show safety advice).")
        return 0
    d = outcome.diagnosis
    if d.get("trial"):
        print("Result: WORKING (TRIAL) — a Tavily web-search summary was received and passed MENDORA's checks. "
              "This is a trial, not a full AI diagnosis; use Nebius for the real one.")
        print(f"  Summary: {d['summary'][:300]}")
        for s_ in d.get("sources", [])[:3]:
            print(f"  Source: {s_['domain']}")
        return 0
    print("Result: WORKING — a real AI diagnosis was received and passed MENDORA's checks.")
    print(f"  Summary: {d['summary']}")
    for c in d["possible_causes"][:3]:
        print(f"  Possible cause: {c['title']}")
    return 0


def check_web_research(transport=None) -> int:
    """One real Tavily web search with a harmless sample problem. The API key is never printed."""
    from .ai import web_research
    from .ai.errors import AIError, AINotConfigured
    from .safety.engine import SafetyInput, assess

    from .config import env_file_path

    settings = get_settings()
    print(f"Settings file: {env_file_path()}")
    print(f"Web research provider: tavily   API key: {'set' if settings.tavily_key else 'NOT SET'} (never shown)")
    if not settings.tavily_key:
        print("Result: NOT CONFIGURED — add TAVILY_API_KEY=... to backend/.env.", file=sys.stderr)
        return 1
    safety = assess(SafetyInput(trade_id="plumbing", description=CHECK_AI_SAMPLE))
    print("Searching the web with Tavily…")
    try:
        out = web_research.research(trade_name="Plumbing", description=CHECK_AI_SAMPLE, safety=safety, settings=settings, transport=transport)
    except AINotConfigured as exc:
        print(f"Result: NOT CONFIGURED — {exc}", file=sys.stderr)
        return 1
    except AIError as exc:
        print(f"Result: FAILED ({type(exc).__name__}) — {exc}", file=sys.stderr)
        print("Check TAVILY_API_KEY in backend/.env and your internet connection.", file=sys.stderr)
        return 1
    print(f"Result: WORKING — Tavily returned {len(out.sources)} source(s)" + (" and an AI summary." if out.answer else "."))
    if out.answer:
        print(f"  Summary: {out.answer[:300]}")
    for src in out.sources[:3]:
        print(f"  Source: {src.title} ({src.domain})")
    return 0


def backup(out_dir: str | None = None) -> int:
    """Safe copy of the SQLite database (works while the server is running) + the uploaded photos."""
    import shutil
    import sqlite3
    from datetime import datetime
    from pathlib import Path

    from .config import BACKEND_DIR

    settings = get_settings()
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        print("Error: backup only supports SQLite. Use your database's own backup tool.", file=sys.stderr)
        return 1
    db_path = Path(url.removeprefix("sqlite:///"))
    if not db_path.is_file():
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        return 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = Path(out_dir) if out_dir else BACKEND_DIR / "backups" / f"backup-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target / "mendora.db")
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    photos = Path(settings.upload_dir)
    copied = 0
    if photos.is_dir():
        shutil.copytree(photos, target / "uploads", dirs_exist_ok=True)
        copied = sum(1 for _ in (target / "uploads").iterdir())
    print(f"Backup saved to {target}  (database + {copied} photo file(s))")
    print("To restore: stop the server, then copy mendora.db (and uploads/) back into the backend folder.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="MENDORA admin tools")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Create an admin account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True, help="Full name")
    sub.add_parser("seed-demo", help="Create clearly-labelled sample technicians for a local demo")
    sub.add_parser("check-ai", help="Make one real AI diagnosis with a sample problem to check the AI setup")
    sub.add_parser("check-web-research", help="Make one real Tavily web search with a sample problem")
    b = sub.add_parser("backup", help="Back up the database and uploaded photos")
    b.add_argument("--out", help="Folder to write the backup to (default: backend/backups/backup-<time>)")
    args = parser.parse_args(argv)

    if args.command == "check-ai":
        return check_ai()
    if args.command == "check-web-research":
        return check_web_research()
    if args.command == "backup":
        return backup(args.out)

    if args.command == "seed-demo":
        password = getpass.getpass("Password for the sample technician accounts (hidden): ")
        if password != getpass.getpass("Repeat password: "):
            print("Error: passwords do not match.", file=sys.stderr)
            return 1
        return seed_demo(password)

    if args.command == "create-admin":
        password = getpass.getpass("Admin password (hidden): ")
        if password != getpass.getpass("Repeat password: "):
            print("Error: passwords do not match.", file=sys.stderr)
            return 1
        return create_admin(args.email, args.name, password)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
