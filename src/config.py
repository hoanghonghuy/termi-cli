import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

def load_config() -> dict:
    """Tải cấu hình từ file config.json."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # Nếu file config bị lỗi, trả về cấu hình mặc định
                pass
                
    # Cấu hình mặc định nếu file không tồn tại hoặc bị lỗi
    return {
        "default_model": "models/gemini-flash-latest",
        "default_format": "rich",
        "default_system_instruction": "You are a helpful AI assistant.",
        "model_fallback_order": [
            "models/gemini-flash-latest",
            "models/gemini-pro-latest"
        ],
        "personas": {},
        "database": {}
    }

def save_config(config: dict):
    """Lưu cấu hình vào file config.json."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)