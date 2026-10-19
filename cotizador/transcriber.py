"""Nota de voz -> texto. Anthropic no ofrece audio, así que se usa la API de OpenAI."""
import io

from .config import TRANSCRIPTION_MODEL


class TranscripcionError(RuntimeError):
    pass


def transcribir(audio: bytes, nombre: str = "nota.wav") -> str:
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as e:
        raise TranscripcionError("Instala el paquete 'openai' para transcribir audio.") from e

    try:
        buf = io.BytesIO(audio)
        buf.name = nombre
        resp = OpenAI().audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL, file=buf, language="es"
        )
    except OpenAIError as e:
        raise TranscripcionError(f"Falló la transcripción: {e}") from e
    return resp.text.strip()
