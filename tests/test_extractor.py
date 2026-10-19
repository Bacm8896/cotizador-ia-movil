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


def test_preguntas_por_defecto_vacias():
    assert ExtraccionTrabajo.model_validate(BASE).preguntas_clarificacion == []


def test_prompt_pide_preguntas_y_usa_catalogo():
    p = construir_prompt()
    assert "preguntas_clarificacion" in p and "METROS TENDIDO CERCA ELECTRICA" in p


@pytest.mark.parametrize("texto,audios,n_partes", [
    ("hola", None, 1),
    ("", [Audio(b"x", "audio/wav")], 1),
    ("hola", [Audio(b"x"), Audio(b"y", "audio/webm")], 3),
])
def test_texto_audio_o_ambos(texto, audios, n_partes):
    c = _Cliente(preguntas_clarificacion=["¿Precio?"])
    r = extraer(texto, audios, client=c)
    assert len(c.llamadas[0]["contents"]) == n_partes
    assert r.preguntas_clarificacion == ["¿Precio?"]


def test_sin_entrada_falla():
    with pytest.raises(ExtraccionError):
        extraer("  ", [], client=_Cliente())
