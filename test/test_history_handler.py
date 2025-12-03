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
