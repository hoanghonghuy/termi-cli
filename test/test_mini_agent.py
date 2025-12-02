import pytest

from termi_cli.handlers import mini_agent


def test_run_http_mini_agent_matches_rule_and_calls_tool_without_prompt(mocker):
    config = {
        "mini_agent": {
            "enabled": True,
            "rules": [
                {
                    "tool_name": "dummy_tool",
                    "patterns": ["hello"],
                    "pass_prompt": False,
                }
            ],
        }
    }

    dummy_tool = mocker.Mock(return_value="OK")
    mocker.patch.object(mini_agent.api, "AVAILABLE_TOOLS", {"dummy_tool": dummy_tool})

    result = mini_agent.run_http_mini_agent("hello world", "hello world", config)

    assert result == "OK"
    dummy_tool.assert_called_once_with()


def test_run_http_mini_agent_passes_prompt_when_flag_true(mocker):
    config = {
        "mini_agent": {
            "enabled": True,
            "rules": [
                {
                    "tool_name": "dummy_tool",
                    "patterns": ["weather"],
                    "pass_prompt": True,
                }
            ],
        }
    }

    dummy_tool = mocker.Mock(return_value="OK")
    mocker.patch.object(mini_agent.api, "AVAILABLE_TOOLS", {"dummy_tool": dummy_tool})

    prompt = "Weather in HCMC tomorrow"
    result = mini_agent.run_http_mini_agent(prompt, prompt, config)

    assert result == "OK"
    dummy_tool.assert_called_once_with(prompt)


def test_run_http_mini_agent_returns_none_when_no_rule_matches(mocker):
    config = {
        "mini_agent": {
            "enabled": True,
            "rules": [
                {
                    "tool_name": "dummy_tool",
                    "patterns": ["xyz"],
                    "pass_prompt": False,
                }
            ],
        }
    }

    dummy_tool = mocker.Mock(return_value="OK")
    mocker.patch.object(mini_agent.api, "AVAILABLE_TOOLS", {"dummy_tool": dummy_tool})

    result = mini_agent.run_http_mini_agent("hello", "hello", config)

    assert result is None
    dummy_tool.assert_not_called()
