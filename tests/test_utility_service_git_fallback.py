import argparse

import termi_cli.application.utility_service as util_mod
from termi_cli.application.utility_service import UtilityService


class DummyGitRepository:
    def __init__(self):
        self.status_called = False
        self.stage_called = False
        self.diff_called = False

    def get_status_porcelain(self) -> str:
        self.status_called = True
        return "M file.py"

    def stage_all(self) -> None:
        self.stage_called = True

    def get_staged_diff(self) -> str:
        self.diff_called = True
        return "diff --staged content"


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):  # pragma: no cover
        self.messages.append(args)


def test_generate_git_commit_message_fallbacks_from_http_to_gemini(monkeypatch):
    # Giả lập config để UtilityService lấy default_model Gemini
    fake_config = {
        "language": "vi",
        "default_model": "models/gemini-pro-latest",
        "commit_model": None,
        "code_model": None,
    }
    monkeypatch.setattr(util_mod, "load_config", lambda: fake_config)

    # Đếm số lần gọi generate_text và mô phỏng lỗi HTTP provider
    call_args = {"calls": []}

    def fake_generate_text(model_name, prompt, system_instruction=None):  # noqa: D401
        """Fake generate_text dùng để kiểm tra fallback."""

        call_args["calls"].append(model_name)
        if len(call_args["calls"]) == 1:
            # Lần đầu: giả lập DeepseekInsufficientBalance
            raise util_mod.api.DeepseekInsufficientBalance("insufficient balance")
        return "Commit message from Gemini"

    monkeypatch.setattr(util_mod.api, "generate_text", fake_generate_text)

    # Không thực thi git commit thật
    monkeypatch.setattr(util_mod.utils, "execute_suggested_commands", lambda *_a, **_k: None)

    git_repo = DummyGitRepository()
    service = UtilityService(git_repo=git_repo)
    console = DummyConsole()
    args = argparse.Namespace(model="deepseek-chat", git_commit=True, git_commit_short=False)

    service.generate_git_commit_message(console, args, short=False)

    # Đảm bảo repository được dùng
    assert git_repo.status_called is True
    assert git_repo.stage_called is True
    assert git_repo.diff_called is True

    # generate_text phải được gọi 2 lần: lần đầu HTTP provider, lần sau fallback Gemini
    assert call_args["calls"][0] == "deepseek-chat"
    assert call_args["calls"][1] == "models/gemini-pro-latest"
