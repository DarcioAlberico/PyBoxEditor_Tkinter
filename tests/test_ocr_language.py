from core.ocr_language import LineDataset, LanguageModel, TERMOS_XADREZ


def test_modelo_de_linguagem_conhece_pontua_e_sugere():
    modelo = LanguageModel.from_texts(["Casa casa cavalo"], dominio=TERMOS_XADREZ)
    assert modelo.conhece("CASA")
    assert modelo.conhece("zugzwang")
    assert modelo.score("casa") > modelo.score("mesa")
    assert "casa" in modelo.sugerir("caza", distancia_maxima=1)


def test_modelo_pode_reutilizar_lexico_existente():
    from core.lexico import Lexico
    modelo = LanguageModel.from_lexico(
        Lexico(palavras={"abertura"}, do_usuario={"Benko"}))
    assert modelo.conhece("ABERTURA")
    assert modelo.conhece("benko")


def test_modelo_persiste(tmp_path):
    modelo = LanguageModel.from_texts(["alpha beta"])
    caminho = tmp_path / "model.json"
    modelo.save_json(caminho)
    carregado = LanguageModel.load_json(caminho)
    assert carregado.conhece("alpha")
    assert carregado.frequencia_palavras["beta"] == 1


def test_dataset_de_linhas_jsonl(tmp_path):
    dataset = LineDataset()
    dataset.add("A line", "page.png", source="synthetic", metadata={"font": "x"})
    caminho = tmp_path / "lines.jsonl"
    dataset.save_jsonl(caminho)
    carregado = LineDataset.load_jsonl(caminho)
    assert carregado.samples[0].text == "A line"
    assert carregado.samples[0].metadata["font"] == "x"
