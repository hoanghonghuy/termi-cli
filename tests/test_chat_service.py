import argparse

from termi_cli.application.chat_service import ChatService


def test_get_gemini_fallback_model_prefers_default():
    config = {
        "default_model": "models/gemini-pro-latest",
        "model_fallback_order": ["models/gemini-flash-latest"],
    }

    result = ChatService.get_gemini_fallback_model(config)

    assert result == "models/gemini-pro-latest"


def test_get_gemini_fallback_model_uses_fallback_order():
    config = {
        "default_model": "deepseek-chat",
        "model_fallback_order": ["models/gemini-flash-latest", "deepseek-chat"],
    }

    result = ChatService.get_gemini_fallback_model(config)

    assert result == "models/gemini-flash-latest"


def test_get_gemini_fallback_model_falls_back_to_default_constant():
    # Khi không có default_model hoặc fallback hợp lệ, hàm sẽ trả về
    # hằng số dự phòng "models/gemini-flash-latest".
    config: dict = {}

    result = ChatService.get_gemini_fallback_model(config)

    assert result == "models/gemini-flash-latest"
