from __future__ import annotations

import logging
import os
import sys
from typing import Any, Callable

from rich.console import Console
from rich.markdown import Markdown

from termi_cli import api, i18n, memory
from termi_cli.config import APP_DIR, CONFIG_PATH, load_config
from termi_cli.handlers import (
    agent_handler,
    chat_handler,
    config_handler,
    core_handler,
    history_handler,
    utility_handler,
)


logger = logging.getLogger(__name__)


RunSingleTurnFn = Callable[[Console, dict, str, Any, Any, str, Any], None]
HandleHistoryFlowFn = Callable[[Console, dict, str, Any, str, Any], tuple[Any, bool]]
RequiresGeminiFn = Callable[[dict, Any], bool]


def run_cli(
    console: Console,
    config: dict,
    language: str,
    parser: Any,
    args: Any,
    cli_help_text: str,
    provided_args: Any | None,
    run_single_turn: RunSingleTurnFn,
    handle_history_flow: HandleHistoryFlowFn,
    requires_gemini_for_command: RequiresGeminiFn,
) -> None:
    """Điều phối toàn bộ flow CLI sau khi đã parse args.

    Hàm này tách khỏi __main__.py để entrypoint mỏng hơn và dễ test hơn.
    """

    # Cho phép override ngôn ngữ tạm thời qua --lang/--language
    if getattr(args, "language", None):
        language = args.language
        config["language"] = language

    # Điều chỉnh mức logging console theo --verbose/--quiet
    root_logger = logging.getLogger()
    if getattr(args, "verbose", False):
        for handler in root_logger.handlers:
            from logging import FileHandler, StreamHandler

            if isinstance(handler, StreamHandler) and not isinstance(handler, FileHandler):
                handler.setLevel(logging.INFO)
    elif getattr(args, "quiet", False):
        for handler in root_logger.handlers:
            from logging import FileHandler, StreamHandler

            if isinstance(handler, StreamHandler) and not isinstance(handler, FileHandler):
                handler.setLevel(logging.ERROR)

    # Khởi tạo config.json mặc định nếu chưa tồn tại (nhẹ nhàng hơn reset-config).
    if getattr(args, "init_config", False):
        load_config()
        console.print(
            i18n.tr(
                language,
                "config_init_success",
                path=str(CONFIG_PATH),
            )
        )
        return

    # Config wizard
    if getattr(args, "setup", False):
        from termi_cli.application.config_wizard import run_config_wizard
        run_config_wizard(language)
        return

    # Check for updates
    if getattr(args, "check_update", False):
        from termi_cli.application.update_checker import get_update_message
        console.print(get_update_message(language))
        return

    # Cho phép reset toàn bộ config về mặc định (xoá file config.json hiện tại)
    if getattr(args, "reset_config", False):
        if "PYTEST_CURRENT_TEST" in os.environ:
            console.print(f"[DEBUG] TERMI_CLI_HOME={os.getenv('TERMI_CLI_HOME')}")
            console.print(f"[DEBUG] APP_DIR={APP_DIR}")
            console.print(f"[DEBUG] CONFIG_PATH={CONFIG_PATH}")
            console.print(f"[DEBUG] CONFIG_PATH.exists(before)={CONFIG_PATH.exists()}")

        if sys.stdin.isatty() and "PYTEST_CURRENT_TEST" not in os.environ:
            answer = console.input(i18n.tr(language, "config_reset_confirm"), markup=False).strip().lower()
            if answer not in ("y", "yes"):
                console.print(i18n.tr(language, "config_reset_cancelled"))
                return

        try:
            if CONFIG_PATH.exists():
                CONFIG_PATH.unlink()

            load_config()

            if "PYTEST_CURRENT_TEST" in os.environ:
                console.print(f"[DEBUG] CONFIG_PATH.exists(after)={CONFIG_PATH.exists()}")
                if CONFIG_PATH.exists():
                    try:
                        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                            console.print(f"[DEBUG] CONFIG_CONTENT(after)={f.read()}")
                    except Exception:
                        pass

            console.print(i18n.tr(language, "config_reset_success", path=str(CONFIG_PATH)))
        except Exception as e:  # noqa: BLE001
            console.print(i18n.tr(language, "config_reset_error", error=e))
        return

    # Cho phép xoá database trí nhớ dài hạn bằng một lệnh riêng
    if getattr(args, "reset_memory", False):
        if "PYTEST_CURRENT_TEST" in os.environ:
            console.print(f"[DEBUG] TERMI_CLI_HOME={os.getenv('TERMI_CLI_HOME')}")
            console.print(f"[DEBUG] APP_DIR={APP_DIR}")
            console.print(f"[DEBUG] DB_PATH={memory.DB_PATH}")
            console.print(f"[DEBUG] DB_PATH.exists(before)={os.path.exists(memory.DB_PATH)}")

        if sys.stdin.isatty() and "PYTEST_CURRENT_TEST" not in os.environ:
            answer = console.input(i18n.tr(language, "memory_reset_confirm"), markup=False).strip().lower()
            if answer not in ("y", "yes"):
                console.print(i18n.tr(language, "memory_reset_cancelled"))
                return

        if memory.reset_memory_db():
            if "PYTEST_CURRENT_TEST" in os.environ:
                console.print(f"[DEBUG] DB_PATH.exists(after)={os.path.exists(memory.DB_PATH)}")
            console.print(i18n.tr(language, "memory_reset_success"))
        else:
            console.print(i18n.tr(language, "memory_reset_error"))
        return

    # Lệnh doctor: kiểm tra môi trường (Python, Gemini, API keys) + diagnostics cấu hình.
    if getattr(args, "doctor", False):
        console.print(f"[bold]Termi Doctor[/bold] - Python: {sys.version.splitlines()[0]}")

        if getattr(api, "GEMINI_AVAILABLE", True):
            console.print("[green]Gemini SDK: available in this environment.[/green]")
        else:
            console.print(
                "[yellow]Gemini SDK: unavailable in this Python environment. "
                "Bạn vẫn có thể dùng các provider HTTP (DeepSeek/Groq/OpenRouter/Ollama), "
                "hoặc chạy Termi trên Python 3.10–3.12 để dùng Gemini đầy đủ.[/yellow]"
            )

        config_handler.show_diagnostics(console, config)
        return

    # Lệnh chẩn đoán cấu hình không cần API key
    if getattr(args, "diagnostics", False):
        config_handler.show_diagnostics(console, config)
        return

    # Tìm kiếm trong trí nhớ dài hạn (không cần API ngoài)
    if getattr(args, "memory_search", None):
        result = memory.search_memory(args.memory_search)
        if not result:
            console.print(i18n.tr(language, "memory_search_no_results"))
        else:
            console.print(Markdown(result))
        return

    # Các thao tác history non-interactive
    if getattr(args, "rm_history", None):
        history_handler.delete_history_entry(console, args.rm_history)
        return

    if getattr(args, "rename_history", None):
        old, new = args.rename_history
        history_handler.rename_history_entry(console, old, new)
        return

    # Quản lý profile cấu hình nhanh
    if getattr(args, "set_lang", None):
        config_handler.set_language(console, config, args.set_lang)
        return

    # Quản lý profile cấu hình nhanh
    if getattr(args, "save_profile", None):
        config_handler.save_profile(console, config, args.save_profile)
        return

    if getattr(args, "list_profiles", False):
        config_handler.list_profiles(console, config)
        return

    if getattr(args, "rm_profile", None):
        config_handler.remove_profile(console, config, args.rm_profile)
        return

    # --- Codebase RAG commands (không cần API key) ---
    if getattr(args, "index_codebase", None) is not None:
        from termi_cli.rag import codebase_indexer, codebase_query
        directory = args.index_codebase or "."
        # Auto-detect project name if not specified
        rag_index_arg = getattr(args, "rag_index", "default")
        if rag_index_arg == "default":
            index_name = codebase_query.get_project_index_name(directory)
        else:
            index_name = rag_index_arg
        console.print(i18n.tr(language, "rag_indexing_start", directory=directory))
        console.print(f"[dim]Index name: {index_name}[/dim]")
        try:
            force = getattr(args, "force_reindex", False)
            stats = codebase_indexer.index_codebase(directory, index_name, force=force)
            if "error" in stats and stats["error"]:
                console.print(i18n.tr(language, "rag_indexing_error", error=stats["error"]))
            else:
                console.print(i18n.tr(
                    language, "rag_indexing_complete",
                    files=stats.get("files", 0),
                    chunks=stats.get("chunks", 0),
                ))
                if stats.get("errors"):
                    for err in stats["errors"][:5]:  # Show first 5 errors
                        console.print(f"[dim red]{err}[/dim red]")
        except Exception as e:
            console.print(i18n.tr(language, "rag_indexing_error", error=str(e)))
        return

    if getattr(args, "clear_index", False):
        from termi_cli.rag import codebase_indexer, codebase_query
        rag_index_arg = getattr(args, "rag_index", "default")
        if rag_index_arg == "default":
            index_name = codebase_query.get_project_index_name()
        else:
            index_name = rag_index_arg
        
        # Get current stats for confirmation
        stats = codebase_indexer.get_index_stats(index_name)
        if stats.get("available", False):
            chunk_count = stats.get("count", 0)
            confirm = console.input(
                f"[yellow]Index '{index_name}' có {chunk_count} chunks. Xác nhận xóa? (y/n): [/yellow]"
            ).strip().lower()
            if confirm not in ("y", "yes"):
                console.print("[yellow]Đã hủy.[/yellow]")
                return
        
        if codebase_indexer.clear_index(index_name):
            console.print(i18n.tr(language, "rag_index_cleared", name=index_name))
        else:
            console.print(i18n.tr(language, "rag_index_clear_failed"))
        return

    if getattr(args, "index_stats", False):
        from termi_cli.rag import codebase_indexer, codebase_query
        rag_index_arg = getattr(args, "rag_index", "default")
        if rag_index_arg == "default":
            index_name = codebase_query.get_project_index_name()
        else:
            index_name = rag_index_arg
        stats = codebase_indexer.get_index_stats(index_name)
        if stats.get("available", False):
            console.print(i18n.tr(
                language, "rag_index_stats",
                name=stats.get("name", index_name),
                count=stats.get("count", 0),
            ))
        else:
            console.print(i18n.tr(language, "rag_index_not_available"))
        return

    # --- MCP commands ---
    if getattr(args, "mcp_list", False):
        from termi_cli.mcp import config as mcp_config
        from rich.table import Table
        
        servers = mcp_config.get_mcp_servers()
        if not servers:
            console.print(i18n.tr(language, "mcp_no_servers"))
        else:
            table = Table(title=i18n.tr(language, "mcp_server_list_title"))
            table.add_column("Name", style="cyan")
            table.add_column("Transport", style="yellow")
            table.add_column("Command/URL", style="dim")
            table.add_column("Enabled", style="green")
            
            for server in servers:
                cmd_or_url = " ".join(server.get("command", [])) or server.get("url", "-")
                enabled = "✅" if server.get("enabled", True) else "❌"
                table.add_row(
                    server.get("name", "?"),
                    server.get("transport", "stdio"),
                    cmd_or_url[:50] + ("..." if len(cmd_or_url) > 50 else ""),
                    enabled,
                )
            console.print(table)
        return

    if getattr(args, "mcp_add", None):
        from termi_cli.mcp import config as mcp_config
        
        add_args = args.mcp_add
        if len(add_args) < 2:
            console.print(i18n.tr(language, "mcp_add_usage"))
            return
        
        name = add_args[0]
        command = add_args[1:]
        
        try:
            mcp_config.add_mcp_server(name=name, transport="stdio", command=command)
            console.print(i18n.tr(language, "mcp_server_added", name=name))
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
        return

    if getattr(args, "mcp_remove", None):
        from termi_cli.mcp import config as mcp_config
        
        name = args.mcp_remove
        if mcp_config.remove_mcp_server(name):
            console.print(i18n.tr(language, "mcp_server_removed", name=name))
        else:
            console.print(i18n.tr(language, "mcp_server_not_found", name=name))
        return

    if getattr(args, "mcp_connect", False):
        from termi_cli.mcp import client as mcp_client
        
        console.print(i18n.tr(language, "mcp_connecting"))
        results = mcp_client.connect_mcp_servers()
        
        if not results:
            console.print(i18n.tr(language, "mcp_no_servers"))
        else:
            for name, status in results.items():
                if "Failed" in status or "error" in status.lower():
                    console.print(i18n.tr(language, "mcp_connect_failed", name=name, status=status))
                else:
                    console.print(i18n.tr(language, "mcp_connected", name=name, status=status))
        return

    # Cho phép liệt kê tools mà không cần GOOGLE_API_KEY
    if getattr(args, "list_tools", False):
        api.list_tools(console)
        return

    requires_gemini = requires_gemini_for_command(config, args)

    if requires_gemini and not getattr(api, "GEMINI_AVAILABLE", True):
        console.print(i18n.tr(language, "gemini_unavailable_for_command"))
        return

    keys = api.initialize_api_keys()

    if not keys and requires_gemini:
        console.print(i18n.tr(language, "error_no_api_key"))
        return

    if keys and getattr(api, "GEMINI_AVAILABLE", True) and requires_gemini:
        if len(keys) > 1:
            console.print(i18n.tr(language, "api_keys_loaded", count=len(keys)))

        api.configure_api(keys[0])

    # --- Xử lý các lệnh tiện ích (thoát ngay sau khi chạy) ---
    if args.list_models:
        api.list_models(console)
        return
    if args.set_model:
        config_handler.model_selection_wizard(console, config)
        return
    if args.add_persona:
        config_handler.add_persona(console, config, args.add_persona[0], args.add_persona[1])
        return
    if args.list_personas:
        config_handler.list_personas(console, config)
        return
    if args.rm_persona:
        config_handler.remove_persona(console, config, args.rm_persona)
        return
    if args.add_instruct:
        config_handler.add_instruction(console, config, args.add_instruct)
        return
    if args.list_instructs:
        config_handler.list_instructions(console, config)
        return
    if args.rm_instruct is not None:
        config_handler.remove_instruction(console, config, args.rm_instruct)
        return
    if args.git_commit or getattr(args, "git_commit_short", False):
        utility_handler.generate_git_commit_message(
            console,
            args,
            short=getattr(args, "git_commit_short", False),
        )
        return
    if args.document:
        utility_handler.document_code_file(console, args)
        return
    if args.refactor:
        utility_handler.refactor_code_file(console, args)
        return

    # --- Xử lý Agent Mode ---
    if args.agent:
        if not args.prompt:
            console.print(i18n.tr(language, "agent_requires_prompt"))
            return
        agent_handler.run_master_agent(console, args)
        return

    history, should_exit = handle_history_flow(
        console,
        config,
        language,
        args,
        cli_help_text,
        provided_args,
    )
    if should_exit:
        return

    # --- Chế độ Chat ---
    if args.chat or args.topic:
        system_instruction_str = core_handler.build_system_instruction(config, args)

        model_name = args.model or config.get("default_model")

        if api.is_ollama_model(model_name) or api.is_openrouter_model(model_name) or api.is_generic_openai_model(model_name) or getattr(model_name, "startswith", lambda _x: False)("deepseek-") or getattr(model_name, "startswith", lambda _x: False)("groq-"):
            chat_handler.run_chat_mode(console, config, args, system_instruction_str)
        else:
            chat_session = api.start_chat_session(
                model_name,
                system_instruction_str,
                history,
                cli_help_text=cli_help_text,
            )
            chat_handler.run_chat_mode_legacy(chat_session, console, config, args)
        return

    # --- Single-turn ---
    run_single_turn(console, config, language, parser, args, cli_help_text, history)
