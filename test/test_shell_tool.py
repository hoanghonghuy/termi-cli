import subprocess

from termi_cli.tools import shell_tool


def test_execute_command_disallows_unknown_command():
    """Lệnh với main_command không có trong SAFE_COMMANDS phải bị từ chối."""
    result = shell_tool.execute_command("rm -rf /")
    assert "Lỗi: Lệnh 'rm' không được phép thực thi" in result


def test_execute_command_safe_command_runs_subprocess(mocker):
    """Lệnh an toàn (git status) phải gọi subprocess.run và trả output ghép STDOUT/STDERR."""

    def fake_run(command, shell, capture_output, text, encoding, timeout):  # noqa: ARG001
        class Result:
            stdout = "OK\n"
            stderr = ""
        return Result()

    run_mock = mocker.patch("termi_cli.tools.shell_tool.subprocess.run", side_effect=fake_run)

    result = shell_tool.execute_command("git status")

    run_mock.assert_called_once()
    assert "--- STDOUT ---" in result
    assert "OK" in result


def test_execute_command_dangerous_cancelled_by_user(mocker):
    """Lệnh nguy hiểm (git commit) khi user trả lời 'n' thì không được thực thi."""
    mocker.patch("builtins.input", return_value="n")
    run_mock = mocker.patch("termi_cli.tools.shell_tool.subprocess.run")

    result = shell_tool.execute_command("git commit -m 'test'")

    run_mock.assert_not_called()
    assert "Lệnh đã bị hủy bởi người dùng." in result


def test_execute_command_dangerous_confirmed_runs(mocker):
    """Lệnh nguy hiểm khi user xác nhận 'y' sẽ được thực thi qua subprocess.run."""

    def fake_run(command, shell, capture_output, text, encoding, timeout):  # noqa: ARG001
        class Result:
            stdout = "done\n"
            stderr = ""
        return Result()

    mocker.patch("builtins.input", return_value="y")
    run_mock = mocker.patch("termi_cli.tools.shell_tool.subprocess.run", side_effect=fake_run)

    result = shell_tool.execute_command("git commit -m 'test'")

    run_mock.assert_called_once()
    assert "done" in result
