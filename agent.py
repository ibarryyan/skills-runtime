from __future__ import annotations

import json
from dataclasses import dataclass

from llm_client import OpenAICompatibleClient
from skill_runtime import SkillMetadata, SkillsRuntime


SYSTEM_PROMPT = """你是一个运行在 Skills Runtime 上的 AI Agent。

你会获得：
1. 用户任务
2. 当前可用 Skill 的名称和描述
3. 被激活 Skill 的完整 Instructions

请遵循这些规则：
- Skill 是行为规范和工作流程，不要把它当作普通背景知识。
- 如果当前任务与激活 Skill 的 Instructions 冲突，以更明确的用户要求和系统要求为准。
- 不要声称执行了实际 Tool / Script，除非运行环境确实提供并执行了它。
- 输出应直接解决用户任务。
"""


@dataclass(frozen=True)
class SkillSelection:
    name: str
    reason: str


class SkillsAgent:
    """LLM-backed agent that uses SkillsRuntime for capability discovery and loading."""

    def __init__(self, runtime: SkillsRuntime, llm: OpenAICompatibleClient) -> None:
        self.runtime = runtime
        self.llm = llm

    def select_skill(self, task: str) -> SkillSelection:
        candidates = self.runtime.discover()
        if not candidates:
            raise RuntimeError("No Skills discovered")

        catalog = "\n".join(
            f'- {skill.name}: {skill.description}'
            for skill in candidates
        )

        prompt = f"""请从下面的 Skill 列表中选择最适合当前任务的一个 Skill。

只允许选择列表中的 name。
返回严格 JSON，不要输出 Markdown：
{{"name":"skill-name","reason":"为什么选择它"}}

当前任务：
{task}

可用 Skills：
{catalog}
"""

        raw = self.llm.chat(
            [
                {"role": "system", "content": "你是一个 Skill Selector，只负责选择最匹配的 Skill。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )

        try:
            data = json.loads(raw)
            name = str(data["name"]).strip()
            reason = str(data.get("reason", "")).strip()
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Skill selector returned invalid JSON: {raw}") from exc

        valid_names = {skill.name for skill in candidates}
        if name not in valid_names:
            raise RuntimeError(
                f"LLM selected unknown Skill '{name}'. Valid Skills: {sorted(valid_names)}"
            )

        return SkillSelection(name=name, reason=reason)

    def run(self, task: str) -> dict[str, str]:
        selection = self.select_skill(task)
        skill = self.runtime.load(selection.name)
        skill_context = self.runtime.context_builder.build(skill)

        user_prompt = f"""当前用户任务：
{task}

当前激活的 Skill：
{skill_context}

请基于用户任务和 Skill Instructions 给出最终结果。
不要编造已经执行的脚本、工具或外部系统操作。
"""

        answer = self.llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        return {
            "selected_skill": selection.name,
            "selection_reason": selection.reason,
            "answer": answer,
        }
