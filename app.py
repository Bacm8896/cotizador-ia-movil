"""Cotizador ALARMEC: asistente por pasos (voz/texto -> Gemini -> revisión -> PDF -> WhatsApp).

PASO 1 Captura · PASO 2 Revisión y faltantes · PASO 3 Vista previa · PASO 4 Entrega.
Gemini solo se invoca al pulsar "Procesar con IA" (paso 1) o "Aplicar ajuste con IA" (paso 2);
revisar, completar precios, recalcular y generar el PDF es Python local.

Ejecutar:  streamlit run app.py
"""
import hmac
import io
from datetime import date

import fitz  # PyMuPDF: convierte el PDF en imagen para la vista previa
import pandas as pd
import streamlit as st

from cotizador import borrador as bd
from cotizador.config import get_setting
from cotizador.extractor import Audio, ExtraccionError, ajustar, extraer
from cotizador.pdf import generar_pdf
from cotizador.whatsapp import enlace, mensaje, normalizar_telefono

st.set_page_config(page_title="Cotizador ALARMEC", page_icon="🧾", layout="wide")

EJEMPLO = (
    "Cotización para el arquitecto Mauricio Pazmiño, teléfono 0983885380, "
    "sector La Floresta en Quito. Tendido de cerca eléctrica, 29 metros a 8 dólares el metro, "
    "material y mano de obra incluidos. 50% a la firma y saldo contraentrega."
)
COLUMNAS = ["cantidad", "descripcion", "precio_unitario", "total_declarado"]
PASOS = {1: "Captura", 2: "Revisión y faltantes", 3: "Vista previa", 4: "Entrega"}
TIPOS_AUDIO = ["wav", "mp3", "ogg", "flac", "aac", "m4a", "webm"]
MIME_AUDIO = {"audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4", "audio/x-wav": "audio/wav"}

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

# ------------------------------------------------------------------- estado
ss.setdefault("paso", 1)
ss.setdefault("texto", "")
ss.setdefault("extraccion_completada", None)  # resultado de Gemini; solo cambia al pulsarse un botón de IA
ss.setdefault("borrador", None)               # datos editables (cotizador.borrador)
ss.setdefault("audio_version", 0)             # cambia la clave de los widgets de audio para limpiarlos
ss.setdefault("ver_editor", 0)
ss.setdefault("items_base", [])
ss.setdefault("pdf", None)
ss.setdefault("cot", None)

st.markdown(
    "<style>div[data-testid='stNumberInput'] input{font-size:1.4rem;height:3rem}</style>",
    unsafe_allow_html=True,
)


def _ir(paso: int) -> None:
    """Cambia de paso y descarta el estado de los widgets del paso anterior."""
    for k in list(ss.keys()):
        if k.startswith(("f_", "precio_", "editor_")):
            del ss[k]
    if paso == 2:
        ss.items_base = [dict(i) for i in ss.borrador["items"]]
        ss.ver_editor += 1
    ss.paso = paso


def _audios(*widgets) -> list[Audio]:
    out = []
    for w in widgets:
        if w is not None:
            mime = MIME_AUDIO.get(getattr(w, "type", None) or "", getattr(w, "type", None) or "audio/wav")
            out.append(Audio(w.getvalue(), mime))
    return out


def _nuevo_borrador(ext) -> None:
    ss.extraccion_completada = ext
    ss.borrador = bd.desde_extraccion(ext)
    _ir(2)


