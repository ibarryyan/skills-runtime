import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import SkillsAgent
from llm_client import LLMConfig, OpenAICompatibleClient
from skill_runtime import SkillsRuntime


class MockLLMHandler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body)
        MockLLMHandler.calls.append(payload)

        messages = payload.get("messages", [])
        user_content = messages[-1]["content"] if messages else ""
        if "Skill Selector" in messages[0]["content"]:
            content = json.dumps(
                {"name": "code-review", "reason": "任务明确要求 Review Go PR"},
                ensure_ascii=False,
            )
        else:
            content = "根据 Code Review Skill，应重点检查并发安全、错误处理和测试覆盖。"

        response = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


class SkillsLLMIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.runtime = SkillsRuntime(root / "skills")
        MockLLMHandler.calls.clear()
        config = LLMConfig(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            api_key="test-key",
            model="mock-model",
            timeout=5,
        )
        self.agent = SkillsAgent(
            self.runtime,
            OpenAICompatibleClient(config),
        )

    def test_runtime(self):
        matches = self.runtime.match("帮我 Review 这个 Go PR")
        self.assertEqual(matches[0][0].name, "code-review")
        self.assertTrue(self.runtime.load("code-review").instructions)

    def test_llm_selection_and_execution(self):
        result = self.agent.run("帮我 Review 这个 Go PR，重点检查并发安全和错误处理")
        self.assertEqual(result["selected_skill"], "code-review")
        self.assertIn("并发安全", result["answer"])
        self.assertEqual(len(MockLLMHandler.calls), 2)
        self.assertEqual(MockLLMHandler.calls[0]["model"], "mock-model")


if __name__ == "__main__":
    unittest.main()
