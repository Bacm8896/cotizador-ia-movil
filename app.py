"""Prototipo: nota de texto/voz -> LLM (JSON) -> validación en Python -> cotización HTML.

Gemini se invoca UNA sola vez, solo cuando se pulsa "Extraer datos con IA".
Todo lo demás (completar datos, recalcular, renderizar) es Python local.

Ejecutar:  streamlit run app.py
"""
import hmac
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cotizador.builder import construir
from cotizador.calculator import EntradaLinea, calcular
from cotizador.config import DEFECTOS, get_setting
from cotizador.extractor import Audio, ExtraccionError, extraer
from cotizador.renderer import render_html
from cotizador.schemas import Cliente, ExtraccionTrabajo
from cotizador.whatsapp import enlace, mensaje, normalizar_telefono

st.set_page_config(page_title="Cotizador ALARMEC", page_icon="🧾", layout="wide")

EJEMPLO = (
    "Cotización para el arquitecto Mauricio Pazmiño, teléfono 0983885380, "
    "sector La Floresta en Quito. Tendido de cerca eléctrica, 29 metros a 8 dólares el metro, "
    "material y mano de obra incluidos. 50% a la firma y saldo contraentrega."
)
COLUMNAS = ["cantidad", "descripcion", "precio_unitario", "total_declarado"]

ss = st.session_state


# ------------------------------------------------------------ acceso por PIN
def _pin_correcto() -> str:
    return get_setting("APP_PIN", "1234")


if not ss.get("autenticado"):
    st.title("🔒 Cotizador ALARMEC")
    with st.form("login"):
        pin = st.text_input("PIN", type="password")
        entrar = st.form_submit_button("Ingresar")
    if entrar:
        if hmac.compare_digest(pin.encode(), _pin_correcto().encode()):
            ss.autenticado = True
            st.rerun()
        st.error("PIN incorrecto.")
    st.stop()

ss.setdefault("texto", "")
ss.setdefault("extraccion_completada", None)  # resultado de Gemini; solo cambia al pulsar el botón
ss.setdefault("audio_version", 0)             # cambia la clave del grabador para limpiarlo

st.markdown(
    "<style>div[data-testid='stNumberInput'] input{font-size:1.4rem;height:3rem}</style>",
    unsafe_allow_html=True,
)


def _audio_de(widget) -> list[Audio]:
    if widget is None:
        return []
    return [Audio(widget.getvalue(), getattr(widget, "type", None) or "audio/wav")]


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Opciones")
    iva = st.number_input("IVA % (0 = como el modelo)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    fecha = st.date_input("Fecha de la cotización", value=date.today())
    st.caption("Los totales siempre los calcula Python; el LLM solo extrae datos.")

st.title("🧾 Cotizador ALARMEC")

# ------------------------------------------------------------------ 1. entrada
st.subheader("1. Datos del trabajo")
col_txt, col_voz = st.columns([3, 2])

with col_voz:
    audio = st.audio_input(
        "Nota de voz (opcional; Gemini la entiende directamente)",
        key=f"audio_input_{ss.audio_version}",
    )
    if audio is not None and st.button("🗑️ Descartar audio y regrabar", type="secondary"):
        ss.audio_version += 1
        st.rerun()

with col_txt:
    if st.button("Cargar ejemplo"):
        ss.texto = EJEMPLO
    st.text_area("Texto o nota", key="texto", height=170,
                 placeholder="Cliente, ítems, cantidades, precios, condiciones…")

# Única llamada a Gemini: solo ocurre en la ejecución en que se pulsa este botón.
if st.button("Extraer datos con IA", type="primary", disabled=not (ss.texto.strip() or audio)):
    with st.spinner("Extrayendo…"):
        try:
            ss.extraccion_completada = extraer(ss.texto, _audio_de(audio))
        except ExtraccionError as e:
            st.error(str(e))

ext: ExtraccionTrabajo | None = ss.extraccion_completada
if ext is None:
    st.info("Escribe o dicta los datos y pulsa **Extraer datos con IA**.")
    st.stop()

# ------------------------------------------------------------ 2. revisión
st.subheader("2. Revisar y corregir")
c = ext.cliente
a, b, c2 = st.columns(3)
nombre = a.text_input("Cliente", c.nombre or "")
atencion = b.text_input("ATN", c.atencion or "")
telefono = c2.text_input("Teléfono", c.telefono or "")
direccion = a.text_input("Dirección", c.direccion or "")
ciudad = b.text_input("Ciudad", c.ciudad or "")
titulo = c2.text_input("Título del trabajo", ext.titulo_trabajo or "")
tiempo_entrega = st.text_input("Tiempo de entrega", ext.tiempo_entrega or DEFECTOS.tiempo_entrega)

clave_ext = hash(ext.model_dump_json())
df_in = pd.DataFrame([i.model_dump() for i in ext.items], columns=COLUMNAS)
df = st.data_editor(
    df_in, num_rows="dynamic", width="stretch", key=f"items_{clave_ext}",
    column_config={
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0),
        "descripcion": st.column_config.TextColumn("Descripción", width="large"),
        "precio_unitario": st.column_config.NumberColumn("P. unitario", min_value=0.0, format="%.2f"),
        "total_declarado": None,  # oculta: solo se usa para avisar de diferencias
    },
)
obs = st.text_area("Observaciones (una por línea)", "\n".join(ext.observaciones), height=70)

