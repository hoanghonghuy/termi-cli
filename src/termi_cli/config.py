import os
import json
import logging
from pathlib import Path

from termi_cli.json_utils import JsonPayloadParseError, parse_json_payload

APP_DIR = Path(os.getenv("TERMI_CLI_HOME") or (Path.home() / ".termi-cli"))
_LEGACY_CONFIG_PATH = Path("config.json")
logger = logging.getLogger(__name__)

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
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            parsed = parse_json_payload(raw_content)
            if isinstance(parsed, dict):
                config_data = parsed
            else:
                logger.warning("Config file %s không phải JSON object, fallback về defaults", CONFIG_PATH)
        except (OSError, JsonPayloadParseError) as err:
            logger.warning(
                "Không thể đọc config %s do JSON không hợp lệ: %s. Sẽ dùng defaults trong runtime.",
                CONFIG_PATH,
                err,
            )

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
        "profiles": {
            # Preset profile: dùng bộ model OpenRouter free mạnh cho coding.
            # Có thể kích hoạt nhanh bằng cờ --profile openrouter-free-coding
            "openrouter-free-coding": {
                "default_model": "openai/gpt-4o-mini",
                "code_model": "meta-llama/llama-3.1-70b-instruct",
                "commit_model": "openai/gpt-4o-mini",
                # Agent vẫn dùng Gemini để tận dụng tool-calls an toàn hơn
                "agent_model": "models/gemini-pro-latest",
                "language": "vi",
                "default_system_instruction": "You are a helpful AI assistant.",
            },
            "dev-groq-fast-coding": {
                "default_model": "groq-chat",
                "code_model": "groq-llama3-8b-8192",
                "commit_model": "groq-chat",
                "agent_model": "models/gemini-pro-latest",
                "language": "vi",
                "default_system_instruction": "You are a helpful AI assistant.",
            },
            "deepseek-reasoning-heavy": {
                "default_model": "deepseek-reasoner",
                "code_model": "deepseek-reasoner",
                "commit_model": "deepseek-chat",
                "agent_model": "models/gemini-pro-latest",
                "language": "vi",
                "default_system_instruction": "You are a helpful AI assistant.",
            },
        },
        # Gán nhãn mặc định cho một số model OpenRouter phổ biến (free tier / OSS)
        "model_labels": {
            "openai/gpt-4o-mini": "(free tier)",
            "google/gemma-2-9b-it": "(free tier)",
            "google/gemma-2-27b-it": "(free tier)",
            "meta-llama/llama-3.1-8b-instruct": "(free tier)",
            "meta-llama/llama-3.1-70b-instruct": "(free tier)",
            "mistralai/mixtral-8x7b-instruct": "(free tier)",
            "mistralai/mistral-7b-instruct": "(free tier)",
            "qwen/qwen2.5-7b-instruct": "(free tier)",
        },
        # Cấu hình mặc định cho mini-agent single-turn khi dùng HTTP providers (DeepSeek/Groq/OpenRouter/Ollama).
        # Người dùng có thể sửa/trộn thêm rule trong config.json.
        "mini_agent": {
            "enabled": True,
            "rules": [
                {
                    "tool_name": "get_current_time",
                    "patterns": [
                        "bây giờ là mấy giờ",
                        "bay gio la may gio",
                        "mấy giờ rồi",
                        "may gio roi",
                        "giờ hệ thống",
                        "gio he thong",
                        "giờ việt nam",
                        "gio viet nam",
                        "hôm nay là ngày mấy",
                        "hom nay la ngay may",
                        "what time is it",
                        "current time",
                        "what is the time",
                        "today's date",
                        "what is today",
                    ],
                    "pass_prompt": False,
                },
                {
                    "tool_name": "get_cli_uptime",
                    "patterns": [
                        "uptime",
                        "thời gian chạy",
                        "thoi gian chay",
                        "thời gian hoạt động",
                        "thoi gian hoat dong",
                        "system uptime",
                    ],
                    "pass_prompt": False,
                },
                {
                    "tool_name": "search_web",
                    "patterns": [
                        "thời tiết",
                        "thoi tiet",
                        "nhiệt độ",
                        "nhiet do",
                        "trời mưa",
                        "troi mua",
                        "weather",
                        "forecast",
                        "temperature",
                        "weather in",
                        "forecast for",
                        "weather in hcmc tomorrow",
                    ],
                    "pass_prompt": True,
                },
                {
                    "tool_name": "search_web",
                    "patterns": [
                        # Tỷ giá VN/EN
                        "tỷ giá",
                        "ty gia",
                        "tỉ giá",
                        "ti gia",
                        "tỷ giá usd",
                        "ty gia usd",
                        "exchange rate",
                        "usd vnd",
                        "eur vnd",
                        "usd to vnd",
                        "eur to vnd",
                        # Giá crypto
                        "giá btc",
                        "gia btc",
                        "giá bitcoin",
                        "gia bitcoin",
                        "btc price",
                        "bitcoin price",
                        "eth price",
                        "crypto price",
                    ],
                    "pass_prompt": True,
                },
            ],
        },
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