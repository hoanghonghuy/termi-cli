import os
import sys
import json
from rich.console import Console

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from termi_cli import api
from termi_cli.infrastructure import http_providers

console = Console()

def test_openai_compatible_multimodal():
    # Mock config
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = "http://localhost:8317/v1"
    os.environ["OPENAI_COMPATIBLE_API_KEY"] = "proxypal-local"
    
    # 1. Test Text-only
    console.print("\n[bold]Testing Text-only...[/bold]")
    model_name = "openai-compatible/iflow/qwen3-max" # Assuming this model exists locally
    
    messages = [
        {"role": "user", "content": "Hello, are you online?"}
    ]
    
    try:
        response = api.generate_text(model_name, messages) # Passing list directly!
        console.print(f"[green]Response:[/green] {response}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")

    # 2. Test Multi-modal Structure (Mock image)
    console.print("\n[bold]Testing Multi-modal Structure (Mock)...[/bold]")
    # We won't actually send a real image to save bytes/complexity, but we check if the code accepts the structure.
    # If the local server doesn't support vision, it might fail, but we want to see if `http_providers` constructs it correctly.
    
    # Tiny 1x1 base64 png
    tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKwAEQAAAABJRU5ErkJggg=="
    
    messages_vision = [
        {
            "role": "user", 
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png}"}}
            ]
        }
    ]
    
    try:
        # We define a custom 'generate' call or just use api.generate_text
        # Note: If local model doesn't support vision, it might error 400.
        # We are testing the Client side logic.
        response = api.generate_text(model_name, messages_vision)
        console.print(f"[green]Vision Response:[/green] {response}")
    except Exception as e:
        console.print(f"[red]Vision Error (Expected if model non-vision):[/red] {e}")

if __name__ == "__main__":
    test_openai_compatible_multimodal()
