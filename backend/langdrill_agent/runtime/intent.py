from __future__ import annotations

import re

from pydantic import BaseModel


class CapabilityIntent(BaseModel):
    requires_runtime: bool
    confidence: float
    reason: str


class CapabilityIntentClassifier:
    ACTION = re.compile(
        r"(?:帮我|请|需要).{0,18}(?:增加|实现|安装|配置|处理|整理|修改|构建|运行)"
        r"|\b(?:install|build|edit|run)\b",
        re.IGNORECASE,
    )
    LEARNING = re.compile(r"(?:出题|刷题|练习|讲解|复盘|单词|阅读题)")

    def classify(self, text: str) -> CapabilityIntent:
        if self.LEARNING.search(text):
            return CapabilityIntent(
                requires_runtime=False,
                confidence=0.9,
                reason="learning_flow",
            )
        matched = bool(self.ACTION.search(text))
        return CapabilityIntent(
            requires_runtime=matched,
            confidence=0.75 if matched else 0.2,
            reason="explicit_action" if matched else "chat",
        )
