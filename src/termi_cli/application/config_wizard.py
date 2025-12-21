"""Config wizard for Termi CLI first-time setup.

Interactive setup for new users.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from termi_cli.config import APP_DIR, load_config, save_config


def run_config_wizard(language: str = "vi") -> bool:
    """Run the interactive configuration wizard.
    
    Args:
        language: Language for the wizard (vi/en)
        
    Returns:
        True if setup completed successfully
    """
    console = Console()
    config = load_config()
    
    # Header
    if language == "vi":
        console.print(Panel(
            "[bold cyan]🚀 Chào mừng đến với Termi CLI![/bold cyan]\n"
            "Hãy cấu hình một số thiết lập cơ bản.",
            title="Wizard Cấu Hình"
        ))
    else:
        console.print(Panel(
            "[bold cyan]🚀 Welcome to Termi CLI![/bold cyan]\n"
            "Let's configure some basic settings.",
            title="Configuration Wizard"
        ))
    
    # Step 1: Language preference
    lang_prompt = "Ngôn ngữ / Language (vi/en)" if language == "vi" else "Language (vi/en)"
    lang_choice = Prompt.ask(lang_prompt, default="vi", choices=["vi", "en"])
    config["language"] = lang_choice
    language = lang_choice  # Update for rest of wizard
    
    # Step 2: API Provider
    if language == "vi":
        console.print("\n[bold]Bước 1: Chọn Provider AI[/bold]")
        console.print("1. Gemini (Google AI)")
        console.print("2. OpenAI Compatible (LM Studio, Ollama, v.v.)")
        console.print("3. DeepSeek")
        console.print("4. Groq")
    else:
        console.print("\n[bold]Step 1: Choose AI Provider[/bold]")
        console.print("1. Gemini (Google AI)")
        console.print("2. OpenAI Compatible (LM Studio, Ollama, etc.)")
        console.print("3. DeepSeek")
        console.print("4. Groq")
    
    provider_choice = Prompt.ask("Choice", default="1", choices=["1", "2", "3", "4"])
    
    if provider_choice == "1":
        # Gemini
        api_key = Prompt.ask(
            "Gemini API Key" if language == "en" else "API Key Gemini",
            password=True
        )
        if api_key:
            config["gemini_api_keys"] = [api_key]
            config["default_gemini_model"] = "gemini-2.0-flash-exp"
            
    elif provider_choice == "2":
        # OpenAI Compatible
        base_url = Prompt.ask(
            "API Base URL (e.g., http://localhost:1234/v1)",
            default="http://localhost:1234/v1"
        )
        api_key = Prompt.ask("API Key (leave empty if not required)", default="", password=True)
        model = Prompt.ask(
            "Model name" if language == "en" else "Tên model",
            default="local-model"
        )
        
        config["openai_compatible"] = {
            "enabled": True,
            "base_url": base_url,
            "api_key": api_key or "not-needed",
            "model": f"openai-compatible/{model}"
        }
        
    elif provider_choice == "3":
        # DeepSeek
        api_key = Prompt.ask("DeepSeek API Key", password=True)
        if api_key:
            config["deepseek_api_key"] = api_key
            
    elif provider_choice == "4":
        # Groq
        api_key = Prompt.ask("Groq API Key", password=True)
        if api_key:
            config["groq_api_key"] = api_key
    
    # Step 3: System instruction
    if language == "vi":
        console.print("\n[bold]Bước 2: Tùy chỉnh (tùy chọn)[/bold]")
        use_custom = Confirm.ask("Bạn có muốn thêm hướng dẫn hệ thống tùy chỉnh không?", default=False)
    else:
        console.print("\n[bold]Step 2: Customization (optional)[/bold]")
        use_custom = Confirm.ask("Would you like to add a custom system instruction?", default=False)
    
    if use_custom:
        instruction = Prompt.ask(
            "System instruction" if language == "en" else "Hướng dẫn hệ thống"
        )
        if instruction:
            config["system_instruction"] = instruction
    
    # Save config
    try:
        save_config(config)
        if language == "vi":
            console.print("\n[bold green]✅ Cấu hình đã được lưu![/bold green]")
            console.print(f"File: {APP_DIR / 'config.json'}")
            console.print("\nBạn có thể bắt đầu sử dụng: [bold]termi \"xin chào\"[/bold]")
        else:
            console.print("\n[bold green]✅ Configuration saved![/bold green]")
            console.print(f"File: {APP_DIR / 'config.json'}")
            console.print("\nYou can start using: [bold]termi \"hello\"[/bold]")
        return True
    except Exception as e:
        console.print(f"[red]Error saving config: {e}[/red]")
        return False


def is_first_run() -> bool:
    """Check if this is the first run (no config file)."""
    config_file = APP_DIR / "config.json"
    return not config_file.exists()
