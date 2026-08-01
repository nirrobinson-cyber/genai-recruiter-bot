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
from app.modules.embedding.build_index import build_index  # noqa: E402
from app.modules.scheduling.db_setup import DB_PATH, build_database  # noqa: E402
from app.state import ConversationState  # noqa: E402

# Generic, company-agnostic palette — not tied to any employer's brand.
# A modern indigo-to-cyan pair plus neutral slate text/greys.
BRAND_PRIMARY = "#4F46E5"
BRAND_DEEP = "#4338CA"
BRAND_ACCENT = "#06B6D4"
BRAND_TEXT = "#1F2937"
BRAND_MUTED = "#64748B"

st.set_page_config(page_title="Python Developer — Recruiting Chat", page_icon="🐍")


def _inject_brand_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
        button, input, textarea {{
            font-family: 'Poppins', sans-serif;
        }}

        div.stButton > button, div.stFormSubmitButton > button {{
            background-color: {BRAND_PRIMARY};
            color: #fff;
            border: none;
            border-radius: 8px;
            font-weight: 500;
            padding: 0.5rem 1.25rem;
            transition: background-color 0.15s ease;
        }}
        div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
            background-color: {BRAND_DEEP};
            color: #fff;
        }}

        [data-testid="stChatMessage"] {{
            border-radius: 14px;
            border: 1px solid #e6ebf0;
            background-color: #ffffff;
        }}

        [data-testid="stForm"] {{
            background: #ffffff;
            border: 1px solid #e6ebf0;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
        }}

        .app-badge {{
            display: inline-block;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }}
        .app-badge-continue {{ background: #EEF2FF; color: {BRAND_PRIMARY}; }}
        .app-badge-schedule {{ background: #FFF4D6; color: #A9740A; }}
        .app-badge-end {{ background: #FBE3E3; color: #C23B3B; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    col_mark, col_title = st.columns([1, 6], vertical_alignment="center")
    with col_mark:
        st.markdown(
            f"<div style='width:48px;height:48px;border-radius:14px;"
            f"background:linear-gradient(135deg,{BRAND_PRIMARY},{BRAND_ACCENT});"
            f"display:flex;align-items:center;justify-content:center;font-size:24px;"
            f"box-shadow:0 2px 8px rgba(79,70,229,0.25);'>🐍</div>",
            unsafe_allow_html=True,
        )
    with col_title:
        st.markdown(
            f"<div style='margin:0;'>"
            f"<h1 style='margin:0;font-size:1.5rem;font-weight:600;color:{BRAND_TEXT};'>"
            f"Python Developer — Recruiting Chat</h1>"
            f"<p style='margin:0;color:{BRAND_MUTED};font-size:0.85rem;'>"
            f"AI-powered recruiting assistant</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<hr style='margin-top:0.5rem;margin-bottom:1rem;border:none;"
        f"border-top:3px solid {BRAND_PRIMARY};'>",
        unsafe_allow_html=True,
    )


@st.cache_resource
def _ensure_data_stores_built() -> None:
    """Streamlit Community Cloud clones a fresh, ephemeral checkout on every
    deploy/reboot, and data/tech.db + data/chroma/ are gitignored/rebuildable
    by design (spec §12) — so they never exist there, and Cloud gives no shell
    to run the setup scripts manually. Build them once per container instead.
    `st.cache_resource` makes this run exactly once per process even though
    Streamlit re-executes the whole script on every rerun. Locally this is a
    no-op once `python -m app.modules.scheduling.db_setup` /
    `build_index` have already been run per the README setup steps.
    """
    if not DB_PATH.exists():
        with st.spinner("First run: building the scheduling database..."):
            build_database()
    chroma_dir = Path(get_settings().chroma_persist_dir)
    if not chroma_dir.exists() or not any(chroma_dir.iterdir()):
        with st.spinner("First run: building the job-description vector index..."):
            build_index()


_ensure_data_stores_built()


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
    _render_header()
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
    label = {"continue": "continue", "schedule": "schedule", "end": "end"}.get(action, action)
    return f'<span class="app-badge app-badge-{action}">{label}</span>'


def _render_chat(state: ConversationState) -> None:
    _render_header()

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
                    st.markdown(
                        _action_badge(state.advisor_outputs[output_index]["action"]),
                        unsafe_allow_html=True,
                    )
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
    _inject_brand_css()
    _init_state()
    _render_sidebar(st.session_state.conv_state)

    if not st.session_state.registered:
        _render_registration_form()
    else:
        _render_chat(st.session_state.conv_state)


if __name__ == "__main__":
    main()
