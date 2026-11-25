"""技能加载器：把 SKILL.md 变成可注入上下文的能力包。

设计来源：nanobot 的 ``agent/skills.py``（扫描 workspace/skills/*/SKILL.md，
只把摘要塞进 system prompt，用到时再加载全文）。

这一点很重要：**工具是函数，技能是说明书**。工具告诉模型「能调什么」，
技能告诉模型「什么时候该调、按什么流程调」。两者分开，能力才能热插拔。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    path: Path

    def content(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except OSError:
            return ""


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _meta(text: str) -> dict[str, str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("'\"")
    return result


class SkillsLoader:
    """扫描若干目录：目录自身的 SKILL.md，或子目录里的 SKILL.md。"""

    def __init__(self, *roots: Path) -> None:
        self.roots = [Path(r) for r in roots]
        self._skills: list[Skill] | None = None

    def list_skills(self) -> list[Skill]:
        if self._skills is not None:
            return self._skills
        found: list[Skill] = []
        seen: set[Path] = set()
        for root in self.roots:
            if not root.exists():
                continue
            candidates = [root / "SKILL.md"]
            if root.is_dir():
                candidates += sorted(root.glob("*/SKILL.md"))
            for path in candidates:
                if not path.is_file() or path.resolve() in seen:
                    continue
                seen.add(path.resolve())
                meta = _meta(path.read_text(encoding="utf-8", errors="replace"))
                found.append(Skill(
                    name=meta.get("name") or path.parent.name or "skill",
                    description=meta.get("description") or "（未提供描述）",
                    path=path,
                ))
        self._skills = found
        return found

    def summary(self) -> str:
        skills = self.list_skills()
        if not skills:
            return "（当前没有加载技能）"
        return "\n".join(f"- {s.name}: {s.description}" for s in skills)

    def load(self, name: str) -> str:
        for skill in self.list_skills():
            if skill.name == name:
                return skill.content()
        return ""
