from __future__ import annotations

import re

from pydantic import BaseModel


class SkillRef(BaseModel):
    id: str
    source: str = "bundled"
    pinned: bool = True


class WorkflowResolver:
    _SIMPLE_EXPLANATION = re.compile(
        r"(?:解释|说明|是什么|什么意思|怎么看|why|explain)",
        re.IGNORECASE,
    )
    _CODE_TASK = re.compile(
        r"(?:代码|编程|后端|前端|模块|重构|迁移|接口|API|数据库|权限|桌面|发布|"
        r"code|refactor|migration|database|permission|release|frontend|backend)",
        re.IGNORECASE,
    )
    _FEATURE_GROUPS = (
        re.compile(r"(?:架构|重构|模块|architecture|refactor|module)", re.IGNORECASE),
        re.compile(r"(?:数据库|迁移|schema|database|migration)", re.IGNORECASE),
        re.compile(r"(?:权限|安全|approval|permission|security)", re.IGNORECASE),
        re.compile(r"(?:桌面|发布|安装|更新|desktop|release|installer|update)", re.IGNORECASE),
        re.compile(r"(?:多个文件|多文件|三个模块|跨模块|multi.?file|cross.?module)", re.IGNORECASE),
        re.compile(r"(?:完整测试|验收|验证|回归|test|verify|acceptance)", re.IGNORECASE),
    )

    def resolve(self, request: str) -> list[SkillRef]:
        clean = " ".join(request.split())
        if not clean or not self._CODE_TASK.search(clean):
            return []
        if self._SIMPLE_EXPLANATION.search(clean) and not re.search(
            r"(?:修改|新增|实现|重构|迁移|发布|edit|implement|refactor|migrate|release)",
            clean,
            re.IGNORECASE,
        ):
            return []
        score = sum(1 for pattern in self._FEATURE_GROUPS if pattern.search(clean))
        if score < 2:
            return []
        return [
            SkillRef(id="using-superpowers"),
            SkillRef(id="brainstorming"),
            SkillRef(id="writing-plans"),
            SkillRef(id="using-git-worktrees"),
            SkillRef(id="test-driven-development"),
            SkillRef(id="requesting-code-review"),
            SkillRef(id="verification-before-completion"),
        ]
