---
title: Termi – Advanced Usage
---

# Termi – Advanced Usage

This document describes the advanced features that are only briefly mentioned in the main `README.md`.

## Developer utilities

- `--document <FILE_PATH>`  
  Generate docstrings and comments for the specified code file.

- `--refactor <FILE_PATH>`  
  Get AI-powered suggestions for restructuring and improving the code.

- `--git-commit`  
  Generate a detailed Conventional Commit message (subject + body) based on staged changes.  
  The CLI writes the message to a temporary file and proposes a `git commit -F` command.

- `--git-commit-short`  
  Generate a short, single-line Conventional Commit subject based on staged changes and propose a `git commit -m` command.
- **Lint reminder:** khi phát triển các tiện ích mới, luôn chạy `python -m ruff check src test tests` (hoặc ít nhất các thư mục liên quan) trước khi mở PR để đảm bảo phong cách thống nhất.

- `--list-tools`  
  List all available tools (core + plugin) that the Agent can call.

## Customization & context

- `-m, --model <NAME>`  
  Select the model for the current run (overrides `default_model`).

- `--set-model`  
  Launch a multi-provider wizard (Gemini / DeepSeek / Groq / OpenRouter) to choose `default_model`, `code_model`, and `commit_model`.

- `--list-models`  
  List available Gemini models (with provider).

- `-i <PATH>`  
  Provide image paths for multimodal analysis.

- `--read-dir`  
  Read the current directory to give more context to the AI.

- Personas and instructions:
  - `--add-persona`, `--list-personas`, `--rm-persona`
  - `--add-instruct`, `--list-instructs`, `--rm-instruct`

## Local models via Ollama

