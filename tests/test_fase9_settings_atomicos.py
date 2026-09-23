import json

from config.settings import Settings


def test_save_de_settings_e_atomico_e_nunca_deixa_tmp(tmp_path):
    caminho = tmp_path / "config" / "settings.json"
    settings = Settings(caminho)
    settings.set("tema", "claro")
    settings.save()

    assert json.loads(caminho.read_text(encoding="utf-8")) == {"tema": "claro"}
    assert not caminho.with_name("settings.json.tmp").exists()


def _no_disco(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_duas_instancias_no_mesmo_arquivo_nao_desfazem_o_que_a_outra_gravou(tmp_path):
    """
    A janela principal e o editor de livros têm cada uma o seu `Settings` sobre o
    mesmo `settings.json`, lido uma vez, ao nascer — e o `appy.py --editor` é outro
    processo com mais um. O `save()` que despejava o `data` inteiro devolvia ao disco
    a foto da construção e apagava o que a outra instância tinha gravado no meio-tempo.
    """
    caminho = tmp_path / "settings.json"
    caminho.write_text(json.dumps({"tema": "claro"}), encoding="utf-8")
    principal, editor = Settings(caminho), Settings(caminho)

    editor.set("editor", {"recentes": ["livro.epub"]})
    editor.save()
    principal.set("ultimo_diretorio_de_entrada", "pdfs")
    principal.save()
    assert _no_disco(caminho) == {"tema": "claro", "editor": {"recentes": ["livro.epub"]},
                                  "ultimo_diretorio_de_entrada": "pdfs"}, \
        "a principal desfez os recentes do editor"

    editor.set("editor", {"recentes": ["livro.epub"], "zoom": 1.5})
    editor.save()
    assert _no_disco(caminho) == {"tema": "claro", "editor": {"recentes": ["livro.epub"], "zoom": 1.5},
                                  "ultimo_diretorio_de_entrada": "pdfs"}, \
        "o editor desfez o diretório da principal"
    # Quem grava passa a enxergar o que a outra gravou.
    assert editor.get("ultimo_diretorio_de_entrada") == "pdfs"

    # Na mesma chave, vale a última gravação.
    principal.set("tema", "escuro")
    principal.save()
    editor.set("tema", "sépia")
    editor.save()
    assert _no_disco(caminho)["tema"] == "sépia"
    assert _no_disco(caminho)["editor"]["zoom"] == 1.5


def test_o_que_muda_dentro_de_um_valor_e_o_que_se_apaga_tambem_chegam_ao_disco(tmp_path):
    """
    A mescla compara com o que a instância leu, e não com as chaves que passaram por
    `set`: `get` devolve o próprio dict guardado, e mexer nele sem `set` antes do
    `save()` gravava — e continua gravando. Apagar de `data`, idem.
    """
    caminho = tmp_path / "settings.json"
    caminho.write_text(json.dumps({"editor": {"zoom": 1.0}, "velha": 1}), encoding="utf-8")
    settings = Settings(caminho)
    settings.get("editor")["zoom"] = 2.0
    del settings.data["velha"]
    settings.save()
    assert _no_disco(caminho) == {"editor": {"zoom": 2.0}}


def test_arquivo_que_nao_se_le_na_hora_de_gravar_recebe_o_que_a_instancia_sabe(tmp_path):
    """
    Sem o que mesclar, vai o que a instância tem, como antes — e não só as chaves que
    ela mudou, o que zeraria as outras preferências por causa de um arquivo ilegível.
    O arquivo que sumiu, esse sim é o estado do disco: fica só o que se gravou depois.
    """
    caminho = tmp_path / "settings.json"
    caminho.write_text(json.dumps({"tema": "claro"}), encoding="utf-8")
    settings = Settings(caminho)
    caminho.write_text("{ quebrado", encoding="utf-8")
    settings.set("idioma", "pt")
    settings.save()
    assert _no_disco(caminho) == {"tema": "claro", "idioma": "pt"}

    caminho.unlink()
    settings.set("zoom", 2)
    settings.save()
    assert _no_disco(caminho) == {"zoom": 2}

