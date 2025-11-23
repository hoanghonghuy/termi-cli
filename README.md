# Termi – Multi‑Provider AI CLI

## Introduction
Termi is a multi‑provider AI Agent Command-Line Interface (CLI) that supports **Google Gemini**, **DeepSeek**, **Groq**, and OpenRouter (HTTP‑compatible). It integrates many tools to help you run complex AI‑assisted workflows, manage code, work with files, calendars, email, and more directly from your terminal.

## Key Features

Based on the project structure and available CLI options, Termi provides the following core capabilities:

*   **Interactive Modes:** Multi‑turn chat (`--chat`) or autonomous Agent mode for complex tasks (`--agent`, with an optional `--agent-dry-run` preview mode).
*   **Multi‑Provider Models:**
    * Gemini: models named like `models/gemini-*` – full support for chat, Agent, and tool‑calls.
    * DeepSeek: models starting with `deepseek-*` – HTTP OpenAI‑compatible endpoints.
    * Groq: models starting with `groq-*` – HTTP OpenAI‑compatible endpoints (with friendly aliases such as `groq-chat`).
    * When DeepSeek/Groq reports **Insufficient Balance**, Termi automatically falls back to Gemini with a clear notice.
*   **Code Utilities:** Generate commit messages (`--git-commit`, `--git-commit-short`), write documentation (`--document`), and suggest refactors (`--refactor`).
*   **Contextual Awareness:** Read images (`-i`), load full directory context (`--read-dir`), and override the system instruction (`-si`).
*   **Personalization:** Manage personas (`--add-persona`, `--list-personas`, `--rm-persona`) and long‑term custom instructions (`--add-instruct`, `--list-instructs`, `--rm-instruct`).
*   **History Management:** Browse history (`--history`), load by topic (`--topic`), print logs (`--print-log`), summarize (`--summarize`), and **rename** or **delete** history entries.
*   **Diagnostics & Tuning:** `--diagnostics` / `--whoami` to inspect the current model & provider configuration and the number of API keys; `--verbose` / `--quiet` to adjust console log verbosity.
*   **Extensible Toolset:** A rich toolset for web search, file system, database, calendar, email, and more; easily extended via plugins.

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

    Create a `.env` file in the project root or define the corresponding environment variables:

    ```bash
    # Gemini (required)
    GOOGLE_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY"
    # Optionally add BACKUP_KEY values if you want key rotation
    GOOGLE_API_KEY_2ND="..."

    # DeepSeek (optional, if you want to use DeepSeek)
    DEEPSEEK_API_KEY="YOUR_DEEPSEEK_API_KEY"
    DEEPSEEK_API_KEY_2ND="..."

    # Groq (optional, if you want to use Groq)
    GROQ_API_KEY="YOUR_GROQ_API_KEY"
    GROQ_API_KEY_2ND="..."
    ```

4.  **Google OAuth (Optional):** If you plan to use the Calendar and Email tools, you will need to set up Google OAuth credentials and ensure `credentials.json` is configured.

## Usage

After installation (for example via `pip install -e .`), the main entrypoint is:

```bash
termi [OPTIONS] [PROMPT]
```

You can also run the CLI directly with Python if you prefer:

```bash
python -m termi_cli [OPTIONS] [PROMPT]
```

### Core Interaction

