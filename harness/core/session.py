"""
Session persistence: save/load conversation state so a session
can be resumed later.
"""
import json
import os
import re
import uuid

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def new_session_id() -> str:
    return str(uuid.uuid4())[:8]


def _session_path(session_id: str) -> str:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("Invalid session ID.")
    sessions_root = os.path.abspath(SESSIONS_DIR)
    path = os.path.abspath(os.path.join(sessions_root, f"{session_id}.json"))
    if os.path.commonpath([sessions_root, path]) != sessions_root:
        raise ValueError("Invalid session path.")
    return path


def save_session(session_id: str, messages: list):
    path = _session_path(session_id)
    with open(path, "w") as f:
        json.dump(messages, f, indent=2, default=str)


def load_session(session_id: str) -> list:
    path = _session_path(session_id)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def list_sessions() -> list[str]:
    return [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
