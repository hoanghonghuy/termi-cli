"""Theme manager for Termi CLI.

Provides customizable color themes for the terminal interface.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from termi_cli.config import APP_DIR, load_config, save_config

logger = logging.getLogger(__name__)

# Built-in themes
THEMES = {
    "default": {
        "name": "Default",
        "user_prompt": "bold green",
        "ai_response": "white",
        "system_message": "dim",
        "error": "bold red",
        "warning": "yellow",
        "success": "green",
        "info": "cyan",
        "highlight": "bold cyan",
        "code_block": "bright_white on grey23",
    },
    "dark": {
        "name": "Dark",
        "user_prompt": "bold bright_green",
        "ai_response": "bright_white",
        "system_message": "grey50",
        "error": "bold bright_red",
        "warning": "bright_yellow",
        "success": "bright_green",
        "info": "bright_cyan",
        "highlight": "bold bright_magenta",
        "code_block": "bright_white on grey15",
    },
    "light": {
        "name": "Light",
        "user_prompt": "bold blue",
        "ai_response": "black",
        "system_message": "grey50",
        "error": "bold red",
        "warning": "dark_orange",
        "success": "dark_green",
        "info": "dark_cyan",
        "highlight": "bold dark_magenta",
        "code_block": "black on grey85",
    },
    "ocean": {
        "name": "Ocean",
        "user_prompt": "bold cyan",
        "ai_response": "bright_white",
        "system_message": "grey58",
        "error": "bold red",
        "warning": "gold1",
        "success": "spring_green2",
        "info": "deep_sky_blue1",
        "highlight": "bold turquoise2",
        "code_block": "bright_white on dark_blue",
    },
    "forest": {
        "name": "Forest",
        "user_prompt": "bold green3",
        "ai_response": "white",
        "system_message": "grey50",
        "error": "bold red",
        "warning": "gold3",
        "success": "chartreuse3",
        "info": "dark_olive_green2",
        "highlight": "bold spring_green3",
        "code_block": "white on dark_green",
    },
}


def get_current_theme() -> str:
    """Get current theme name from config."""
    config = load_config()
    return config.get("theme", "default")


def set_theme(theme_name: str) -> bool:
    """Set the current theme.
    
    Args:
        theme_name: Name of theme to set
        
    Returns:
        True if successful
    """
    if theme_name not in THEMES:
        return False
    
    config = load_config()
    config["theme"] = theme_name
    save_config(config)
    return True


def get_theme_style(key: str) -> str:
    """Get a style from current theme.
    
    Args:
        key: Style key (user_prompt, ai_response, etc.)
        
    Returns:
        Rich style string
    """
    theme_name = get_current_theme()
    theme = THEMES.get(theme_name, THEMES["default"])
    return theme.get(key, "")


def list_themes() -> list[str]:
    """List available theme names."""
    return list(THEMES.keys())


def get_theme_info(theme_name: str) -> Optional[dict]:
    """Get theme info by name."""
    return THEMES.get(theme_name)


def preview_theme(theme_name: str) -> str:
    """Generate preview text for a theme."""
    theme = THEMES.get(theme_name)
    if not theme:
        return ""
    
    lines = [
        f"Theme: {theme['name']}",
        f"[{theme['user_prompt']}]You: Hello AI[/{theme['user_prompt']}]",
        f"[{theme['ai_response']}]AI: Hello! How can I help?[/{theme['ai_response']}]",
        f"[{theme['success']}]✓ Success message[/{theme['success']}]",
        f"[{theme['error']}]✗ Error message[/{theme['error']}]",
        f"[{theme['warning']}]⚠ Warning message[/{theme['warning']}]",
    ]
    return "\n".join(lines)
