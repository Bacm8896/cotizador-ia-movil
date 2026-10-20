"""Cotización en PDF (ReportLab, A4). Solo lista lo cotizado: sin filas vacías de talonario."""
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, HRFlowable, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from xml.sax.saxutils import escape

from .config import EMPRESA, LOGO_PATH
from .renderer import money, qty
from .schemas import Cotizacion

MARGEN = 20 * mm
ROJO = colors.HexColor("#C8102E")       # rojo del logo ALARMEC
GRIS_OSCURO = colors.HexColor("#2B2B2B")
GRIS = colors.HexColor("#6B6B6B")
GRIS_CLARO = colors.HexColor("#F3F3F3")
LINEA = colors.HexColor("#D9D9D9")
ANCHO = A4[0] - 2 * MARGEN
ALTO = A4[1] - 2 * MARGEN
BASE_GAP = 5 * mm
MAX_GAP = 16 * mm


def _s(nombre, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13, textColor=GRIS_OSCURO)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


ST = {
    "txt": _s("txt"),
    "peq": _s("peq", fontSize=8.5, leading=11.5, textColor=GRIS),
    "emp_nombre": _s("emp_nombre", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=ROJO, alignment=TA_RIGHT),
    "emp": _s("emp", fontSize=8.5, leading=11.5, textColor=GRIS, alignment=TA_RIGHT),
    "titulo": _s("titulo", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=GRIS_OSCURO),
    "fecha": _s("fecha", fontSize=9.5, textColor=GRIS, alignment=TA_RIGHT),
    "et": _s("et", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=ROJO),
    "th": _s("th", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white),
    "th_r": _s("th_r", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=TA_RIGHT),
    "th_c": _s("th_c", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=TA_CENTER),
    "td_c": _s("td_c", alignment=TA_CENTER),
    "td_r": _s("td_r", alignment=TA_RIGHT),
    "tot_et": _s("tot_et", textColor=GRIS, alignment=TA_RIGHT),
    "tot_v": _s("tot_v", alignment=TA_RIGHT),
    "total_et": _s("total_et", fontName="Helvetica-Bold", fontSize=11, textColor=colors.white, alignment=TA_RIGHT),
    "total_v": _s("total_v", fontName="Helvetica-Bold", fontSize=12, textColor=colors.white, alignment=TA_RIGHT),
    "firma": _s("firma", alignment=TA_CENTER, leading=13),
    "pie": _s("pie", fontSize=8, textColor=GRIS, alignment=TA_CENTER),
}


def _p(texto: str, estilo: str) -> Paragraph:
    return Paragraph(escape(texto or ""), ST[estilo])


def _usd(v: Decimal) -> str:
    return f"$ {money(v)}"


class _Gap(Spacer):
    """Separador cuya altura se reparte luego para llenar la hoja."""

    def __init__(self, base=BASE_GAP):
        super().__init__(1, base)
        self.base = base


def _cabecera() -> Table:
    logo = ""
    if LOGO_PATH.exists():
        w, h = ImageReader(str(LOGO_PATH)).getSize()
        ancho = 34 * mm
        logo = Image(str(LOGO_PATH), width=ancho, height=ancho * h / w)
    datos = [
        _p(EMPRESA.nombre, "emp_nombre"),
        Paragraph(escape(EMPRESA.giro), ST["emp"]),
        Paragraph(escape(f"{EMPRESA.direccion.title()} · {EMPRESA.ciudad_emision}"), ST["emp"]),
        Paragraph(escape(f"Tel. {EMPRESA.telefono}"), ST["emp"]),
    ]
    t = Table([[logo, datos]], colWidths=[40 * mm, ANCHO - 40 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _titulo(cot: Cotizacion) -> Table:
    t = Table([[_p("COTIZACIÓN", "titulo"), _p(f"{EMPRESA.ciudad_emision}, {cot.fecha.capitalize()}", "fecha")]],
              colWidths=[ANCHO * 0.5, ANCHO * 0.5])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _cliente(cot: Cotizacion) -> Table:
    def campo(etiqueta, valor):
        return [_p(etiqueta, "et"), _p(valor or "—", "txt")]

    filas = [
        [campo("CLIENTE", cot.cliente_nombre), campo("TELÉFONO", cot.cliente_telefono)],
        [campo("DIRECCIÓN", cot.cliente_direccion), campo("CIUDAD", cot.cliente_ciudad)],
    ]
    if cot.cliente_atencion:
        filas.append([campo("ATENCIÓN", cot.cliente_atencion), ""])
    t = Table(filas, colWidths=[ANCHO * 0.58, ANCHO * 0.42])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ROJO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _items(cot: Cotizacion) -> Table:
    w = [18 * mm, ANCHO - 18 * mm - 30 * mm - 32 * mm, 30 * mm, 32 * mm]
    filas = [[_p("CANT.", "th_c"), _p("DESCRIPCIÓN", "th"), _p("P. UNITARIO", "th_r"), _p("TOTAL", "th_r")]]
    if cot.titulo_trabajo:
        filas.append(["", Paragraph(f"<b>{escape(cot.titulo_trabajo)}</b>", ST["txt"]), "", ""])
    for l in cot.lineas:
        filas.append([_p(qty(l.cantidad), "td_c"), _p(l.descripcion, "txt"),
                      _p(_usd(l.precio_unitario), "td_r"), _p(_usd(l.total), "td_r")])
    for o in cot.observaciones:
        filas.append(["", Paragraph(f"<i>{escape(o)}</i>", ST["peq"]), "", ""])

    t = Table(filas, colWidths=w, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), ROJO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINEA),
        ("LINEBELOW", (0, -1), (-1, -1), 1, GRIS),
    ]
    for i in range(2, len(filas), 2):  # cebra sutil
        estilo.append(("BACKGROUND", (0, i), (-1, i), GRIS_CLARO))
    t.setStyle(TableStyle(estilo))
    return t


