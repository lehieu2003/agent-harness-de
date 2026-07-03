"""
Built-in skills: markdown files with domain-specific instructions,
loaded into the system prompt when relevant.

Drop a `.md` file in the skills/ directory with a one-line description
as the first line, and it becomes available to the agent.
"""
import os

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")


def list_skills() -> dict[str, str]:
    """Returns {skill_name: description} for all available skills."""
    skills = {}
    if not os.path.exists(SKILLS_DIR):
        return skills
    for fname in os.listdir(SKILLS_DIR):
        if fname.endswith(".md"):
            path = os.path.join(SKILLS_DIR, fname)
            with open(path) as f:
                first_line = f.readline().strip().lstrip("#").strip()
            skills[fname.replace(".md", "")] = first_line
    return skills


def load_skill(name: str) -> str:
    path = os.path.join(SKILLS_DIR, f"{name}.md")
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read()


def relevant_skills_block(user_message: str) -> str:
    """
    Simplest possible relevance check: keyword match against skill
    descriptions. Upgrade to an LLM call for smarter routing later.
    """
    skills = list_skills()
    matched = []
    lowered = user_message.lower()
    for name, desc in skills.items():
        keywords = [w.lower() for w in desc.split() if len(w) > 4]
        if any(kw in lowered for kw in keywords):
            matched.append(load_skill(name))
    if not matched:
        return ""
    return "\n\n---\n\n".join(matched)
