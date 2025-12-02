# Termi – Multi‑Provider AI CLI

## Introduction
Termi is a multi‑provider AI Agent Command-Line Interface (CLI) that supports **Google Gemini**, **DeepSeek**, **Groq**, and **OpenRouter** (HTTP‑compatible). It helps you run AI‑assisted workflows, manage code, and work with files directly from your terminal.

## Quick installation

- Requires **Python 3.8+**.
- Install dependencies:

```bash
pip install -r requirements.txt
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

When an HTTP provider (DeepSeek/Groq/OpenRouter) reports **Insufficient Balance**, Termi automatically falls back to a safe Gemini model with a clear notice, including during the Agent's initial plan analysis phase.

## Configuration & data directory

- Configuration is loaded from `config.json` under:
  - `~/.termi-cli` (default), or
  - the directory pointed to by `TERMI_CLI_HOME`.

- Default UI language is **Vietnamese** (`"language": "vi"`); override per run with:

```bash
termi --lang en "Explain this code"
```

- Use `termi --diagnostics` to inspect the current model/provider configuration and loaded API keys (without showing their values).

## More commands & advanced docs

For developer utilities (e.g. `--git-commit`, `--git-commit-short`, `--document`, `--refactor`), history & memory tools, profiles, plugin tools, and advanced Agent tuning options, see:

- the built‑in CLI help:

```bash
termi --help
```

- and the extra documentation in `docs/ADVANCED.md`.

## Contributing

We welcome all contributions to improve this CLI Agent. In short:

1. **Fork** the repository.
2. **Clone** your fork and create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```
3. **Commit** your changes with clear and descriptive messages.
4. **Open a Pull Request** to the main repository.