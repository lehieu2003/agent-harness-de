import unittest

from harness.prompts import SKILLS_HEADING, build_system_prompt


class PromptAssemblyTests(unittest.TestCase):
    def test_build_system_prompt_returns_base_when_skills_disabled(self):
        result = build_system_prompt(
            base_prompt="base",
            user_message="use data quality skills",
            use_skills=False,
            skill_loader=lambda _: "skill instructions",
        )

        self.assertEqual(result, "base")

    def test_build_system_prompt_returns_base_when_no_skills_match(self):
        result = build_system_prompt(
            base_prompt="base",
            user_message="hello",
            skill_loader=lambda _: "",
        )

        self.assertEqual(result, "base")

    def test_build_system_prompt_appends_matching_skill_block(self):
        result = build_system_prompt(
            base_prompt="base",
            user_message="pipeline failed",
            skill_loader=lambda _: "investigate first",
        )

        self.assertIn("base", result)
        self.assertIn(SKILLS_HEADING, result)
        self.assertIn("investigate first", result)


if __name__ == "__main__":
    unittest.main()
