import json
from types import SimpleNamespace
from contextlib import contextmanager

from rich.console import Console

from termi_cli.handlers import agent_handler
from termi_cli import i18n
from termi_cli.api import RPDQuotaExhausted


def _make_args(**kwargs):
    """Tạo một đối tượng args đơn giản giống argparse.Namespace."""
    return SimpleNamespace(**kwargs)


def test_execute_tool_dry_run_skips_real_tool_and_returns_message(mocker, monkeypatch):
    """Khi dry_run=True, tool không được thực thi thật và trả về message DRY-RUN i18n."""
    console = mocker.MagicMock(spec=Console)
    fake_tool = mocker.MagicMock(return_value="REAL_RESULT")

    # Giả lập AVAILABLE_TOOLS chỉ chứa một tool đơn giản
    monkeypatch.setattr(
        agent_handler.api,
        "AVAILABLE_TOOLS",
        {"dummy_tool": fake_tool},
        raising=False,
    )

    # Ngôn ngữ cố định để so sánh output
    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi"},
    )

    tool_args = {"x": 1}
    result = agent_handler._execute_tool(
        console,
        tool_name="dummy_tool",
        tool_args=tool_args,
        dry_run=True,
    )

    # Tool không được gọi trong chế độ dry-run
    fake_tool.assert_not_called()

    expected = i18n.tr(
        "vi",
        "agent_dry_run_tool_observation",
        tool_name="dummy_tool",
        tool_args=tool_args,
    )
    assert result == expected


def test_execute_tool_write_file_flows_through_confirmation(mocker, monkeypatch):
    """Khi gọi write_file ở chế độ thường, phải đi qua confirm_and_write_file."""
    console = mocker.MagicMock(spec=Console)

    # Tool write_file trả về yêu cầu xác nhận
    fake_write_tool = mocker.MagicMock(
        return_value="USER_CONFIRMATION_REQUIRED:WRITE_FILE:/tmp/demo.txt"
    )
    monkeypatch.setattr(
        agent_handler.api,
        "AVAILABLE_TOOLS",
        {"write_file": fake_write_tool},
        raising=False,
    )

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi"},
    )

    mock_confirm = mocker.patch(
        "termi_cli.handlers.agent_handler.confirm_and_write_file",
        return_value="CONFIRMED_RESULT",
    )

    tool_args = {"path": "/tmp/demo.txt", "content": "hello"}

    result = agent_handler._execute_tool(
        console,
        tool_name="write_file",
        tool_args=tool_args,
        dry_run=False,
    )

    # Tool write_file được gọi với đúng tham số
    fake_write_tool.assert_called_once_with(**tool_args)
    # Sau đó helper confirm_and_write_file được gọi để ghi file thật
    mock_confirm.assert_called_once_with(console, "/tmp/demo.txt", "hello")
    # Kết quả cuối cùng là kết quả từ confirm_and_write_file
    assert result == "CONFIRMED_RESULT"


def test_execute_tool_normal_non_write_file_calls_tool(mocker, monkeypatch):
    """Ở chế độ thường, tool bình thường phải được gọi và trả về kết quả."""
    console = mocker.MagicMock(spec=Console)

    @contextmanager
    def null_status(*_args, **_kwargs):
        yield

    # Giả lập context manager cho console.status
    console.status.side_effect = null_status

    fake_tool = mocker.MagicMock(return_value="REAL_RESULT")
    monkeypatch.setattr(
        agent_handler.api,
        "AVAILABLE_TOOLS",
        {"dummy_tool": fake_tool},
        raising=False,
    )

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi"},
    )

    tool_args = {"x": 1}

    result = agent_handler._execute_tool(
        console,
        tool_name="dummy_tool",
        tool_args=tool_args,
        dry_run=False,
    )

    fake_tool.assert_called_once_with(**tool_args)
    assert result == "REAL_RESULT"


