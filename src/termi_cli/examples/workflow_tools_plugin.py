import os
import shlex
import subprocess
from typing import Optional


def _run_command(cmd: str, cwd: Optional[str] = None, timeout: int = 300) -> str:
    """Chạy một lệnh shell đơn giản và trả về output (stdout + stderr, được cắt ngắn)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd or os.getcwd(),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as e:
        return f"[workflow_tools] Error while running '{cmd}': {e}"

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    combined = stdout
    if stderr:
        combined += "\nSTDERR:\n" + stderr

    combined = combined.strip()
    if len(combined) > 4000:
        combined = combined[-4000:]

    prefix = f"[workflow_tools] Command '{cmd}' exited with code {proc.returncode}.\n"
    return prefix + (combined or "(no output)")


def workflow_run_pytest(cwd: Optional[str] = None, flags: str = "") -> str:
    """Chạy pytest trong thư mục hiện tại (hoặc cwd) với flags tùy chọn.

    Ví dụ tool-call từ Agent:
      - tool_name: "workflow_run_pytest"
      - tool_args: {"cwd": "/path/to/project", "flags": "-q"}
    """
    flags = flags or ""
    cmd = "pytest " + flags
    return _run_command(cmd.strip(), cwd=cwd)


def workflow_run_quick_tests(cwd: Optional[str] = None) -> str:
    """Chạy pytest -q (quick mode)."""
    return _run_command("pytest -q", cwd=cwd)


def workflow_git_status_short(cwd: Optional[str] = None) -> str:
    """Chạy git status --short để xem nhanh các file thay đổi."""
    return _run_command("git status --short", cwd=cwd)


PLUGIN_TOOLS = {
    "workflow_run_pytest": workflow_run_pytest,
    "workflow_run_quick_tests": workflow_run_quick_tests,
    "workflow_git_status_short": workflow_git_status_short,
}
