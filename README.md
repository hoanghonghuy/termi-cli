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

## Contributing

We welcome all contributions to improve this CLI Agent. Here is a brief guide:

1.  **Fork** the repository.
2.  **Clone** your fork and create a new feature branch:
    ```bash
    git checkout -b feature/my-new-feature
    ```
3.  **Commit** your changes with clear and descriptive messages.
4.  **Push** your branch and open a **Pull Request** to the main repository.