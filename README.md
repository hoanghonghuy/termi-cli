# CLI AI Agent

## Introduction
This is a powerful Command-Line Interface (CLI) AI Agent built with the Gemini models. It integrates various tools to perform complex tasks, manage code, handle files, and interact with calendars and email, all from the comfort of your terminal.

## Key Features

Based on the project structure and CLI options, the agent offers a wide range of capabilities:

*   **Interactive Modes:** Engage in continuous conversation (`--chat`) or delegate complex tasks to the Autonomous Agent (`--agent`).
*   **Code Utilities:** Seamlessly integrate AI into your development workflow with features for automatic Git commit message generation (`--git-commit`), code documentation (`--document`), and refactoring suggestions (`--refactor`).
*   **Contextual Awareness:** Provide advanced context by analyzing images (`-i`), reading entire directories (`--read-dir`), and overriding the AI's core instructions (`-si`).
*   **Personalization:** Define and manage custom personas (`--add-persona`) and long-term, custom instructions (`--add-instruct`) to tailor the AI's behavior.
*   **History Management:** Efficiently manage chat sessions with named topics (`--topic`), history browsing (`--history`), and session summarization (`--summarize`).
*   **Extensible Toolset:** The agent is equipped with a rich set of tools for web search, file system manipulation, database interaction, calendar management, and email search.

## Installation

### Prerequisites

You need Python 3.8+.

### Steps

1.  **Clone the repository** (if applicable).

2.  **Install the dependencies** from `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up API Key:** The application requires a Google Gemini API key. Create a `.env` file in the project root and add your key, or set it as an environment variable:
    ```
    GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```

4.  **Google OAuth (Optional):** If you plan to use the Calendar and Email tools, you will need to set up Google OAuth credentials and ensure `credentials.json` is configured.

## Usage

The main entry point is typically executed via `python src/main.py` or a configured shell alias.

### Core Interaction

| Command | Description |
| :--- | :--- |
| `python src/main.py "Your question"` | Single-turn, direct prompt to the AI. |
| `python src/main.py --chat` | Start an interactive, multi-turn chat session. |
| `python src/main.py --agent "A complex task to perform"` | Activate the autonomous Agent mode to solve the task using available tools. |

### Developer Utilities

| Flag | Description |
| :--- | :--- |
| `--document <FILE_PATH>` | Automatically generate docstrings and comments for the specified code file. |
| `--refactor <FILE_PATH>` | Get AI-powered suggestions for restructuring and improving the code in the specified file. |
| `--git-commit` | Generate a detailed Git commit message based on the currently staged changes. |

### Customization & Context

| Flag | Description |
| :--- | :--- |
| `-i <PATH>` | Provide one or more image file paths for multimodal analysis. |
| `--read-dir` | Read the content of the current directory to provide context to the AI. |
| `--add-persona <NAME> <INSTRUCTION>` | Save a new persona with a custom system instruction. |
| `--add-instruct <INSTRUCTION>` | Save a long-term, persistent instruction for the AI to follow in all sessions. |

### Language & i18n

The CLI supports multiple UI languages via a simple configuration key:

- Default language is **Vietnamese** (`"language": "vi"` in `config.json`).
- You can temporarily override the language per run using:

  ```bash
  # Force English UI for this run only
  python src/main.py --lang en "Explain this code"
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
- `memory_db/` – long‑term memory database.
- `memory_db_corrupted_*/` – backup folders created automatically if the DB is considered corrupted.
- `chat_logs/` – stored chat history JSON files.
- `logs/termi.log` – application logs.
- `token.json` – Google OAuth token for Calendar/Email tools.

Running the CLI from any directory will not scatter these files in your projects; they all live under `APP_DIR`.

### Agent Modes: Normal vs Dry‑Run

The autonomous Agent mode can operate in two main styles:

- **Normal execution** (default):

  ```bash
  python src/main.py --agent "Set up a small API service for this project"
  ```

  The Agent is allowed to call internal tools such as `write_file`, `execute_command`, DB/file tools, etc. File writes are still guarded by an explicit confirmation step in the CLI.

- **Dry‑run execution** (safe preview):

  ```bash
  python src/main.py --agent --agent-dry-run "Design a CLI utility for this repo"
  ```

  In dry‑run mode:

  - The Agent still analyzes the request and produces a **project plan** or **simple task steps**.
  - You see a rich panel describing the plan and a **checklist table** of all planned files (`path` + `description`).
  - For each step, instead of actually calling tools, the Agent only **simulates** the call and prints a message like:

    > DRY-RUN: Would call tool `tool_name` with args `{...}`, but only simulating the result.

  - No real file writes, shell commands or DB changes are executed.

This is useful when you want to inspect or iterate on the plan safely before letting the Agent touch your files.

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