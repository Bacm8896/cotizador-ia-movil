"""Modelos Pydantic.

`ExtraccionTrabajo` es el esquema JSON que el LLM está obligado a devolver
(Structured Outputs). Los demás modelos son el resultado ya validado en Python.
"""
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- LLM output
class Cliente(BaseModel):
    nombre: str | None = Field(description="Nombre del cliente, con título si lo dice (ARQ., ING., SR.)")
    atencion: str | None = Field(description="Persona de contacto (ATN), si es distinta del cliente")
    telefono: str | None = Field(description="Teléfono del cliente")
    direccion: str | None = Field(description="Dirección o sector de la obra")
    ciudad: str | None = Field(description="Ciudad, si se menciona")


class ItemExtraido(BaseModel):
    cantidad: float = Field(description="Cantidad numérica (metros, unidades, etc.)")
    descripcion: str = Field(description="Descripción del ítem en MAYÚSCULAS, incluyendo la unidad (p. ej. 'METROS TENDIDO CERCA ELECTRICA')")
    precio_unitario: float | None = Field(description="Precio unitario si se dijo explícitamente; null si no")
    total_declarado: float | None = Field(
        description="Total de la línea SOLO si el texto lo menciona literalmente; no lo calcules"
    )


class ExtraccionTrabajo(BaseModel):
    cliente: Cliente
    titulo_trabajo: str | None = Field(description="Título de la sección, en MAYÚSCULAS (p. ej. 'CERCA ELECTRICA')")
    items: list[ItemExtraido]
    observaciones: list[str] = Field(
        description="Notas al pie de los ítems en MAYÚSCULAS (p. ej. 'MATERIAL Y MANO DE OBRA INCLUIDOS')"
    )
    forma_pago: str | None = Field(description="Forma de pago si se menciona (p. ej. '50% A LA FIRMA DEL CONTRATO')")
    saldo: str | None = Field(description="Condición del saldo si se menciona (p. ej. 'CONTRAENTREGA')")
    tiempo_entrega: str | None = Field(description="Tiempo de entrega si se menciona")
    garantia: str | None = Field(description="Garantía si se menciona")
    total_declarado: float | None = Field(
        description="Total general SOLO si el texto lo menciona literalmente; no lo calcules"
    )
    preguntas_clarificacion: list[str] = Field(
        default_factory=list,
        description="De 1 a 3 preguntas breves si faltan datos críticos; lista vacía si todo está claro",
    )


# ------------------------------------------------------- Resultado validado
class Linea(BaseModel):
    cantidad: Decimal
    descripcion: str
    precio_unitario: Decimal
    total: Decimal


class Cotizacion(BaseModel):
    """Todo lo que necesita la plantilla HTML."""

    fecha: str
    cliente_nombre: str = ""
    cliente_atencion: str = ""
    cliente_telefono: str = ""
    cliente_direccion: str = ""
    cliente_ciudad: str = ""
    titulo_trabajo: str = ""
    lineas: list[Linea] = []
    observaciones: list[str] = []
    subtotal: Decimal = Decimal("0.00")
    iva_porcentaje: Decimal = Decimal("0")
    iva: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    forma_pago: str = ""
    saldo: str = ""
    tiempo_entrega: str = ""
    garantia: str = ""
