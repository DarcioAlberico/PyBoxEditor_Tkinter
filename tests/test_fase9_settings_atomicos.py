import json

from config.settings import Settings


def test_save_de_settings_e_atomico_e_nunca_deixa_tmp(tmp_path):
    caminho = tmp_path / "config" / "settings.json"
    settings = Settings(caminho)
    settings.set("tema", "claro")
    settings.save()

    assert json.loads(caminho.read_text(encoding="utf-8")) == {"tema": "claro"}
    assert not caminho.with_name("settings.json.tmp").exists()

