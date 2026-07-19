"""CLI entry point — terminal chat loop for the recruiting chatbot."""

from __future__ import annotations

import argparse

from app.config import get_settings, setup_logging
from app.graph import run_turn
from app.state import ConversationState


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

    state = ConversationState()
    print("Recruiter bot ready. Type 'quit' to exit.")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"quit", "exit"}:
            print("Bot: Thanks for chatting.")
            break
        result = run_turn(user_input, state)
        print(f"Bot [{result['action']}]: {result['message']}")
        for step in result["trace"]:
            print(f"  trace: {step['advisor']} -> {step['decision']} ({step['reason']})")


if __name__ == "__main__":
    main()
