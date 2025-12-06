# Termi – Multi‑Provider AI CLI

## Introduction

Termi is a multi‑provider AI Agent Command‑Line Interface (CLI) that supports **Google Gemini**, **DeepSeek**, **Groq**, **OpenRouter** (HTTP‑compatible), and **Ollama** (local models such as Qwen3:8B). It helps you run AI‑assisted workflows, manage code, and work with files directly from your terminal.

## Quick installation

- Requires **Python 3.10+**.
- Gemini-based features (Agent, tool‑calls, model discovery) are primarily tested on Python 3.10–3.12.
- HTTP‑only providers (DeepSeek, Groq, OpenRouter, Ollama) can still work on newer Python versions (e.g. 3.14) even when the Gemini SDK is unavailable.
- Install the CLI from the project root:

```bash
pip install .
```

- For local development (tests + lint):

```bash
pip install -e .[dev]
```

- Configure at least a Gemini API key (others are optional). For local development you can use a `.env` file:

```bash
# Gemini (required)
GOOGLE_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY"

# Optional extra providers
DEEPSEEK_API_KEY="YOUR_DEEPSEEK_API_KEY"
GROQ_API_KEY="YOUR_GROQ_API_KEY"
# Optional OpenRouter key if you use OpenRouter profiles
OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"
```

## Quick usage

```bash
# Single-turn question
termi "Explain this file"

# Chat session
termi --chat

# Autonomous Agent for a more complex task
termi --agent "Set up a small API service for this project"
```

Use `termi --help` to see all available flags and commands.

## Models & providers

- **Gemini**: models named like `models/gemini-*` – full support for chat, Agent, and tool‑calls.
- **DeepSeek**: models starting with `deepseek-*` – HTTP OpenAI‑compatible endpoints.
- **Groq**: models starting with `groq-*` – HTTP OpenAI‑compatible endpoints (with aliases such as `groq-chat`).
- **OpenRouter**: OpenAI‑compatible HTTP models referenced by IDs like `openai/gpt-4o-mini`.
- **Ollama (local)**: models referenced like `ollama/qwen3:8b` – run completely on your machine via Ollama's OpenAI‑compatible API.

All HTTP provider responses are parsed through a hardened JSON helper that removes trailing commas before closing `}` / `]`, making the CLI more robust against provider formatting issues.

## Configuration & data directory

- Configuration is loaded from `config.json` under:
  - `~/.termi-cli` (default), or
  - the directory pointed to by `TERMI_CLI_HOME`.

- Default UI language is **Vietnamese** (`"language": "vi"`); override per run with for example:

```bash
termi --lang en "Explain this code"
```

- Use `termi --diagnostics` to inspect the current model/provider configuration and loaded API keys (without showing their values).

## Internal architecture (short)

Internally, Termi is split into three main layers:

- **Presentation (CLI & handlers)**
  - `__main__.py` and `presentation/cli_app.py` parse CLI flags and route commands.
  - `handlers/*_handler.py` are thin wrappers that delegate to application services.

- **Application (services & DTOs)**
  - `application/chat_service.py`, `application/agent_service.py`, `application/history_service.py`, `application/config_service.py`, `application/utility_service.py`.
  - Small DTOs such as `AgentExecutionContext`, `ChatLoopOptions`, `HttpChatOptions` group related options from config + CLI args.
  - `application/services/__init__.py` provides a simple service container.

- **Infrastructure**
  - `infrastructure/http_providers.py` implements HTTP providers (DeepSeek, Groq, OpenRouter, Ollama).
  - `infrastructure/history_repository.py` and `infrastructure/config_repository.py` wrap filesystem access for history and config.
  - `infrastructure/git_repository.py` wraps git subprocess calls for commit utilities.

For visual diagrams (ASCII and PlantUML) of this architecture, see `docs/ARCHITECTURE_DIAGRAM.md`.

## More commands & advanced docs

For developer utilities (e.g. `--git-commit`, `--git-commit-short`, `--document`, `--refactor`), history & memory tools, profiles, plugin tools, and advanced Agent tuning options, see:

- the built‑in CLI help:

```bash
termi --help
```

- and the extra documentation in `docs/ADVANCED.md`.

For the internal multi‑provider routing and Provider abstraction (Gemini / DeepSeek / Groq / OpenRouter / Ollama), see the section ["Provider architecture (developers)"](docs/ADVANCED.md#provider-architecture-developers).

## Contributing

We welcome all contributions to improve this CLI Agent. In short:

1. **Fork** the repository.
2. **Clone** your fork and create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```
3. **Commit** your changes with clear and descriptive messages.
4. **Open a Pull Request** to the main repository.
