"""Todo gravador de arquivo do usuário passa pela escrita atômica (RG-03, R-01; invariante 17).

Duas provas. **Por AST**, sobre `core`, `ui` e `config`: nenhum `.tmp` de nome fixo
(`caminho + ".tmp"`, `with_suffix(".tmp")`) e nenhum `mkstemp` fora de
`core/escrita_atomica.py` — a lista nominal (princípio 7 da spec) começa vazia. **Por
interrupção**, para cada um dos gravadores que a spec listou: com a troca final do
temporário pelo destino falhando, o arquivo que já existia fica intacto e nenhum
temporário sobra na pasta.

O diário de revisão, que só acrescenta (`editorial_review.py`), fica fora de propósito:
ele tem a regra dele (R-09).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from core import escrita_atomica as ea

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))

#: `arquivo:linha` -> motivo. Vazia: nenhum temporário próprio é aceito.
PERMITIDOS: dict[str, str] = {}


def _proibidos(arvore: ast.AST):
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value.endswith(".tmp"):
            yield no.lineno, f"temporário de nome fixo {no.value!r}"
        elif isinstance(no, ast.Attribute) and no.attr == "mkstemp":
            yield no.lineno, "mkstemp fora da escrita atômica"
        elif isinstance(no, ast.Name) and no.id == "mkstemp":
            yield no.lineno, "mkstemp fora da escrita atômica"


def test_nenhum_gravador_tem_temporario_proprio():
    achados = []
    for pasta in ("core", "ui", "config"):
        for arquivo in sorted((RAIZ / pasta).rglob("*.py")):
            relativo = arquivo.relative_to(RAIZ).as_posix()
            if relativo == "core/escrita_atomica.py":
                continue
            for linha, motivo in _proibidos(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if f"{relativo}:{linha}" not in PERMITIDOS:
                    achados.append(f"{relativo}:{linha}: {motivo}")
    assert not achados, "use core.escrita_atomica:\n" + "\n".join(achados)


# ----------------------------------------------------------------------
# Interrupção: a troca final falha, e o arquivo de antes fica
# ----------------------------------------------------------------------

def _livro_do_editor():
    import editor_livros
    return editor_livros.livro_completo()


def _documento_editorial():
    from core.editorial_model import (Decision, EditorialBlock, EditorialDocument,
                                      EditorialPage, Evidence, SourceRef)
    origem = SourceRef("book", 0, (1, 2, 30, 40), "img-hash", "raster")
    evidencia = Evidence("ev-1", origem, observed_text="1. e4", confidence=0.8)
    bloco = EditorialBlock(id="block-1", kind="paragraph", order=0, source_refs=[origem],
                           decision=Decision("1. e4", ["ev-1"], "automatic", ["engine_consensus"]))
    pagina = EditorialPage("book-p001", 0, [origem], [bloco], [evidencia])
    return EditorialDocument("book", "Livro", "en", [pagina], pipeline_version="t", source_sha256="s")


def _paginas_do_ocr():
    from core import livro
    return [livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("Capítulo", titulo=True, nivel=1),
                                                   livro.Paragrafo("1.e4 e5 2.Nf3")])]


def _settings(destino):
    from config.settings import Settings
    s = Settings(str(destino))
    s.data["x"] = 1
    s.save()


def _autosave(destino):
    from core.services.document_service import _GravadorAssincrono
    g = _GravadorAssincrono()
    g.agendar(str(destino), {"paginas": []})
    g._thread.join(timeout=10)
    assert isinstance(g.ultimo_erro, OSError)       # a falha chega à UI, como antes
    raise g.ultimo_erro


def _cache_do_ocr(destino):
    from core.ocr_result import PageResult
    from core.ocr_runtime import OCRCache
    cache = OCRCache(destino.parent)
    caminho = cache._path("chave")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("original", encoding="utf-8")
    cache.save("chave", PageResult("page-0000", lines=[]))


def _png_do_par(destino):
    from PIL import Image

    from ui.documento import Documento
    erro = Documento._write_box_pair(None, str(destino.with_suffix(".box")), Image.new("L", (20, 20), 255), [])
    raise OSError(erro)


def _pdf_editorial(destino):
    from core.editorial_export import EditorialExporter, ExportOptions
    EditorialExporter().export(_documento_editorial(), destino, ExportOptions(format="pdf"))


GRAVADORES = {
    "settings.json": ("settings.json", _settings),
    "rascunho do editor": ("r.json", lambda d: __import__("core.editor.projeto", fromlist=["x"])
                           .gravar_json_atomico(str(d), {"a": 1})),
    "pdf do editor": ("l.pdf", lambda d: __import__("core.editor.pdf_io", fromlist=["x"])
                      .escrever(_livro_do_editor(), str(d))),
    "autosave da janela": ("a.json", _autosave),
    "documento editorial": ("doc.json", lambda d: _documento_editorial().save_json(d)),
    "txt da fachada": ("f.txt", lambda d: __import__("core.editorial_export", fromlist=["x"])
                       ._gravar_atomico(d, "novo")),
    "léxico do usuário": ("l.txt", lambda d: __import__("core.lexico", fromlist=["x"])
                          .salvar_do_usuario(str(d), ["e4"])),
    "rótulos de linha": ("rec_gt.txt", lambda d: __import__("core.linha_review", fromlist=["x"])
                         ._salvar(d.parent, [])),
    "manifesto do corpus": ("m.json", lambda d: __import__("core.ocr_corpus", fromlist=["x"])
                            .salvar_manifesto(__import__("core.ocr_corpus", fromlist=["x"])
                                              .CorpusManifest(name="c", documents=[]), d)),
    "cache do OCR": (None, _cache_do_ocr),
    "correções": ("c.json", lambda d: __import__("core.ocr_phase7", fromlist=["x"])
                  .CorrectionDataset(name="c").save(d)),
    "txt do editor": ("l.txt", lambda d: __import__("core.editor.txt_io", fromlist=["x"])
                      .escrever(_livro_do_editor(), str(d))),
    "html do editor": ("l.html", lambda d: __import__("core.editor.html_io", fromlist=["x"])
                       .escrever_unico(_livro_do_editor(), str(d))),
    "pgn do editor": ("c.pgn", lambda d: __import__("core.editor.pgn_io", fromlist=["x"])
                      .escrever(_livro_do_editor().capitulos[0], str(d))),
    "buscas salvas": ("b.json", lambda d: __import__("core.editor.buscas_salvas", fromlist=["x"])
                      .Colecao().exportar_json(str(d))),
    "clipes": ("c.json", lambda d: __import__("core.editor.clipes", fromlist=["x"]).Clipes().exportar(str(d))),
    "pdf editorial": ("e.pdf", _pdf_editorial),
    ".box": ("p.box", lambda d: __import__("core.formato_box", fromlist=["x"]).escrever(str(d), [], 100)),
    "png do par": ("p.png", _png_do_par),
    "epub do editor": ("l.epub", lambda d: __import__("core.editor.epub", fromlist=["x"])
                       .escrever(_livro_do_editor(), str(d))),
    "epub do ocr": ("o.epub", lambda d: __import__("core.exportar", fromlist=["x"]).para_epub(_paginas_do_ocr(), str(d))),
    "docx do ocr": ("o.docx", lambda d: __import__("core.exportar", fromlist=["x"]).para_docx(_paginas_do_ocr(), str(d))),
    "docx do editor": ("l.docx", lambda d: __import__("core.editor.docx_io", fromlist=["x"])
                       .escrever(_livro_do_editor(), str(d))),
}


@pytest.mark.parametrize("nome", sorted(GRAVADORES))
def test_queda_antes_da_troca_deixa_o_arquivo_de_antes(nome, tmp_path, monkeypatch):
    arquivo, gravar = GRAVADORES[nome]
    pasta = tmp_path / "saida"
    pasta.mkdir()
    destino = pasta / (arquivo or "_")
    if arquivo:
        destino.write_text("original", encoding="utf-8")

    def queda(temporario, alvo):
        raise OSError("queda antes da troca")

    monkeypatch.setattr(ea, "_trocar", queda)
    with pytest.raises(OSError):
        gravar(destino)
    for f in pasta.rglob("*"):
        if f.is_file():
            assert f.read_text(encoding="utf-8", errors="replace") == "original", f"{nome}: {f.name} mudou"
            assert not f.name.endswith(".tmp"), f"{nome}: sobrou o temporário {f.name}"


def test_cada_ponto_da_spec_tem_seu_caso():
    """Os 22 pontos do R-01 menos os dois `torch.save` do treino de linhas, que pedem um
    treino inteiro e ficam cobertos pela varredura por AST; mais os três que já usavam
    `mkstemp` (o EPUB e o DOCX do OCR e o DOCX do editor)."""
    assert len(GRAVADORES) == 22 - 2 + 3
