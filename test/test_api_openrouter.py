import pytest

from termi_cli import api


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("models/gemini-flash-latest", False),
        ("deepseek-chat", False),
        ("groq-llama-3.1-70b", False),
        ("openai/gpt-4o-mini", True),
        ("meta-llama/llama-3.3-70b-instruct", True),
        ("ollama/qwen3:8b", False),
    ],
)
def test_is_openrouter_model_classification(model_name, expected):
    assert api.is_openrouter_model(model_name) is expected
