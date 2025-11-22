# Termi – Multi‑Provider AI CLI

## Introduction
Termi là một Command-Line Interface (CLI) AI Agent đa provider, hỗ trợ **Google Gemini**, **DeepSeek** và **Groq**. Nó tích hợp nhiều công cụ để xử lý tác vụ phức tạp, quản lý code, thao tác file, lịch, email… trực tiếp từ terminal.

## Key Features

Dựa trên cấu trúc project và các tùy chọn CLI, Termi mang lại các khả năng chính sau:

*   **Interactive Modes:** Chat nhiều lượt (`--chat`) hoặc giao nhiệm vụ phức tạp cho Agent tự trị (`--agent`, có cả chế độ `--agent-dry-run`).
*   **Multi‑Provider Models:**
    * Gemini: model dạng `models/gemini-*` – hỗ trợ đầy đủ chat, Agent và tool‑calls.
    * DeepSeek: model bắt đầu bằng `deepseek-*` – gọi HTTP OpenAI-compatible.
    * Groq: model bắt đầu bằng `groq-*` – gọi HTTP OpenAI-compatible (có alias như `groq-chat`).
    * Khi DeepSeek/Groq báo **Insufficient Balance**, Termi tự fallback sang Gemini với thông báo rõ ràng.
*   **Code Utilities:** Tích hợp sinh commit message (`--git-commit`, `--git-commit-short`), viết documentation (`--document`) và gợi ý refactor (`--refactor`).
*   **Contextual Awareness:** Đọc ảnh (`-i`), đọc toàn bộ thư mục (`--read-dir`), override system instruction (`-si`).
*   **Personalization:** Quản lý persona (`--add-persona`, `--list-personas`, `--rm-persona`) và custom instructions dài hạn (`--add-instruct`, `--list-instructs`, `--rm-instruct`).
*   **History Management:** Duyệt lịch sử (`--history`), load theo topic (`--topic`), in log (`--print-log`), tóm tắt (`--summarize`), **đổi tên** và **xóa** lịch sử.
*   **Diagnostics & Tuning:** `--diagnostics/--whoami` để xem cấu hình model & provider hiện tại, số lượng API key; `--verbose`/`--quiet` để điều chỉnh độ ồn log.
*   **Extensible Toolset:** Bộ tools phong phú cho web search, file system, database, calendar, email; cho phép mở rộng bằng plugin.

## Installation

### Prerequisites

You need Python 3.8+.

### Steps

1.  **Clone the repository** (if applicable).

2.  **Install the dependencies** from `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up API Keys:**

    Tạo file `.env` ở thư mục gốc hoặc đặt biến môi trường tương ứng:

    ```bash
    # Gemini (bắt buộc)
    GOOGLE_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY"
    # Có thể thêm BACKUP_KEY nếu muốn xoay vòng
    GOOGLE_API_KEY_2ND="..."

    # DeepSeek (tùy chọn, nếu muốn dùng DeepSeek)
    DEEPSEEK_API_KEY="YOUR_DEEPSEEK_API_KEY"
    DEEPSEEK_API_KEY_2ND="..."

    # Groq (tùy chọn, nếu muốn dùng Groq)
    GROQ_API_KEY="YOUR_GROQ_API_KEY"
    GROQ_API_KEY_2ND="..."
    ```

4.  **Google OAuth (Optional):** If you plan to use the Calendar and Email tools, you will need to set up Google OAuth credentials and ensure `credentials.json` is configured.

## Usage

Sau khi cài đặt (ví dụ thông qua `pip install -e .`), entrypoint chính là lệnh:

```bash
termi [OPTIONS] [PROMPT]
```

Bạn vẫn có thể chạy trực tiếp bằng Python nếu muốn:

```bash
python -m termi_cli [OPTIONS] [PROMPT]
```

### Core Interaction

| Command | Description |
| :--- | :--- |
| `termi "Your question"` | Single-turn, direct prompt to the AI (Gemini hoặc DeepSeek/Groq nếu chọn model tương ứng). |
| `termi --chat` | Start an interactive, multi-turn chat session. |
| `termi --chat -m deepseek-chat` | Chat nhiều lượt với DeepSeek (HTTP provider). |
| `termi --chat -m groq-chat` | Chat nhiều lượt với Groq (alias tới model khuyến nghị). |
| `termi --agent "A complex task to perform"` | Activate the autonomous Agent mode (Gemini) to solve the task using available tools. |

### Developer Utilities

| Flag | Description |
| :--- | :--- |
| `--document <FILE_PATH>` | Automatically generate docstrings and comments for the specified code file. |
| `--refactor <FILE_PATH>` | Get AI-powered suggestions for restructuring and improving the code in the specified file. |
| `--git-commit` | Generate a detailed Conventional Commit message (subject + body) based on the currently staged changes. The CLI writes the message to a temporary file and proposes a `git commit -F` command. |
| `--git-commit-short` | Generate a short, single-line Conventional Commit subject based on the currently staged changes and propose a `git commit -m` command. |
| `--list-tools` | List all available tools (core + plugin) for Agent/tool-calls. |

#### Example: AI-assisted Git commit

You can let the CLI ask the AI to write commit messages for you. For example:

```bash
# Generate a full Conventional Commit (subject + body)
termi --git-commit

