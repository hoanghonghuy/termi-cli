import argparse

import termi_cli.application.agent_service as agent_mod
from termi_cli.application.agent_service import AgentExecutionContext


class DummyConsole:
    def print(self, *args, **kwargs):  # pragma: no cover
        pass


def test_agent_execution_context_uses_default_max_steps_when_arg_missing(monkeypatch):
    fake_config = {
        "language": "en",
        "agent_model": "models/gemini-flash-latest",
        "agent_allow_http": False,
        "model_fallback_order": [],
    }

    monkeypatch.setattr(agent_mod, "load_config", lambda: fake_config)

    console = DummyConsole()
    args = argparse.Namespace(agent_dry_run=False, agent_max_steps=None)

    ctx = AgentExecutionContext.from_args(console=console, args=args, default_max_steps=42)

    assert ctx.language == "en"
    assert ctx.dry_run is False
    assert ctx.max_steps == 42


def test_agent_execution_context_sets_use_http_agent_for_http_models(monkeypatch):
    fake_config = {
        "language": "vi",
        "agent_model": "deepseek-chat",
        "agent_allow_http": True,
        "model_fallback_order": [],
    }

    monkeypatch.setattr(agent_mod, "load_config", lambda: fake_config)

    console = DummyConsole()
    args = argparse.Namespace(agent_dry_run=False, agent_max_steps=None)

    ctx = AgentExecutionContext.from_args(console=console, args=args, default_max_steps=5)

    assert ctx.agent_model_name == "deepseek-chat"
    assert ctx.use_http_agent is True
