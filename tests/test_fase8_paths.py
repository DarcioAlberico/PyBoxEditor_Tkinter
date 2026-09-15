from pathlib import Path

from config import paths


def test_caminhos_persistentes_sao_deterministicos(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert paths.data_dir() == tmp_path / "data" / paths.APP_NAME
    assert paths.settings_path().name == "settings.json"
    assert paths.crash_log_path().name == "crash_log.txt"


def test_fallback_nao_escreve_no_pacote(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    assert paths.settings_path() == tmp_path / ".local" / "share" / paths.APP_NAME / "settings.json"


def test_settings_default_usa_diretorio_de_dados(monkeypatch, tmp_path):
    from config.settings import Settings

    destino = tmp_path / "config" / "settings.json"
    monkeypatch.setattr("config.settings.settings_path", lambda: destino)
    settings = Settings()
    settings.set("idioma", "pt")
    settings.save()
    assert Path(destino).is_file()