with st.expander("JSON devuelto por el LLM"):
    st.json(ext.model_dump())

# ------------------------------------- asistente de datos faltantes (solo Python)
filas = [
    (n, str(r.descripcion or "").strip() or f"ítem {n + 1}", _num(r.precio_unitario))
    for n, r in enumerate(df.itertuples(index=False))
]
sin_precio = [(n, d) for n, d, p in filas if not p or p <= 0]
datos_cliente = {"nombre del cliente": nombre, "teléfono": telefono, "dirección": direccion}
faltan_cliente = [k for k, v in datos_cliente.items() if not v.strip()]

precios_manuales: dict[int, float] = {}
if sin_precio or faltan_cliente:
    with st.container(border=True):
        st.markdown("### ⚠️ Completa estos datos para finalizar la cotización:")
        if faltan_cliente:
            st.write("Falta: " + ", ".join(faltan_cliente) + " (campos de arriba).")
        for n, desc in sin_precio:
            precios_manuales[n] = st.number_input(
                f"💵 Precio para: {desc}", min_value=0.0, step=0.5, format="%.2f",
                key=f"precio_{clave_ext}_{n}_{abs(hash(desc))}",
            )

entradas = []
for (n, desc, precio), r in zip(filas, df.itertuples(index=False)):
    if not precio or precio <= 0:
        precio = precios_manuales.get(n) or None  # None si sigue en 0
    entradas.append(EntradaLinea(_num(r.cantidad), str(r.descripcion or ""), precio, _num(r.total_declarado)))

if any(e.precio_unitario is None or e.precio_unitario <= 0 for e in entradas):
    st.stop()  # hasta que todos los ítems tengan precio > 0 no se muestra la cotización

# ------------------------------------------------------------ 3. validación
res = calcular(entradas, iva_porcentaje=iva, total_declarado=ext.total_declarado)

st.subheader("3. Validación matemática")
for m in res.errores:
    st.error(m)
for m in res.advertencias:
    st.warning(m)
if not res.ok:
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Subtotal", f"{res.subtotal:,.2f}")
m2.metric(f"IVA {iva:g}%", f"{res.iva:,.2f}")
m3.metric("Total", f"{res.total:,.2f}")
st.dataframe(
    pd.DataFrame(
        [{"Cantidad": float(l.cantidad), "Descripción": l.descripcion,
          "P. unitario": float(l.precio_unitario), "Total": float(l.total)} for l in res.lineas]
    ),
    hide_index=True, width="stretch",
)

# ------------------------------------------------------------ 4. cotización
st.subheader("4. Cotización")
revisada = ExtraccionTrabajo(
    cliente=Cliente(nombre=nombre, atencion=atencion, telefono=telefono, direccion=direccion, ciudad=ciudad),
    titulo_trabajo=titulo,
    items=[],
    observaciones=[o.strip() for o in obs.splitlines() if o.strip()],
    forma_pago=ext.forma_pago, saldo=ext.saldo, tiempo_entrega=tiempo_entrega.strip() or None,
    garantia=ext.garantia, total_declarado=ext.total_declarado,
)
cot = construir(revisada, res, fecha)
html = render_html(cot)
components.html(html, height=1250, scrolling=True)

st.subheader("5. Enviar")
col_desc, col_wa = st.columns(2)
with col_desc:
    st.markdown("**📥 Guardar en el móvil**")
    st.download_button(
        "Descargar cotización", html, file_name="cotizacion.html", mime="text/html",
        width="stretch", type="primary",
    )
    st.caption("Se guarda como HTML; ábrelo y usa Imprimir → Guardar como PDF si lo necesitas en PDF.")
with col_wa:
    st.markdown("**📲 Enviar por WhatsApp**")
    numero = st.text_input("WhatsApp del cliente", value=telefono, key=f"wa_{clave_ext}")
    valido = normalizar_telefono(numero) is not None
    st.link_button(
        "Enviar por WhatsApp", enlace(numero, mensaje(cot)), width="stretch", type="primary",
    )
    st.caption(
        "Se abre WhatsApp con la cotización escrita lista para enviar."
        if valido else "Número no válido o vacío: WhatsApp te dejará elegir el contacto."
    )
