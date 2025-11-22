import os
import json
from pathlib import Path

APP_DIR = Path(os.getenv("TERMI_CLI_HOME") or (Path.home() / ".termi-cli"))
_LEGACY_CONFIG_PATH = Path("config.json")

if _LEGACY_CONFIG_PATH.exists():
    CONFIG_PATH = _LEGACY_CONFIG_PATH
else:
    CONFIG_PATH = APP_DIR / "config.json"

MODEL_RPM_LIMITS = {
    "models/gemini-2.5-pro": 2,
    "models/gemini-pro-latest": 2,
    "models/gemini-flash-latest": 15,
}

def load_config() -> dict:
    """Tải cấu hình từ file config.json."""
    config_data = {}
    config_exists = CONFIG_PATH.exists()

    if config_exists:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                config_data = json.load(f)
            except json.JSONDecodeError:
                # Nếu file hỏng, giữ nguyên để người dùng tự xử lý,
                # và chỉ dùng defaults trong runtime mà không ghi đè.
                pass
                
    # --- Cấu hình mặc định ---
    defaults = {
        "default_model": "models/gemini-flash-latest",
        "agent_model": "models/gemini-pro-latest",
        # Model dành riêng cho các tiện ích code (refactor/document).
        # Mặc định trùng với default_model để không thay đổi behaviour cũ.
        "code_model": "models/gemini-flash-latest",
        # Model dành riêng cho việc sinh commit message.
        # Mặc định trùng với default_model để backward-compatible.
        "commit_model": "models/gemini-flash-latest",
        "default_format": "rich",
        "default_system_instruction": "You are a helpful AI assistant.",
        "language": "vi",
        "model_fallback_order": [
            "models/gemini-flash-latest",
            "models/gemini-pro-latest"
        ],
        "personas": {},
        "database": {},
        "profiles": {},
    }
    
    final_config = {**defaults, **config_data}

    # Đảm bảo language luôn ở dạng hợp lệ
    lang_val = final_config.get("language", "vi")
    if lang_val not in ("vi", "en"):
        final_config["language"] = "vi"

    # Nếu chưa có file config, tự tạo một file mới với giá trị mặc định.
    if not config_exists:
        try:
            save_config(final_config)
        except Exception:
            # Không để lỗi ghi file làm hỏng quá trình khởi động CLI.
            pass

    return final_config

def save_config(config: dict):
    """Lưu cấu hình vào file config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)