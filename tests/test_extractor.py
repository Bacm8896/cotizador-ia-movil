import pytest

from cotizador.extractor import Audio, ExtraccionError, construir_prompt, extraer
from cotizador.schemas import ExtraccionTrabajo

BASE = {
    "cliente": {"nombre": "A", "atencion": None, "telefono": None, "direccion": None, "ciudad": None},
    "titulo_trabajo": None, "items": [], "observaciones": [], "forma_pago": None, "saldo": None,
    "tiempo_entrega": None, "garantia": None, "total_declarado": None,
}


class _Resp:
    def __init__(self, **extra):
        self.parsed = ExtraccionTrabajo.model_validate({**BASE, **extra})


class _Cliente:
    def __init__(self, **extra):
        self.llamadas = []
        self.models = self
        self._extra = extra

    def generate_content(self, **kw):
        self.llamadas.append(kw)
        return _Resp(**self._extra)


def test_prompt_usa_catalogo_y_no_pide_preguntas():
    p = construir_prompt()
    assert "METROS TENDIDO CERCA ELECTRICA" in p and "clarificacion" not in p
    assert "preguntas_clarificacion" not in ExtraccionTrabajo.model_json_schema()["properties"]


@pytest.mark.parametrize("texto,audios,n_partes", [
    ("hola", None, 1),
    ("", [Audio(b"x", "audio/wav")], 1),
    ("hola", [Audio(b"x"), Audio(b"y", "audio/webm")], 3),
])
def test_texto_audio_o_ambos(texto, audios, n_partes):
    c = _Cliente()
    extraer(texto, audios, client=c)
    assert len(c.llamadas) == 1  # una sola llamada por extracción
    assert len(c.llamadas[0]["contents"]) == n_partes


def test_sin_entrada_falla():
    with pytest.raises(ExtraccionError):
        extraer("  ", [], client=_Cliente())


def test_ajustar_hace_una_llamada_con_el_json_actual_y_la_instruccion():
    from cotizador.extractor import ajustar

    c = _Cliente()
    actual = ExtraccionTrabajo.model_validate(BASE)
    ajustar(actual, "agrega una sirena a 45", [Audio(b"x")], client=c)
    assert len(c.llamadas) == 1
    contenido = c.llamadas[0]["contents"]
    assert actual.model_dump_json() in contenido and "agrega una sirena a 45" in contenido
    assert len(contenido) == 5  # 3 textos + audio + instrucción
    with pytest.raises(ExtraccionError):
        ajustar(actual, "  ", [], client=c)
    assert len(c.llamadas) == 1
