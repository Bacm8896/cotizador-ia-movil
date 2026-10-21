"""Cotización en PDF (ReportLab, A4) con la estructura de la cotización de referencia.

Cabecera (logo izquierda, datos a la derecha) · título y datos del cliente · tabla de ítems ·
subtotal / IVA · notas técnicas · bloque de cierre. Solo lista lo cotizado: sin filas vacías.
"""
import io
from decimal import Decimal
from functools import lru_cache
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from .config import EMPRESA, ruta_logo
from .renderer import money, qty
from .schemas import Cotizacion

MARGEN = 20 * mm
ROJO = colors.HexColor("#B71C1C")        # rojo institucional
TEXTO = colors.HexColor("#333333")
GRIS = colors.HexColor("#666666")
TENUE = colors.HexColor("#EBF3FB")       # fondo de las notas técnicas
BORDE = colors.HexColor("#4A4A4A")
ANCHO = A4[0] - 2 * MARGEN
ALTO = A4[1] - 2 * MARGEN
LOGO_MAX_W = 46 * mm   # el logo se ajusta dentro de esta caja sin deformarse
LOGO_MAX_H = 29 * mm
LOGO_MAX_PX = 800      # resolución controlada: se reduce si el archivo es muy grande
BASE_GAP = 5 * mm
MAX_GAP = 14 * mm


def _s(nombre, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13, textColor=TEXTO)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


ST = {
    "txt": _s("txt"),
    "peq": _s("peq", fontSize=8.5, leading=11.5, textColor=GRIS),
    "marca": _s("marca", fontName="Helvetica-Bold", fontSize=25, leading=28, textColor=ROJO, alignment=TA_RIGHT),
    "eslogan": _s("eslogan", fontName="Helvetica-Bold", fontSize=11.5, leading=15, alignment=TA_RIGHT),
    "datos": _s("datos", fontSize=8.5, leading=11.5, textColor=GRIS, alignment=TA_RIGHT),
    "titulo": _s("titulo", fontName="Helvetica-Bold", fontSize=14, leading=17, alignment=TA_RIGHT),
    "fecha": _s("fecha", fontSize=10, alignment=TA_RIGHT),
    "txt_r": _s("txt_r", alignment=TA_RIGHT),
    "th": _s("th", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.white, alignment=TA_CENTER),
    "td_c": _s("td_c", alignment=TA_CENTER),
    "td_r": _s("td_r", alignment=TA_RIGHT),
    "sub_et": _s("sub_et", fontName="Helvetica-Bold", alignment=TA_RIGHT),
    "sub_v": _s("sub_v", fontName="Helvetica-Bold", alignment=TA_RIGHT),
    "tot_et": _s("tot_et", fontName="Helvetica-Bold", fontSize=11, textColor=ROJO, alignment=TA_RIGHT),
    "tot_v": _s("tot_v", fontName="Helvetica-Bold", fontSize=11, textColor=ROJO, alignment=TA_RIGHT),
    "iva_nota": _s("iva_nota", fontName="Helvetica-Oblique", fontSize=8.5, textColor=GRIS, alignment=TA_RIGHT),
    "nota_ti": _s("nota_ti", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    "nota": _s("nota", leftIndent=10, bulletIndent=0, leading=13),
    "cierre_ti": _s("cierre_ti", fontName="Helvetica-Bold", fontSize=10.5, leading=14),
    "firma": _s("firma", leading=13),
    "firma_b": _s("firma_b", fontName="Helvetica-Bold", leading=13),
}


def _p(texto: str, estilo: str) -> Paragraph:
    return Paragraph(escape(texto or ""), ST[estilo])


def _usd(v: Decimal) -> str:
    return f"$ {money(v)}"


def _fecha_texto(fecha: str) -> str:
    """'19 DE OCTUBRE DEL 2026' -> '19 de Octubre del 2026'."""
    t = fecha.lower().split()
    if len(t) == 5:  # día de mes del año
        t[2] = t[2].capitalize()
    return " ".join(t)


class _Gap(Spacer):
    """Separador cuya altura se reparte luego para llenar la hoja."""

    def __init__(self, base=BASE_GAP):
        super().__init__(1, base)
        self.base = base


# ------------------------------------------------------------------ logo
@lru_cache(maxsize=4)
def _logo_png(ruta: str, mtime_ns: int) -> tuple[bytes, int, int]:
    """Logo reducido (si hace falta) y recodificado a PNG; la clave incluye mtime para detectar reemplazos."""
    img = PILImage.open(ruta)
    img.load()
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA")
    img.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX), PILImage.LANCZOS)
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