# Generate a short, single-line commit subject only
termi --git-commit-short
```

In both cases, the CLI will show you the proposed `git commit` command and ask for confirmation before executing it.

### Customization & Context

| Flag | Description |
| :--- | :--- |
| `-m, --model <NAME>` | Chọn model cho phiên hiện tại (ghi đè tạm thởi `default_model` trong config). Hỗ trợ Gemini, DeepSeek (`deepseek-*`), Groq (`groq-*`). |
| `--set-model` | Chạy wizard để chọn `default_model`, `code_model`, `commit_model` với gợi ý provider. |
| `--list-models` | Liệt kê các model Gemini khả dụng (kèm cột Provider). |
| `--diagnostics`, `--whoami` | Hiển thị model đang dùng cho default/code/commit/agent, provider của từng model và số lượng API key (không lộ giá trị). |
| `--verbose` / `--quiet` | Điều chỉnh độ ồn log trên console (INFO hoặc chỉ ERROR). |
| `-i <PATH>` | Provide one or more image file paths for multimodal analysis. |
| `--read-dir` | Read the content of the current directory to provide context to the AI. |
| `--add-persona <NAME> <INSTRUCTION>` | Save a new persona with a custom system instruction. |
| `--list-personas`, `--rm-persona` | List hoặc xóa persona đã lưu. |
| `--add-instruct <INSTRUCTION>` | Save a long-term, persistent instruction for the AI to follow in all sessions. |
| `--list-instructs`, `--rm-instruct` | List hoặc xóa custom instructions đã lưu. |

### Language & i18n

The CLI supports multiple UI languages via a simple configuration key:

- Default language is **Vietnamese** (`"language": "vi"` in `config.json`).
- You can temporarily override the language per run using:

  ```bash
  # Force English UI for this run only
  termi --lang en "Explain this code"
  ```

Supported values for `--lang/--language`:

- `vi` – Vietnamese UI messages
- `en` – English UI messages

The same language setting is reused across core CLI, history browser, chat mode, and Agent output panels.

### Runtime Data Directory (APP_DIR)

To keep your working directories clean, all runtime data is stored under a dedicated application directory:

- By default: `APP_DIR = ~/.termi-cli`
- Or set explicitly via environment variable:

  ```bash
  export TERMI_CLI_HOME=/path/to/.termi-cli
  ```

Inside `APP_DIR`, the following paths are used:

- `config.json` – persistent configuration (unless a local `config.json` exists in the current directory, which is preferred for backward compatibility).
- `memory_db/` – long‑term memory database, storing context and instructions for the AI to learn from and improve over time.
- `memory_db_corrupted_*/` – backup folders created automatically if the DB is considered corrupted.
- `chat_logs/` – stored chat history JSON files.
- `logs/termi.log` – application logs.
- `token.json` – Google OAuth token for Calendar/Email tools.

### Resetting long‑term memory

If the long‑term memory DB becomes corrupted or you simply want to wipe all stored context, you can reset it safely via:

```bash
termi --reset-memory
```

This command deletes the `memory_db/` directory under `APP_DIR`. On the next run, Termi will lazily recreate a fresh database the first time it needs to read/write long‑term memory.

Running the CLI from any directory will not scatter these files in your projects; they all live under `APP_DIR`.

### Agent Modes: Normal vs Dry‑Run

The autonomous Agent mode can operate in two main styles:

- **Normal execution** (default):

  ```bash
  termi --agent "Set up a small API service for this project"
  ```

  The Agent is allowed to call internal tools such as `write_file`, `execute_command`, DB/file tools, etc. File writes are still guarded by an explicit confirmation step in the CLI.

- **Dry‑run execution** (safe preview):

  ```bash
  termi --agent --agent-dry-run "Design a CLI utility for this repo"
  ```

  In dry‑run mode:

### Agent Tuning, History & Profiles

#### Agent tuning flags

- `--agent-max-steps N`  
  Giới hạn số bước tối đa mà Agent được phép chạy trong **một phiên**.  
  Nếu không truyền flag này, Agent dùng giá trị mặc định nội bộ (30 bước cho project plan, 10 bước cho simple task).

Ví dụ:

```bash
termi --agent "Thiết kế kiến trúc cho service này" --agent-max-steps 8
termi --agent --agent-dry-run "Refactor module XYZ" --agent-max-steps 5
```

#### History & Memory scripting

Các lệnh sau giúp thao tác lịch sử và trí nhớ **không cần vào UI tương tác**:

- `--rm-history TARGET`  
  Xóa một lịch sử chat. `TARGET` có thể là đường dẫn file JSON hoặc tên topic.  
  Ví dụ:

  ```bash
  termi --rm-history "debug-openapi-errors"
  termi --rm-history "~/.termi-cli/chat_logs/chat_debug-openapi-errors.json"
  ```

- `--rename-history OLD NEW`  
  Đổi tên một lịch sử chat. `OLD` là path hoặc topic cũ, `NEW` là tiêu đề mới.  
  Ví dụ:

  ```bash
  termi --rename-history "debug-openapi-errors" "Fix OpenAPI client generator"
  ```

- `--memory-search QUERY`  
  Tìm kiếm trong trí nhớ dài hạn (long‑term memory) các tương tác liên quan, in ra dưới dạng markdown.  
  Ví dụ:

  ```bash
  termi --memory-search "migrations for user table"
  ```

#### Quick configuration profiles

Profiles cho phép lưu nhanh và áp dụng lại một bộ cấu hình model/ngôn ngữ/instruction:

- Lưu profile hiện tại:

  ```bash
  termi --save-profile dev-gemini
  ```

- Liệt kê profile đã có:

  ```bash
  termi --list-profiles
  ```

- Áp dụng profile cho một phiên chạy:

  ```bash
  termi --profile dev-gemini --chat
  ```

  Profile sẽ thiết lập lại `default_model`, `code_model`, `commit_model`, `agent_model`, `language`,
  và `default_system_instruction` trong runtime của phiên hiện tại.

- Xóa profile:

  ```bash
  termi --rm-profile dev-gemini
  ```

### Extending with Plugin Tools

Advanced users can extend the available tools without modifying the core codebase, using a simple plugin mechanism.

- Plugins are discovered in: `APP_DIR/plugins/*.py`
- Each plugin file (not starting with `_`) can define a dictionary:

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

- On startup, the CLI automatically imports these plugin modules and merges `PLUGIN_TOOLS` into the internal `AVAILABLE_TOOLS` map used for function‑calling.
- If a plugin tries to define a tool with the same name as a core tool, the core tool takes precedence (the plugin entry is ignored).
- Any plugin import error is ignored gracefully so that a broken plugin does not prevent the CLI from starting.

With this mechanism, you can gradually build a library of project‑specific tools (e.g., custom deployment scripts, internal APIs, Jira integrations) without forking the main repository.

## Contributing

We welcome all contributions to improve this CLI Agent. Here is a brief guide:

1.  **Fork** the repository.
2.  **Clone** your fork and create a new feature branch:
    ```bash
    git checkout -b feature/my-new-feature
    ```
3.  **Commit** your changes with clear and descriptive messages.
4.  **Push** your branch and open a **Pull Request** to the main repository.