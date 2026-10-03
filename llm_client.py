from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LLMError(RuntimeError):
    """Raised when an LLM request fails or returns an unexpected response."""


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 120.0
    ssl_verify: bool = True
    ca_bundle: str | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = ""
        api_key = ""
        model = ""
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", base_url),
                ("LLM_API_KEY", api_key),
                ("LLM_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise LLMError(
                "Missing environment variables: " + ", ".join(missing)
            )

        try:
            timeout = float(os.getenv("LLM_TIMEOUT", "120"))
        except ValueError as exc:
            raise LLMError("LLM_TIMEOUT must be a number") from exc

        ssl_verify = _parse_bool(
            os.getenv("LLM_SSL_VERIFY", "false"),
            name="LLM_SSL_VERIFY",
        )

        ca_bundle = os.getenv("LLM_CA_BUNDLE", "").strip() or None
        if ca_bundle:
            ca_path = Path(ca_bundle).expanduser()
            if not ca_path.is_file():
                raise LLMError(
                    f"LLM_CA_BUNDLE does not exist or is not a file: {ca_path}"
                )

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            ssl_verify=ssl_verify,
            ca_bundle=ca_bundle,
        )


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise LLMError(
        f"{name} must be one of true/false, 1/0, yes/no, on/off"
    )


class OpenAICompatibleClient:
    """Tiny client for OpenAI-compatible /chat/completions APIs."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.ssl_context = self._build_ssl_context()

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }

        url = self._endpoint()
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout,
                context=self.ssl_context,
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMError(
                f"LLM HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            raise LLMError(
                f"Failed to reach LLM endpoint: {reason}"
            ) from exc
        except TimeoutError as exc:
            raise LLMError("LLM request timed out") from exc
        except ssl.SSLError as exc:
            raise LLMError(
                "TLS/SSL error while connecting to LLM endpoint: "
                f"{exc}"
            ) from exc

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(
                f"Unexpected LLM response: {raw[:1000]}"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM returned empty content")

        return content.strip()

    def _build_ssl_context(self) -> ssl.SSLContext:
        if not self.config.ssl_verify:
            # Development/test only. This disables server certificate verification.
            return ssl._create_unverified_context()  # noqa: SLF001

        if self.config.ca_bundle:
            return ssl.create_default_context(
                cafile=self.config.ca_bundle,
            )

        return ssl.create_default_context()

    def _endpoint(self) -> str:
        base = self.config.base_url
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"
