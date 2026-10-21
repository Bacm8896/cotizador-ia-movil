"""
Cotizador ALARMEC - Sistema automatizado de cotizaciones comerciales
Desarrollado por: Byron Carvajal (https://www.linkedin.com/in/byroncarvajalia)
Versión: 1.0 (Beta)

Número correlativo de cotización (AÑO-NÚMERO) guardado en data/secuencia.json.

En Streamlit Cloud el disco es temporal: la secuencia se reinicia si la app se redespliega.
Por eso el número es siempre editable en el paso 2.
"""
import json
import re

from .config import BASE_DIR

ARCHIVO = BASE_DIR / "data" / "secuencia.json"
PATRON = re.compile(r"(\d{4})-(\d+)")


def _leer() -> dict:
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def siguiente(anio: int) -> str:
    """Sugerencia: el siguiente número del año (no se consume hasta registrar)."""
    return f"{anio}-{int(_leer().get(str(anio), 0)) + 1:04d}"


def registrar(numero: str) -> None:
    """Marca un número como usado para que la próxima sugerencia sea la siguiente."""
    m = PATRON.fullmatch((numero or "").strip())
    if not m:
        return
    anio, n = m.group(1), int(m.group(2))
    datos = _leer()
    if n > int(datos.get(anio, 0)):
        datos[anio] = n
        try:
            ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
            ARCHIVO.write_text(json.dumps(datos), encoding="utf-8")
        except OSError:
            pass  # disco de solo lectura: se sigue sin persistir
