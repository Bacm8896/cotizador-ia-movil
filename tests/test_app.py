"""Asistente por pasos con Gemini simulado (unittest.mock): nunca se llama a la API real."""
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from cotizador.schemas import ExtraccionTrabajo

APP = str(Path(__file__).parent.parent / "app.py")


def _datos(precio=5, cliente=True, items=None):
    return {
        "cliente": {"nombre": "ING. PEREZ" if cliente else None, "atencion": None,
                    "telefono": "0987003533" if cliente else None,
                    "direccion": "LA FLORESTA" if cliente else None, "ciudad": None},
        "titulo_trabajo": "CAMARAS",
        "items": items or [{"cantidad": 2, "descripcion": "CAMARA DOMO", "precio_unitario": precio, "total_declarado": None}],
        "observaciones": [], "forma_pago": None, "saldo": None, "tiempo_entrega": None,
        "garantia": None, "notas_tecnicas": None, "total_declarado": None,
    }


def _ext(**kw):
    return ExtraccionTrabajo.model_validate(_datos(**kw))


def _boton(at, texto):
    return next(b for b in at.button if texto in b.label)


def _abrir():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["autenticado"] = True
    return at.run()


def _hasta_paso2(at):
    at.text_area[0].input("dos domos a 5").run()
    _boton(at, "Procesar con IA").click().run()
    return at


def _total(at):
    return [m.value for m in at.metric][-1]


def test_flujo_completo_4_pasos_con_una_sola_llamada_a_gemini():
    with mock.patch("cotizador.extractor.extraer", return_value=_ext()) as ext, \
         mock.patch("cotizador.extractor.ajustar") as aj:
        at = _abrir()
        assert at.session_state["paso"] == 1
        _hasta_paso2(at)
        assert at.session_state["paso"] == 2 and not at.exception
        assert _total(at) == "10.00"

        # editar campos / IVA no llama a Gemini
        at.text_input[0].input("OTRO NOMBRE").run()
        at.sidebar.number_input[0].set_value(15).run()
        assert _total(at) == "11.50"

        _boton(at, "Continuar").click().run()
        assert at.session_state["paso"] == 3 and not at.exception
        assert at.session_state["pdf"][:4] == b"%PDF"

        _boton(at, "más cambios").click().run()          # vuelve al paso 2 conservando lo editado
        assert at.session_state["paso"] == 2
        assert at.text_input[0].value == "OTRO NOMBRE"

        _boton(at, "Continuar").click().run()
        _boton(at, "Aprobar").click().run()
        assert at.session_state["paso"] == 4 and not at.exception
        assert any("Descargar PDF" in str(e) for e in at.get("download_button"))
        assert at.get("link_button")

        _boton(at, "Iniciar nueva").click().run()
        assert at.session_state["paso"] == 1 and at.session_state["borrador"] is None

        assert ext.call_count == 1 and aj.call_count == 0


def test_faltantes_y_precio_cero_bloquean_hasta_completar():
    with mock.patch("cotizador.extractor.extraer", return_value=_ext(precio=None, cliente=False)):
        at = _hasta_paso2(_abrir())
        assert _boton(at, "Continuar").disabled
        texto = " ".join(w.value for w in at.warning)
        assert "Teléfono" in texto and "Dirección" in texto and "Precio del ítem" in texto
        assert any("Completa estos datos" in m.value for m in at.markdown)

        caja = next(n for n in at.number_input if "Precio para: CAMARA DOMO" in n.label)
        caja.set_value(7.5).run()
        assert not _boton(at, "Continuar").disabled and _total(at) == "15.00"


def test_ajuste_con_ia_es_una_llamada_explicita_y_reemplaza_el_borrador():
    nuevo = _ext(items=[
        {"cantidad": 2, "descripcion": "CAMARA DOMO", "precio_unitario": 5, "total_declarado": None},
        {"cantidad": 1, "descripcion": "SIRENA", "precio_unitario": 45, "total_declarado": None},
    ])
    with mock.patch("cotizador.extractor.extraer", return_value=_ext()) as ext, \
         mock.patch("cotizador.extractor.ajustar", return_value=nuevo) as aj:
        at = _hasta_paso2(_abrir())
        at.text_area(key="f_instruccion").input("agrega una sirena a 45").run()
        assert aj.call_count == 0  # escribir no llama
        _boton(at, "Aplicar ajuste").click().run()
        assert aj.call_count == 1 and ext.call_count == 1 and not at.exception
        assert _total(at) == "55.00"
        assert aj.call_args.args[1] == "agrega una sirena a 45"


def test_iva_por_defecto_cero_y_notas_tecnicas_llegan_al_pdf():
    ext = ExtraccionTrabajo.model_validate({**_datos(), "notas_tecnicas": "Requiere internet estable."})
    with mock.patch("cotizador.extractor.extraer", return_value=ext):
        at = _hasta_paso2(_abrir())
        assert at.sidebar.number_input[0].value == 0
        campo = at.text_area(key="f_notas_tecnicas")
        assert campo.value == "Requiere internet estable."      # extraída por la IA
        campo.input("Requiere internet estable.\nCámaras IP66.").run()  # editable
        _boton(at, "Continuar").click().run()
        import fitz
        texto = fitz.open(stream=at.session_state["pdf"], filetype="pdf")[0].get_text()
        assert "NOTAS Y REQUISITOS TÉCNICOS" in texto and "IP66" in texto
        assert "* Precios no incluyen IVA" in texto
