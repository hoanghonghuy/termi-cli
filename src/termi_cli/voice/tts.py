"""Text-to-Speech (TTS) module for voice output.

Provides multiple backends:
- Local: Uses pyttsx3 (cross-platform)
- Cloud: Uses OpenAI TTS API
"""

from __future__ import annotations

import os
import io
import logging
import tempfile
from typing import Literal

logger = logging.getLogger(__name__)

# Check for available TTS backends
_PYTTSX3_AVAILABLE = False
_PLAYSOUND_AVAILABLE = False

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    logger.debug("pyttsx3 not available")

try:
    import playsound
    _PLAYSOUND_AVAILABLE = True
except ImportError:
    playsound = None
    logger.debug("playsound not available, audio playback may be limited")


class LocalTTS:
    """Text-to-Speech using local pyttsx3 engine."""
    
    def __init__(self, voice_id: str | None = None, rate: int = 150):
        """Initialize local TTS.
        
        Args:
            voice_id: Voice ID to use (None for default)
            rate: Speech rate (words per minute)
        """
        self._engine = None
        self.voice_id = voice_id
        self.rate = rate
    
    @property
    def is_available(self) -> bool:
        """Check if local TTS is available."""
        return _PYTTSX3_AVAILABLE
    
    def _ensure_engine(self):
        """Initialize the TTS engine if not already done."""
        if self._engine is None and _PYTTSX3_AVAILABLE:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            
            if self.voice_id:
                self._engine.setProperty("voice", self.voice_id)
    
    def speak(self, text: str) -> bool:
        """Speak text aloud.
        
        Args:
            text: Text to speak
            
        Returns:
            True if successful.
        """
        if not _PYTTSX3_AVAILABLE:
            logger.warning("pyttsx3 not available for TTS")
            return False
        
        try:
            self._ensure_engine()
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except Exception as e:
            logger.error("Error speaking text: %s", e)
            return False
    
    def save_to_file(self, text: str, output_path: str) -> bool:
        """Save speech to audio file.
        
        Args:
            text: Text to convert
            output_path: Output file path
            
        Returns:
            True if successful.
        """
        if not _PYTTSX3_AVAILABLE:
            return False
        
        try:
            self._ensure_engine()
            self._engine.save_to_file(text, output_path)
            self._engine.runAndWait()
            return True
        except Exception as e:
            logger.error("Error saving speech to file: %s", e)
            return False
    
    def get_available_voices(self) -> list[dict]:
        """Get list of available voices.
        
        Returns:
            List of voice dictionaries with id, name, languages.
        """
        if not _PYTTSX3_AVAILABLE:
            return []
        
        try:
            self._ensure_engine()
            voices = self._engine.getProperty("voices")
            return [
                {
                    "id": v.id,
                    "name": v.name,
                    "languages": getattr(v, "languages", []),
                }
                for v in voices
            ]
        except Exception:
            return []


class CloudTTS:
    """Text-to-Speech using OpenAI TTS API."""
    
    def __init__(
        self,
        api_key: str | None = None,
        voice: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"] = "nova",
        model: str = "tts-1",
    ):
        """Initialize cloud TTS.
        
        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            voice: Voice to use
            model: Model to use ('tts-1' or 'tts-1-hd')
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.voice = voice
        self.model = model
    
    @property
    def is_available(self) -> bool:
        """Check if cloud TTS is available."""
        return bool(self.api_key)
    
    def generate_audio(self, text: str) -> bytes | None:
        """Generate audio from text.
        
        Args:
            text: Text to convert
            
        Returns:
            MP3 audio bytes, or None if failed.
        """
        if not self.api_key:
            return None
        
        try:
            import httpx
            
            response = httpx.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text,
                    "voice": self.voice,
                    "response_format": "mp3",
                },
                timeout=30.0,
            )
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error("TTS API error: %s", response.text)
                return None
                
        except Exception as e:
            logger.error("Error calling TTS API: %s", e)
            return None
    
    def speak(self, text: str) -> bool:
        """Generate and play speech.
        
        Args:
            text: Text to speak
            
        Returns:
            True if successful.
        """
        audio = self.generate_audio(text)
        if not audio:
            return False
        
        return self._play_audio(audio)
    
    def _play_audio(self, audio_bytes: bytes) -> bool:
        """Play audio bytes.
        
        Args:
            audio_bytes: MP3 audio bytes
            
        Returns:
            True if successful.
        """
        try:
            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            
            try:
                if _PLAYSOUND_AVAILABLE:
                    playsound.playsound(tmp_path)
                    return True
                else:
                    # Try system command as fallback
                    import subprocess
                    import platform
                    
                    system = platform.system()
                    if system == "Windows":
                        # Use Windows Media Player command line
                        subprocess.run(
                            ["cmd", "/c", "start", "/min", "", tmp_path],
                            check=True,
                        )
                    elif system == "Darwin":
                        subprocess.run(["afplay", tmp_path], check=True)
                    else:
                        subprocess.run(
                            ["mpv", "--really-quiet", tmp_path],
                            check=True,
                        )
                    return True
            finally:
                # Clean up temp file after a delay
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error("Error playing audio: %s", e)
            return False
    
    def save_to_file(self, text: str, output_path: str) -> bool:
        """Save speech to audio file.
        
        Args:
            text: Text to convert
            output_path: Output file path
            
        Returns:
            True if successful.
        """
        audio = self.generate_audio(text)
        if not audio:
            return False
        
        try:
            with open(output_path, "wb") as f:
                f.write(audio)
            return True
        except Exception as e:
            logger.error("Error saving audio file: %s", e)
            return False


def get_tts_engine(prefer_local: bool = True) -> LocalTTS | CloudTTS:
    """Get an appropriate TTS engine.
    
    Args:
        prefer_local: If True, prefer local engine when available
        
    Returns:
        TTS engine instance.
    """
    if prefer_local and _PYTTSX3_AVAILABLE:
        return LocalTTS()
    return CloudTTS()


def is_tts_available() -> bool:
    """Check if any TTS engine is available."""
    return _PYTTSX3_AVAILABLE or bool(os.environ.get("OPENAI_API_KEY"))
