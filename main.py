from pathlib import Path

from agent import SkillsAgent
from llm_client import LLMConfig, OpenAICompatibleClient, LLMError
from skill_runtime import SkillsRuntime


def main() -> None:
    runtime = SkillsRuntime(Path(__file__).parent / "skills")
    config = LLMConfig.from_env()
    llm = OpenAICompatibleClient(config)
    agent = SkillsAgent(runtime, llm)

    task = "帮我 Review 这个 Go PR，重点检查并发安全和错误处理"

    print("=== Skill Discovery ===")
    for skill in runtime.discover():
        print(f"- {skill.name}: {skill.description}")

    print("\n=== LLM Skill Selection ===")
    result = agent.run(task)
    print(f"Selected Skill: {result['selected_skill']}")
    print(f"Reason: {result['selection_reason']}")

    print("\n=== LLM Execution ===")
    print(result["answer"])


if __name__ == "__main__":
    try:
        main()
    except LLMError as exc:
        print(f"LLM Error: {exc}")
        raise SystemExit(1)