def test_execute_project_plan_prints_dry_run_header_when_flag_set(mocker, monkeypatch):
    """execute_project_plan phải in header DRY-RUN khi args.agent_dry_run=True."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=True)

    # Cấu hình đơn giản, tránh gọi API thật
    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    # Tạo project_plan tối thiểu nhưng hợp lệ
    project_plan = {
        "project_name": "Demo",
        "reasoning": "Because tests",
        "structure": {"root": {}},
        "files": [
            {"path": "foo.py", "description": "demo file"},
        ],
    }

    # Patch API để không gọi ra ngoài, cho vòng lặp kết thúc sớm
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        return_value=object(),
    )
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        side_effect=RuntimeError("stop loop"),
    )

    # Không cần quan tâm _execute_tool được gọi bao nhiêu lần ở đây,
    # behavior chính đã được test ở các test unit phía trên.
    agent_handler.execute_project_plan(console, args, project_plan)

    # Header DRY-RUN phải được in ra
    dry_run_header = i18n.tr("vi", "agent_dry_run_mode_header")
    printed_args = [call.args[0] for call in console.print.call_args_list]
    assert dry_run_header in printed_args


def test_run_master_agent_handles_invalid_initial_json_and_prints_error(mocker):
    """run_master_agent: khi JSON ban đầu không hợp lệ, phải in lỗi và thoát an toàn."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(prompt="Demo goal")

    # Cấu hình đơn giản, tránh gọi API thật
    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    # Không quan tâm tới model thật, chỉ cần object placeholder
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.genai.GenerativeModel",
        return_value=object(),
    )

    # API trả về text không chứa JSON hợp lệ
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_generate_content",
        return_value=type("Resp", (), {"text": "no-json-here"}),
    )

    mock_exec_project = mocker.patch("termi_cli.handlers.agent_handler.execute_project_plan")
    mock_exec_simple = mocker.patch("termi_cli.handlers.agent_handler.execute_simple_task")

    agent_handler.run_master_agent(console, args)

    # Không được gọi vào các hàm thực thi kế hoạch
    mock_exec_project.assert_not_called()
    mock_exec_simple.assert_not_called()

    # In ra thông điệp lỗi với nội dung của ValueError bên trong
    printed = [str(call.args[0]) for call in console.print.call_args_list if call.args]
    assert any("Agent không trả về JSON hợp lệ ban đầu." in text for text in printed)


def test_run_master_agent_retries_on_quota_and_then_executes_plan(mocker):
    """run_master_agent: gặp quota (RPDQuotaExhausted) thì retry và sau đó thực thi project_plan."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(prompt="Demo goal")

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.genai.GenerativeModel",
        return_value=object(),
    )

    plan = {"project_name": "Demo"}
    # Mô phỏng đúng định dạng mà model thường trả về: JSON trong khối ```json ... ```
    success_payload = json.dumps({"task_type": "project_plan", "plan": plan})
    success_resp = type(
        "Resp",
        (),
        {"text": f"```json\n{success_payload}\n```"},
    )

    mock_generate = mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_generate_content",
        side_effect=[RPDQuotaExhausted("quota"), success_resp],
    )

    mock_exec_project = mocker.patch("termi_cli.handlers.agent_handler.execute_project_plan")

    agent_handler.run_master_agent(console, args)

    # Gọi API ít nhất 2 lần (1 lần lỗi quota, 1 lần thành công)
    assert mock_generate.call_count == 2

    # Cuối cùng phải gọi execute_project_plan với plan đúng
    mock_exec_project.assert_called_once()
    _, exec_args, exec_kwargs = mock_exec_project.mock_calls[0]
    # exec_args = (console, args, plan_dict)
    assert exec_args[2] == plan


def test_execute_project_plan_handles_quota_and_recreates_session(mocker):
    """execute_project_plan: khi gặp RPDQuotaExhausted trong bước executor, phải recreate session."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=False)

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    project_plan = {
        "project_name": "Demo",
        "reasoning": "Because tests",
        "structure": {"root": {}},
        "files": [],
    }

    # start_chat_session được gọi ban đầu và sau khi quota để recreate session
    mock_start = mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        side_effect=[object(), object()],
    )

    # Lần đầu tiên gửi message bị quota, lần hai trả về step finish hợp lệ
    step_finish = {
        "thought": "done",
        "action": {"tool_name": "finish", "tool_args": {"answer": "ok"}},
    }
    success_payload = json.dumps(step_finish)
    success_resp = type("Resp", (), {"text": f"```json\n{success_payload}\n```"})

    calls = [RPDQuotaExhausted("quota"), success_resp]

    def fake_send(_session, _prompt):
        value = calls.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        side_effect=fake_send,
    )

    agent_handler.execute_project_plan(console, args, project_plan)

    # Đã recreate session sau khi quota
    assert mock_start.call_count == 2

    # In ra thông báo recreate session
    recreate_msg = i18n.tr("vi", "agent_recreate_session_quota")
    printed = [call.args[0] for call in console.print.call_args_list if call.args]
    assert recreate_msg in printed


