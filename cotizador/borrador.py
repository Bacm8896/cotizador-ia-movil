"""Borrador editable de la cotización (estado del asistente por pasos). Python puro, sin Streamlit."""
import math
from datetime import date

from .builder import construir
from .calculator import EntradaLinea, Resultado, calcular
from .config import DEFECTOS
from .schemas import Cliente, Cotizacion, ExtraccionTrabajo, ItemExtraido

CAMPOS_TEXTO = (
    "nombre", "atencion", "telefono", "direccion", "ciudad", "titulo",
    "forma_pago", "saldo", "tiempo_entrega", "garantia", "observaciones", "notas_tecnicas",
)
CONDICIONES = {  # campo -> (nombre legible, valor por defecto)
    "forma_pago": ("forma de pago", DEFECTOS.forma_pago),
    "saldo": ("saldo", DEFECTOS.saldo),
    "tiempo_entrega": ("tiempo de entrega", DEFECTOS.tiempo_entrega),
    "garantia": ("garantía", DEFECTOS.garantia),
}


def num(v) -> float | None:
    """NaN/None/'' -> None; cualquier número -> float."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def limpiar_items(items: list[dict]) -> list[dict]:
    """Normaliza filas del editor: sin NaN y sin filas totalmente vacías."""
    out = []
    for it in items:
        fila = {
            "cantidad": num(it.get("cantidad")),
            "descripcion": str(it.get("descripcion") or "").strip(),
            "precio_unitario": num(it.get("precio_unitario")),
            "total_declarado": num(it.get("total_declarado")),
        }
        if fila["descripcion"] or fila["cantidad"] is not None or fila["precio_unitario"] is not None:
            out.append(fila)
    return out


def desde_extraccion(ext: ExtraccionTrabajo) -> dict:
    c = ext.cliente
    b = {
        "nombre": c.nombre or "", "atencion": c.atencion or "", "telefono": c.telefono or "",
        "direccion": c.direccion or "", "ciudad": c.ciudad or DEFECTOS.ciudad_cliente,
        "titulo": ext.titulo_trabajo or "",
        "observaciones": "\n".join(ext.observaciones),
        "notas_tecnicas": (ext.notas_tecnicas or "").strip(),
        "items": limpiar_items([i.model_dump() for i in ext.items]),
        "total_declarado": ext.total_declarado,
        "usados_defecto": [],
    }
    for campo, (nombre, defecto) in CONDICIONES.items():
        valor = getattr(ext, campo)
        b[campo] = valor or defecto
        if not valor:
            b["usados_defecto"].append(nombre)
    return b


def a_extraccion(b: dict, con_items: bool = True) -> ExtraccionTrabajo:
    items = []
    if con_items:
        items = [
            ItemExtraido(**i)
            for i in limpiar_items(b["items"]) if i["cantidad"] is not None and i["descripcion"]
        ]
    return ExtraccionTrabajo(
        cliente=Cliente(nombre=b["nombre"], atencion=b["atencion"], telefono=b["telefono"],
                        direccion=b["direccion"], ciudad=b["ciudad"]),
        titulo_trabajo=b["titulo"] or None,
        items=items,
        observaciones=[o.strip() for o in b["observaciones"].splitlines() if o.strip()],
        forma_pago=b["forma_pago"] or None, saldo=b["saldo"] or None,
        tiempo_entrega=b["tiempo_entrega"] or None, garantia=b["garantia"] or None,
        notas_tecnicas=b["notas_tecnicas"].strip() or None,
        total_declarado=b.get("total_declarado"),
    )


def indices_sin_precio(items: list[dict]) -> list[int]:
    return [n for n, i in enumerate(items) if not i["precio_unitario"] or i["precio_unitario"] <= 0]


def faltantes(b: dict) -> list[str]:
    """Datos que suelen faltar, en lenguaje claro, para el cuadro de advertencia."""
    out = []
    if not b["nombre"].strip():
        out.append("Nombre del cliente")
    if not b["telefono"].strip():
        out.append("Teléfono del cliente")
    if not b["direccion"].strip():
        out.append("Dirección")
    if not b["items"]:
        out.append("Ningún ítem cotizado")
    for n in indices_sin_precio(b["items"]):
        out.append(f"Precio del ítem «{b['items'][n]['descripcion'] or n + 1}» (está en 0 o vacío)")
    return out


def entradas(items: list[dict]) -> list[EntradaLinea]:
    return [EntradaLinea(i["cantidad"], i["descripcion"], i["precio_unitario"], i["total_declarado"]) for i in items]


def calcular_borrador(b: dict, iva: float = 0.0) -> Resultado:
    return calcular(entradas(b["items"]), iva_porcentaje=iva, total_declarado=b.get("total_declarado"))


def cotizacion(b: dict, iva: float, fecha: date) -> tuple[Cotizacion, Resultado]:
    res = calcular_borrador(b, iva)
    return construir(a_extraccion(b, con_items=False), res, fecha), res
