"""Streamlit PoC (spec §8, Epic E6): registration form -> chat UI -> dev trace panel.

Zero decision logic lives here — every turn goes through the exact same
`app.graph.run_turn` entry point the terminal loop (`app/main.py`) uses.
This module only renders `ConversationState`/`run_turn` output.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# `streamlit run` only ever puts this script's OWN directory on sys.path, not
# its parent — so `app` (at the repo root) only resolves if the caller
# happened to already have the repo root on sys.path (e.g. cwd == repo root
# in some shells). Make this launchable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Bridge Streamlit Community Cloud secrets to the environment BEFORE
# app.config's settings singleton is ever constructed (it reads os.environ /
# .env via pydantic-settings) — locally, .env is used instead. Accessing
# st.secrets raises StreamlitSecretNotFoundError when no secrets.toml exists
# at all (the normal local-dev case), not just when a key is missing.
try:
    _secrets = dict(st.secrets)
except Exception:
    _secrets = {}
for _key in ("OPENAI_API_KEY", "DEMO_NOW_OVERRIDE"):
    if _key in _secrets:
        os.environ[_key] = str(_secrets[_key])

from app.config import get_settings  # noqa: E402
from app.graph import run_turn  # noqa: E402
from app.state import ConversationState  # noqa: E402

st.set_page_config(page_title="GenAI Recruiter Bot", page_icon="💬")


def _opening_message(registration: dict[str, Any]) -> str:
    name = registration["full_name"].split()[0] if registration["full_name"].strip() else "there"
    return (
        f"Hi {name}, thanks for applying to our Python Developer opening! "
        "Tell me a bit about your recent Python projects, or ask me anything about the role."
    )


def _init_state() -> None:
    if "conv_state" not in st.session_state:
        st.session_state.conv_state = None
        st.session_state.registered = False
        st.session_state.dev_mode = False


def _reset() -> None:
    st.session_state.conv_state = None
    st.session_state.registered = False


def _render_registration_form() -> None:
    st.title("Python Developer — Recruiting Chat")
    st.write("A few details before we start (per the flowchart's registration entry point).")
    with st.form("registration_form"):
        full_name = st.text_input("Full name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        years_experience = st.number_input(
            "Years of Python experience", min_value=0, max_value=50, step=1
        )
        submitted = st.form_submit_button("Start chatting")

    if submitted:
        if not full_name.strip():
            st.error("Full name is required.")
            return
        registration = {
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "years_experience": int(years_experience),
        }
        state = ConversationState(registration_data=registration)
        state.add_message("assistant", _opening_message(registration))
        st.session_state.conv_state = state
        st.session_state.registered = True
        st.rerun()


def _action_badge(action: str) -> str:
    return {"continue": "🟦 continue", "schedule": "🟨 schedule", "end": "🟥 end"}.get(
        action, action
    )


def _render_chat(state: ConversationState) -> None:
    st.title("Python Developer — Recruiting Chat")

    # advisor_outputs has exactly one entry per assistant turn EXCEPT the
    # synthetic opening greeting added at registration, which has no
    # advisor_outputs entry (no advisor was consulted for it) — align from
    # the end so the greeting is skipped, not misaligned against a real turn.
    assistant_turns = [turn for turn in state.history if turn["role"] == "assistant"]
    turns_without_output = len(assistant_turns) - len(state.advisor_outputs)

    assistant_seen = 0
    for turn in state.history:
        with st.chat_message(turn["role"]):
            st.write(turn["content"])
            if turn["role"] == "assistant":
                output_index = assistant_seen - turns_without_output
                if st.session_state.dev_mode and output_index >= 0:
                    st.caption(_action_badge(state.advisor_outputs[output_index]["action"]))
                assistant_seen += 1

    last_action = state.advisor_outputs[-1]["action"] if state.advisor_outputs else None
    if last_action == "end":
        st.info("Conversation ended. Use **Reset** in the sidebar to start a new one.")
        return

    user_input = st.chat_input("Type your reply...")
    if user_input:
        run_turn(user_input, state)
        st.rerun()


def _render_sidebar(state: ConversationState | None) -> None:
    with st.sidebar:
        st.session_state.dev_mode = st.toggle(
            "Dev mode (action badges + trace panel)", value=st.session_state.dev_mode
        )
        if st.button("Reset conversation"):
            _reset()
            st.rerun()

        if not st.session_state.dev_mode or state is None:
            return

        st.divider()
        st.subheader("Dev trace panel")
        if not state.advisor_outputs:
            st.caption("No turns yet.")
            return

        for turn_number, output in enumerate(state.advisor_outputs, start=1):
            with st.expander(
                f"Turn {turn_number} — {output['action']}",
                expanded=(turn_number == len(state.advisor_outputs)),
            ):
                st.write(f"**consulted:** {', '.join(output.get('consulted', [])) or '(none)'}")
                for step in output.get("trace", []):
                    st.write(f"- **{step['advisor']}** -> `{step['decision']}` — {step['reason']}")
                    if step.get("slots"):
                        st.write("  slots:", step["slots"])
                    if step.get("sources"):
                        st.write("  retrieved chunks:", step["sources"])
                if output.get("slots"):
                    st.write("**offered slots:**", output["slots"])


def main() -> None:
    get_settings()  # fail fast on missing config, same as `python -m app.main --check-config`
    _init_state()
    _render_sidebar(st.session_state.conv_state)

    if not st.session_state.registered:
        _render_registration_form()
    else:
        _render_chat(st.session_state.conv_state)


if __name__ == "__main__":
    main()
