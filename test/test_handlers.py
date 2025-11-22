import argparse
from termi_cli.handlers import config_handler as handlers
from termi_cli.handlers import utility_handler

def test_add_instruction(mocker):
    """Kiểm tra việc thêm một chỉ dẫn mới."""
    # 1. Giả lập hàm save_config để nó không ghi file thật
    mock_save = mocker.patch('termi_cli.handlers.config_handler.save_config')
    
    # 2. Tạo config ban đầu
    config = {"saved_instructions": ["rule1"]}
    
    # 3. Gọi hàm cần test
    handlers.add_instruction(console=mocker.MagicMock(), config=config, instruction="rule2")
    
    # 4. Kiểm tra
    assert "rule2" in config["saved_instructions"]
    assert len(config["saved_instructions"]) == 2
    mock_save.assert_called_once_with(config)

def test_remove_instruction(mocker):
    """Kiểm tra việc xóa một chỉ dẫn."""
    mock_save = mocker.patch('termi_cli.handlers.config_handler.save_config')
    
    config = {"saved_instructions": ["rule1", "rule2", "rule3"]}
    
    # Xóa item ở giữa (index=2)
    handlers.remove_instruction(console=mocker.MagicMock(), config=config, index=2)
    
    assert config["saved_instructions"] == ["rule1", "rule3"]
    mock_save.assert_called_once_with(config)

def test_add_persona(mocker):
    """Kiểm tra việc thêm một persona mới."""
    mock_save = mocker.patch('termi_cli.handlers.config_handler.save_config')
    
    config = {"personas": {"coder": "You are a coder."}}
    
    handlers.add_persona(console=mocker.MagicMock(), config=config, name="tester", instruction="You are a tester.")
    
    assert "tester" in config["personas"]
    assert config["personas"]["tester"] == "You are a tester."
    mock_save.assert_called_once_with(config)

def test_remove_persona(mocker):
    """Kiểm tra việc xóa một persona."""
    mock_save = mocker.patch('termi_cli.handlers.config_handler.save_config')
    
    config = {"personas": {"coder": "...", "tester": "..."}}
    
    handlers.remove_persona(console=mocker.MagicMock(), config=config, name="coder")
    
    assert "coder" not in config["personas"]
    assert "tester" in config["personas"]
    mock_save.assert_called_once_with(config)

def test_generate_git_commit_message_short_builds_single_line_subject(mocker):
    """generate_git_commit_message(short=True) phải tạo lệnh git commit -m với subject 1 dòng, đã xử lý dấu quote."""

    console = mocker.MagicMock()

    # Giả lập load_config để không phụ thuộc file thật
    mocker.patch(
        "termi_cli.handlers.utility_handler.load_config",
        return_value={
            "language": "vi",
            "default_model": "models/gemini-flash-latest",
            "commit_model": "models/gemini-flash-latest",
        },
    )

    # Giả lập git status và git diff --staged
    check_output_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.check_output",
        side_effect=[
            "M file.py\n",  # git status --porcelain
            "diff --git a/file.py b/file.py\n+change\n",  # git diff --staged
        ],
    )

    run_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.run",
        return_value=None,
    )

    # Giả lập model và nội dung trả về từ AI
    mocker.patch(
        "termi_cli.handlers.utility_handler.api.generate_text",
        return_value='feat: add "short" commit\n\nBody line that should be ignored.',
    )

    exec_suggested_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.utils.execute_suggested_commands"
    )

    args = argparse.Namespace(model=None)

    utility_handler.generate_git_commit_message(console, args, short=True)

    # Đảm bảo đã gọi git status, git add, git diff --staged
    assert check_output_mock.call_count == 2
    run_mock.assert_called_once_with(["git", "add", "."], check=True, capture_output=True)

    # Kiểm tra lệnh git commit -m mà utils nhận được
    exec_suggested_mock.assert_called_once()
    fake_ai_response, _console = exec_suggested_mock.call_args.args
    assert "```shell" in fake_ai_response
    assert "git commit -m" in fake_ai_response
    # Subject phải là dòng đầu tiên, đã thay " bằng '
    assert "feat: add 'short' commit" in fake_ai_response


def test_generate_git_commit_message_short_single_line_response(mocker):
    """Trường hợp AI trả về đúng 1 dòng, vẫn phải build git commit -m chính xác."""
    console = mocker.MagicMock()

    mocker.patch(
        "termi_cli.handlers.utility_handler.load_config",
        return_value={
            "language": "vi",
            "default_model": "models/gemini-flash-latest",
            "commit_model": "models/gemini-flash-latest",
        },
    )

    check_output_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.check_output",
        side_effect=[
            "M file.py\n",
            "diff --git a/file.py b/file.py\n+change\n",
        ],
    )

    mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.run",
        return_value=None,
    )

    mocker.patch(
        "termi_cli.handlers.utility_handler.api.generate_text",
        return_value="chore: update docs",
    )

    exec_suggested_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.utils.execute_suggested_commands"
    )

    args = argparse.Namespace(model=None)
    utility_handler.generate_git_commit_message(console, args, short=True)

    assert check_output_mock.call_count == 2
    exec_suggested_mock.assert_called_once()
    fake_ai_response, _console = exec_suggested_mock.call_args.args
    assert 'git commit -m "chore: update docs"' in fake_ai_response


def test_generate_git_commit_message_short_empty_response_does_not_execute(mocker):
    """Nếu AI trả về rỗng/whitespace thì không được gọi execute_suggested_commands."""
    console = mocker.MagicMock()

    mocker.patch(
        "termi_cli.handlers.utility_handler.load_config",
        return_value={
            "language": "vi",
            "default_model": "models/gemini-flash-latest",
            "commit_model": "models/gemini-flash-latest",
        },
    )

    check_output_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.check_output",
        side_effect=[
            "M file.py\n",
            "diff --git a/file.py b/file.py\n+change\n",
        ],
    )

    mocker.patch(
        "termi_cli.handlers.utility_handler.subprocess.run",
        return_value=None,
    )

    mocker.patch(
        "termi_cli.handlers.utility_handler.api.generate_text",
        return_value="   \n  ",  # chỉ toàn whitespace
    )

    exec_suggested_mock = mocker.patch(
        "termi_cli.handlers.utility_handler.utils.execute_suggested_commands"
    )

    args = argparse.Namespace(model=None)
    utility_handler.generate_git_commit_message(console, args, short=True)

    # Vẫn gọi git status/diff nhưng không tạo lệnh commit
    assert check_output_mock.call_count == 2
    exec_suggested_mock.assert_not_called()