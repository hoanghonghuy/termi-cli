"""
src/config.py

Phiên bản hoàn chỉnh:
- Giữ nguyên load_config() và save_config() như gốc
- Bổ sung xử lý API keys, thư mục chat_logs, và cờ tắt stderr native
- Hợp nhất cấu hình mặc định mở rộng để tương thích với toàn bộ hệ thống
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

CONFIG_PATH = Path("config.json")

# Cấu hình mặc định mở rộng
DEFAULT_CONFIG = {
    "default_model": "models/gemini-flash-latest",
    "default_format": "rich",
    "default_system_instruction": "You are a helpful AI assistant.",
    "model_fallback_order": [
        "models/gemini-flash-latest",
        "models/gemini-pro-latest"
    ],
    "personas": {},
    "database": {},
    # ---- các trường mở rộng mới để tương thích phần còn lại ----
    "chat_logs_dir": "chat_logs",
    "api_keys": [],
    "silence_native_stderr": True
}


def load_config() -> dict:
    """Tải cấu hình từ file config.json và hợp nhất với mặc định."""
    load_dotenv()  # nạp biến môi trường nếu có

    config = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                user_config = json.load(f)
                if isinstance(user_config, dict):
                    config.update(user_config)
            except json.JSONDecodeError:
                # Nếu file config bị lỗi, giữ nguyên mặc định
                pass

    # ---- Hỗ trợ API keys từ biến môi trường ----
    env_keys = (
        os.getenv("API_KEYS")
        or os.getenv("GEMINI_API_KEYS")
        or os.getenv("GOOGLE_API_KEYS")
    )
    if env_keys:
        keys = [k.strip() for k in env_keys.split(",") if k.strip()]
        if keys:
            config["api_keys"] = keys

    # dò API_KEY_1...API_KEY_10
    if not config.get("api_keys"):
        collected = []
        for i in range(1, 11):
            key = os.getenv(f"API_KEY_{i}") or os.getenv(f"GEMINI_API_KEY_{i}")
            if key:
                collected.append(key.strip())
        if collected:
            config["api_keys"] = collected

    # ---- Đảm bảo thư mục chat_logs tồn tại ----
    chat_logs_dir = Path(config.get("chat_logs_dir", "chat_logs"))
    try:
        chat_logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # ---- Cờ tắt stderr native ----
    env_silence = os.getenv("SILENCE_NATIVE_STDERR")
    if env_silence is not None:
        config["silence_native_stderr"] = env_silence not in ("0", "false", "no")

    return config


def save_config(config: dict):
    """Lưu cấu hình vào file config.json."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
