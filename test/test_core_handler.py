from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from google.api_core.exceptions import ResourceExhausted, PermissionDenied, InvalidArgument

from termi_cli.handlers import core_handler


def test_confirm_and_write_file_user_accepts(tmp_path, mocker):
    """Khi user trả lời 'y', file phải được ghi ra đĩa với nội dung đúng."""
    console = mocker.MagicMock()
    console.input.return_value = "y"

    file_path = tmp_path / "out.txt"

    # Đảm bảo language là 'vi' để dùng bộ i18n mặc định
    mocker.patch("termi_cli.handlers.core_handler.load_config", return_value={"language": "vi"})

    result = core_handler.confirm_and_write_file(console, str(file_path), "hello")

    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == "hello"
    assert "Đã ghi thành công" in result


def test_confirm_and_write_file_user_denies(tmp_path, mocker):
    """Khi user trả lời khác 'y', không ghi file và trả về thông báo từ chối."""
    console = mocker.MagicMock()
    console.input.return_value = "n"

    file_path = tmp_path / "out.txt"

    mocker.patch("termi_cli.handlers.core_handler.load_config", return_value={"language": "vi"})

    result = core_handler.confirm_and_write_file(console, str(file_path), "hello")

    assert not file_path.exists()
    assert "từ chối" in result


def test_handle_conversation_turn_executes_tools_when_function_calls_present(mocker, monkeypatch):
    """handle_conversation_turn phải gọi _execute_single_tool_call khi có function_calls."""
    console = mocker.MagicMock()
    chat_session = object()
    prompt_parts = ["hello"]

    # Chuẩn bị một function_call giả lập mà _send_and_accumulate sẽ trả về
    func_call = SimpleNamespace(name="dummy_tool", args={"x": 1})

    # Lần đầu: trả về text + 1 function_call, lần hai: chỉ có text, không còn function_call
    calls = [
        ("Hello", [func_call]),
        ("Final answer", []),
    ]

    def fake_send_and_accumulate(session, message, total_tokens):
        return calls.pop(0)

    mocker.patch(
        "termi_cli.handlers.core_handler._send_and_accumulate",
        side_effect=fake_send_and_accumulate,
    )

    def fake_execute_single_tool_call(func_call_arg, status, console_arg, tool_calls_log):
        # Ghi log giống logic thật để dễ assert
        entry = {
            "name": func_call_arg.name,
            "args": dict(func_call_arg.args),
            "result": "OK",
        }
        tool_calls_log.append(entry)
        return {
            "function_response": {
                "name": func_call_arg.name,
                "response": {"result": "OK"},
            }
        }

    mocker.patch(
        "termi_cli.handlers.core_handler._execute_single_tool_call",
        side_effect=fake_execute_single_tool_call,
    )

    # Đảm bảo max_attempts > 0 nhưng không ảnh hưởng tới flow
    monkeypatch.setattr(core_handler.api, "_api_keys", ["k1"], raising=False)

    mocker.patch(
        "termi_cli.handlers.core_handler.api.get_model_token_limit",
        return_value=999,
    )

    result_text, total_tokens, token_limit, tool_calls_log = core_handler.handle_conversation_turn(
        chat_session,
        prompt_parts,
        console,
        model_name="dummy-model",
        args=None,
    )

    # Text trả về phải ghép từ hai chunk
    assert "Hello" in result_text
    assert "Final answer" in result_text

    # Token limit lấy từ api.get_model_token_limit
    assert token_limit == 999

    # tool_calls_log được ghi lại đúng một lần cho dummy_tool
    assert tool_calls_log == [
        {"name": "dummy_tool", "args": {"x": 1}, "result": "OK"},
    ]


def test_handle_conversation_turn_retries_on_quota_and_recreates_session(mocker, monkeypatch):
    """Khi gặp ResourceExhausted, handle_conversation_turn phải retry và recreate session."""
    console = mocker.MagicMock()
    chat_session = object()
    prompt_parts = ["hello"]

    # Lần đầu _send_and_accumulate ném ResourceExhausted, lần hai trả về text bình thường
    calls = [
        ResourceExhausted("quota"),
        ("Hello after quota", []),
    ]

    def fake_send_and_accumulate(session, message, total_tokens):
        value = calls.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    mocker.patch(
        "termi_cli.handlers.core_handler._send_and_accumulate",
        side_effect=fake_send_and_accumulate,
    )

    # Đảm bảo có ít nhất 2 api_keys để vòng retry hoạt động
    monkeypatch.setattr(core_handler.api, "_api_keys", ["k1", "k2"], raising=False)

    mock_switch = mocker.patch(
        "termi_cli.handlers.core_handler.api.switch_to_next_api_key",
        return_value="key#2",
    )
    mock_start = mocker.patch(
        "termi_cli.handlers.core_handler.api.start_chat_session",
        return_value=object(),
    )

    # Tránh phụ thuộc vào config/tham số thật
    mocker.patch(
        "termi_cli.handlers.core_handler.get_session_recreation_args",
        return_value=("sys", [], ""),
    )

    mocker.patch(
        "termi_cli.handlers.core_handler.api.get_model_token_limit",
        return_value=123,
    )

    result_text, total_tokens, token_limit, tool_calls_log = core_handler.handle_conversation_turn(
        chat_session,
        prompt_parts,
        console,
        model_name="dummy-model",
        args=None,
    )

    # Sau khi retry, vẫn phải trả về text lần thứ hai
    assert "Hello after quota" in result_text
    assert token_limit == 123

    # Đã switch key và recreate session đúng 1 lần
    mock_switch.assert_called_once()
    mock_start.assert_called_once()

    # In ra cảnh báo quota và thông báo chuyển key
    printed = [str(call.args[0]) for call in console.print.call_args_list if call.args]
    assert any("Gặp lỗi Quota" in text for text in printed)
    assert any("Đã chuyển sang" in text for text in printed)


