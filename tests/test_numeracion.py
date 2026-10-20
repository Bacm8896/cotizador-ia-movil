from cotizador import numeracion


def test_secuencia_sugiere_registra_y_persiste(tmp_path, monkeypatch):
    monkeypatch.setattr(numeracion, "ARCHIVO", tmp_path / "data" / "secuencia.json")
    assert numeracion.siguiente(2026) == "2026-0001"
    assert numeracion.siguiente(2026) == "2026-0001"          # sugerir no consume
    numeracion.registrar("2026-0001")
    assert numeracion.siguiente(2026) == "2026-0002"
    numeracion.registrar("2026-1023")                          # el usuario edita el número
    assert numeracion.siguiente(2026) == "2026-1024"
    numeracion.registrar("2026-0005")                          # uno menor no retrocede
    assert numeracion.siguiente(2026) == "2026-1024"
    assert numeracion.siguiente(2027) == "2027-0001"           # cada año reinicia


def test_registrar_ignora_formatos_libres_y_disco_de_solo_lectura(tmp_path, monkeypatch):
    monkeypatch.setattr(numeracion, "ARCHIVO", tmp_path / "s.json")
    numeracion.registrar("ABC-1")
    numeracion.registrar("")
    assert not (tmp_path / "s.json").exists()
    monkeypatch.setattr(numeracion, "ARCHIVO", tmp_path / "nada" / "x" / "s.json")
    monkeypatch.setattr(type(numeracion.ARCHIVO), "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError()), raising=False)
    numeracion.registrar("2026-0003")  # no debe lanzar
