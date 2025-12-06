import argparse

import termi_cli.application.agent_service as agent_mod
from termi_cli.application.agent_service import AgentExecutionContext


class DummyConsole:
    def print(self, *args, **kwargs):  # pragma: no cover - chỉ để thoả mãn interface
        pass


def test_agent_execution_context_from_args_with_gemini(monkeypatch):
    fake_config = {
        "language": "vi",
        "agent_model": "models/gemini-pro-latest",
        "agent_allow_http": False,
        "model_fallback_order": [],
    }

    # Đảm bảo AgentExecutionContext dùng config giả thay vì đọc file thật.
    monkeypatch.setattr(agent_mod, "load_config", lambda: fake_config)

    console = DummyConsole()
    args = argparse.Namespace(agent_dry_run=True, agent_max_steps=5)

    ctx = AgentExecutionContext.from_args(console=console, args=args, default_max_steps=10)

    assert ctx.config is fake_config
    assert ctx.language == "vi"
    assert ctx.dry_run is True
    assert ctx.agent_model_name == "models/gemini-pro-latest"
    assert ctx.use_http_agent is False
    assert ctx.max_steps == 5
