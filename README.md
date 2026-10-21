# Cotizador ALARMEC

Nota de texto/voz → IA (Groq: Whisper + LLM en JSON, o Gemini como alternativa) → validación matemática en Python → cotización en PDF corporativo, con envío por WhatsApp.

```
app.py                      asistente por pasos (Captura → Revisión → Vista previa → Entrega)
cotizador/
  config.py                 empresa, condiciones por defecto, catálogo, get_setting (secrets → entorno)
  schemas.py                esquema del LLM (ExtraccionTrabajo) + modelo Cotizacion
  extractor.py              Groq (Whisper + LLM JSON) o Gemini: extraer() y ajustar() (una llamada por pulsación, sin reintentos)
  borrador.py               estado editable, datos faltantes y cálculo (Python puro)
  calculator.py             cálculo con Decimal, advertencias y errores
  builder.py / renderer.py  Cotizacion y formato (1.234,50); el HTML tipo Excel queda como legado
  pdf.py                    PDF A4 con ReportLab (márgenes 20 mm, solo ítems cotizados)
  whatsapp.py               enlace wa.me con el resumen de la cotización
tests/                      todos con mocks: ninguno consume la API de Groq ni de Gemini
```

## Uso
```
pip install -r requirements.txt
copy .env.example .env      # completar claves
streamlit run app.py
python -m pytest
```

## Autor y Créditos

- **Desarrollador:** Byron Carvajal
- **LinkedIn:** [Byron Carvajal](https://www.linkedin.com/in/byroncarvajalia)
- **GitHub:** [@Bacm8896](https://github.com/Bacm8896)
- **Versión:** v1.0 (Beta)

**Descripción técnica:** arquitectura en Streamlit Cloud, extracción inteligente con Groq API (Whisper + LLM)
y generación determinista de PDFs corporativos con ReportLab.