def _totales(cot: Cotizacion) -> Table:
    filas = [[_p("Subtotal", "tot_et"), _p(_usd(cot.subtotal), "tot_v")]]
    if cot.iva_porcentaje > 0:
        filas.append([_p(f"IVA {qty(cot.iva_porcentaje)}%", "tot_et"), _p(_usd(cot.iva), "tot_v")])
    filas.append([_p("TOTAL", "total_et"), _p(_usd(cot.total), "total_v")])
    t = Table(filas, colWidths=[32 * mm, 38 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, -1), (-1, -1), ROJO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, -1), (-1, -1), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _condiciones(cot: Cotizacion) -> Table | None:
    filas = []
    pago = cot.forma_pago + (f" · Saldo: {cot.saldo}" if cot.saldo else "") if cot.forma_pago else cot.saldo
    for etiqueta, valor in (("FORMA DE PAGO", pago), ("TIEMPO DE ENTREGA", cot.tiempo_entrega), ("GARANTÍA", cot.garantia)):
        if valor:
            filas.append([_p(etiqueta, "et"), _p(valor, "txt")])
    if not filas:
        return None
    t = Table([[_p("CONDICIONES COMERCIALES", "et"), ""], *filas], colWidths=[40 * mm, ANCHO - 40 * mm])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), 0.8, LINEA),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, LINEA),
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _firma() -> Table:
    bloque = [
        HRFlowable(width=62 * mm, thickness=0.8, color=GRIS_OSCURO, spaceBefore=0, spaceAfter=4),
        Paragraph(f"<b>Sr. {escape(EMPRESA.firmante_nombre.title())}</b>", ST["firma"]),
        Paragraph(escape(EMPRESA.cargo.capitalize()), ST["firma"]),
        Paragraph(escape(f"{EMPRESA.nombre} · Tel. {EMPRESA.telefono}"), ST["peq"].clone("f2", alignment=TA_CENTER)),
    ]
    t = Table([["", [Spacer(1, 12 * mm), *bloque]]], colWidths=[ANCHO - 70 * mm, 70 * mm])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _story(cot: Cotizacion) -> list:
    story = [
        _cabecera(),
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=1.2, color=ROJO, spaceAfter=0),
        _Gap(),
        _titulo(cot),
        _Gap(4 * mm),
        _cliente(cot),
        _Gap(),
        _items(cot),
        Spacer(1, 3 * mm),
        _totales(cot),
        _Gap(),
    ]
    # condiciones + firma viajan juntas: si no caben debajo de los totales, pasan completas a la página siguiente
    cond, firma = _condiciones(cot), _firma()
    necesario = firma.wrap(ANCHO, ALTO)[1] + 8 * mm + (cond.wrap(ANCHO, ALTO)[1] if cond is not None else 0)
    story.append(CondPageBreak(necesario + 2 * mm))
    if cond is not None:
        story.append(cond)
    story += [_Gap(8 * mm), firma]
    return story


def _repartir_espacio(story: list) -> None:
    """Estira los separadores para que el contenido ocupe la hoja sin un hueco desproporcionado."""
    gaps = [f for f in story if isinstance(f, _Gap)]
    usado = 0.0
    for f in story:
        _, h = f.wrap(ANCHO, ALTO)
        usado += h
    sobra = ALTO - usado - 10 * mm  # 10 mm de seguridad
    if sobra <= 0 or not gaps:
        return
    extra = min(sobra / sum(g.base for g in gaps), (MAX_GAP / BASE_GAP) - 1)
    for g in gaps:
        g.height = g.base * (1 + extra)


def generar_pdf(cot: Cotizacion) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN, bottomMargin=MARGEN,
        title=f"Cotización {EMPRESA.nombre} - {cot.cliente_nombre}".strip(" -"),
        author=EMPRESA.nombre,
    )
    # marco sin relleno interno: el ancho/alto útil es exactamente ANCHO x ALTO
    marco = Frame(MARGEN, MARGEN, ANCHO, ALTO, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    story = _story(cot)
    _repartir_espacio(story)

    def pie(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"{EMPRESA.nombre} · Tel. {EMPRESA.telefono} · Página {d.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="a4", frames=[marco], onPage=pie)])
    doc.build(story)
    return buf.getvalue()
