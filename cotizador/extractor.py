"""Extracción con Google Gemini (SDK google-genai) y salida estructurada Pydantic.

Acepta texto, audio o ambos: Gemini entiende el audio directamente, sin paso de
transcripción aparte. Funciona con la capa gratuita de Google AI Studio.
"""
from typing import NamedTuple

from google import genai
from google.genai import errors, types

from .config import CATALOGO_ALARMEC, gemini_model, get_setting
from .schemas import ExtraccionTrabajo

__all__ = ["Audio", "ExtraccionError", "ajustar", "construir_prompt", "extraer"]

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

Catálogo oficial (descripción oficial | formas en que suelen dictarlo | precio unitario):
{catalogo}

Uso del catálogo:
- Si un producto dictado coincide con una entrada, usa su DESCRIPCIÓN OFICIAL exacta (conservando la cantidad dictada).
- Si la nota da un precio, respétalo. Usa el precio del catálogo solo cuando la nota no dice precio y el catálogo lo tiene.
- Si el catálogo no tiene precio para esa entrada ('sin precio'), deja precio_unitario en null.
- Si el ítem NO está en el catálogo, conserva textualmente lo dictado; no fuerces una coincidencia dudosa.
"""


def _texto_catalogo() -> str:
    lineas = []
    for it in CATALOGO_ALARMEC:
        precio = f"{it.precio_unitario:.2f}" if it.precio_unitario is not None else "sin precio"
        lineas.append(f"- {it.descripcion} | {', '.join(it.alias)} | {precio}")
    return "\n".join(lineas)


def construir_prompt() -> str:
    return SYSTEM_PROMPT.format(catalogo=_texto_catalogo())


class ExtraccionError(RuntimeError):
    pass


class Audio(NamedTuple):
    data: bytes
    mime: str = "audio/wav"


def _partes(texto: str, audios: list[Audio] | None) -> list:
    partes: list = [types.Part.from_bytes(data=a.data, mime_type=a.mime) for a in audios or [] if a.data]
    if texto.strip():
        partes.append(texto.strip())
    return partes


def _generar(partes: list, system: str, client: genai.Client | None) -> ExtraccionTrabajo:
    """UNA llamada a Gemini (sin reintentos automáticos: cada reintento gasta cuota gratuita)."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=ExtraccionTrabajo,
        temperature=0,
    )
    try:
        client = client or genai.Client(
            api_key=get_setting("GEMINI_API_KEY"),
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
        )
        resp = client.models.generate_content(model=gemini_model(), contents=partes, config=config)
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


def extraer(
    texto: str = "",
    audios: list[Audio] | None = None,
    client: genai.Client | None = None,
) -> ExtraccionTrabajo:
    partes = _partes(texto, audios)
    if not partes:
        raise ExtraccionError("Escribe un texto o graba una nota de voz.")
    return _generar(partes, construir_prompt(), client)


PROMPT_AJUSTE = """Recibirás la cotización ACTUAL en JSON y una INSTRUCCIÓN DE AJUSTE del usuario (texto y/o voz). Devuelve la cotización COMPLETA actualizada aplicando únicamente lo que pide la instrucción; todo lo demás se mantiene exactamente igual. Si pide agregar un ítem, añádelo al final; si pide quitar o cambiar uno, modifica solo ese. No inventes datos que no se mencionen. Mantén las mayúsculas y las reglas del catálogo de abajo.

"""


def ajustar(
    actual: ExtraccionTrabajo,
    instruccion: str = "",
    audios: list[Audio] | None = None,
    client: genai.Client | None = None,
) -> ExtraccionTrabajo:
    """Aplica una instrucción de ajuste a la cotización actual. Una llamada por pulsación del usuario."""
    if not (instruccion.strip() or any(a.data for a in audios or [])):
        raise ExtraccionError("Escribe o dicta la instrucción de ajuste.")
    partes: list = ["COTIZACIÓN ACTUAL (JSON):", actual.model_dump_json(), "INSTRUCCIÓN DE AJUSTE:"]
    partes += _partes(instruccion, audios)  # audio(s) y/o texto
    return _generar(partes, PROMPT_AJUSTE + construir_prompt(), client)
