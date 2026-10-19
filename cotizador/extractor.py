"""Extracción con Claude + Structured Outputs (JSON validado por Pydantic)."""
import anthropic

from .config import ANTHROPIC_MODEL
from .schemas import ExtraccionTrabajo

SYSTEM_PROMPT = """\
Eres el asistente de cotizaciones de una empresa de seguridad electrónica en Quito, Ecuador \
(alarmas, CCTV, cercas eléctricas, porteros, motores de garaje, domótica).

Recibirás una nota (texto escrito o transcripción de voz) con los datos de un trabajo. \
Extrae el cliente, los ítems con sus cantidades y precios, y las condiciones comerciales.

Reglas:
- Extrae solo lo que la nota dice. Si un dato no aparece, devuelve null (o lista vacía); nunca lo inventes.
- NO calcules totales ni subtotales: solo copia 'total_declarado' si la nota lo menciona literalmente.
- Escribe descripciones, título y observaciones en MAYÚSCULAS, como en las cotizaciones de la empresa.
- Incluye la unidad en la descripción del ítem ('METROS TENDIDO CERCA ELECTRICA', 'CAMARAS DOMO 2MP').
- Si la nota dice 'material y mano de obra incluidos' (o similar), ponlo en observaciones.
- Las transcripciones de voz pueden tener errores; interpreta cifras habladas ('veintinueve' = 29, 'ocho dólares' = 8).
"""


class ExtraccionError(RuntimeError):
    pass


def extraer(texto: str, client: anthropic.Anthropic | None = None) -> ExtraccionTrabajo:
    client = client or anthropic.Anthropic()
    try:
        resp = client.messages.parse(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto}],
            output_format=ExtraccionTrabajo,
        )
    except anthropic.AuthenticationError as e:
        raise ExtraccionError("API key de Anthropic inválida o ausente (ANTHROPIC_API_KEY).") from e
    except anthropic.RateLimitError as e:
        raise ExtraccionError("Límite de uso alcanzado; reintenta en unos segundos.") from e
    except anthropic.APIConnectionError as e:
        raise ExtraccionError("No se pudo conectar con la API de Anthropic.") from e
    except anthropic.APIStatusError as e:
        raise ExtraccionError(f"Error de la API ({e.status_code}): {e.message}") from e

    if resp.stop_reason == "refusal":
        raise ExtraccionError("El modelo rechazó la solicitud.")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise ExtraccionError("La respuesta quedó incompleta; acorta la nota o reintenta.")
    return resp.parsed_output
