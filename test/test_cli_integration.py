import os
import sys
import json
import subprocess
from pathlib import Path
from io import StringIO

import chromadb
from chromadb.config import Settings
from rich.console import Console

from termi_cli import cli as cli_module
from termi_cli import __main__ as cli_entry
from termi_cli import api
from termi_cli.handlers import agent_handler, config_handler
from termi_cli.utils import sanitize_filename
from termi_cli.config import load_config


def _run_cli(tmp_path: Path, args: list[str], env_extra: dict | None = None):
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


def test_model_selection_wizard_openrouter_quick_flow(tmp_path, monkeypatch):
    """Wizard --set-model với provider OpenRouter cho phép chọn nhanh từ danh sách gợi ý."""
    home = tmp_path / "home"
    home.mkdir()

    # Đảm bảo config.json nằm trong TERMI_CLI_HOME tạm
    monkeypatch.setenv("TERMI_CLI_HOME", str(home))
    config = load_config()

    # Console ghi ra StringIO để test không in ra stdout thật
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True)

    # Chuỗi input: 4 (OpenRouter), 1 (model gợi ý đầu tiên), "" (code_model dùng default), "" (commit_model dùng code)
    inputs = iter(["4", "1", "", ""])

    def fake_input(prompt: str = "", markup: bool = True):  # noqa: ARG001
        try:
            return next(inputs)
        except StopIteration:  # Phòng trường hợp wizard hỏi thêm
            return ""

    monkeypatch.setattr(console, "input", fake_input)

    config_handler.model_selection_wizard(console, config)

    # Kiểm tra config đã được cập nhật với một OpenRouter model hợp lệ
    default_model = config.get("default_model")
    code_model = config.get("code_model")
    commit_model = config.get("commit_model")

    assert api.is_openrouter_model(default_model)
    assert code_model == default_model
    assert commit_model == code_model