# ------------------------------------------------------------------ secciones
def _cabecera() -> list:
    """Logo a la izquierda; a la derecha marca, eslogan, especialidades, dirección y teléfono. Filete rojo debajo."""
    contacto = f"Tel: {EMPRESA.telefono}" + (f" | {EMPRESA.correo}" if EMPRESA.correo else "")
    derecha = [
        _p(EMPRESA.nombre, "marca"),
        _p(EMPRESA.eslogan, "eslogan"),
        _p(EMPRESA.especialidades, "datos"),
        _p(f"Dirección: {EMPRESA.direccion_pdf} | {EMPRESA.ciudad_emision}, Ecuador", "datos"),
        _p(contacto, "datos"),
    ]
    logo = _logo()
    ancho_logo = (logo.drawWidth + 6 * mm) if logo is not None else 0
    t = Table([[logo or "", derecha]], colWidths=[ancho_logo, ANCHO - ancho_logo])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [t, Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=1.75, color=ROJO, spaceBefore=0, spaceAfter=0)]


def _datos_documento(cot: Cotizacion) -> Table:
    """Dos columnas compactas. Izquierda: cliente, dirección y ciudad. Derecha (alineada a la derecha):
    Nº de cotización y fecha arriba, y el teléfono a la altura de la ciudad."""
    def campo(etiqueta, valor, estilo="txt"):
        return Paragraph(f"<b>{etiqueta}:</b> {escape(valor or '—')}", ST[estilo])

    izquierda = [campo("CLIENTE", cot.cliente_nombre)]
    if cot.cliente_atencion:
        izquierda.append(campo("ATENCIÓN", cot.cliente_atencion))
    izquierda += [campo("DIRECCIÓN", cot.cliente_direccion), campo("CIUDAD", cot.cliente_ciudad)]
    titulo = "COTIZACIÓN Nº: " + cot.numero if cot.numero else "COTIZACIÓN"
    derecha = [_p(titulo, "titulo"), _p(f"{EMPRESA.ciudad_emision}, {_fecha_texto(cot.fecha)}", "fecha")]
    derecha += [""] * (len(izquierda) - 3) + [campo("TELÉFONO", cot.cliente_telefono, "txt_r")]
    t = Table([[a, b] for a, b in zip(izquierda, derecha)], colWidths=[ANCHO * 0.58, ANCHO * 0.42])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return t


def _items(cot: Cotizacion) -> Table:
    w = [18 * mm, ANCHO - 18 * mm - 30 * mm - 32 * mm, 30 * mm, 32 * mm]
    filas = [[_p(h, "th") for h in ("CANT.", "DESCRIPCIÓN", "PRECIO UNIT.", "PRECIO TOTAL")]]
    spans = []
    if cot.titulo_trabajo:
        filas.append(["", Paragraph(f"<b>{escape(cot.titulo_trabajo)}</b>", ST["txt"]), "", ""])
        spans.append(len(filas) - 1)
    for l in cot.lineas:
        filas.append([_p(qty(l.cantidad), "td_c"), _p(l.descripcion, "txt"),
                      _p(_usd(l.precio_unitario), "td_r"), _p(_usd(l.total), "td_r")])
    for o in cot.observaciones:
        filas.append(["", Paragraph(f"<i>{escape(o)}</i>", ST["peq"]), "", ""])
        spans.append(len(filas) - 1)

    t = Table(filas, colWidths=w, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), ROJO),
        ("GRID", (0, 0), (-1, -1), 0.6, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for r in spans:  # título del trabajo y observaciones ocupan descripción + precios
        estilo.append(("SPAN", (1, r), (3, r)))
    t.setStyle(TableStyle(estilo))
    return t


def _liquidacion(cot: Cotizacion) -> Table:
    """SUBTOTAL (y nota de IVA) alineados a la derecha; con IVA > 0 se desglosa Subtotal, IVA y Total."""
    if cot.iva_porcentaje > 0:
        filas = [
            [_p("SUBTOTAL:", "sub_et"), _p(_usd(cot.subtotal), "sub_v")],
            [_p(f"IVA {qty(cot.iva_porcentaje)}%:", "sub_et"), _p(_usd(cot.iva), "sub_v")],
            [_p("TOTAL:", "tot_et"), _p(_usd(cot.total), "tot_v")],
        ]
    else:
        filas = [
            [_p("SUBTOTAL:", "sub_et"), _p(_usd(cot.subtotal), "sub_v")],
            [_p("* Precios no incluyen IVA", "iva_nota"), ""],
        ]
    t = Table(filas, colWidths=[ANCHO - 32 * mm, 32 * mm], hAlign="RIGHT")
    estilo = [
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if cot.iva_porcentaje > 0:
        estilo.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, BORDE))
    else:
        estilo.append(("SPAN", (0, 1), (1, 1)))
    t.setStyle(TableStyle(estilo))
    return t


