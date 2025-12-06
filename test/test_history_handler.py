import pytest

pytest.skip(
    "Legacy tests for old history_handler internals; behavior is now covered by HistoryService tests in tests/ directory.",
    allow_module_level=True,
)

import json

from termi_cli.handlers import history_handler


def test_handle_history_summary_http_ollama_calls_generate_text(monkeypatch, mocker):
    """default_model Ollama phải đi vào nhánh HTTP và gọi api.generate_text trực tiếp."""

    console = mocker.MagicMock()
    config = {
        "language": "vi",
        "default_model": "ollama/qwen3:8b",
    }

    history = [
        {"role": "user", "parts": [{"text": "Hello"}]},
        {"role": "model", "parts": [{"text": "Hi there"}]},
    ]

    captured = {}

    def fake_generate_text(model_name, prompt, system_instruction):  # noqa: ARG001
        captured["model_name"] = model_name
        captured["prompt"] = prompt
        captured["system_instruction"] = system_instruction
        return "Tóm tắt mẫu"

    mocker.patch.object(history_handler.api, "generate_text", side_effect=fake_generate_text)
    mocker.patch.object(history_handler.api, "start_chat_session", side_effect=AssertionError("Should not start chat session"))
    mocker.patch.object(history_handler, "Markdown", lambda text: text)

    history_handler.handle_history_summary(console, config, history, cli_help_text="help")

    assert captured["model_name"] == "ollama/qwen3:8b"
    assert captured["system_instruction"] == "You are a helpful summarizer."
    assert "Hello" in captured["prompt"]
    console.print.assert_any_call("Tóm tắt mẫu")


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


def test_show_history_browser_filters_by_title(tmp_path, monkeypatch):
    console = DummyConsole(["1"])

    monkeypatch.setattr(history_handler, "HISTORY_DIR", str(tmp_path))
    monkeypatch.setattr(history_handler, "load_config", lambda: {"language": "vi"})

    file1 = tmp_path / "chat_alpha.json"
    file2 = tmp_path / "chat_beta.json"

    file1.write_text(
        json.dumps({"title": "Alpha chat", "history": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    file2.write_text(
        json.dumps({"title": "Beta feature search", "history": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    selected = history_handler.show_history_browser(console, filter_query="beta")

    assert selected is not None
    assert str(selected).endswith("chat_beta.json")