| Command | Description |
| :--- | :--- |
| `termi "Your question"` | Single-turn, direct prompt to the AI (using the configured default model). |
| `termi --chat` | Start an interactive, multi-turn chat session. |
| `termi --chat -m deepseek-chat` | Multi-turn chat session using DeepSeek over the HTTP provider. |
| `termi --chat -m groq-chat` | Multi-turn chat session using Groq (alias mapped to the recommended Groq model). |
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
| `-m, --model <NAME>` | Select the model for the current run (temporarily overriding `default_model` in the config). Supports Gemini, DeepSeek (`deepseek-*`), Groq (`groq-*`), and OpenRouter IDs (`provider/model`). |
| `--set-model` | Launch a multi-provider wizard (Gemini / DeepSeek / Groq / OpenRouter) to choose `default_model`, `code_model`, and `commit_model`. For OpenRouter you can either select from a suggested list or enter the model ID manually. |
| `--list-models` | List available Gemini models (with a Provider column). |
| `--diagnostics`, `--whoami` | Show which models are used for default/code/commit/agent, the provider of each model, and how many API keys are loaded (without revealing their values). |
| `--verbose` / `--quiet` | Adjust console log verbosity (more INFO logs or only ERRORs). |
| `-i <PATH>` | Provide one or more image file paths for multimodal analysis. |
| `--read-dir` | Read the content of the current directory to provide context to the AI. |
| `--add-persona <NAME> <INSTRUCTION>` | Save a new persona with a custom system instruction. |
| `--list-personas`, `--rm-persona` | List or delete saved personas. |
| `--add-instruct <INSTRUCTION>` | Save a long-term, persistent instruction for the AI to follow in all sessions. |
| `--list-instructs`, `--rm-instruct` | List or delete saved custom instructions. |

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

When running in an interactive TTY, the CLI will ask for a `y/n` confirmation before actually deleting the database. In non‑interactive environments (scripts, CI, tests), the confirmation is skipped so that automation never hangs.

Similarly, you can reset the configuration back to defaults:

```bash
termi --reset-config
```

This deletes the current `config.json` (either the one under `APP_DIR` or the legacy `config.json` in the current directory) and recreates it with default values. Just like `--reset-memory`, it asks for confirmation in interactive terminals but runs non‑interactively when used from scripts.

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
  Limits the maximum number of steps the Agent is allowed to run in **a single session**.  
  If you omit this flag, internal defaults are used (30 steps for project‑plan flows, 10 steps for simple tasks).

Examples:

```bash
termi --agent "Design the architecture for this service" --agent-max-steps 8
termi --agent --agent-dry-run "Refactor module XYZ" --agent-max-steps 5
```

#### History & Memory scripting

The following commands let you work with history and memory **without entering the interactive UI**:

- `--rm-history TARGET`  
  Delete a chat history entry. `TARGET` can be a JSON file path or a topic name.  
  For example:

  ```bash
  termi --rm-history "debug-openapi-errors"
  termi --rm-history "~/.termi-cli/chat_logs/chat_debug-openapi-errors.json"
  ```

- `--rename-history OLD NEW`  
  Rename a chat history entry. `OLD` is the old path or topic, `NEW` is the new title.  
  For example:

  ```bash
  termi --rename-history "debug-openapi-errors" "Fix OpenAPI client generator"
  ```

- `--memory-search QUERY`  
  Search long‑term memory for related past interactions and print them as Markdown.  
  For example:

  ```bash
  termi --memory-search "migrations for user table"
  ```

#### Quick configuration profiles

Profiles let you quickly save and reuse a set of model / language / instruction settings:

- Save the current profile:

  ```bash
  termi --save-profile dev-gemini
  ```

- List existing profiles:

  ```bash
  termi --list-profiles
  ```

- Apply a profile for a given run:

  ```bash
  termi --profile dev-gemini --chat
  ```

  The profile will override `default_model`, `code_model`, `commit_model`, `agent_model`, `language`,
  and `default_system_instruction` for the current run.

- In addition to the profiles you create yourself, Termi ships with a built‑in preset:

  ```bash
  # Use the OpenRouter free model bundle optimized for coding
  termi --profile openrouter-free-coding --chat
  ```

  This preset maps:
  - `default_model` → `openai/gpt-4o-mini`
  - `code_model` → `meta-llama/llama-3.1-70b-instruct`
  - `commit_model` → `openai/gpt-4o-mini`
  - `agent_model` → `models/gemini-pro-latest`

- Remove a profile:

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