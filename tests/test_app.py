"""Flujo de la app con el extractor simulado (sin red)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import cotizador.extractor as ex
from cotizador.schemas import ExtraccionTrabajo

BASE = {
    "cliente": {"nombre": "A", "atencion": None, "telefono": None, "direccion": None, "ciudad": None},
    "titulo_trabajo": None,
    "items": [{"cantidad": 2, "descripcion": "CAMARA DOMO", "precio_unitario": 5, "total_declarado": None}],
    "observaciones": [], "forma_pago": None, "saldo": None, "tiempo_entrega": None,
    "garantia": None, "total_declarado": None,
}


def _app(monkeypatch, respuestas):
    llamadas = []

    def falso(texto="", audios=None, client=None):
        llamadas.append((texto, audios))
        return ExtraccionTrabajo.model_validate({**BASE, **respuestas[len(llamadas) - 1]})

    monkeypatch.setattr(ex, "extraer", falso)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30)
    at.session_state["autenticado"] = True
    at.run()
    return at, llamadas


def _boton(at, texto):
    return next(b for b in at.button if texto in b.label)


def test_sin_preguntas_pasa_directo_a_revision(monkeypatch):
    at, _ = _app(monkeypatch, [{}])
    at.text_area[0].input("dos domos a 5").run()
    _boton(at, "Extraer").click().run()
    assert not at.exception and not at.info[1:]  # solo el aviso inicial, sin preguntas
    assert [m.value for m in at.metric][-1] == "10.00"


def test_preguntas_y_respuesta_reextraen_con_contexto(monkeypatch):
    at, llamadas = _app(monkeypatch, [{"preguntas_clarificacion": ["¿Cuál es el cliente?"]}, {}])
    at.text_area[0].input("dos domos a 5").run()
    _boton(at, "Extraer").click().run()
    assert any("La IA necesita confirmar" in i.value for i in at.info)

    at.text_area[1].input("Es para el Ing. Pérez").run()
    _boton(at, "Responder y actualizar").click().run()
    assert not at.exception
    texto = llamadas[1][0]
    assert "dos domos a 5" in texto and "ACLARACIÓN DEL USUARIO: Es para el Ing. Pérez" in texto
    assert not any("La IA necesita confirmar" in i.value for i in at.info)
