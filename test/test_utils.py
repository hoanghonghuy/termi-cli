import pytest
import os
from termi_cli import utils

def test_sanitize_filename():
    """
    Kiểm tra hàm sanitize_filename với nhiều trường hợp khác nhau.
    """
    assert utils.sanitize_filename("Hello World") == "hello_world"
    assert utils.sanitize_filename("Chào Đại Ca") == "chao_dai_ca"
    assert utils.sanitize_filename("File*Name?/!@#$%^&.txt") == "filename.txt"
    assert utils.sanitize_filename("  leading -- and -- trailing  ") == "leading_and_trailing"
    assert utils.sanitize_filename("") == ""
    assert utils.sanitize_filename("!@#$%^") == ""

def test_get_directory_context(tmp_path, monkeypatch):
    """
    Kiểm tra hàm get_directory_context.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    (project_dir / "main.py").write_text("print('hello')")
    (project_dir / "README.md").write_text("# My Project")
    (project_dir / "config.ini").write_text("key=value")
    
    sub_dir = project_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "logic.js").write_text("console.log('logic');")
    
    monkeypatch.chdir(project_dir)
    
    context = utils.get_directory_context()
    
    # Kiểm tra với các đường dẫn đã được chuẩn hóa, không còn './'
    main_py_path = "main.py"
    readme_path = "README.md"
    logic_js_path = os.path.join('subdir', 'logic.js')

    assert f"--- START OF FILE: {main_py_path} ---" in context
    assert "print('hello')" in context
    
    assert f"--- START OF FILE: {readme_path} ---" in context
    assert "# My Project" in context
    
    assert f"--- START OF FILE: {logic_js_path} ---" in context
    assert "console.log('logic');" in context
    
    assert "config.ini" not in context
    assert "key=value" not in context

def test_execute_suggested_commands_no_blocks(mocker):
    """Nếu text không có khối shell, không được gọi shell_tool.execute_command."""
    console = mocker.MagicMock()
    exec_mock = mocker.patch("termi_cli.tools.shell_tool.execute_command")

    utils.execute_suggested_commands("No shell blocks here", console)

    exec_mock.assert_not_called()


def test_execute_suggested_commands_skip_all(mocker):
    """User chọn 'n' ở prompt đầu tiên thì bỏ qua tất cả lệnh."""
    text = """```shell\necho 1\necho 2\n```"""
    console = mocker.MagicMock()
    console.input.return_value = "n"
    exec_mock = mocker.patch("termi_cli.tools.shell_tool.execute_command")

    utils.execute_suggested_commands(text, console)

    console.input.assert_called_once()
    exec_mock.assert_not_called()


def test_execute_suggested_commands_execute_all(mocker):
    """User chọn 'a' thì tất cả lệnh trong block được thực thi với skip_confirm=True."""
    text = """```shell\necho 1\necho 2\n```"""
    console = mocker.MagicMock()
    console.input.return_value = "a"
    exec_mock = mocker.patch(
        "termi_cli.tools.shell_tool.execute_command",
        return_value="OK",
    )

    utils.execute_suggested_commands(text, console)

    console.input.assert_called_once()
    # Hai lệnh trong block
    assert exec_mock.call_count == 2
    exec_mock.assert_any_call("echo 1", skip_confirm=True)
    exec_mock.assert_any_call("echo 2", skip_confirm=True)


def test_execute_suggested_commands_per_command_and_quit(mocker):
    """Khi không chọn 'a', từng lệnh sẽ hỏi riêng qua input() và có thể quit giữa chừng."""
    text = """```bash\necho 1\necho 2\n```"""
    console = mocker.MagicMock()
    # Lựa chọn ban đầu khác n/q/a để vào nhánh per-command
    console.input.return_value = "y"

    # Lần 1: 'y' -> thực thi, Lần 2: 'q' -> dừng vòng lặp
    input_mock = mocker.patch("builtins.input", side_effect=["y", "q"])
    exec_mock = mocker.patch(
        "termi_cli.tools.shell_tool.execute_command",
        return_value="OK",
    )

    utils.execute_suggested_commands(text, console)

    console.input.assert_called_once()
    # Thực thi đúng 1 lệnh vì sau đó user chọn 'q'
    exec_mock.assert_called_once_with("echo 1", skip_confirm=True)
    assert input_mock.call_count == 2