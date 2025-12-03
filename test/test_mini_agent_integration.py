from termi_cli import cli as cli_module
from termi_cli import __main__ as cli_entry


def test_single_turn_http_uses_mini_agent_before_generate_text(tmp_path, monkeypatch, mocker):
    """Single-turn với default_model HTTP phải gọi mini_agent trước khi fallback LLM."""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))

    # Config stub: dùng HTTP model (deepseek-chat) để đi vào nhánh HTTP
    config = {
        "language": "vi",
        "default_model": "deepseek-chat",
        "code_model": "deepseek-chat",
        "commit_model": "deepseek-chat",
        "agent_model": "models/gemini-pro-latest",
        "mini_agent": {
            "enabled": True,
            "rules": [],
        },
    }

    mocker.patch.object(cli_entry, "load_config", return_value=config)
    mocker.patch.object(cli_entry.api, "GEMINI_AVAILABLE", True)
    mocker.patch.object(cli_entry, "genai", None)

    # Đảm bảo _run_single_turn không cố đọc stdin thật dưới pytest
    class DummyStdin:
        def isatty(self):  # pragma: no cover - trivial shim
            return True

    monkeypatch.setattr(cli_entry.sys, "stdin", DummyStdin(), raising=False)

    captured = {}

    def fake_run_http_mini_agent(prompt_text, user_intent, config=None, **_):  # noqa: ARG001
        captured["prompt_text"] = prompt_text
        captured["user_intent"] = user_intent
        return "MINI_AGENT_RESULT"

    mocker.patch.object(cli_entry.mini_agent, "run_http_mini_agent", side_effect=fake_run_http_mini_agent)

    # Nếu generate_text được gọi thì coi như mini-agent không short-circuit được
    def fail_generate_text(*args, **kwargs):  # noqa: ARG002
        raise AssertionError("generate_text should not be called when mini-agent returns a result")

    mocker.patch.object(cli_entry.api, "generate_text", side_effect=fail_generate_text)

    parser = cli_module.create_parser()
    args = parser.parse_args(["Weather in HCMC tomorrow"])

    # Gọi main() trực tiếp với provided_args để dùng cùng process (cho phép patching)
    cli_entry.main(provided_args=args)

    # Đảm bảo mini-agent đã được gọi với đúng prompt
    assert captured["prompt_text"] == "Weather in HCMC tomorrow"
    assert captured["user_intent"] == "Weather in HCMC tomorrow"


def test_single_turn_http_with_ollama_cloud_routes_generate_text(tmp_path, monkeypatch, mocker):
    """Single-turn với default_model Ollama Cloud vẫn phải dùng nhánh HTTP và gọi generate_text."""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))

    config = {
        "language": "vi",
        "default_model": "ollama-cloud/qwen3-coder:480b-cloud",
        "mini_agent": {"enabled": True, "rules": []},
    }

    mocker.patch.object(cli_entry, "load_config", return_value=config)

    class DummyStdin:
        def isatty(self):  # pragma: no cover - shim
            return True

    monkeypatch.setattr(cli_entry.sys, "stdin", DummyStdin(), raising=False)

    mocker.patch.object(cli_entry.mini_agent, "run_http_mini_agent", return_value=None)

    captured = {}

    def fake_generate_text(model_name, prompt, system_instruction=None):  # noqa: ARG001
        captured["model_name"] = model_name
        captured["prompt"] = prompt
        return "OK"

    mocker.patch.object(cli_entry.api, "generate_text", side_effect=fake_generate_text)

    parser = cli_module.create_parser()
    args = parser.parse_args(["Tell me something"])

    cli_entry.main(provided_args=args)

    assert captured["model_name"] == "ollama-cloud/qwen3-coder:480b-cloud"
    assert captured["prompt"] == "Tell me something"


def test_single_turn_http_respects_mini_agent_off_flag(tmp_path, monkeypatch, mocker):
    """Single-turn HTTP với --mini-agent-off phải bỏ qua mini-agent và gọi generate_text trực tiếp."""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))

    config = {
        "language": "vi",
        "default_model": "deepseek-chat",
        "code_model": "deepseek-chat",
        "commit_model": "deepseek-chat",
        "agent_model": "models/gemini-pro-latest",
        "mini_agent": {
            "enabled": True,
            "rules": [],
        },
    }

    mocker.patch.object(cli_entry, "load_config", return_value=config)
    mocker.patch.object(cli_entry.api, "GEMINI_AVAILABLE", True)
    mocker.patch.object(cli_entry, "genai", None)

    class DummyStdin:
        def isatty(self):  # pragma: no cover - trivial shim
            return True

    monkeypatch.setattr(cli_entry.sys, "stdin", DummyStdin(), raising=False)

    # Mini-agent không được phép được gọi khi bật --mini-agent-off
    mini_agent_mock = mocker.patch.object(
        cli_entry.mini_agent,
        "run_http_mini_agent",
        side_effect=AssertionError("mini-agent should not be called when --mini-agent-off is set"),
    )

    captured = {}

    def fake_generate_text(model_name, prompt, system_instruction=None):  # noqa: ARG001
        captured["model_name"] = model_name
        captured["prompt"] = prompt
        return "OK"

    mocker.patch.object(cli_entry.api, "generate_text", side_effect=fake_generate_text)

    parser = cli_module.create_parser()
    args = parser.parse_args(["--mini-agent-off", "Weather in HCMC tomorrow"])

    cli_entry.main(provided_args=args)

    mini_agent_mock.assert_not_called()
    assert captured["model_name"] == "deepseek-chat"
    assert captured["prompt"] == "Weather in HCMC tomorrow"
