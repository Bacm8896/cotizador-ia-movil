"""Cotización en PDF (ReportLab, A4). Solo lista lo cotizado: sin filas vacías de talonario."""
import io
from decimal import Decimal
from functools import lru_cache

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from PIL import Image as PILImage
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, HRFlowable, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from xml.sax.saxutils import escape

from .config import EMPRESA, ruta_logo
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
AZUL_TENUE = colors.HexColor("#EEF3F8")
LOGO_MAX_W = 40 * mm   # el logo se ajusta dentro de esta caja sin deformarse
LOGO_MAX_H = 13 * mm
LOGO_MAX_PX = 700      # resolución controlada: se reduce si el archivo es muy grande
BASE_GAP = 5 * mm
MAX_GAP = 16 * mm


def _s(nombre, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13, textColor=GRIS_OSCURO)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


ST = {
    "txt": _s("txt"),
    "peq": _s("peq", fontSize=8.5, leading=11.5, textColor=GRIS),
    "emp_nombre": _s("emp_nombre", fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=GRIS_OSCURO, charSpace=2.5),
    "emp_giro": _s("emp_giro", fontSize=8.5, leading=11.5, textColor=GRIS),
    "barra": _s("barra", fontSize=8.5, leading=11, textColor=GRIS_OSCURO),
    "nota_ti": _s("nota_ti", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=ROJO),
    "nota": _s("nota", fontSize=9, leading=12.5, leftIndent=9, bulletIndent=0),
    "iva_nota": _s("iva_nota", fontName="Helvetica-Oblique", fontSize=8.5, textColor=GRIS, alignment=TA_RIGHT),
    "titulo": _s("titulo", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=GRIS_OSCURO),
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


@lru_cache(maxsize=4)
def _logo_png(ruta: str, mtime_ns: int) -> tuple[bytes, int, int]:
    """Logo reducido (si hace falta) y recodificado a PNG; la clave incluye mtime para detectar reemplazos."""
    img = PILImage.open(ruta)
    img.load()
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA")
    img.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue(), img.width, img.height


def _logo() -> Image | None:
    ruta = ruta_logo()
    if ruta is None:
        return None
    try:
        datos, w, h = _logo_png(str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        return None
    escala = min(LOGO_MAX_W / w, LOGO_MAX_H / h)  # conserva la proporción, sea cual sea el archivo
    return Image(io.BytesIO(datos), width=w * escala, height=h * escala, hAlign="LEFT", mask="auto")


def _cabecera() -> list:
    """Logo arriba; debajo ALARMEC y los servicios; debajo una barra con dirección, teléfono y correo."""
    bloques: list = []
    logo = _logo()
    if logo is not None:
        bloques += [logo, Spacer(1, 2 * mm)]
    bloques += [_p(EMPRESA.nombre, "emp_nombre"), Paragraph(escape(EMPRESA.giro), ST["emp_giro"]), Spacer(1, 2.5 * mm)]

    celdas = [
        Paragraph(f"<font color='#C8102E'><b>DIRECCIÓN</b></font>&nbsp; {escape(EMPRESA.direccion.title())} · {escape(EMPRESA.ciudad_emision)}", ST["barra"]),
        Paragraph(f"<font color='#C8102E'><b>TELÉFONO</b></font>&nbsp; {escape(EMPRESA.telefono)}", ST["barra"]),
    ]
    anchos = [ANCHO * 0.58, ANCHO * 0.42]
    if EMPRESA.correo:
        celdas.append(Paragraph(f"<font color='#C8102E'><b>CORREO</b></font>&nbsp; {escape(EMPRESA.correo)}", ST["barra"]))
        anchos = [ANCHO * 0.42, ANCHO * 0.24, ANCHO * 0.34]
    barra = Table([celdas], colWidths=anchos)
    barra.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, ROJO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return bloques + [barra]


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
        return Paragraph(f"<font color='#C8102E' size='7.5'><b>{etiqueta}</b></font>&nbsp;&nbsp;{escape(valor or '—')}", ST["txt"])

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
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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


def _notas_tecnicas(cot: Cotizacion) -> Table | None:
    lineas = [l.strip() for l in cot.notas_tecnicas.splitlines() if l.strip()]
    if not lineas:
        return None  # sin notas: no se deja ningún hueco
    contenido = [_p("NOTAS Y REQUISITOS TÉCNICOS", "nota_ti"), Spacer(1, 2)]
    contenido += [Paragraph(escape(l), ST["nota"], bulletText="•") for l in lineas]
    t = Table([[contenido]], colWidths=[ANCHO])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_TENUE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, GRIS),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _condiciones(cot: Cotizacion, ancho: float) -> Table | None:
    filas = []
    pago = cot.forma_pago + (f" · Saldo: {cot.saldo}" if cot.saldo else "") if cot.forma_pago else cot.saldo
    for etiqueta, valor in (("FORMA DE PAGO", pago), ("TIEMPO DE ENTREGA", cot.tiempo_entrega), ("GARANTÍA", cot.garantia)):
        if valor:
            filas.append([_p(etiqueta, "et"), _p(valor, "txt")])
    if not filas:
        return None
    t = Table([[_p("CONDICIONES COMERCIALES", "et"), ""], *filas], colWidths=[36 * mm, ancho - 36 * mm])
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


def _firma(ancho: float) -> Table:
    bloque = [
        HRFlowable(width=ancho * 0.85, thickness=0.8, color=GRIS_OSCURO, spaceBefore=0, spaceAfter=4),
        Paragraph(f"<b>Sr. {escape(EMPRESA.firmante_nombre.title())}</b>", ST["firma"]),
        Paragraph(escape(EMPRESA.cargo.capitalize()), ST["firma"]),
        Paragraph(escape(f"{EMPRESA.nombre} · Tel. {EMPRESA.telefono}"), ST["peq"].clone("f2", alignment=TA_CENTER)),
    ]
    t = Table([["", [Spacer(1, 9 * mm), *bloque]]], colWidths=[0, ancho])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _pie(cot: Cotizacion) -> Table:
    """Condiciones comerciales (izquierda) y firma (derecha) en una sola franja: ahorra alto de hoja."""
    ancho_c = ANCHO * 0.64
    ancho_f = ANCHO - ancho_c - 6 * mm
    cond = _condiciones(cot, ancho_c)
    t = Table([[cond or "", "", _firma(ancho_f)]], colWidths=[ancho_c, 6 * mm, ancho_f])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _story(cot: Cotizacion) -> list:
    story = [
        *_cabecera(),
        _Gap(3 * mm),
        _titulo(cot),
        _Gap(3.5 * mm),
        _cliente(cot),
        _Gap(),
        _items(cot),
        Spacer(1, 3 * mm),
        _totales(cot),
    ]
    if cot.iva_porcentaje <= 0:
        story += [Spacer(1, 1.5 * mm), _p("* Precios no incluyen IVA", "iva_nota")]
    notas = _notas_tecnicas(cot)
    if notas is not None:
        story += [_Gap(4 * mm), notas]
    story.append(_Gap())
    pie = _pie(cot)  # si no cabe debajo, pasa completo a la página siguiente
    story += [CondPageBreak(pie.wrap(ANCHO, ALTO)[1] + 2 * mm), pie]
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
