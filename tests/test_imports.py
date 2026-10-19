"""Importa lo que app.py necesita en un proceso limpio (detecta ImportError y ciclos)."""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_imports_de_app_en_proceso_limpio():
    codigo = (
        "from cotizador.extractor import Audio, ExtraccionError, extraer\n"
        "from cotizador.config import DEFECTOS, get_setting\n"
        "from cotizador.builder import construir\n"
        "from cotizador.renderer import render_html\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
