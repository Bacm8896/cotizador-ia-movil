from decimal import Decimal as D

import fitz
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from cotizador.pdf import generar_pdf
from cotizador.schemas import Cotizacion, Linea

BASE = dict(
    fecha="06 DE ABRIL DEL 2023", cliente_nombre="ARQ. MAURICIO PAZMIÑO", cliente_telefono="0983885380",
    cliente_direccion="LA FLORESTA", cliente_ciudad="QUITO-ECUADOR", titulo_trabajo="CERCA ELECTRICA",
    observaciones=["MATERIAL Y MANO DE OBRA INCLUIDOS"], forma_pago="50% A LA FIRMA DEL CONTRATO",
    saldo="CONTRAENTREGA", tiempo_entrega="DE 2 A 4 DIAS LABORABLES", garantia="UN AÑO EN EQUIPO E INSTALACIÓN",
)


def _cot(n_items=1, iva=False):
    lineas = [Linea(cantidad=D(i + 1), descripcion=f"ITEM {i + 1} DE PRUEBA", precio_unitario=D("8.00"),
                    total=D(i + 1) * D("8.00")) for i in range(n_items)]
    sub = sum(l.total for l in lineas)
    imp = (sub * D("0.15")).quantize(D("0.01")) if iva else D("0")
    return Cotizacion(**BASE, lineas=lineas, subtotal=sub, iva_porcentaje=D(15) if iva else D(0), iva=imp, total=sub + imp)


def _paginas(pdf: bytes):
    return fitz.open(stream=pdf, filetype="pdf")


def test_pdf_valido_una_pagina_con_los_datos():
    pdf = generar_pdf(_cot(1))
    assert pdf[:4] == b"%PDF"
    doc = _paginas(pdf)
    assert len(doc) == 1
    texto = doc[0].get_text()
    for esperado in ("COTIZACIÓN", "ARQ. MAURICIO PAZMIÑO", "ITEM 1 DE PRUEBA", "$ 8,00", "TOTAL",
                     "CONDICIONES COMERCIALES", "Sr. Luis Carvajal V.", "Asesor en seguridad"):
        assert esperado in texto, esperado
    assert "IVA" not in texto


def test_pdf_con_iva():
    assert "IVA 15%" in _paginas(generar_pdf(_cot(3, iva=True)))[0].get_text()


def test_sin_filas_vacias_el_alto_depende_de_los_items():
    # 1 y 8 ítems caben en una hoja; la tabla solo tiene filas de ítems (sin relleno tipo talonario)
    for n in (1, 8):
        assert len(_paginas(generar_pdf(_cot(n)))) == 1


def test_muchos_items_paginan_y_repiten_encabezado():
    doc = _paginas(generar_pdf(_cot(45)))
    assert len(doc) >= 2
    assert "DESCRIPCIÓN" in doc[0].get_text() and "DESCRIPCIÓN" in doc[1].get_text()
    assert "Sr. Luis Carvajal" in doc[-1].get_text() and "CONDICIONES COMERCIALES" in doc[-1].get_text()


def test_condiciones_y_firma_no_se_separan():
    for n in range(1, 16):
        paginas = [p.get_text() for p in _paginas(generar_pdf(_cot(n, iva=True)))]
        donde = [("CONDICIONES COMERCIALES" in t, "Sr. Luis Carvajal" in t) for t in paginas]
        assert sum(c for c, _ in donde) == 1 and any(c and f for c, f in donde), n


@pytest.mark.parametrize("n", [1, 8, 45])
def test_margenes_minimos_de_20mm(n):
    margen = 20 * mm - 3  # tolerancia de 1 mm por el ascendente de la tipografía
    for p in _paginas(generar_pdf(_cot(n))):
        for x0, y0, x1, y1, txt, *_ in p.get_text("blocks"):
            if y0 > A4[1] - 20 * mm:  # pie de página (número de página), fuera del marco a propósito
                continue
            assert x0 >= margen and x1 <= A4[0] - margen, txt
            assert y0 >= margen, txt
        for img in p.get_image_info():
            x0, y0, x1, y1 = img["bbox"]
            assert x0 >= margen and y0 >= margen and x1 <= A4[0] - margen
