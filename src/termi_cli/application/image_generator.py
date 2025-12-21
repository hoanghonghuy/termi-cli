"""
Image Generation Module - Supports OpenAI Compatible and Gemini APIs.
"""
import os
import base64
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional
from termi_cli.i18n import tr

# --- Constants ---
DEFAULT_OUTPUT_DIR = Path.home() / ".termi_cli" / "generated_images"
OPENAI_IMAGE_ENDPOINT = "/v1/images/generations"

class ImageGenerator:
    """Handles image generation via OpenAI Compatible or Gemini APIs."""
    
    def __init__(self, config: dict, language: str = "en"):
        self.config = config
        self.lang = language
        self.output_dir = Path(config.get("image_output_dir", DEFAULT_OUTPUT_DIR))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str, size: str = "1024x1024", model: str | None = None) -> dict:
        """
        Generate an image from a text prompt.
        
        Returns: {"success": bool, "path": str | None, "error": str | None}
        """
        provider = self.config.get("provider", "openai_compatible")
        
        if provider == "gemini":
            return self._generate_gemini(prompt, size, model)
        else:
            return self._generate_openai_compatible(prompt, size, model)

    def _generate_openai_compatible(self, prompt: str, size: str, model: str | None) -> dict:
        """Generate image using OpenAI-compatible /v1/images/generations endpoint."""
        # Default to local proxy (ProxyPal) - matches existing codebase pattern
        oa_config = self.config.get("openai_compatible", {})
        base_url = oa_config.get("base_url") or self.config.get("http_base_url") or "http://localhost:8317/v1"
        api_key = oa_config.get("api_key") or self.config.get("http_api_key") or os.getenv("OPENAI_API_KEY", "proxypal-local")
        
        # Build request - note: endpoint is /images/generations, not /v1/images/generations if base already has /v1
        if base_url.endswith("/v1"):
            url = f"{base_url}/images/generations"
        else:
            url = f"{base_url.rstrip('/')}{OPENAI_IMAGE_ENDPOINT}"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json"  # Get base64 for local save
        }
        if model:
            payload["model"] = model
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            
            # Extract and save image
            b64_data = data.get("data", [{}])[0].get("b64_json")
            if not b64_data:
                return {"success": False, "path": None, "error": "No image data in response"}
            
            image_path = self._save_image(b64_data, prompt)
            return {"success": True, "path": str(image_path), "error": None}
            
        except httpx.HTTPStatusError as e:
            return {"success": False, "path": None, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"success": False, "path": None, "error": str(e)}

    def _generate_gemini(self, prompt: str, size: str, model: str | None) -> dict:
        """Generate image using Gemini Imagen API."""
        try:
            import google.generativeai as genai
        except ImportError:
            return {"success": False, "path": None, "error": "Gemini SDK not available. Use Python 3.10-3.12."}
        
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            return {"success": False, "path": None, "error": tr(self.lang, "imggen_no_api_key")}
        
        genai.configure(api_key=api_key)
        
        try:
            # Gemini Imagen model
            imagen_model = genai.ImageGenerationModel("imagen-3.0-generate-001")
            result = imagen_model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio="1:1" if size == "1024x1024" else "16:9"
            )
            
            if result.images:
                # Save the image
                image_data = result.images[0]._pil_image
                image_path = self._save_pil_image(image_data, prompt)
                return {"success": True, "path": str(image_path), "error": None}
            else:
                return {"success": False, "path": None, "error": "No images generated"}
                
        except Exception as e:
            return {"success": False, "path": None, "error": str(e)}

    def _save_image(self, b64_data: str, prompt: str) -> Path:
        """Save base64 image data to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c if c.isalnum() else "_" for c in prompt[:30])
        filename = f"{timestamp}_{safe_prompt}.png"
        filepath = self.output_dir / filename
        
        image_bytes = base64.b64decode(b64_data)
        filepath.write_bytes(image_bytes)
        return filepath

    def _save_pil_image(self, pil_image, prompt: str) -> Path:
        """Save PIL image to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c if c.isalnum() else "_" for c in prompt[:30])
        filename = f"{timestamp}_{safe_prompt}.png"
        filepath = self.output_dir / filename
        
        pil_image.save(str(filepath))
        return filepath


# --- Convenience Function ---

def generate_image(config: dict, prompt: str, language: str = "en", size: str = "1024x1024") -> dict:
    """Quick function to generate an image."""
    generator = ImageGenerator(config, language)
    return generator.generate(prompt, size)
