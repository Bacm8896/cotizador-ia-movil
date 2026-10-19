"""Flujo de la app con el extractor simulado (sin red)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import cotizador.extractor as ex
from cotizador.schemas import ExtraccionTrabajo

APP = str(Path(__file__).parent.parent / "app.py")


def _extraccion(precio, cliente=True):
    return {
        "cliente": {"nombre": "ING. PEREZ" if cliente else None, "atencion": None,
                    "telefono": "0999" if cliente else None,
                    "direccion": "LA FLORESTA" if cliente else None, "ciudad": None},
        "titulo_trabajo": None,
        "items": [{"cantidad": 2, "descripcion": "CAMARA DOMO", "precio_unitario": precio, "total_declarado": None}],
        "observaciones": [], "forma_pago": None, "saldo": None, "tiempo_entrega": None,
        "garantia": None, "total_declarado": None,
    }


def _app(monkeypatch, datos):
    llamadas = []

    def falso(texto="", audios=None, client=None):
        llamadas.append(texto)
        return ExtraccionTrabajo.model_validate(datos)

    monkeypatch.setattr(ex, "extraer", falso)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["autenticado"] = True
    at.run()
    at.text_area[0].input("dos domos").run()
    next(b for b in at.button if "Extraer" in b.label).click().run()
    return at, llamadas


def _total(at):
    return [m.value for m in at.metric][-1]


def test_con_precio_pasa_directo_y_gemini_se_llama_una_vez(monkeypatch):
    at, llamadas = _app(monkeypatch, _extraccion(5))
    assert not at.exception and _total(at) == "10.00"
    assert at.session_state["extraccion_completada"] is not None
    # interactuar (editar campos, IVA) no vuelve a llamar a Gemini
    at.text_input[1].input("Otro nombre").run()
    at.sidebar.number_input[0].set_value(15).run()
    assert len(llamadas) == 1 and not at.exception


def test_sin_precio_pide_casilla_y_recalcula_sin_gemini(monkeypatch):
    at, llamadas = _app(monkeypatch, _extraccion(None, cliente=False))
    assert not at.metric  # cotización bloqueada
    ni = [n for n in at.number_input if "Precio para: CAMARA DOMO" in n.label]
    assert ni, "debe haber casilla de precio para el ítem"
    assert any("Completa estos datos" in m.value for m in at.markdown)
    assert any("nombre del cliente" in m.value for m in at.markdown)

    ni[0].set_value(7.5).run()
    assert not at.exception and _total(at) == "15.00"
    assert len(llamadas) == 1
