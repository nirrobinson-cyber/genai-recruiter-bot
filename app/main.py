"""CLI entry point — terminal chat loop (full implementation in Phase 4, GRB-043).

Run:  python -m app.main --help
"""

import argparse

from app.config import get_settings, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genai-recruiter-bot",
        description="Multi-agent SMS-style recruiting chatbot (terminal PoC).",
    )
    parser.add_argument("--check-config", action="store_true", help="Validate settings and exit.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    setup_logging()
    settings = get_settings()
    if args.check_config:
        print(f"Config OK — main model: {settings.main_agent_model}, now(): {settings.now()}")
        return
    print("Chat loop not implemented yet — arrives in Phase 4 (GRB-043). Try --check-config.")


if __name__ == "__main__":
    main()
