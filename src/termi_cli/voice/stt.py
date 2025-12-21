"""Speech-to-Text (STT) module for voice input.

Provides multiple backends:
- Local: Uses faster-whisper or whisper.cpp
- Cloud: Uses OpenAI Whisper API
"""

from __future__ import annotations

import os
import io
import wave
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Check for available STT backends
_WHISPER_AVAILABLE = False
_SOUNDDEVICE_AVAILABLE = False

try:
    import sounddevice as sd
    import numpy as np
    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    np = None
    logger.debug("sounddevice not available, audio recording disabled")

try:
    from faster_whisper import WhisperModel
    _WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    logger.debug("faster-whisper not available, using fallback or cloud API")


class AudioRecorder:
    """Record audio from microphone."""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        """Initialize the audio recorder.
        
        Args:
            sample_rate: Audio sample rate (default: 16000 Hz for Whisper)
            channels: Number of audio channels (default: 1 for mono)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self._recording = False
        self._frames: list = []
    
    @property
    def is_available(self) -> bool:
        """Check if audio recording is available."""
        return _SOUNDDEVICE_AVAILABLE
    
    def record_until_silence(
        self,
        silence_threshold: float = 0.02,
        silence_duration: float = 1.5,
        max_duration: float = 30.0,
    ) -> bytes | None:
        """Record audio until silence is detected.
        
        Args:
            silence_threshold: RMS threshold for silence detection
            silence_duration: Duration of silence to stop recording (seconds)
            max_duration: Maximum recording duration (seconds)
            
        Returns:
            WAV audio bytes, or None if recording failed.
        """
        if not _SOUNDDEVICE_AVAILABLE:
            return None
        
        self._frames = []
        self._recording = True
        
        silence_samples = int(silence_duration * self.sample_rate / 1024)
        max_samples = int(max_duration * self.sample_rate / 1024)
        silence_count = 0
        
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                blocksize=1024,
            ) as stream:
                sample_count = 0
                
                while self._recording and sample_count < max_samples:
                    data, _ = stream.read(1024)
                    self._frames.append(data.copy())
                    sample_count += 1
                    
                    # Check for silence
                    rms = np.sqrt(np.mean(data ** 2))
                    if rms < silence_threshold:
                        silence_count += 1
                        if silence_count >= silence_samples:
                            break
                    else:
                        silence_count = 0
            
            return self._frames_to_wav()
            
        except Exception as e:
            logger.error("Error recording audio: %s", e)
            return None
    
    def record_for_duration(self, duration: float = 5.0) -> bytes | None:
        """Record audio for a fixed duration.
        
        Args:
            duration: Recording duration in seconds
            
        Returns:
            WAV audio bytes, or None if recording failed.
        """
        if not _SOUNDDEVICE_AVAILABLE:
            return None
        
        try:
            samples = int(duration * self.sample_rate)
            recording = sd.rec(
                samples,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
            )
            sd.wait()
            
            self._frames = [recording]
            return self._frames_to_wav()
            
        except Exception as e:
            logger.error("Error recording audio: %s", e)
            return None
    
    def stop(self):
        """Stop recording."""
        self._recording = False
    
    def _frames_to_wav(self) -> bytes | None:
        """Convert recorded frames to WAV bytes."""
        if not self._frames or not _SOUNDDEVICE_AVAILABLE:
            return None
        
        try:
            import numpy as np
            
            audio = np.concatenate(self._frames, axis=0)
            audio_int16 = (audio * 32767).astype(np.int16)
            
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_int16.tobytes())
            
            return buffer.getvalue()
            
        except Exception as e:
            logger.error("Error converting audio to WAV: %s", e)
            return None


class LocalWhisperSTT:
    """Speech-to-Text using local faster-whisper."""
    
    def __init__(self, model_size: str = "base"):
        """Initialize local Whisper STT.
        
        Args:
            model_size: Model size ('tiny', 'base', 'small', 'medium', 'large')
        """
        self.model_size = model_size
        self._model: Optional[WhisperModel] = None
    
    @property
    def is_available(self) -> bool:
        """Check if local Whisper is available."""
        return _WHISPER_AVAILABLE
    
    def _ensure_model(self):
        """Load the model if not already loaded."""
        if self._model is None and _WHISPER_AVAILABLE:
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
    
    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio to text.
        
        Args:
            audio_bytes: WAV audio bytes
            
        Returns:
            Transcribed text.
        """
        if not _WHISPER_AVAILABLE:
            return "[Error: faster-whisper not installed]"
        
        try:
            self._ensure_model()
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            
            try:
                segments, _ = self._model.transcribe(
                    tmp_path,
                    beam_size=5,
                    language="vi",  # Auto-detect or specify
                    vad_filter=True,
                )
                
                text = " ".join(seg.text for seg in segments)
                return text.strip()
                
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            logger.error("Error transcribing audio: %s", e)
            return f"[Error: {e}]"


class CloudWhisperSTT:
    """Speech-to-Text using OpenAI Whisper API."""
    
    def __init__(self, api_key: str | None = None):
        """Initialize cloud Whisper STT.
        
        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    
    @property
    def is_available(self) -> bool:
        """Check if cloud Whisper is available."""
        return bool(self.api_key)
    
    def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        """Transcribe audio to text using OpenAI API.
        
        Args:
            audio_bytes: WAV audio bytes
            language: Language code (default: vi)
            
        Returns:
            Transcribed text.
        """
        if not self.api_key:
            return "[Error: No OpenAI API key]"
        
        try:
            import httpx
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            
            try:
                with open(tmp_path, "rb") as f:
                    response = httpx.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files={"file": ("audio.wav", f, "audio/wav")},
                        data={
                            "model": "whisper-1",
                            "language": language,
                        },
                        timeout=30.0,
                    )
                
                if response.status_code == 200:
                    return response.json().get("text", "")
                else:
                    return f"[Error: API returned {response.status_code}]"
                    
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            logger.error("Error calling Whisper API: %s", e)
            return f"[Error: {e}]"


def get_stt_engine(prefer_local: bool = True) -> LocalWhisperSTT | CloudWhisperSTT:
    """Get an appropriate STT engine.
    
    Args:
        prefer_local: If True, prefer local engine when available
        
    Returns:
        STT engine instance.
    """
    if prefer_local and _WHISPER_AVAILABLE:
        return LocalWhisperSTT()
    return CloudWhisperSTT()


def is_stt_available() -> bool:
    """Check if any STT engine is available."""
    return _WHISPER_AVAILABLE or bool(os.environ.get("OPENAI_API_KEY"))


def is_recording_available() -> bool:
    """Check if audio recording is available."""
    return _SOUNDDEVICE_AVAILABLE
