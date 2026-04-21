"""Audio transcription using OpenAI Whisper API."""

import logging
import httpx

from config import get_settings

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """Transcriber for audio messages using Whisper API."""

    def __init__(self):
        """Initialize Whisper client."""
        settings = get_settings()
        self.api_key = settings.openai_api_key
        logger.info("AudioTranscriber initialized")

    async def transcribe_from_url(self, audio_url: str) -> str:
        """Transcribe audio file from URL."""
        try:
            # Download audio file
            async with httpx.AsyncClient() as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                audio_data = response.content

            # Send to Whisper API
            async with httpx.AsyncClient() as client:
                files = {
                    "file": ("audio.ogg", audio_data, "audio/ogg"),
                    "model": (None, "whisper-1"),
                    "language": (None, "es"),
                }
                headers = {"Authorization": f"Bearer {self.api_key}"}

                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
                transcript = result.get("text", "")

                logger.info(f"Transcribed audio from {audio_url}: {len(transcript)} chars")
                return transcript
        except httpx.HTTPError as e:
            logger.error(f"HTTP error transcribing audio: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to transcribe audio from {audio_url}: {e}")
            raise


async def get_audio_transcriber() -> AudioTranscriber:
    """Get or create audio transcriber (dependency injection)."""
    return AudioTranscriber()