@st.cache_data(show_spinner=False)
def _paginas_png(pdf: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf, filetype="pdf")
    return [p.get_pixmap(dpi=110).tobytes("png") for p in doc]


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Opciones")
    iva = st.number_input("IVA % (0 = sin IVA)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    fecha = st.date_input("Fecha de la cotización", value=date.today())
    st.caption("Los totales siempre los calcula Python; la IA solo extrae datos.")

st.title("🧾 Cotizador ALARMEC")
st.progress(ss.paso / 4, text=f"Paso {ss.paso} de 4 · {PASOS[ss.paso]}")

# =============================================================== PASO 1
if ss.paso == 1:
    col_txt, col_voz = st.columns([3, 2])
    with col_voz:
        grabado = st.audio_input("🎙️ Grabar nota de voz", key=f"audio_input_{ss.audio_version}")
        subido = st.file_uploader("…o subir un audio", type=TIPOS_AUDIO, key=f"audio_subido_{ss.audio_version}")
        if (grabado is not None or subido is not None) and st.button("🗑️ Descartar audio y regrabar"):
            ss.audio_version += 1
            st.rerun()
    with col_txt:
        if st.button("Cargar ejemplo"):
            ss.texto = EJEMPLO
        st.text_area("Texto o nota (opcional si hay audio)", key="texto", height=170,
                     placeholder="Cliente, ítems, cantidades, precios, condiciones…")

    audios = _audios(grabado, subido)
    # Llamada a Gemini: solo en la ejecución en que se pulsa este botón.
    if st.button("Procesar con IA", type="primary", disabled=not (ss.texto.strip() or audios)):
        with st.spinner("Procesando…"):
            try:
                _nuevo_borrador(extraer(ss.texto, audios))
            except ExtraccionError as e:
                st.error(str(e))
            else:
                st.rerun()
    if ss.borrador is not None:
        st.info("Ya hay un borrador en curso.")
        if st.button("Volver al borrador →"):
            _ir(2)
            st.rerun()

# =============================================================== PASO 2
elif ss.paso == 2:
    b = ss.borrador
    for campo in bd.CAMPOS_TEXTO:
        ss.setdefault(f"f_{campo}", b[campo])

    st.subheader("Datos del cliente y condiciones")
    a, c, d = st.columns(3)
    a.text_input("Cliente", key="f_nombre")
    c.text_input("ATN", key="f_atencion")
    d.text_input("Teléfono", key="f_telefono")
    a.text_input("Dirección", key="f_direccion")
    c.text_input("Ciudad", key="f_ciudad")
    d.text_input("Título del trabajo", key="f_titulo")
    e1, e2 = st.columns(2)
    e1.text_input("Forma de pago", key="f_forma_pago")
    e2.text_input("Saldo", key="f_saldo")
    e1.text_input("Tiempo de entrega", key="f_tiempo_entrega")
    e2.text_input("Garantía", key="f_garantia")

    st.subheader("Ítems")
    df_in = pd.DataFrame(ss.items_base, columns=COLUMNAS)
    df = st.data_editor(
        df_in, num_rows="dynamic", width="stretch", key=f"editor_{ss.ver_editor}",
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0),
            "descripcion": st.column_config.TextColumn("Descripción", width="large"),
            "precio_unitario": st.column_config.NumberColumn("P. unitario", min_value=0.0, format="%.2f"),
            "total_declarado": None,  # oculta: solo se usa para avisar de diferencias
        },
    )
    st.text_area("Observaciones (una por línea)", key="f_observaciones", height=70)

    # Casillas de precio para los ítems sin precio (Python local, recalcula al instante)
    items = bd.limpiar_items(df.to_dict("records"))
    pendientes = bd.indices_sin_precio(items)
    if pendientes:
        with st.container(border=True):
            st.markdown("### ⚠️ Completa estos datos para finalizar la cotización:")
            for n in pendientes:
                nombre_item = items[n]["descripcion"] or f"ítem {n + 1}"
                p = st.number_input(
                    f"💵 Precio para: {nombre_item}", min_value=0.0, step=0.5, format="%.2f",
                    key=f"precio_{ss.ver_editor}_{n}",
                )
                if p > 0:
                    items[n]["precio_unitario"] = p

    # Guarda lo editado en el borrador (así sobrevive a ir y volver de otros pasos)
    for campo in bd.CAMPOS_TEXTO:
        b[campo] = ss[f"f_{campo}"]
    b["items"] = items

    # Cuadro de advertencia con lo que falta
    faltan = bd.faltantes(b)
    if faltan or b["usados_defecto"]:
        with st.container(border=True):
            if faltan:
                st.warning("**Faltan datos:**\n\n" + "\n".join(f"- {f}" for f in faltan))
            if b["usados_defecto"]:
                st.info("No se mencionaron " + ", ".join(b["usados_defecto"])
                        + ": se usaron los valores por defecto de la empresa (puedes editarlos arriba).")

    res = bd.calcular_borrador(b, iva)
    if not pendientes:  # los errores de precio ya los explica el cuadro de arriba
        for m in res.errores:
            st.error(m)
    for m in res.advertencias:
        st.warning(m)
    if res.ok:
        m1, m2, m3 = st.columns(3)
        m1.metric("Subtotal", f"{res.subtotal:,.2f}")
        m2.metric(f"IVA {iva:g}%", f"{res.iva:,.2f}")
        m3.metric("Total", f"{res.total:,.2f}")

    with st.expander("✨ Instrucción de ajuste con IA (opcional)"):
        st.caption("Ej.: «agrega una sirena a 45 dólares» o «cambia la cantidad de cámaras a 6». "
                   "Cada pulsación del botón usa una llamada a Gemini.")
        instr = st.text_area("Instrucción por texto", key="f_instruccion", height=70)
        voz = st.audio_input("…o por voz", key=f"audio_ajuste_{ss.audio_version}")
        if st.button("Aplicar ajuste con IA", disabled=not (instr.strip() or voz is not None)):
            with st.spinner("Aplicando ajuste…"):
                try:
                    _nuevo_borrador(ajustar(bd.a_extraccion(b), instr, _audios(voz)))
                except ExtraccionError as e:
                    st.error(str(e))
                else:
                    ss.audio_version += 1
                    st.rerun()

    n1, n2 = st.columns(2)
    if n1.button("← Volver a la captura"):
        _ir(1)
        st.rerun()
    if n2.button("Continuar a la vista previa →", type="primary", disabled=not res.ok):
        ss.cot, _ = bd.cotizacion(b, iva, fecha)
        ss.pdf = generar_pdf(ss.cot)
        _ir(3)
        st.rerun()

