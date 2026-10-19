# Cotizador ALARMEC (prototipo)

Nota de texto/voz → Claude (Structured Outputs, JSON validado con Pydantic) → validación matemática en Python → cotización HTML con el membrete del Excel modelo.

```
app.py                      UI Streamlit (flujo en 4 pasos)
cotizador/
  config.py                 datos de la empresa y condiciones por defecto
  schemas.py                esquema del LLM (ExtraccionTrabajo) + modelo para la plantilla
  extractor.py              Claude: client.messages.parse(output_format=...)
  transcriber.py            voz → texto (OpenAI; Anthropic no ofrece audio)
  calculator.py             cálculo con Decimal, advertencias y errores
  builder.py                extracción + cálculo + defaults → Cotizacion
  renderer.py               Jinja2, formato 1.234,50, fecha "06 DE ABRIL DEL 2023"
templates/cotizacion.html.j2
tests/test_calculator.py
```

## Uso
```
pip install -r requirements.txt
copy .env.example .env      # completar claves
streamlit run app.py
python -m pytest
```