def test_handle_conversation_turn_raises_permission_denied_without_retry(mocker, monkeypatch):
    """Khi gặp PermissionDenied, phải re-raise và không switch key hay recreate session."""
    console = mocker.MagicMock()
    chat_session = object()
    prompt_parts = ["hello"]

    def fake_send_and_accumulate(session, message, total_tokens):
        raise PermissionDenied("denied")

    mocker.patch(
        "termi_cli.handlers.core_handler._send_and_accumulate",
        side_effect=fake_send_and_accumulate,
    )

    monkeypatch.setattr(core_handler.api, "_api_keys", ["k1"], raising=False)

    mock_switch = mocker.patch(
        "termi_cli.handlers.core_handler.api.switch_to_next_api_key",
    )
    mock_start = mocker.patch(
        "termi_cli.handlers.core_handler.api.start_chat_session",
    )

    with pytest.raises(PermissionDenied):
        core_handler.handle_conversation_turn(
            chat_session,
            prompt_parts,
            console,
            model_name="dummy-model",
            args=None,
        )

    mock_switch.assert_not_called()
    mock_start.assert_not_called()


def test_handle_conversation_turn_raises_invalid_argument_without_retry(mocker, monkeypatch):
    """Khi gặp InvalidArgument, phải re-raise và không switch key hay recreate session."""
    console = mocker.MagicMock()
    chat_session = object()
    prompt_parts = ["hello"]

    def fake_send_and_accumulate(session, message, total_tokens):
        raise InvalidArgument("bad-args")

    mocker.patch(
        "termi_cli.handlers.core_handler._send_and_accumulate",
        side_effect=fake_send_and_accumulate,
    )

    monkeypatch.setattr(core_handler.api, "_api_keys", ["k1"], raising=False)

    mock_switch = mocker.patch(
        "termi_cli.handlers.core_handler.api.switch_to_next_api_key",
    )
    mock_start = mocker.patch(
        "termi_cli.handlers.core_handler.api.start_chat_session",
    )

    with pytest.raises(InvalidArgument):
        core_handler.handle_conversation_turn(
            chat_session,
            prompt_parts,
            console,
            model_name="dummy-model",
            args=None,
        )

    mock_switch.assert_not_called()
    mock_start.assert_not_called()


def test_accumulate_response_stream_with_plain_text_only():
    """accumulate_response_stream: chỉ có text thường thì full_text được ghép lại, không có function_calls."""

    class Part:
        def __init__(self, text):
            self.text = text

    class Content:
        def __init__(self, parts):
            self.parts = parts

    class Candidate:
        def __init__(self, content):
            self.content = content

    class Chunk:
        def __init__(self, candidates):
            self.candidates = candidates

    stream = [
        Chunk([Candidate(Content([Part("Hello "), Part("world")]))]),
    ]

    full_text, function_calls = core_handler.accumulate_response_stream(stream)

    assert "Hello" in full_text
    assert "world" in full_text
    assert function_calls == []


def test_accumulate_response_stream_parses_embedded_json_tool_call():
    """accumulate_response_stream: khi part.text là JSON tool_call, phải tạo function_call tương ứng."""

    tool_payload = {
        "tool_name": "write_file",
        "tool_args": {"path": "demo.txt", "content": "hi"},
    }

    class Part:
        def __init__(self, text):
            self.text = text

    class Content:
        def __init__(self, parts):
            self.parts = parts

    class Candidate:
        def __init__(self, content):
            self.content = content

    class Chunk:
        def __init__(self, candidates):
            self.candidates = candidates

    json_text = json.dumps(tool_payload)
    stream = [
        Chunk([Candidate(Content([Part(json_text)]))]),
    ]

    full_text, function_calls = core_handler.accumulate_response_stream(stream)

    # Khi parse JSON tool_call, full_text phải rỗng và có 1 function_call tạo từ JSON
    assert full_text == ""
    assert len(function_calls) == 1
    fc = function_calls[0]
    assert getattr(fc, "name") == "write_file"
    assert getattr(fc, "args") == {"path": "demo.txt", "content": "hi"}


def test_accumulate_response_stream_collects_native_function_calls():
    """accumulate_response_stream: nếu part.function_call có sẵn, phải thêm nguyên object đó vào function_calls."""

    class Part:
        def __init__(self, function_call):
            self.function_call = function_call
            self.text = None

    class Content:
        def __init__(self, parts):
            self.parts = parts

    class Candidate:
        def __init__(self, content):
            self.content = content

    class Chunk:
        def __init__(self, candidates):
            self.candidates = candidates

    native_fc = SimpleNamespace(name="from_model", args={"y": 2})

    stream = [
        Chunk([Candidate(Content([Part(native_fc)]))]),
    ]

    full_text, function_calls = core_handler.accumulate_response_stream(stream)

    assert full_text == ""
    assert function_calls == [native_fc]
