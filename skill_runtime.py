from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class SkillError(Exception):
    """Base exception for Skill Runtime errors."""


class SkillFormatError(SkillError):
    """Raised when SKILL.md is malformed."""


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path


@dataclass(frozen=True)
class LoadedSkill:
    metadata: SkillMetadata
    instructions: str
    resources: dict[str, list[Path]] = field(default_factory=dict)


class SkillLoader:
    """Read Skill metadata first, then load full Skill content on demand."""

    FRONTMATTER_RE = re.compile(
        r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z",
        re.DOTALL,
    )

    def read_metadata(self, skill_dir: Path) -> SkillMetadata:
        skill_dir = skill_dir.resolve()
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            raise SkillFormatError(f"SKILL.md not found: {skill_file}")

        frontmatter, _ = self._read_skill_file(skill_file)
        name = self._scalar(frontmatter, "name")
        description = self._scalar(frontmatter, "description")

        if not name:
            raise SkillFormatError(f"Missing 'name' in {skill_file}")
        if not description:
            raise SkillFormatError(f"Missing 'description' in {skill_file}")

        return SkillMetadata(name=name, description=description, path=skill_dir)

    def load(self, metadata: SkillMetadata) -> LoadedSkill:
        skill_file = metadata.path / "SKILL.md"
        frontmatter, instructions = self._read_skill_file(skill_file)

        name = self._scalar(frontmatter, "name")
        description = self._scalar(frontmatter, "description")
        if name != metadata.name or description != metadata.description:
            raise SkillFormatError(
                f"Skill metadata changed after discovery: {metadata.path}"
            )

        return LoadedSkill(
            metadata=metadata,
            instructions=instructions.strip(),
            resources=self._discover_resources(metadata.path),
        )

    def _read_skill_file(self, skill_file: Path) -> tuple[dict[str, str], str]:
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise SkillError(f"Failed to read {skill_file}: {exc}") from exc

        match = self.FRONTMATTER_RE.match(content)
        if not match:
            raise SkillFormatError(
                f"Invalid frontmatter in {skill_file}: expected --- ... ---"
            )

        frontmatter: dict[str, str] = {}
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            frontmatter[key.strip()] = value.strip().strip("'\"")

        return frontmatter, match.group(2)

    @staticmethod
    def _scalar(frontmatter: dict[str, str], key: str) -> str:
        return frontmatter.get(key, "").strip()

    @staticmethod
    def _discover_resources(skill_dir: Path) -> dict[str, list[Path]]:
        result: dict[str, list[Path]] = {}
        for dirname in ("scripts", "references", "assets"):
            directory = skill_dir / dirname
            if directory.is_dir():
                result[dirname] = sorted(
                    p for p in directory.rglob("*") if p.is_file()
                )
            else:
                result[dirname] = []
        return result


class SkillRegistry:
    """Discover and index Skills without eagerly loading their instructions."""

    def __init__(self, loader: SkillLoader | None = None) -> None:
        self.loader = loader or SkillLoader()
        self._skills: dict[str, SkillMetadata] = {}

    def discover(self, root: Path) -> list[SkillMetadata]:
        root = root.resolve()
        if not root.is_dir():
            raise SkillError(f"Skills directory not found: {root}")

        discovered: list[SkillMetadata] = []
        for skill_file in sorted(root.rglob("SKILL.md")):
            metadata = self.loader.read_metadata(skill_file.parent)
            existing = self._skills.get(metadata.name)
            if existing and existing.path != metadata.path:
                raise SkillError(
                    f"Duplicate Skill name '{metadata.name}':\n"
                    f"  - {existing.path}\n"
                    f"  - {metadata.path}"
                )
            self._skills[metadata.name] = metadata
            discovered.append(metadata)
        return discovered

    def get(self, name: str) -> SkillMetadata | None:
        return self._skills.get(name)

    def all(self) -> list[SkillMetadata]:
        return sorted(self._skills.values(), key=lambda skill: skill.name)


class SkillMatcher:
    """Simple deterministic lexical fallback matcher."""

    STOP_WORDS = {
        "the", "a", "an", "this", "that", "is", "are", "to", "for", "of",
        "and", "or", "with", "please", "help", "me", "一下", "帮我", "看看",
        "这个", "的", "了", "请", "帮", "我",
    }

    def match(
        self,
        task: str,
        skills: Iterable[SkillMetadata],
        top_k: int = 3,
    ) -> list[tuple[SkillMetadata, float]]:
        task_tokens = self._tokens(task)
        task_text = task.lower()
        scored: list[tuple[SkillMetadata, float]] = []

        for skill in skills:
            name_tokens = self._tokens(skill.name.replace("-", " "))
            description_tokens = self._tokens(skill.description)
            name_overlap = task_tokens & name_tokens
            desc_overlap = task_tokens & description_tokens
            score = (2.0 * len(name_overlap) + len(desc_overlap)) / max(len(task_tokens), 1)

            if "review" in task_text and "review" in skill.name.lower():
                score += 0.5
            if "go" in task_tokens and "go" in skill.name.lower():
                score += 0.15

            if name_overlap or desc_overlap or score > 0:
                scored.append((skill, score))

        scored.sort(key=lambda item: (-item[1], item[0].name))
        return scored[:top_k]

    def _tokens(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9_+#.-]+|[\u4e00-\u9fff]", text.lower())
        return {word for word in words if word not in self.STOP_WORDS}


class SkillContextBuilder:
    """Render a loaded Skill into text that can be injected into an LLM context."""

    def build(self, skill: LoadedSkill) -> str:
        lines = [
            f"# Active Skill: {skill.metadata.name}",
            "",
            "## Description",
            skill.metadata.description,
            "",
            "## Instructions",
            skill.instructions,
        ]

        resource_lines: list[str] = []
        for category, paths in skill.resources.items():
            if not paths:
                continue
            resource_lines.append(f"- {category}:")
            resource_lines.extend(
                f"  - {path.relative_to(skill.metadata.path)}" for path in paths
            )

        if resource_lines:
            lines.extend(["", "## Available Resources", *resource_lines])

        return "\n".join(lines).strip()


class SkillsRuntime:
    """Skill management layer: discovery, matching, loading and context building."""

    def __init__(self, skills_dir: Path) -> None:
        self.loader = SkillLoader()
        self.registry = SkillRegistry(self.loader)
        self.matcher = SkillMatcher()
        self.context_builder = SkillContextBuilder()
        self.skills_dir = skills_dir.resolve()
        self.refresh()

    def refresh(self) -> list[SkillMetadata]:
        self.registry = SkillRegistry(self.loader)
        return self.registry.discover(self.skills_dir)

    def discover(self) -> list[SkillMetadata]:
        return self.registry.all()

    def match(self, task: str, top_k: int = 3) -> list[tuple[SkillMetadata, float]]:
        return self.matcher.match(task, self.registry.all(), top_k=top_k)

    def load(self, skill_name: str) -> LoadedSkill:
        metadata = self.registry.get(skill_name)
        if metadata is None:
            raise SkillError(f"Skill not found: {skill_name}")
        return self.loader.load(metadata)

    def build_context(self, skill_name: str) -> str:
        return self.context_builder.build(self.load(skill_name))
