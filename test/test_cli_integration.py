import os
import sys
import json
import subprocess
from pathlib import Path
from io import StringIO
from types import SimpleNamespace

import pytest
try:
    import chromadb
    from chromadb.config import Settings
except Exception as e:  # pragma: no cover
    pytest.skip(f"chromadb is not available or misconfigured: {e}", allow_module_level=True)
from rich.console import Console

from termi_cli import cli as cli_module
from termi_cli import __main__ as cli_entry
from termi_cli import api
from termi_cli.handlers import agent_handler, config_handler
from termi_cli.utils import sanitize_filename
from termi_cli.config import load_config


def _run_cli(
    tmp_path: Path,
    args: list[str],
    env_extra: dict | None = None,
    stdin_text: str | None = None,
):
    """Chạy CLI trong một thư mục tạm với TERMI_CLI_HOME riêng.

    Trả về đối tượng CompletedProcess để test có thể kiểm tra stdout/stderr.
    """
    env = os.environ.copy()

    # Đảm bảo không phụ thuộc API key thật trong môi trường
    for key in [
        "GOOGLE_API_KEY",
        "GOOGLE_API_KEY_2ND",
        "GOOGLE_API_KEY_3RD",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEY_2ND",
        "DEEPSEEK_API_KEY_3RD",
        "GROQ_API_KEY",
        "GROQ_API_KEY_2ND",
        "GROQ_API_KEY_3RD",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_2ND",
        "OPENROUTER_API_KEY_3RD",
    ]:
        env.pop(key, None)

    # Ép encoding UTF-8 cho stdout/stderr của subprocess để Rich không bị UnicodeEncodeError
    env.setdefault("PYTHONIOENCODING", "utf-8")

    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})

    result = subprocess.run(
        [sys.executable, "-m", "termi_cli", *args],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin_text,
    )
    return result


