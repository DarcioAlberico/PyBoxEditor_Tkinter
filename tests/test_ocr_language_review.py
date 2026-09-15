from core.ocr_language import LineDataset, LanguageModel, TERMOS_XADREZ
from core.ocr_result import WordResult
from core.ocr_review import ReviewStore, detectar_suspeitas


def _word(text="Casa", conf=0.9, alternatives=None):
    return WordResult("w1", text, conf, (1, 2, 30, 20), "l1", "fused",
                      alternatives=alternatives or [])


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


def test_detector_de_suspeitas_cobre_confianca_dicionario_e_divergencia():
    modelo = LanguageModel.from_texts(["Casa"])
    palavras = [_word("Caza", 0.55, ["Casa"]), _word("Casa", 0.95)]
    palavras[1].id = "w2"
    suspeitas = detectar_suspeitas(palavras, modelo)
    assert len(suspeitas) == 1
    assert "low_confidence" in suspeitas[0].reason
    assert "unknown_word" in suspeitas[0].reason


def test_review_store_aplica_correcao_sem_perder_original(tmp_path):
    store = ReviewStore(tmp_path / "review.json")
    original = _word("Caza", 0.5)
    corrigida = store.apply(original, "Casa")
    assert corrigida.text == "Casa"
    assert corrigida.original_text == "Caza"
    assert corrigida.source == "manual"
    assert len(store.events) == 1
    destino = tmp_path / "active.jsonl"
    assert store.export_active_learning(destino) == 1
    assert destino.exists()


def test_review_store_desfaz_ultima_correcao_e_persiste(tmp_path):
    caminho = tmp_path / "review.json"
    store = ReviewStore(caminho)
    palavra = _word("Caza", 0.5)
    store.apply(palavra, "Casa")
    store.apply(_word("teh", 0.4), "the")

    evento = store.undo()
    assert evento is not None
    assert evento.before == "teh"
    assert [item.after for item in store.events] == ["Casa"]
    assert len(ReviewStore(caminho).events) == 1
    assert ReviewStore(tmp_path / "vazio.json").undo() is None