def test_execute_project_plan_handles_invalid_step_json_and_prints_error(mocker):
    """execute_project_plan: khi JSON step không hợp lệ, phải in lỗi và dừng."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=False)

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    project_plan = {
        "project_name": "Demo",
        "reasoning": "Because tests",
        "structure": {"root": {}},
        "files": [],
    }

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        return_value=object(),
    )

    # Trả về text không có JSON hợp lệ => raise ValueError trong executor loop
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        return_value=type("Resp", (), {"text": "no-json-here"}),
    )

    mock_exec_tool = mocker.patch("termi_cli.handlers.agent_handler._execute_tool")

    agent_handler.execute_project_plan(console, args, project_plan)

    # Không nên gọi tool nào khi JSON không hợp lệ
    mock_exec_tool.assert_not_called()

    printed = [str(call.args[0]) for call in console.print.call_args_list if call.args]
    assert any("No valid JSON found." in text for text in printed)


def test_execute_simple_task_handles_quota_and_recreates_session(mocker):
    """execute_simple_task: khi quota ở bước tiếp theo, phải recreate session."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=False)

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    first_step = {
        "thought": "First",
        "action": {"tool_name": "dummy_tool", "tool_args": {"x": 1}},
    }

    mock_start = mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        side_effect=[object(), object()],
    )

    # Bước đầu tiên gọi tool bình thường
    mock_exec_tool = mocker.patch(
        "termi_cli.handlers.agent_handler._execute_tool",
        return_value="OBS",
    )

    # Bước thứ hai: đầu tiên quota, sau đó trả về step finish hợp lệ
    step_finish = {
        "thought": "Second",
        "action": {"tool_name": "finish", "tool_args": {"answer": "ok"}},
    }
    success_payload = json.dumps(step_finish)
    success_resp = type("Resp", (), {"text": f"```json\n{success_payload}\n```"})

    calls = [RPDQuotaExhausted("quota"), success_resp]

    def fake_send(_session, _prompt):
        value = calls.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        side_effect=fake_send,
    )

    agent_handler.execute_simple_task(console, args, first_step)

    # Tool được gọi ít nhất một lần cho bước đầu tiên
    mock_exec_tool.assert_called()

    # Đã recreate session sau khi quota
    assert mock_start.call_count == 2

    recreate_msg = i18n.tr("vi", "agent_recreate_session_quota")
    printed = [call.args[0] for call in console.print.call_args_list if call.args]
    assert recreate_msg in printed


def test_execute_simple_task_handles_invalid_step_json_and_prints_error(mocker):
    """execute_simple_task: khi JSON ở bước tiếp theo không hợp lệ, phải in lỗi và dừng."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=False)

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    first_step = {
        "thought": "First",
        "action": {"tool_name": "dummy_tool", "tool_args": {"x": 1}},
    }

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        return_value=object(),
    )

    # Bước đầu tiên gọi tool bình thường
    mock_exec_tool = mocker.patch(
        "termi_cli.handlers.agent_handler._execute_tool",
        return_value="OBS",
    )

    # Bước tiếp theo trả về text không có JSON hợp lệ
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        return_value=type("Resp", (), {"text": "no-json-here"}),
    )

    agent_handler.execute_simple_task(console, args, first_step)

    # Tool chỉ được gọi cho bước đầu tiên
    mock_exec_tool.assert_called_once()

    printed = [str(call.args[0]) for call in console.print.call_args_list if call.args]
    assert any("No valid JSON found." in text for text in printed)


def test_execute_simple_task_prints_dry_run_header_when_flag_set(mocker, monkeypatch):
    """execute_simple_task phải in header DRY-RUN khi args.agent_dry_run=True."""
    console = mocker.MagicMock(spec=Console)
    args = _make_args(agent_dry_run=True)

    mocker.patch(
        "termi_cli.handlers.agent_handler.load_config",
        return_value={"language": "vi", "agent_model": "dummy-model"},
    )

    first_step = {
        "thought": "First step",
        "action": {"tool_name": "dummy_tool", "tool_args": {"x": 1}},
    }

    mocker.patch(
        "termi_cli.handlers.agent_handler.api.start_chat_session",
        return_value=object(),
    )

    # Các bước tiếp theo sẽ gây lỗi có kiểm soát để thoát vòng lặp sớm
    mocker.patch(
        "termi_cli.handlers.agent_handler.api.resilient_send_message",
        side_effect=RuntimeError("stop after first step"),
    )

    # Không cần assert _execute_tool tại đây, đã được cover ở các test unit.
    agent_handler.execute_simple_task(console, args, first_step)

    # Header DRY-RUN được in ra
    dry_run_header = i18n.tr("vi", "agent_dry_run_mode_header")
    printed_args = [call.args[0] for call in console.print.call_args_list]
    assert dry_run_header in printed_args
