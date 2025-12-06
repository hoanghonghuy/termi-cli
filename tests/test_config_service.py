from rich.console import Console

from termi_cli.application.config_service import ConfigService


class DummyConfigRepository:
    def __init__(self):
        self.saved_config = None

    def load(self):  # pragma: no cover - không dùng trong các test hiện tại
        return {}

    def save(self, config: dict) -> None:
        self.saved_config = config


def test_add_persona_uses_repository_save():
    repo = DummyConfigRepository()
    service = ConfigService(repository=repo)
    console = Console(record=True)
    config: dict = {}

    service.add_persona(console, config, name="dev", instruction="You are a dev")

    assert config["personas"]["dev"] == "You are a dev"
    assert repo.saved_config is config


def test_add_instruction_appends_and_saves():
    repo = DummyConfigRepository()
    service = ConfigService(repository=repo)
    console = Console(record=True)
    config: dict = {}

    service.add_instruction(console, config, "Be concise")

    assert "saved_instructions" in config
    assert config["saved_instructions"] == ["Be concise"]
    assert repo.saved_config is config
