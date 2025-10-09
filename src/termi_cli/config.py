import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

MODEL_RPM_LIMITS = {
    "models/gemini-2.5-pro": 2,
    "models/gemini-pro-latest": 2,
    "models/gemini-flash-latest": 15,
}

def load_config() -> dict:
    """Tải cấu hình từ file config.json."""
    config_data = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                config_data = json.load(f)
            except json.JSONDecodeError:
                pass # Sẽ sử dụng giá trị mặc định nếu file lỗi
                
    # --- Cấu hình mặc định ---
    defaults = {
        "default_model": "models/gemini-flash-latest",
        "agent_model": "models/gemini-pro-latest",
        "default_format": "rich",
        "default_system_instruction": "You are a helpful AI assistant.",
        "model_fallback_order": [
            "models/gemini-flash-latest",
            "models/gemini-pro-latest"
        ],
        "personas": {},
        "database": {}
    }
    
    final_config = {**defaults, **config_data}
    
    return final_config

def save_config(config: dict):
    """Lưu cấu hình vào file config.json."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)