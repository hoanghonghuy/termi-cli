"""Alias system for Termi CLI.

Allows users to create shortcuts for frequently used commands.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from termi_cli.config import APP_DIR

logger = logging.getLogger(__name__)

ALIAS_FILE = APP_DIR / "aliases.json"


def load_aliases() -> dict[str, str]:
    """Load aliases from file."""
    if ALIAS_FILE.exists():
        try:
            with open(ALIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load aliases: %s", e)
    return {}


def save_aliases(aliases: dict[str, str]) -> bool:
    """Save aliases to file."""
    try:
        with open(ALIAS_FILE, "w", encoding="utf-8") as f:
            json.dump(aliases, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save aliases: %s", e)
        return False


def add_alias(name: str, command: str) -> bool:
    """Add or update an alias.
    
    Args:
        name: Alias name
        command: Command to execute
        
    Returns:
        True if successful
    """
    aliases = load_aliases()
    aliases[name] = command
    return save_aliases(aliases)


def remove_alias(name: str) -> bool:
    """Remove an alias.
    
    Args:
        name: Alias name to remove
        
    Returns:
        True if removed, False if not found
    """
    aliases = load_aliases()
    if name in aliases:
        del aliases[name]
        return save_aliases(aliases)
    return False


def get_alias(name: str) -> Optional[str]:
    """Get command for an alias.
    
    Args:
        name: Alias name
        
    Returns:
        Command string or None
    """
    aliases = load_aliases()
    return aliases.get(name)


def list_aliases() -> dict[str, str]:
    """List all aliases."""
    return load_aliases()


def expand_alias(input_text: str) -> str:
    """Expand alias if input matches.
    
    Args:
        input_text: User input
        
    Returns:
        Expanded command or original input
    """
    parts = input_text.strip().split(maxsplit=1)
    if not parts:
        return input_text
    
    alias_name = parts[0]
    aliases = load_aliases()
    
    if alias_name in aliases:
        command = aliases[alias_name]
        if len(parts) > 1:
            # Append remaining args
            return f"{command} {parts[1]}"
        return command
    
    return input_text
