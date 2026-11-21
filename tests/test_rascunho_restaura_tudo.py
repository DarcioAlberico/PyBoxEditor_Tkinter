"""O rascunho restaura tudo (RG-05, R-55).

- `Rascunho.restaurar` não religava a ponte: o livro vindo do documento editorial,
  recuperado do rascunho, salvava sem levar as correções ao diário, sem aviso.
- O rascunho da janela principal levava oito campos do box: `negativo`, `margem` e
  `moldura` se perdiam na recuperação, e o `.box` salvo em seguida perdia o campo 8.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.box_model import BoxEntry
from core.editor import epub
from core.editor.projeto import Projeto, Rascunho
from core.services.document_service import DocumentSession
from test_editor_importar_ir import documento_sintetico


def _projeto_da_ponte(tmp_path, documento="doc.json"):
    doc = documento_sintetico("doc")
    doc.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    caminho = str(tmp_path / documento)
    doc.save_json(caminho)
    livro = epub.novo_livro("Livro", "", "pt")
    livro.origem.documento_editorial = caminho
    projeto = Projeto(livro, None)
    assert projeto.religar_documento_editorial()
    return projeto, caminho


def test_restaurar_o_rascunho_religa_a_ponte(tmp_path):
    projeto, _ = _projeto_da_ponte(tmp_path)
    rascunho = Rascunho(projeto, pasta=str(tmp_path)).gravar()
    restaurado = Rascunho.restaurar(rascunho)
    assert restaurado.documento_editorial is not None, "a ponte não voltou com o rascunho"
    assert restaurado.documento_editorial.document_id == "doc"
    assert restaurado.diario == str(tmp_path / "saida.review.jsonl")


def test_a_ponte_que_nao_religa_avisa(tmp_path):
    projeto, documento = _projeto_da_ponte(tmp_path)
    rascunho = Rascunho(projeto, pasta=str(tmp_path)).gravar()
    with open(documento, "w", encoding="utf-8") as f:
        f.write("{ quebrado")
    restaurado = Rascunho.restaurar(rascunho)
    assert restaurado.documento_editorial is None
    assert restaurado.relatorio is not None
    assert any("ponte desligada" in a for a in restaurado.relatorio.avisos), \
        "a ponte desligada não chegou a quem abriu o rascunho"


def test_o_rascunho_da_janela_guarda_todos_os_campos_do_box(tmp_path):
    sessao = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=2, is_pdf=True, dpi=300)
    box = BoxEntry("♘", 10, 20, 30, 40, confidence=0.5, source="ocr", angulo=90,
                   negativo=True, margem=0.75, moldura=True)
    sessao.store(0, [box])
    sessao.mark_dirty(0)
    payload = sessao.montar_payload()

    outra = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=2, is_pdf=True, dpi=300)
    outra.aplicar_payload(payload)
    assert outra.boxes_for(0)[0].as_state() == box.as_state()

    # Gravado a 200 dpi e aberto a 300: as coordenadas reescalam, o resto fica.
    payload["dpi"] = 200
    terceira = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=2, is_pdf=True, dpi=300)
    terceira.aplicar_payload(payload)
    lido = terceira.boxes_for(0)[0]
    assert (lido.x1, lido.y1, lido.x2, lido.y2) == (15, 30, 45, 60)
    assert (lido.negativo, lido.margem, lido.moldura, lido.angulo) == (True, 0.75, True, 90)


def test_o_rascunho_antigo_de_oito_campos_continua_carregando(tmp_path):
    payload = {"schema": 1, "dpi": 300, "sujas": [0],
               "paginas": {"0": [["a", 1, 2, 3, 4, 0.9, "ocr", 180], ["b", 5, 6, 7, 8]]}}
    sessao = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=1, is_pdf=True, dpi=300)
    sessao.aplicar_payload(payload)
    a, b = sessao.boxes_for(0)
    assert (a.char, a.angulo, a.negativo, a.moldura) == ("a", 180, False, False)
    assert (b.char, b.confidence, b.source, b.angulo) == ("b", 0.0, "", 0)