def test_cli_diagnostics_runs_without_api_keys(tmp_path):
    """--diagnostics phải chạy được mà không cần API key và in bảng cấu hình."""
    home = tmp_path / "home"
    home.mkdir()

    result = _run_cli(tmp_path, ["--diagnostics"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    # Tiếng Việt mặc định: tiêu đề bảng diagnostics
    assert (
        "Thông tin cấu hình model hiện tại" in result.stdout
        or "Current model configuration diagnostics" in result.stdout
    )


def test_cli_doctor_runs_without_api_keys(tmp_path):
    """--doctor phải chạy được mà không cần API key và in header Doctor."""

    home = tmp_path / "home"
    home.mkdir()

    result = _run_cli(tmp_path, ["--doctor"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Termi Doctor" in result.stdout


def test_cli_reset_memory_uses_isolated_app_dir(tmp_path):
    """--reset-memory phải xoá đúng APP_DIR/memory_db dựa trên TERMI_CLI_HOME."""
    home = tmp_path / "home"
    memdir = home / "memory_db"
    memdir.mkdir(parents=True)
    (memdir / "dummy.txt").write_text("x", encoding="utf-8")

    result = _run_cli(tmp_path, ["--reset-memory"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    # Thư mục memory_db phải bị xoá
    assert not memdir.exists()
    # Thông báo i18n (có thể VI hoặc EN), nhưng chắc chắn chứa memory_db
    assert "memory_db" in result.stdout


def test_cli_reset_config_restores_defaults_in_isolated_home(tmp_path):
    """--reset-config phải xoá config tuỳ biến và khôi phục giá trị mặc định."""
    home = tmp_path / "home"
    home.mkdir()

    config_path = home / "config.json"
    # Tạo một config tuỳ biến với default_model khác
    custom_config = {"default_model": "deepseek-chat"}
    config_path.write_text(json.dumps(custom_config, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(tmp_path, ["--reset-config"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    assert config_path.exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert config_data.get("default_model") == "models/gemini-flash-latest"


def test_cli_init_config_creates_config_with_defaults(tmp_path):
    """--init-config phải tạo config.json mặc định nếu chưa tồn tại."""

    home = tmp_path / "home"
    home.mkdir()

    config_path = home / "config.json"
    assert not config_path.exists()

    result = _run_cli(tmp_path, ["--init-config"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    assert config_path.exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert config_data.get("default_model") == "models/gemini-flash-latest"


def test_cli_profile_save_list_and_remove_in_isolated_home(tmp_path):
    """Kiểm tra luồng save/list/rm profile qua CLI với TERMI_CLI_HOME tách biệt."""
    home = tmp_path / "home"
    home.mkdir()

    # Lưu profile
    save_result = _run_cli(tmp_path, ["--save-profile", "dev-gemini"], {"TERMI_CLI_HOME": home})
    assert save_result.returncode == 0, save_result.stdout + save_result.stderr

    config_path = home / "config.json"
    assert config_path.exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = config_data.get("profiles") or {}
    assert "dev-gemini" in profiles

    # List profiles phải hiển thị tên profile
    list_result = _run_cli(tmp_path, ["--list-profiles"], {"TERMI_CLI_HOME": home})
    assert list_result.returncode == 0, list_result.stdout + list_result.stderr
    assert "dev-gemini" in list_result.stdout

    # Xoá profile
    rm_result = _run_cli(tmp_path, ["--rm-profile", "dev-gemini"], {"TERMI_CLI_HOME": home})
    assert rm_result.returncode == 0, rm_result.stdout + rm_result.stderr

    # Sau khi xoá, list-profiles không còn hiển thị profile dev-gemini
    list_after_rm = _run_cli(tmp_path, ["--list-profiles"], {"TERMI_CLI_HOME": home})
    assert list_after_rm.returncode == 0, list_after_rm.stdout + list_after_rm.stderr
    assert "dev-gemini" not in list_after_rm.stdout


def test_cli_memory_search_returns_results(tmp_path):
    """--memory-search phải đọc được dữ liệu từ memory_db và in kết quả."""
    home = tmp_path / "home"
    home.mkdir()

    db_path = home / "memory_db"
    client = chromadb.PersistentClient(
        path=str(db_path), settings=Settings(anonymized_telemetry=False)
    )
    coll = client.get_or_create_collection(name="long_term_memory")
    coll.add(documents=["Test migrations for user table"], ids=["1"])

    result = _run_cli(
        tmp_path,
        ["--memory-search", "migrations"],
        {"TERMI_CLI_HOME": home},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # Header tiếng Anh do memory.search_memory sinh ra
    assert "Relevant Past Interactions" in result.stdout


def test_cli_rm_history_by_topic(tmp_path):
    """--rm-history phải xoá đúng file history theo topic."""
    home = tmp_path / "home"
    hist_dir = home / "chat_logs"
    hist_dir.mkdir(parents=True)

    topic = "debug-openapi-errors"
    filename = f"chat_{sanitize_filename(topic)}.json"
    hist_path = hist_dir / filename
    payload = {"title": topic, "history": []}
    hist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(
        tmp_path,
        ["--rm-history", topic],
        {"TERMI_CLI_HOME": home},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not hist_path.exists()


def test_cli_rename_history_by_topic(tmp_path):
    """--rename-history phải đổi tên file và cập nhật title trong JSON."""
    home = tmp_path / "home"
    hist_dir = home / "chat_logs"
    hist_dir.mkdir(parents=True)

    topic = "debug-openapi-errors"
    filename = f"chat_{sanitize_filename(topic)}.json"
    hist_path = hist_dir / filename
    payload = {"title": topic, "history": []}
    hist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    new_title = "Fix OpenAPI client generator"
    result = _run_cli(
        tmp_path,
        ["--rename-history", topic, new_title],
        {"TERMI_CLI_HOME": home},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not hist_path.exists()

    files = list(hist_dir.glob("chat_*.json"))
    assert len(files) == 1
    new_path = files[0]
    data = json.loads(new_path.read_text(encoding="utf-8"))
    assert data.get("title") == new_title


def test_cli_history_shows_saved_conversation(tmp_path):
    home = tmp_path / "home"
    hist_dir = home / "chat_logs"
    hist_dir.mkdir(parents=True)

    payload = {
        "title": "Demo history",
        "history": [
            {"role": "user", "parts": [{"text": "Hello from history"}]},
            {"role": "model", "parts": [{"text": "Hi there"}]},
        ],
    }
    hist_path = hist_dir / "chat_demo.json"
    hist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(
        tmp_path,
        ["--history"],
        {"TERMI_CLI_HOME": home},
        stdin_text="1\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Hello from history" in result.stdout


def test_cli_agent_max_steps_passed_to_agent(tmp_path, monkeypatch, mocker):
    """--agent-max-steps phải được truyền xuống args của Agent."""
    home = tmp_path / "home"
    home.mkdir()

    # Đảm bảo config & APP_DIR nằm trong thư mục tạm, và có API key giả để initialize_api_keys không fail
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    parser = cli_module.create_parser()
    args = parser.parse_args([
        "--agent",
        "--agent-max-steps",
        "5",
        "Do something important",
    ])

    captured: dict = {}

    def fake_run_master_agent(console, agent_args):  # noqa: ARG001
        captured["max_steps"] = getattr(agent_args, "agent_max_steps", None)
        captured["prompt"] = agent_args.prompt

    mocker.patch.object(agent_handler, "run_master_agent", side_effect=fake_run_master_agent)

    # Gọi main() trực tiếp với provided_args để không đụng parser của sys.argv
    cli_entry.main(provided_args=args)

    assert captured["max_steps"] == 5
    assert captured["prompt"] == "Do something important"


def test_cli_agent_dry_run_flag_passed_to_agent(tmp_path, monkeypatch, mocker):
    """--agent-dry-run phải được truyền đúng cho Agent qua CLI bridge."""

    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("TERMI_CLI_HOME", str(home))
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    parser = cli_module.create_parser()
    args = parser.parse_args([
        "--agent",
        "--agent-dry-run",
        "Inspect dry-run behaviour",
    ])

    captured: dict = {}

    def fake_run_master_agent(console, agent_args):  # noqa: ARG001
        captured["dry_run"] = getattr(agent_args, "agent_dry_run", False)
        captured["prompt"] = agent_args.prompt
def test_cli_agent_http_deepseek_uses_http_path_without_gemini(tmp_path, monkeypatch, mocker):
    """CLI --agent với HTTP agent DeepSeek + agent_allow_http=True phải dùng nhánh HTTP (generate_text)."""

    home = tmp_path / "home"
    home.mkdir()

    # Chuỗi input: 2 (provider DeepSeek), 1 (deepseek-chat), "" (code_model dùng default), "" (commit_model dùng code)
    stdin_data = "2\n1\n\n\n"

    result = _run_cli(
        tmp_path,
        ["--set-model"],
        {
            "TERMI_CLI_HOME": home,
            # Cần key giả để _requires_gemini cho phép đi vào model_selection_wizard
            "GOOGLE_API_KEY": "dummy-key",
        },
        stdin_text=stdin_data,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    config_path = home / "config.json"
    assert config_path.exists()

    config_data = json.loads(config_path.read_text(encoding="utf-8"))

    assert config_data.get("default_model") == "deepseek-chat"
    assert config_data.get("code_model") == "deepseek-chat"
    assert config_data.get("commit_model") == "deepseek-chat"


def test_cli_diagnostics_prints_provider_hints(tmp_path):
    """--diagnostics (CLI thật) phải in thêm gợi ý/mẫu lệnh cho provider (ví dụ Gemini)."""

    home = tmp_path / "home"
    home.mkdir()

    result = _run_cli(tmp_path, ["--diagnostics"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr

    # Với language mặc định là "vi", show_diagnostics sẽ in diagnostics_hint_gemini
    # Nếu sau này user chuyển sang EN, test vẫn an toàn vì chấp nhận cả tiếng Anh.
    assert (
        "Ví dụ Gemini" in result.stdout
        or "Gemini example" in result.stdout
    )


def test_cli_diagnostics_with_deepseek_model_prints_deepseek_hint(tmp_path):
    """--diagnostics với default_model DeepSeek phải in hint DeepSeek."""

    home = tmp_path / "home"
    home.mkdir()

    config_path = home / "config.json"
    custom_config = {"default_model": "deepseek-chat"}
    config_path.write_text(json.dumps(custom_config, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(tmp_path, ["--diagnostics"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "Ví dụ DeepSeek" in result.stdout
        or "DeepSeek example" in result.stdout
    )


def test_cli_diagnostics_with_openrouter_model_prints_openrouter_hint(tmp_path):
    """--diagnostics với default_model OpenRouter phải in hint OpenRouter."""

    home = tmp_path / "home"
    home.mkdir()

    config_path = home / "config.json"
    custom_config = {"default_model": "openai/gpt-4o-mini"}
    config_path.write_text(json.dumps(custom_config, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(tmp_path, ["--diagnostics"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "Ví dụ OpenRouter" in result.stdout
        or "OpenRouter example" in result.stdout
    )


def test_cli_diagnostics_with_ollama_model_shows_ollama_provider(tmp_path):
    """--diagnostics với default_model Ollama phải hiển thị provider Ollama trong bảng."""

    home = tmp_path / "home"
    home.mkdir()

    config_path = home / "config.json"
    custom_config = {"default_model": "ollama/qwen3:8b"}
    config_path.write_text(json.dumps(custom_config, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(tmp_path, ["--diagnostics"], {"TERMI_CLI_HOME": home})

    assert result.returncode == 0, result.stdout + result.stderr
    # Bảng diagnostics phải chứa chữ "Ollama" trong cột Provider
    assert "Ollama" in result.stdout


def test_requires_gemini_for_agent_with_ollama_does_not_need_gemini():
    """_requires_gemini_for_command: Agent với agent_model Ollama phải không yêu cầu Gemini."""

    config = {
        "agent_model": "ollama/qwen3:8b",
        "agent_allow_http": False,
        "default_model": "models/gemini-flash-latest",
    }

    args = SimpleNamespace(agent=True)

    assert cli_entry._requires_gemini_for_command(config, args) is False


def test_cli_git_commit_short_in_repo_auto_staging(tmp_path, monkeypatch, mocker):
    """--git-commit-short qua CLI phải chạy non-interactive nhờ PYTEST_CURRENT_TEST."""

    # Tạo repo git tạm
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.chdir(repo)

    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Termi Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "termi@example.com"], cwd=repo, check=True)

    file_path = repo / "main.py"
    file_path.write_text("print('v1')\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)

    # Sửa file để tạo diff chưa staged
    file_path.write_text("print('v2')\n", encoding="utf-8")

    # Cấu hình môi trường cho CLI: TERMI_CLI_HOME tách biệt + GOOGLE_API_KEY giả
    home = repo / "home"
    home.mkdir()
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    # Nếu console.input bị gọi (do không tôn trọng PYTEST_CURRENT_TEST) thì test phải fail
    def fail_on_console_input(self, *args, **kwargs):  # noqa: ARG002
        raise AssertionError("Console.input should not be called for git-commit-short under pytest")

    monkeypatch.setattr("rich.console.Console.input", fail_on_console_input, raising=True)

    # Patch generate_text để không gọi mạng, và utils.execute_suggested_commands để tránh thực thi shell
    captured: dict = {}

    def fake_generate_text(model_name, prompt, system_instruction=None):  # noqa: ARG001
        captured["model_name"] = model_name
        captured["prompt"] = prompt
        captured["system_instruction"] = system_instruction
        return "feat: demo commit"

    mocker.patch(
        "termi_cli.handlers.utility_handler.api.generate_text",
        side_effect=fake_generate_text,
    )

    exec_calls: dict = {}

    def fake_execute_suggested_commands(text, console):  # noqa: ARG001
        exec_calls["text"] = text

    mocker.patch(
        "termi_cli.handlers.utility_handler.utils.execute_suggested_commands",
        side_effect=fake_execute_suggested_commands,
    )

    parser = cli_module.create_parser()
    args = parser.parse_args(["--git-commit-short"])

    # Gọi main() trực tiếp với provided_args để dùng cùng process (cho phép patching)
    cli_entry.main(provided_args=args)

    # Đảm bảo generate_text được gọi để sinh commit message
    assert captured.get("model_name") is not None
    # Và utils.execute_suggested_commands được gọi với lệnh git commit -m tương ứng
    assert "git commit -m" in exec_calls.get("text", "")


def test_cli_image_when_pillow_broken_prints_friendly_message(tmp_path, monkeypatch, capsys):
    """-i/--image khi Pillow hỏng (Image is None) phải in thông báo i18n thân thiện."""

    home = tmp_path / "home"
    home.mkdir()

    # TERMI_CLI_HOME tách biệt và GOOGLE_API_KEY giả để _requires_gemini cho phép chạy single-turn
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    # Buộc nhánh Pillow hỏng bằng cách đặt Image = None trên module __main__
    monkeypatch.setattr(cli_entry, "Image", None, raising=True)

    # Tránh việc _run_single_turn đọc từ stdin thật dưới pytest (gây lỗi capture)
    class DummyStdin:
        def isatty(self):  # pragma: no cover - trivial shim
            return True

    monkeypatch.setattr(cli_entry.sys, "stdin", DummyStdin(), raising=False)

    parser = cli_module.create_parser()
    args = parser.parse_args(["-i", "nonexistent.png", "Test image input"])

    cli_entry.main(provided_args=args)

    out, err = capsys.readouterr()
    combined = out + err

    # Thông báo có thể là VI hoặc EN, kiểm tra cả hai cụm chính
    assert (
        "Tính năng đọc ảnh không khả dụng" in combined
        or "Image input is not available" in combined
    )
