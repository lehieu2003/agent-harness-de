"""
Prompt assembly.

This module owns how the base system prompt is combined with optional skill
instructions. Keeping this out of the agent loop makes prompt behavior easier
to test and evolve.
"""
from .skills import relevant_skills_block


SKILLS_HEADING = "# Relevant skill instructions"


def build_system_prompt(
    base_prompt: str,
    user_message: str,
    use_skills: bool = True,
    skill_loader=None,
) -> str:
    if not use_skills:
        return base_prompt

    if skill_loader is None:
        skill_loader = relevant_skills_block

    skills_block = skill_loader(user_message)
    if not skills_block:
        return base_prompt

    return f"{base_prompt}\n\n{SKILLS_HEADING}\n{skills_block}"
