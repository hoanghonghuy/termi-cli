"""Plugin Manager for Termi CLI.

Loads dynamic python scripts from plugins directory and registers them as tools.
"""
import os
import sys
import importlib.util
import inspect
from pathlib import Path

from termi_cli.config import APP_DIR

PLUGINS_DIR = APP_DIR / "plugins"

def ensure_plugins_dir():
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        # Create a sample plugin
        sample_path = PLUGINS_DIR / "sample_plugin.py"
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write('''"""Sample plugin for Termi."""
from termi_cli.api import termi_tool

@termi_tool
def hello_plugin(name: str):
    """Prints a greeting from a plugin."""
    return f"Hello {name} from Termi Plugin System!"
''')

def load_plugins(verbose=False):
    """Load all .py files in plugins dir."""
    ensure_plugins_dir()
    
    loaded_tools = {}
    
    # Add plugins dir to sys.path so plugins can import each other if needed
    sys.path.insert(0, str(PLUGINS_DIR))
    
    for file_path in PLUGINS_DIR.glob("*.py"):
        if file_path.name.startswith("_"):
            continue
            
        module_name = file_path.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Scan module for functions decorated with @termi_tool
                # Actually, we rely on the tool registering itself or we scan functions
                # But since we don't have a global registry in api yet for plugins, 
                # we need a way to identify them.
                # Let's inspect functions.
                
                for name, func in inspect.getmembers(module, inspect.isfunction):
                    if getattr(func, "_is_termi_tool", False):
                        loaded_tools[name] = func
                        if verbose:
                            print(f"Loaded plugin tool: {name}")
                            
        except Exception as e:
            if verbose:
                print(f"Failed to load plugin {module_name}: {e}")

    sys.path.pop(0)
    return loaded_tools
