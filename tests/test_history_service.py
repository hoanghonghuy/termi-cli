from types import SimpleNamespace

from termi_cli.application.history_service import HistoryService


class DummyPart:
    def __init__(self, text=None, function_call=None, function_response=None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response


class DummyContent:
    def __init__(self, role, parts):
        self.role = role
        self.parts = parts


def test_serialize_history_basic():
    parts = [
        DummyPart(text="hello"),
        DummyPart(function_call=SimpleNamespace(name="tool_x", args={"x": 1})),
    ]
    history = [DummyContent("user", parts)]

    service = HistoryService()
    result = service.serialize_history(history)

    assert isinstance(result, list)
    assert result[0]["role"] == "user"
    assert result[0]["parts"][0]["text"] == "hello"
    assert result[0]["parts"][1]["function_call"]["name"] == "tool_x"
