# Cotizador ALARMEC (prototipo)

Nota de texto/voz → Google Gemini (salida estructurada Pydantic; texto o audio directo, capa gratuita) → validación matemática en Python → cotización HTML con el membrete del Excel modelo.

```
app.py                      asistente por pasos (Captura → Revisión → Vista previa → Entrega)
cotizador/
  config.py                 empresa, condiciones por defecto, catálogo, get_setting (secrets → entorno)
  schemas.py                esquema del LLM (ExtraccionTrabajo) + modelo Cotizacion
  extractor.py              Gemini: extraer() y ajustar() (una llamada por pulsación, sin reintentos)
  borrador.py               estado editable, datos faltantes y cálculo (Python puro)
  calculator.py             cálculo con Decimal, advertencias y errores
  builder.py / renderer.py  Cotizacion y formato (1.234,50); el HTML tipo Excel queda como legado
  pdf.py                    PDF A4 con ReportLab (márgenes 20 mm, solo ítems cotizados)
  whatsapp.py               enlace wa.me con el resumen de la cotización
tests/                      todos con mocks: ninguno consume la API de Gemini
```

## Uso
```
pip install -r requirements.txt
copy .env.example .env      # completar claves
streamlit run app.py
python -m pytest
```