# =============================================================== PASO 3
elif ss.paso == 3:
    cot, res = bd.cotizacion(ss.borrador, iva, fecha)  # refleja cambios de IVA/fecha de la barra lateral
    ss.cot, ss.pdf = cot, generar_pdf(cot)
    st.subheader("Vista previa del documento")
    for png in _paginas_png(ss.pdf):
        st.image(png, width="stretch")
    st.metric("Total", f"$ {res.total:,.2f}")
    n1, n2 = st.columns(2)
    if n1.button("← Hacer más cambios"):
        _ir(2)
        st.rerun()
    if n2.button("✅ Aprobar y Generar PDF", type="primary"):
        _ir(4)
        st.rerun()

# =============================================================== PASO 4
else:
    cot, pdf = ss.cot, ss.pdf
    st.success("✅ Cotización lista.")
    nombre_archivo = "cotizacion_" + (cot.cliente_nombre.strip().replace(" ", "_") or "cliente") + ".pdf"
    col_desc, col_wa = st.columns(2)
    with col_desc:
        st.markdown("**📥 Guardar en el móvil**")
        st.download_button(
            "Descargar PDF", io.BytesIO(pdf), file_name=nombre_archivo, mime="application/pdf",
            width="stretch", type="primary",
        )
    with col_wa:
        st.markdown("**📲 Enviar por WhatsApp**")
        numero = st.text_input("WhatsApp del cliente", value=cot.cliente_telefono, key="f_whatsapp")
        st.link_button("Enviar por WhatsApp", enlace(numero, mensaje(cot)), width="stretch", type="primary")
        st.caption(
            "Se abre WhatsApp con el resumen escrito; adjunta el PDF descargado en el chat."
            if normalizar_telefono(numero) else "Número no válido o vacío: WhatsApp te dejará elegir el contacto."
        )
    st.divider()
    n1, n2 = st.columns(2)
    if n1.button("← Hacer más cambios"):
        _ir(2)
        st.rerun()
    if n2.button("🆕 Iniciar nueva cotización"):
        for k in list(ss.keys()):
            if k != "autenticado":
                del ss[k]
        st.rerun()
