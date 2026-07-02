"""
Session persistence: save/load conversation state so a session
can be resumed later.
"""
import json
import os
import uuid

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def new_session_id() -> str:
    return str(uuid.uuid4())[:8]


def save_session(session_id: str, messages: list):
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path, "w") as f:
        json.dump(messages, f, indent=2, default=str)


def load_session(session_id: str) -> list:
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def list_sessions() -> list[str]:
    return [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