Termi can talk to local models exposed by [Ollama](https://ollama.com/) using its OpenAI-compatible Chat Completions API.

Basic steps:

1. Install Ollama and pull a model, for example:

   ```bash
   ollama pull qwen3:8b
   ```

2. Make sure the Ollama server is running (by default on `http://127.0.0.1:11434`).

3. In your `config.json`, set a model such as:

   ```json
   { "default_model": "ollama/qwen3:8b" }
   ```

   You can also use `ollama/qwen3:8b` for `agent_model` if you want the Agent to run on Qwen locally.

4. Optionally override the Ollama base URL via:

   ```bash
   export OLLAMA_BASE_URL="http://localhost:11434"
   ```

You can then use this model with any Termi command that accepts `-m/--model`, for example:

```bash
termi -m ollama/qwen3:8b "Explain this file"
termi --chat -m ollama/qwen3:8b
termi --agent -m ollama/qwen3:8b "Refactor this module"
```

## Language & i18n

- Default UI language is Vietnamese (`"language": "vi"`).
- Per-run override:

```bash
termi --lang en "Explain this code"
```

Supported values:
- `vi` – Vietnamese UI messages  
- `en` – English UI messages  

The same setting is reused across core CLI, history browser, chat mode, and Agent panels.

## Runtime data, reset & troubleshooting

Runtime data lives under `APP_DIR`:

- Default: `~/.termi-cli`
- Or: whatever `TERMI_CLI_HOME` points to.

Important paths:

- `config.json` – persistent configuration.
- `memory_db/` – long‑term memory database.
- `chat_logs/` – stored chat history.
- `logs/termi.log` – application logs.

Reset commands:

```bash
# Reset long‑term memory DB
termi --reset-memory

# Reset configuration to defaults
termi --reset-config
```

Interactive terminals ask for confirmation; non-interactive runs skip it.

## Python version & Gemini compatibility

- The project targets **Python 3.10+** (as specified in `pyproject.toml`).
- Gemini-based features rely on `google-generativeai` and its transitive dependencies (such as `protobuf`). These libraries may lag behind the latest CPython releases.
- On newer Python versions where the Gemini SDK cannot be imported cleanly (for example due to binary wheels not being available yet), Termi behaves as follows:
  - HTTP-only providers (**DeepSeek**, **Groq**, **OpenRouter**, **Ollama local/Cloud**) continue to work via pure-HTTP code paths.
  - Commands that strictly require Gemini (e.g. some Agent flows or model listing) print a clear error message suggesting you either:
    - switch to an HTTP model, or
    - run Termi on a supported Python version (for example 3.10–3.12) where Gemini is fully available.
  - The test suite uses lightweight stubs so that Agent logic can still be tested even when the real Gemini SDK is not installed.

## Provider architecture (developers)

Termi routes all single-turn text generation through `api.generate_text(model_name, prompt, system_instruction=None)`:

- A small helper `_detect_provider_kind(model_name)` maps the model name to a logical provider kind:
  `deepseek`, `groq`, `openrouter`, `ollama`, `ollama_cloud`, or `gemini`.
- For HTTP providers (`deepseek`, `groq`, `openrouter`, `ollama`, `ollama_cloud`), Termi uses a lightweight class-based abstraction:
  - `BaseProvider` (abstract) defines `generate(model_name, prompt, system_instruction) -> str`.
  - Concrete providers (`DeepseekProvider`, `GroqProvider`, `OpenRouterProvider`, `OllamaProvider`, `OllamaCloudProvider`) wrap the existing resilient HTTP helpers
    such as `_resilient_deepseek_api_call`, `_resilient_groq_api_call`, `_resilient_openrouter_api_call`, `_ollama_chat_completions`, and `_ollama_cloud_chat_completions`.
  - A simple registry `_PROVIDER_REGISTRY: dict[str, BaseProvider]` maps provider kinds to their instances.
- `generate_text` calls the appropriate `BaseProvider.generate(...)` for HTTP providers, and keeps the original Gemini SDK path for `provider_kind == "gemini"`.
- **JSON hardening:** mọi response HTTP đều đi qua helper `parse_json_payload`, helper này sanitize dấu phẩy thừa trước `}`/`]` rồi mới `json.loads`, giúp tránh crash khi provider trả JSON sai chuẩn.

To add a new HTTP provider, you typically:

1. Extend `_detect_provider_kind` to return a new kind (e.g. `"mycloud"`) for specific model name patterns.
2. Implement a `MyCloudProvider(BaseProvider)` that calls your HTTP API and returns the final text.
3. Register it in `_PROVIDER_REGISTRY["mycloud"]`.

### HTTP metrics & diagnostics

- `api.generate_text` duy trì một bộ đếm nhẹ `_HTTP_METRICS` cho các provider HTTP:
  - `http_calls_total`: số lần gọi HTTP thực sự sau khi miss cache.
  - `http_calls_by_provider`: phân rã theo `deepseek`, `groq`, `openrouter`, `ollama`, `ollama_cloud`.
  - `http_cache_hits_total`: số lần cache trả về kết quả, tránh phải gọi HTTP.
- Các số liệu này có thể truy vấn qua `api.get_http_metrics()` (dùng trong diagnostics hoặc tooling nội bộ) và được log ở mức DEBUG, giúp theo dõi hiệu quả cache cũng như tần suất gọi từng provider mà không ảnh hưởng tới API công khai.

## Agent modes and tuning

### Modes

- Normal execution (default):

```bash
termi --agent "Set up a small API service for this project"
```

- Dry-run (preview without destructive side effects):

```bash
termi --agent --agent-dry-run "Design a CLI utility for this repo"
```

### Tuning

- `--agent-max-steps N`  
  Limit the number of steps per Agent session.

Examples:

```bash
termi --agent "Design the architecture for this service" --agent-max-steps 8
termi --agent --agent-dry-run "Refactor module XYZ" --agent-max-steps 5
```

## History & memory scripting

Work with history/memory without entering the interactive UI:

- `--rm-history TARGET`  
  Delete a chat history entry (by topic or JSON file path).

- `--rename-history OLD NEW`  
  Rename a history entry.

- `--memory-search QUERY`  
  Search long‑term memory and print results as Markdown.

## Profiles

Profiles let you save and reuse model/language/instruction settings.

- Save current profile:

```bash
termi --save-profile dev-gemini
```

- List profiles:

```bash
termi --list-profiles
```

- Apply a profile:

```bash
termi --profile dev-gemini --chat
```

Profiles can override `default_model`, `code_model`, `commit_model`, `agent_model`, `language`, and `default_system_instruction` for that run.

## Plugin tools

Advanced users can add custom tools without modifying the core code.

- Plugins are discovered in: `APP_DIR/plugins/*.py`
- Each plugin can expose a `PLUGIN_TOOLS` dict:

```python
# ~/.termi-cli/plugins/http_tools.py

def ping_url(url: str) -> str:
    """Ping a URL with a simple HTTP GET."""
    import requests
    try:
        resp = requests.get(url, timeout=5)
        return f"Status: {resp.status_code}, length: {len(resp.content)}"
    except Exception as e:
        return f"Error while requesting {url}: {e}"

PLUGIN_TOOLS = {
    "ping_url": ping_url,
}
```

On startup, Termi imports these plugins and merges `PLUGIN_TOOLS` into its internal tool map. Import errors are ignored so a broken plugin does not prevent the CLI from starting.

## HTTP mini-agent for local/HTTP models

When your `default_model` is an HTTP provider (such as `deepseek-*`, `groq-*`, OpenRouter IDs, or `ollama/...`), Termi's single‑turn mode includes a lightweight **HTTP mini‑agent**.

Before sending the prompt to the HTTP model, the mini‑agent:

- Normalizes the prompt to lowercase.
- Checks it against a list of **pattern rules** defined in `config.json` under the `mini_agent` key.
- If a rule matches, it calls a local/tool function (e.g. `get_current_time`, `get_cli_uptime`, or `search_web`) and returns the result directly.
- If no rule matches, it falls back to calling the HTTP model as usual.

This is designed for very common questions where tools provide more accurate answers than the model alone (time, uptime, weather, FX/crypto prices, etc.).

### Configuration: `mini_agent` in `config.json`

The `mini_agent` configuration lives in the same `config.json` file as your models. Its structure looks like:

- `enabled` (bool): turns the HTTP mini‑agent on or off.
- `rules` (list): each rule has:
  - `tool_name`: the name of a tool from `api.AVAILABLE_TOOLS` (e.g. `get_current_time`, `get_cli_uptime`, `search_web`).
  - `patterns`: list of substrings; if any of them appears in the normalized prompt, the rule matches.
  - `pass_prompt` (bool):
    - `false`: the tool is called as `tool()`.
    - `true`: the tool is called as `tool(prompt)` (used for `search_web` so the full question is preserved as the query).

By default, Termi ships with rules for:

- **Current time / date**: mapped to `get_current_time`.
- **CLI uptime**: mapped to `get_cli_uptime`.
- **Weather queries** (both Vietnamese and English patterns, including examples like `weather in HCMC tomorrow`): mapped to `search_web`.
- **FX & crypto prices** (e.g. `tỷ giá usd`, `usd to vnd`, `btc price`, `eth price`): also mapped to `search_web`.

You can customize or extend these rules by editing `mini_agent.rules` in your `config.json`:

- Add new patterns (in Vietnamese or English).
- Add new tools (for example, a custom `fx_tool` or `crypto_tool` defined via the plugin system) by setting `tool_name` to the new tool's name and listing the patterns you want it to handle.
- Disable the mini‑agent entirely by setting `"enabled": false`.

The same `mini_agent` configuration is also summarized by the `termi --diagnostics` command, which prints whether the mini-agent is enabled, how many rules are loaded, and which tools are referenced.

## Ollama local vs. Ollama Cloud

Termi nhận diện hai dạng model Ollama:

1. **Local daemon (prefix `ollama/...`)** – ví dụ `ollama/qwen3:8b`.
   - Gọi qua OpenAI-compatible endpoint `http://localhost:11434/v1/chat/completions`.
   - Có thể đổi host bằng biến môi trường `OLLAMA_BASE_URL`.
   - Không cần API key.

2. **Ollama Cloud (prefix `ollama-cloud/...`)** – ví dụ `ollama-cloud/qwen3-coder:480b-cloud`.
   - Gọi REST API `https://ollama.com/api/chat` (có thể override bằng `OLLAMA_CLOUD_BASE_URL`).
   - Cần thiết lập `OLLAMA_API_KEY` (tạo tại [https://ollama.com/settings/keys](https://ollama.com/settings/keys)).
   - Tương thích với cùng cú pháp prompt như local daemon.

### Cấu hình

Trong `config.json`, bạn có thể đặt `default_model`, `code_model`, `commit_model`… thành `ollama/<tag>` (local) hoặc `ollama-cloud/<tag>` (cloud). Ví dụ:

```json
{
  "default_model": "ollama-cloud/qwen3-coder:480b-cloud",
  "code_model": "ollama/qwen3:8b"
}
```

### Diagnostics & mini-agent

`termi --diagnostics` sẽ hiển thị rõ provider "⚫ Ollama" (local) hoặc "⚫☁️ Ollama Cloud" và liệt kê các cảnh báo mini-agent (nếu rule/tool không hợp lệ).

### Khi nào dùng Cloud?

- Bạn muốn chạy những model lớn (như `qwen3-coder:480b-cloud`) mà máy local không đủ tài nguyên.
- Cần sẵn sàng ngay không phải tự pull model.

Nhược điểm: cần internet và phụ thuộc quota tài khoản Ollama Cloud.
