"""Extracción con Google Gemini (SDK google-genai) y salida estructurada Pydantic.

Acepta texto, audio o ambos: Gemini entiende el audio directamente, sin paso de
transcripción aparte. Funciona con la capa gratuita de Google AI Studio.
"""
import time

from google import genai
from google.genai import errors, types

from .config import GEMINI_MODEL
from .schemas import ExtraccionTrabajo

SYSTEM_PROMPT = """\
Eres el asistente de cotizaciones de una empresa de seguridad electrónica en Quito, Ecuador \
(alarmas, CCTV, cercas eléctricas, porteros, motores de garaje, domótica).

Recibirás una nota (texto escrito y/o nota de voz) con los datos de un trabajo. \
Extrae el cliente, los ítems con sus cantidades y precios, y las condiciones comerciales.

Reglas:
- Extrae solo lo que la nota dice. Si un dato no aparece, devuelve null (o lista vacía); nunca lo inventes.
- NO calcules totales ni subtotales: solo copia 'total_declarado' si la nota lo menciona literalmente.
- Escribe descripciones, título y observaciones en MAYÚSCULAS, como en las cotizaciones de la empresa.
- Incluye la unidad en la descripción del ítem ('METROS TENDIDO CERCA ELECTRICA', 'CAMARAS DOMO 2MP').
- Si la nota dice 'material y mano de obra incluidos' (o similar), ponlo en observaciones.
- En audio, interpreta cifras habladas ('veintinueve' = 29, 'ocho dólares' = 8).
"""


class ExtraccionError(RuntimeError):
    pass


def extraer(
    texto: str = "",
    audio: bytes | None = None,
    audio_mime: str = "audio/wav",
    client: genai.Client | None = None,
) -> ExtraccionTrabajo:
    partes: list = []
    if audio:
        partes.append(types.Part.from_bytes(data=audio, mime_type=audio_mime))
    if texto.strip():
        partes.append(texto.strip())
    if not partes:
        raise ExtraccionError("Escribe un texto o graba una nota de voz.")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ExtraccionTrabajo,
        temperature=0,
    )
    try:
        client = client or genai.Client()  # lee GEMINI_API_KEY / GOOGLE_API_KEY
        for intento in range(3):  # la capa gratuita devuelve 503 en picos de demanda
            try:
                resp = client.models.generate_content(model=GEMINI_MODEL, contents=partes, config=config)
                break
            except errors.ServerError:
                if intento == 2:
                    raise
                time.sleep(2 * (intento + 1))
    except ValueError as e:  # el SDK lo lanza si no hay API key
        raise ExtraccionError("Falta la API key de Gemini (GEMINI_API_KEY en .env).") from e
    except errors.ClientError as e:
        if e.code == 429:
            raise ExtraccionError("Se alcanzó el límite de la capa gratuita; espera un minuto y reintenta.") from e
        if e.code in (400, 401, 403):
            raise ExtraccionError(f"Solicitud o API key rechazada por Gemini: {e.message}") from e
        raise ExtraccionError(f"Error de Gemini ({e.code}): {e.message}") from e
    except errors.ServerError as e:
        raise ExtraccionError("Gemini no está disponible por ahora; reintenta.") from e

    ext = resp.parsed
    if not isinstance(ext, ExtraccionTrabajo):
        raise ExtraccionError("Gemini no devolvió un JSON válido; reintenta o reformula la nota.")
    return ext
