"""One-command project runner.

Usage:
    python run.py api            # FastAPI backend  -> http://localhost:8000/docs
    python run.py ui             # Streamlit dashboard -> http://localhost:8501
    python run.py ui-react       # React dashboard -> http://localhost:5173
    python run.py seed           # demo user/tickets/payment records
    python run.py ingest         # embed knowledge_base/*.txt into pgvector
    python run.py demo           # run the three acceptance scenarios
    python run.py test           # pytest suite
    python run.py doctor         # configuration / connectivity report
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def cmd_api(args: argparse.Namespace) -> None:
    command = [
        sys.executable, "-m", "uvicorn", "api.main:app",
        "--host", args.host, "--port", str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    subprocess.run(command, cwd=ROOT)


def cmd_ui(args: argparse.Namespace) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", "frontend/app.py",
            "--server.port", str(args.port),
        ],
        cwd=ROOT,
    )


def cmd_ui_react(_: argparse.Namespace) -> None:
    import shutil

    npm = shutil.which("npm")
    if not npm:
        print("npm was not found. Install Node.js 18+ to run the React dashboard.")
        return
    subprocess.run([npm, "run", "dev"], cwd=ROOT / "frontend-react")


def cmd_seed(_: argparse.Namespace) -> None:
    from database.seed import main as seed_main

    seed_main()


def cmd_ingest(_: argparse.Namespace) -> None:
    from database.connection import check_database_connection
    from database.repository import Repository
    from rag.ingestion import KnowledgeIngestion

    ok, message = check_database_connection()
    print(message)
    if not ok:
        print("Configure DATABASE_URL and run the migrations first.")
        return
    repository = Repository()
    ingestion = KnowledgeIngestion(repository)
    print("Loading, chunking and embedding knowledge_base documents...")
    result = ingestion.ingest_directory()
    print(json.dumps(result, indent=2, default=str))


def cmd_test(args: argparse.Namespace) -> None:
    command = [sys.executable, "-m", "pytest", "-q", "tests"]
    if args.verbose:
        command = [sys.executable, "-m", "pytest", "-v", "tests"]
    subprocess.run(command, cwd=ROOT)


def cmd_doctor(_: argparse.Namespace) -> None:
    print("=" * 62)
    print("Customer Support AI - configuration report")
    print("=" * 62)
    print(f"Python: {sys.version.split()[0]}")

    from llm.model_config import validate_configuration
    from database.connection import check_database_connection

    config = validate_configuration()
    for key, value in config.items():
        print(f"{key:32s}: {value}")

    ok, message = check_database_connection()
    print(f"{'database':32s}: {'OK' if ok else 'NOT READY'} - {message}")

    migrations = sorted((ROOT / "database" / "migrations").glob("*.sql"))
    print(f"{'migrations found':32s}: {len(migrations)} "
          f"({', '.join(m.name for m in migrations)})")

    try:
        import sentence_transformers  # noqa: F401

        print(f"{'sentence-transformers':32s}: installed (384-dim local embeddings)")
    except Exception as exc:  # pragma: no cover
        print(f"{'sentence-transformers':32s}: MISSING ({exc})")

    if config["groq_configured"]:
        from llm.groq_client import GroqClient

        try:
            models = GroqClient().list_models()
            print(f"{'groq models available':32s}: {len(models)}")
            print(f"{'groq model configured':32s}: {config['groq_model']}")
            if config["groq_model"] not in models:
                print("  WARNING: configured model not in the account's model list.")
                print("  Available (free-tier candidates):")
                for model in models[:20]:
                    print(f"    - {model}")
        except Exception as exc:
            print(f"{'groq connectivity':32s}: FAILED - {exc}")
    else:
        print(f"{'groq':32s}: GROQ_API_KEY missing (see .env.example)")

    print("\nReminder: never commit .env - it contains secrets.")


def cmd_demo(_: argparse.Namespace) -> None:
    from database.connection import check_database_connection
    from database.repository import Repository
    from llm.groq_client import GroqClient
    from orchestration.coordinator import SupportCoordinator

    ok, message = check_database_connection()
    print(message)
    groq = GroqClient()
    if not ok:
        print("\nDemo requires Supabase DATABASE_URL. Configure .env, run migrations, retry.")
        return
    if not groq.available:
        print("\nDemo requires GROQ_API_KEY. Add it to .env and retry.")
        return

    repo = Repository()
    coordinator = SupportCoordinator(repo, groq=groq)
    user = repo.get_or_create_user("Demo Student", "demo.student@example.com")
    demo_ref = "TXNDEMO01"
    repo.insert_payment_record(
        user_id=user["id"], transaction_ref=demo_ref,
        amount=49.99, status="completed", description="Pro subscription",
    )
    repo.insert_payment_record(
        user_id=user["id"], transaction_ref="TXNDEMO02",
        amount=49.99, status="completed", description="Pro subscription duplicate",
    )

    scenarios = [
        ("BILLING", "My payment was deducted twice", f"I was charged twice for {demo_ref}. Please refund the duplicate."),
        ("TECHNICAL", "App crashes on login", "My application crashes every time I try to log in on Android 14."),
        ("ESCALATION", "Confused about everything", "Something feels off with my stuff. Not sure."),
    ]

    for label, subject, message in scenarios:
        print("\n" + "=" * 62)
        print(f"SCENARIO: {label}")
        print("=" * 62)
        ticket = repo.create_ticket(user_id=user["id"], subject=subject, message=message)
        repo.add_conversation(ticket["id"], user["id"], "customer", message)
        result = coordinator.process_ticket_sync(ticket["id"])
        print(f"Status         : {result.get('status')}")
        print(f"Category       : {result.get('category')}")
        print(f"Assigned agent : {result.get('assigned_agent')}")
        print(f"Reply          : {(result.get('customer_reply') or '')[:300]}")
        if result.get("sources"):
            print(f"Sources        : {result['sources']}")
        print("Trace:")
        print(json.dumps(result.get("trace", []), indent=2, default=str))

        if result.get("status") == "escalated":
            escalation = repo.get_escalation_by_ticket(ticket["id"])
            if escalation:
                print(f"Human escalation created: {escalation['id']} "
                      f"(priority {escalation['priority']})")
                verdict = coordinator.escalation.process_human_verdict(
                    escalation_id=escalation["id"],
                    verdict="Reviewed manually. Issue is a general inquiry; contacted customer for details.",
                    resolution="A human agent has reviewed your case and will follow up by email.",
                    action="resolve",
                )
                print(f"Human verdict applied -> ticket status: {verdict['ticket_status']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Customer Support AI runner")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api", help="Run the FastAPI backend")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(func=cmd_api)

    ui = sub.add_parser("ui", help="Run the Streamlit dashboard")
    ui.add_argument("--port", type=int, default=8501)
    ui.set_defaults(func=cmd_ui)

    sub.add_parser(
        "ui-react", help="Run the React (Vite) dashboard on :5173"
    ).set_defaults(func=cmd_ui_react)

    sub.add_parser("seed", help="Seed demo data").set_defaults(func=cmd_seed)
    sub.add_parser("ingest", help="Index knowledge base").set_defaults(func=cmd_ingest)
    sub.add_parser("doctor", help="Configuration report").set_defaults(func=cmd_doctor)
    sub.add_parser("demo", help="Run acceptance scenarios").set_defaults(func=cmd_demo)

    test = sub.add_parser("test", help="Run the pytest suite")
    test.add_argument("--verbose", action="store_true")
    test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