def _notas_tecnicas(cot: Cotizacion) -> Table | None:
    lineas = [l.strip() for l in cot.notas_tecnicas.splitlines() if l.strip()]
    if not lineas:
        return None  # sin notas: no se deja ningún hueco
    contenido = [_p("NOTAS Y REQUISITOS TÉCNICOS", "nota_ti"), Spacer(1, 2)]
    contenido += [Paragraph(escape(l), ST["nota"], bulletText="•") for l in lineas]
    t = Table([[contenido]], colWidths=[ANCHO])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TENUE),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _cierre(cot: Cotizacion) -> KeepTogether:
    """Condiciones comerciales + ATENTAMENTE + firma, siempre juntos (nunca una firma huérfana)."""
    flow: list = []
    pago = cot.forma_pago + (f" | Saldo {cot.saldo.lower()}" if cot.saldo else "") if cot.forma_pago else cot.saldo
    condiciones = [(et, v) for et, v in (("FORMA DE PAGO", pago), ("TIEMPO DE ENTREGA", cot.tiempo_entrega),
                                         ("GARANTÍA", cot.garantia)) if v]
    if condiciones:
        flow.append(_p("CONDICIONES COMERCIALES", "cierre_ti"))
        flow.append(Spacer(1, 2))
        flow += [Paragraph(f"<b>{et}:</b> {escape(v)}", ST["txt"]) for et, v in condiciones]
        flow.append(Spacer(1, 6 * mm))
    flow += [
        _p("ATENTAMENTE,", "firma_b"),
        Spacer(1, 11 * mm),
        HRFlowable(width=55 * mm, thickness=0.8, color=TEXTO, hAlign="LEFT", spaceBefore=0, spaceAfter=3),
        _p(f"Sr. {EMPRESA.firmante_nombre.title()}", "firma"),
        _p(EMPRESA.cargo, "firma_b"),
    ]
    return KeepTogether(flow)


# ------------------------------------------------------------------ ensamblado
def _story(cot: Cotizacion) -> list:
    story = [
        *_cabecera(),
        _Gap(5 * mm),
        _datos_documento(cot),
        _Gap(),
        _items(cot),
        Spacer(1, 2 * mm),
        _liquidacion(cot),
    ]
    notas = _notas_tecnicas(cot)
    if notas is not None:
        story += [_Gap(), notas]
    story += [_Gap(7 * mm), _cierre(cot)]
    return story


def _alto(f) -> float:
    if isinstance(f, KeepTogether):  # su wrap exige canvas: se suma el alto de su contenido
        return sum(_alto(c) for c in f._content)
    return f.wrap(ANCHO, ALTO)[1]


def _repartir_espacio(story: list) -> None:
    """Estira los separadores para que el contenido ocupe la hoja sin un hueco desproporcionado."""
    gaps = [f for f in story if isinstance(f, _Gap)]
    sobra = ALTO - sum(_alto(f) for f in story) - 10 * mm  # 10 mm de seguridad
    if sobra <= 0 or not gaps:
        return
    extra = min(sobra / sum(g.base for g in gaps), (MAX_GAP / BASE_GAP) - 1)
    for g in gaps:
        g.height = g.base * (1 + extra)


def generar_pdf(cot: Cotizacion) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN, bottomMargin=MARGEN,
        title=f"Cotización {cot.numero} {EMPRESA.nombre} - {cot.cliente_nombre}".replace("  ", " ").strip(" -"),
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
