"""Ningún test debe consumir la API real de Gemini."""
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def sin_gemini_real(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def prohibido(*a, **k):
        raise AssertionError("Un test intentó crear un cliente real de Gemini; usa un mock.")

    with mock.patch("cotizador.extractor.genai.Client", side_effect=prohibido):
        yield
