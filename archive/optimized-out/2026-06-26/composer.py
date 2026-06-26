from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComposerOption:
    key: str
    label: str
    prompt_fragment: str


class ComposerService:
    OPTIONS = [
        ComposerOption("A", "词汇辨析", "Focus on CET-4 vocabulary contrasts and common collocations."),
        ComposerOption("B", "语法纠错", "Focus on grammar error correction and sentence structure."),
        ComposerOption("C", "阅读理解", "Focus on short reading comprehension with evidence-based answers."),
        ComposerOption("D", "翻译写作", "Focus on Chinese-English translation and compact writing practice."),
    ]

    def next_turn(self, goal: str, selected_options: list[str], extra_content: str) -> dict[str, Any]:
        selected_keys = {item.strip().upper() for item in selected_options}
        selected = [option for option in self.OPTIONS if option.key in selected_keys]
        if not selected:
            selected = [self.OPTIONS[0], self.OPTIONS[1]]

        goal_text = goal.strip() or "CET-4 English practice"
        extra_text = extra_content.strip()
        prompt_parts = [
            f"Learning goal: {goal_text}",
            "Selected practice modes:",
            *[f"- {option.key}. {option.label}: {option.prompt_fragment}" for option in selected],
        ]
        if extra_text:
            prompt_parts.append(f"Extra learner request: {extra_text}")
        prompt_parts.append("Generate the next practice round with one multiple-choice question first, then wait for the learner answer.")

        return {
            "options": [option.__dict__ for option in self.OPTIONS],
            "selected": [option.__dict__ for option in selected],
            "composed_prompt": "\n".join(prompt_parts),
            "assistant_message": "已组入你的选择。你可以点击“发送到主聊天”开始下一轮练习。",
        }
