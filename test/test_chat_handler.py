import pytest

pytest.skip(
    "Legacy tests for old chat_handler internals; behavior is now covered by ChatService tests in tests/ directory.",
    allow_module_level=True,
)

import json
from types import SimpleNamespace

from termi_cli.handlers import chat_handler


class DummyConsole:
    def __init__(self, inputs):
        self._inputs = list(inputs)
        self.print_calls = []

    def input(self, *args, **kwargs):
        if not self._inputs:
            raise AssertionError("Console.input called more times than expected")
        return self._inputs.pop(0)

    def print(self, *args, **kwargs):
        self.print_calls.append((args, kwargs))


def test_run_chat_mode_deepseek_with_ollama_model(tmp_path, monkeypatch, mocker):
    """run_chat_mode_deepseek phải gọi api.generate_text với model Ollama được chọn."""

    console = DummyConsole(["Tell me something", "exit", "My chat title"])
    config = {
        "language": "vi",
        "default_model": "ollama/qwen3:8b",
        "mini_agent": {"enabled": False, "rules": []},
    }
    args = SimpleNamespace(model="ollama/qwen3:8b", topic=None, load=None)

    monkeypatch.setattr(chat_handler, "HISTORY_DIR", str(tmp_path))
    mocker.patch.object(chat_handler.utils, "execute_suggested_commands")

    captured_calls = []

    def fake_generate_text(model_name, prompt, system_instruction=None):
        captured_calls.append(
            {
                "model_name": model_name,
                "prompt": prompt,
                "system_instruction": system_instruction,
            }
        )
        return "Assistant response"

    mocker.patch.object(chat_handler.api, "generate_text", side_effect=fake_generate_text)

    chat_handler.run_chat_mode_deepseek(
        console,
        config,
        args,
        system_instruction="Bạn là trợ lý hữu ích",
    )

    assert captured_calls  # phải có ít nhất một lần gọi
    assert captured_calls[0]["model_name"] == "ollama/qwen3:8b"
    assert "Tell me something" in captured_calls[0]["prompt"]
    assert captured_calls[0]["system_instruction"] == "Bạn là trợ lý hữu ích"

    files = list(tmp_path.glob("chat_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["title"] == "My chat title"
    assert len(payload["history"]) >= 1


def test_run_chat_mode_deepseek_respects_mini_agent_off_flag(tmp_path, monkeypatch, mocker):
    """run_chat_mode_deepseek: khi --mini-agent-off, không được gọi mini_agent.run_http_mini_agent."""

    console = DummyConsole(["Tell me something", "exit", "My chat title"])
    config = {
        "language": "vi",
        "default_model": "ollama/qwen3:8b",
        "mini_agent": {"enabled": True, "rules": []},
    }
    args = SimpleNamespace(model="ollama/qwen3:8b", topic=None, load=None, mini_agent_off=True)

    monkeypatch.setattr(chat_handler, "HISTORY_DIR", str(tmp_path))
    mocker.patch.object(chat_handler.utils, "execute_suggested_commands")

    mini_agent_mock = mocker.patch.object(
        chat_handler.mini_agent,
        "run_http_mini_agent",
        side_effect=AssertionError("mini-agent should not be called when --mini-agent-off is set"),
    )

    mocker.patch.object(chat_handler.api, "generate_text", return_value="Assistant response")

    chat_handler.run_chat_mode_deepseek(
        console,
        config,
        args,
        system_instruction="Bạn là trợ lý hữu ích",
    )

    mini_agent_mock.assert_not_called()
