"""MCP (Model Context Protocol) client implementation.

This module provides a client for:
- Connecting to MCP servers (stdio, sse, streamable-http)
- Discovering available tools
- Executing tool calls
"""

from __future__ import annotations

import subprocess
import threading
import queue
import json
import logging
import os
from typing import Any, Callable

from termi_cli.mcp import config as mcp_config

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Error connecting to MCP server."""
    pass


class MCPTimeoutError(MCPClientError):
    """Timeout waiting for MCP server response."""
    pass


class StdioMCPClient:
    """MCP client for stdio transport.
    
    Communicates with MCP servers via stdin/stdout using JSON-RPC.
    """
    
    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        """Initialize the stdio MCP client.
        
        Args:
            command: Command to start the server
            env: Additional environment variables
            timeout: Default timeout for operations
        """
        self.command = command
        self.env = env or {}
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self._request_id = 0
        self._response_queue: queue.Queue = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._running = False
        self._tools: dict[str, dict[str, Any]] = {}
    
    def _get_next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    
    def _reader_loop(self):
        """Background thread to read responses from the server."""
        while self._running and self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    try:
                        response = json.loads(line)
                        self._response_queue.put(response)
                    except json.JSONDecodeError:
                        logger.debug("Non-JSON line from MCP server: %s", line[:100])
            except Exception as e:
                logger.debug("Error reading from MCP server: %s", e)
                break
    
    def connect(self) -> bool:
        """Start the MCP server process and connect.
        
        Returns:
            True if connected successfully.
        """
        if self.process:
            return True
        
        try:
            # Merge environment
            full_env = os.environ.copy()
            full_env.update(self.env)
            
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=full_env,
            )
            
            self._running = True
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            
            # Send initialize request
            init_result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "termi-cli",
                    "version": "1.0.0",
                }
            })
            
            if init_result is None:
                raise MCPConnectionError("Failed to initialize MCP connection")
            
            # Send initialized notification
            self._send_notification("notifications/initialized", {})
            
            # Discover tools
            self._discover_tools()
            
            return True
            
        except Exception as e:
            logger.error("Failed to start MCP server: %s", e)
            self.disconnect()
            raise MCPConnectionError(f"Failed to connect: {e}")
    
    def disconnect(self):
        """Disconnect from the MCP server."""
        self._running = False
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        
        if self._reader_thread:
            self._reader_thread.join(timeout=1)
            self._reader_thread = None
    
    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Send a JSON-RPC request and wait for response.
        
        Args:
            method: The method name
            params: The parameters
            
        Returns:
            The result, or None if failed.
        """
        if not self.process or not self.process.stdin:
            raise MCPConnectionError("Not connected to MCP server")
        
        request_id = self._get_next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        
        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            raise MCPConnectionError(f"Failed to send request: {e}")
        
        # Wait for response
        try:
            response = self._response_queue.get(timeout=self.timeout)
            
            if response.get("id") != request_id:
                # Keep looking (simplified handling)
                logger.debug("Got response for different request ID")
                return None
            
            if "error" in response:
                error = response["error"]
                logger.error("MCP error: %s", error.get("message", "Unknown error"))
                return None
            
            return response.get("result")
            
        except queue.Empty:
            raise MCPTimeoutError(f"Timeout waiting for response to {method}")
    
    def _send_notification(self, method: str, params: dict[str, Any]):
        """Send a JSON-RPC notification (no response expected).
        
        Args:
            method: The method name
            params: The parameters
        """
        if not self.process or not self.process.stdin:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        
        try:
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            logger.debug("Failed to send notification: %s", e)
    
    def _discover_tools(self):
        """Discover available tools from the server."""
        result = self._send_request("tools/list", {})
        
        if result and "tools" in result:
            for tool in result["tools"]:
                name = tool.get("name", "")
                if name:
                    self._tools[name] = tool
                    logger.debug("Discovered MCP tool: %s", name)
    
    def get_tools(self) -> dict[str, dict[str, Any]]:
        """Get discovered tools.
        
        Returns:
            Dictionary mapping tool names to their schemas.
        """
        return self._tools.copy()
    
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server.
        
        Args:
            name: The tool name
            arguments: The tool arguments
            
        Returns:
            The tool result.
        """
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        
        if result is None:
            return f"Error calling MCP tool '{name}'"
        
        # Extract content from result
        content = result.get("content", [])
        if isinstance(content, list):
            # Concatenate text content
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts) if texts else str(result)
        
        return str(result)


class MCPManager:
    """Manages multiple MCP client connections."""
    
    def __init__(self):
        self.clients: dict[str, StdioMCPClient] = {}
        self._tools: dict[str, tuple[str, Callable]] = {}  # tool_name -> (server_name, callable)
    
    def connect_all(self) -> dict[str, str]:
        """Connect to all enabled MCP servers.
        
        Returns:
            Dictionary mapping server names to status messages.
        """
        servers = mcp_config.get_enabled_servers()
        results = {}
        
        for server in servers:
            name = server.get("name", "unknown")
            transport = server.get("transport", "stdio")
            
            if transport != "stdio":
                results[name] = f"Unsupported transport: {transport}"
                continue
            
            command = server.get("command")
            if not command:
                results[name] = "No command specified"
                continue
            
            try:
                client = StdioMCPClient(
                    command=command,
                    env=server.get("env"),
                )
                client.connect()
                self.clients[name] = client
                
                # Register tools
                for tool_name, tool_schema in client.get_tools().items():
                    full_name = f"mcp:{name}:{tool_name}"
                    self._tools[full_name] = (name, lambda n=name, t=tool_name, c=client: 
                        lambda **kwargs: c.call_tool(t, kwargs))
                
                results[name] = f"Connected, {len(client.get_tools())} tools"
                
            except Exception as e:
                results[name] = f"Failed: {e}"
        
        return results
    
    def disconnect_all(self):
        """Disconnect from all MCP servers."""
        for client in self.clients.values():
            try:
                client.disconnect()
            except Exception:
                pass
        self.clients.clear()
        self._tools.clear()
    
    def get_all_tools(self) -> dict[str, Callable]:
        """Get all tools from all connected MCP servers.
        
        Returns:
            Dictionary mapping full tool names to callables.
        """
        tools = {}
        for full_name, (server_name, tool_factory) in self._tools.items():
            tools[full_name] = tool_factory()
        return tools
    
    def call_tool(self, full_name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool by its full name.
        
        Args:
            full_name: Full tool name (mcp:server:tool)
            arguments: Tool arguments
            
        Returns:
            Tool result as string.
        """
        parts = full_name.split(":", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return f"Invalid MCP tool name: {full_name}"
        
        server_name = parts[1]
        tool_name = parts[2]
        
        client = self.clients.get(server_name)
        if not client:
            return f"MCP server '{server_name}' not connected"
        
        return client.call_tool(tool_name, arguments)


# Global MCP manager instance
_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager instance."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


def connect_mcp_servers() -> dict[str, str]:
    """Connect to all configured MCP servers.
    
    Returns:
        Status dictionary.
    """
    return get_mcp_manager().connect_all()


def disconnect_mcp_servers():
    """Disconnect from all MCP servers."""
    get_mcp_manager().disconnect_all()


def get_mcp_tools() -> dict[str, Callable]:
    """Get all available MCP tools.
    
    Returns:
        Dictionary of tool callables.
    """
    return get_mcp_manager().get_all_tools()


def call_mcp_tool(full_name: str, arguments: dict[str, Any]) -> str:
    """Call an MCP tool.
    
    Args:
        full_name: Full tool name (mcp:server:tool)
        arguments: Tool arguments
        
    Returns:
        Tool result.
    """
    return get_mcp_manager().call_tool(full_name, arguments)
