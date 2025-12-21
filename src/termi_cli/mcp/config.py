"""MCP (Model Context Protocol) configuration management.

This module handles:
- Loading MCP server configurations from config.json
- Validating server definitions
"""

from __future__ import annotations

import logging
from typing import Any

from termi_cli.config import load_config, save_config

logger = logging.getLogger(__name__)


def get_mcp_servers() -> list[dict[str, Any]]:
    """Get list of configured MCP servers.
    
    Returns:
        List of server configuration dictionaries.
    """
    config = load_config()
    servers = config.get("mcp_servers", [])
    
    if not isinstance(servers, list):
        return []
    
    return [s for s in servers if isinstance(s, dict) and s.get("name")]


def add_mcp_server(
    name: str,
    transport: str,
    command: list[str] | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Add a new MCP server configuration.
    
    Args:
        name: Unique name for the server
        transport: Transport type ('stdio', 'sse', 'streamable-http')
        command: Command to start the server (for stdio)
        url: URL for the server (for sse/streamable-http)
        env: Environment variables to pass to the server
        
    Returns:
        The created server configuration.
    """
    config = load_config()
    
    if "mcp_servers" not in config:
        config["mcp_servers"] = []
    
    # Check for duplicate name
    existing_names = {s.get("name") for s in config["mcp_servers"] if isinstance(s, dict)}
    if name in existing_names:
        raise ValueError(f"MCP server '{name}' already exists")
    
    server_config = {
        "name": name,
        "transport": transport,
        "enabled": True,
    }
    
    if transport == "stdio":
        if not command:
            raise ValueError("stdio transport requires 'command'")
        server_config["command"] = command
    else:
        if not url:
            raise ValueError(f"{transport} transport requires 'url'")
        server_config["url"] = url
    
    if env:
        server_config["env"] = env
    
    config["mcp_servers"].append(server_config)
    save_config(config)
    
    return server_config


def remove_mcp_server(name: str) -> bool:
    """Remove an MCP server configuration.
    
    Args:
        name: Name of the server to remove
        
    Returns:
        True if removed, False if not found.
    """
    config = load_config()
    servers = config.get("mcp_servers", [])
    
    original_len = len(servers)
    config["mcp_servers"] = [s for s in servers if s.get("name") != name]
    
    if len(config["mcp_servers"]) < original_len:
        save_config(config)
        return True
    
    return False


def toggle_mcp_server(name: str, enabled: bool) -> bool:
    """Enable or disable an MCP server.
    
    Args:
        name: Name of the server
        enabled: Whether to enable the server
        
    Returns:
        True if found and updated, False if not found.
    """
    config = load_config()
    servers = config.get("mcp_servers", [])
    
    for server in servers:
        if server.get("name") == name:
            server["enabled"] = enabled
            save_config(config)
            return True
    
    return False


def get_enabled_servers() -> list[dict[str, Any]]:
    """Get list of enabled MCP servers.
    
    Returns:
        List of enabled server configurations.
    """
    return [s for s in get_mcp_servers() if s.get("enabled", True)]
