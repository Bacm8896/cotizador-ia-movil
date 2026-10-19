"""Prototipo: nota de texto/voz -> LLM (JSON) -> validación en Python -> cotización HTML.

Ejecutar:  streamlit run app.py
"""
import hmac
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cotizador.builder import construir
from cotizador.calculator import EntradaLinea, calcular
from cotizador.config import get_setting
from cotizador.extractor import ExtraccionError, extraer
from cotizador.renderer import render_html
from cotizador.schemas import Cliente, ExtraccionTrabajo

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
ss.setdefault("ext", None)  # ExtraccionTrabajo vigente


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
    audio = st.audio_input("Nota de voz (opcional; Gemini la entiende directamente)")

with col_txt:
    if st.button("Cargar ejemplo"):
        ss.texto = EJEMPLO
    st.text_area("Texto o nota", key="texto", height=170,
                 placeholder="Cliente, ítems, cantidades, precios, condiciones…")

if st.button("Extraer datos con IA", type="primary", disabled=not (ss.texto.strip() or audio)):
    with st.spinner("Extrayendo…"):
        try:
            audio_bytes = audio.getvalue() if audio is not None else None
            audio_mime = (getattr(audio, "type", None) or "audio/wav") if audio is not None else "audio/wav"
            ss.ext = extraer(ss.texto, audio_bytes, audio_mime)
        except ExtraccionError as e:
            st.error(str(e))

ext: ExtraccionTrabajo | None = ss.ext
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

df_in = pd.DataFrame([i.model_dump() for i in ext.items], columns=COLUMNAS)
df = st.data_editor(
    df_in, num_rows="dynamic", width="stretch", key=f"items_{hash(ext.model_dump_json())}",
    column_config={
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0),
        "descripcion": st.column_config.TextColumn("Descripción", width="large"),
        "precio_unitario": st.column_config.NumberColumn("P. unitario", min_value=0.0, format="%.2f"),
        "total_declarado": st.column_config.NumberColumn("Total dicho (referencia)", format="%.2f", disabled=True),
    },
)
obs = st.text_area("Observaciones (una por línea)", "\n".join(ext.observaciones), height=70)

with st.expander("JSON devuelto por el LLM"):
    st.json(ext.model_dump())

# ------------------------------------------------------------ 3. validación
def _num(v):
    return None if pd.isna(v) else float(v)

entradas = [
    EntradaLinea(_num(r.cantidad), str(r.descripcion or ""), _num(r.precio_unitario), _num(r.total_declarado))
    for r in df.itertuples(index=False)
]
res = calcular(entradas, iva_porcentaje=iva, total_declarado=ext.total_declarado)

st.subheader("3. Validación matemática")
for m in res.errores:
    st.error(m)
for m in res.advertencias:
    st.warning(m)
if res.ok:
    m1, m2, m3 = st.columns(3)
    m1.metric("Subtotal", f"{res.subtotal:,.2f}")
    m2.metric(f"IVA {iva:g}%", f"{res.iva:,.2f}")
    m3.metric("Total", f"{res.total:,.2f}")
else:
    st.stop()

# ------------------------------------------------------------ 4. cotización
st.subheader("4. Cotización")
revisada = ExtraccionTrabajo(
    cliente=Cliente(nombre=nombre, atencion=atencion, telefono=telefono, direccion=direccion, ciudad=ciudad),
    titulo_trabajo=titulo,
    items=[],
    observaciones=[o.strip() for o in obs.splitlines() if o.strip()],
    forma_pago=ext.forma_pago, saldo=ext.saldo, tiempo_entrega=ext.tiempo_entrega,
    garantia=ext.garantia, total_declarado=ext.total_declarado,
)
html = render_html(construir(revisada, res, fecha))
components.html(html, height=1250, scrolling=True)
st.download_button("Descargar HTML", html, file_name="cotizacion.html", mime="text/html")
st.caption("Para PDF: abre el HTML descargado y usa Imprimir → Guardar como PDF.")
