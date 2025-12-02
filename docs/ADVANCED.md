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
