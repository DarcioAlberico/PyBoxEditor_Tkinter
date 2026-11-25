"""Os silêncios que mudam a saída falam (RG-18, R-37).

Um teste por item da lista que muda o que o usuário recebe, e a varredura: em `ui` não há
`except` nu ou `except Exception` de corpo só `pass`, salvo os da lista nominal.
"""

import ast
import json
import logging
import os
import types
from pathlib import Path

import numpy as np
import pytest

from core import formato_box, vertical
from core import log as log_do_core
from core.box_model import BoxEntry
from core.dataset_check import nome_canonico, png_legivel
from core.editorial_export import imagem_do_diagrama, trechos_com_estilo
from core.editorial_model import Decision, EditorialBlock
from core.ocr_runtime import OCRCache, OCRCancelled
from core.ocr_training import preparar_engines
from core.services.document_service import DocumentSession
from core.services.ocr_service import OCRService

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _cada_aviso_do_zero(caplog):
    log_do_core.esquecer()
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=log_do_core.RAIZ)      # outro teste pode tê-lo posto em INFO
    yield
    log_do_core.esquecer()


def _avisos(caplog, pedaco, nivel=logging.WARNING):
    return [r for r in caplog.records if pedaco in r.getMessage() and r.levelno == nivel]


# ----------------------------------------------------------------------
# core
# ----------------------------------------------------------------------

PILHA = [BoxEntry("a", 10, 10 + 20 * i, 30, 26 + 20 * i) for i in range(4)]
PAGINA = np.full((120, 60), 255, np.uint8)


def test_o_arbitro_que_falha_fala_uma_vez(caplog):
    def ruim(recorte):
        raise RuntimeError("modelo quebrado")

    vertical.decidir_angulo(PAGINA, PILHA, ruim)
    assert len(_avisos(caplog, "árbitro do texto girado falhou")) == 1


@pytest.mark.parametrize("erro", [OCRCancelled(), AttributeError("erro de programa"), KeyError("x")])
def test_o_cancelamento_e_o_erro_de_programa_passam_pelo_arbitro(erro):
    def ruim(recorte):
        raise erro

    with pytest.raises(type(erro)):
        vertical.decidir_angulo(PAGINA, PILHA, ruim)


def test_o_cache_nao_soma_o_que_nao_removeu(tmp_path, monkeypatch, caplog):
    cache = OCRCache(tmp_path)
    for nome in ("sai", "preso"):
        (tmp_path / f"{nome}.json").write_text("x" * 100, encoding="utf-8")
        os.utime(tmp_path / f"{nome}.json", (1, 1))
    original = Path.unlink

    def unlink(self, *a, **k):
        if self.name == "preso.json":
            raise PermissionError("em uso")
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", unlink)
    relatorio = cache.prune(max_age_seconds=1, now=10_000.0)
    assert relatorio == {"removed": 1, "remaining": 1, "bytes_removed": 100, "bytes_remaining": 100}
    assert _avisos(caplog, "preso.json não saiu", logging.INFO)


def test_a_amostra_que_nao_abre_fala(tmp_path, caplog):
    assert png_legivel(str(tmp_path / "nao-existe.png")) is False
    assert _avisos(caplog, "nao-existe.png não se lê")


def test_a_pasta_que_nao_e_classe_diz_por_que(monkeypatch, caplog):
    from core import dataset_check

    def recusa(pasta, strict):
        raise dataset_check.NomeDePastaInvalido("torto")

    monkeypatch.setattr(dataset_check, "folder_to_char", recusa)
    assert nome_canonico("xyz") is None
    assert _avisos(caplog, "torto", logging.DEBUG)


def test_a_linha_que_nao_e_box_se_conta(caplog):
    boxes = formato_box.ler_texto("a 1 2 3 4 0\nb um dois 3 4 0\nlixo\n\n", 100)
    assert [b.char for b in boxes] == ["a"]
    [aviso] = _avisos(caplog, "não são boxes")
    assert aviso.getMessage().startswith("2 linha(s)") and "b um dois" in aviso.getMessage()


def test_o_box_inteiro_nao_avisa(caplog):
    formato_box.ler_texto("a 1 2 3 4 0\n\n", 100)
    assert not caplog.records


def test_o_campo_de_terceiro_fala_uma_vez(caplog):
    linhas = "a 1 2 3 4 0 xx 0 ocr yy\n" * 5
    assert len(formato_box.ler_texto(linhas, 100)) == 5
    assert len(_avisos(caplog, "campo ângulo", logging.INFO)) == 1
    assert len(_avisos(caplog, "campo confiança", logging.INFO)) == 1


def test_o_rascunho_conta_so_o_que_voltou(caplog, tmp_path):
    sessao = DocumentSession(str(tmp_path / "l.pdf"), num_pages=5, is_pdf=True)
    bom = list(BoxEntry("a", 1, 2, 3, 4).as_state())
    payload = {"dpi": 0, "paginas": {"0": [bom, ["torto"]], "1": [["torto"]], "x": [bom], "2": []},
               "sujas": [0, "y"]}
    assert sessao.aplicar_payload(payload) == 2            # a 0 e a 2, que o usuário esvaziou
    assert len(sessao.boxes_for(0)) == 1
    [aviso] = _avisos(caplog, "ficaram de fora")
    assert "2 página(s) (1, x)" in aviso.getMessage() and "2 box(es)" in aviso.getMessage()
    assert _avisos(caplog, "página que não existe: 'y'")


def test_o_rascunho_inteiro_nao_avisa(caplog, tmp_path):
    sessao = DocumentSession(str(tmp_path / "l.pdf"), num_pages=5, is_pdf=True)
    assert sessao.aplicar_payload({"paginas": {"0": [list(BoxEntry("a", 1, 2, 3, 4).as_state())]}}) == 1
    assert not caplog.records


def test_o_peso_que_nao_se_prepara_fala(monkeypatch, caplog):
    from core import ocr_training

    monkeypatch.setattr(ocr_training, "_status_engine", lambda nome, modulo: ocr_training.EngineTrainingStatus(
        nome, True))

    def falha(*a):
        raise RuntimeError("sem rede")

    estados = preparar_engines(types.SimpleNamespace(preparar_easyocr=falha, preparar_paddleocr=falha),
                               preparar_pesos=True)
    assert "sem rede" in estados[1].message and "sem rede" in estados[2].message
    assert _avisos(caplog, "EasyOCR ficou sem os pesos") and _avisos(caplog, "PaddleOCR ficou sem os pesos")


def _paddle(monkeypatch, erro):
    class Modelo:
        def predict(self, *a, **k):
            raise erro

    servico = OCRService()
    monkeypatch.setattr(servico, "_init_paddleocr", lambda *a: Modelo())
    return servico


@pytest.mark.parametrize("metodo", ["paddleocr_ocr_conf", "paddleocr_linha_conf"])
def test_o_recorte_que_o_paddle_recusa_fala_uma_vez(monkeypatch, caplog, metodo):
    servico = _paddle(monkeypatch, ValueError("recorte vazio"))
    for _ in range(3):
        assert getattr(servico, metodo)(np.zeros((4, 4, 3), np.uint8)) == ("", 0.0)
    assert len(_avisos(caplog, "PaddleOCR recusou um recorte")) == 1


@pytest.mark.parametrize("metodo", ["paddleocr_ocr_conf", "paddleocr_linha_conf"])
@pytest.mark.parametrize("erro", [KeyError("campo"), TypeError("assinatura")])
def test_o_que_nao_e_do_recorte_sobe(monkeypatch, metodo, erro):
    with pytest.raises(type(erro)):
        getattr(_paddle(monkeypatch, erro), metodo)(np.zeros((4, 4, 3), np.uint8))


def test_a_resposta_torta_do_paddle_fala(caplog):
    assert OCRService._resultado_paddle(types.SimpleNamespace(json="{ quebrado")) == ("", 0.0)
    assert _avisos(caplog, "JSON que não se lê")
    assert OCRService._resultado_paddle({"rec_text": "A", "rec_score": "muita"}) == ("A", 0.0)
    assert OCRService._resultado_paddle([[[0, 0], ("B", "muita")]]) == ("B", 0.0)
    assert len(_avisos(caplog, "sem confiança")) == 1


def _bloco(kind, valor, **estilo):
    return EditorialBlock("b1", kind, 0, [], Decision(valor, [], "automatic"), style=estilo)


def test_a_imagem_do_diagrama_que_nao_se_le_fala(caplog):
    bloco = _bloco("diagram", {"fen": "8/8/8/8/8/8/8/4K2k w - - 0 1", "png_base64": "isto não é base64!"})
    assert imagem_do_diagrama(bloco)[1] == "desenho"
    assert _avisos(caplog, "a imagem guardada do diagrama b1 não se lê")


def test_a_enfase_que_nao_se_le_fala_uma_vez(caplog):
    bloco = _bloco("paragraph", "texto", bold_spans=[["a", "b"], [0, 2]], italic_spans=[[1]])
    for _ in range(2):
        trechos_com_estilo("texto", bloco)
    assert len(_avisos(caplog, "faixa de negrito")) == 1
    assert len(_avisos(caplog, "faixa de itálico")) == 1


# ----------------------------------------------------------------------
# ui
# ----------------------------------------------------------------------

def _falha(*a, **k):
    raise OSError("disco cheio")


def test_a_preferencia_que_nao_grava_fala(monkeypatch, caplog):
    from tkinter import filedialog

    from ui.documento import Documento

    class Config:
        set = staticmethod(lambda *a: None)
        get = staticmethod(lambda *a: None)
        save = staticmethod(_falha)

    janela = types.SimpleNamespace(_configuracoes=lambda: Config, CHAVE_DA_JANELA="janela",
                                   _estado_da_janela=lambda anterior: {})
    documento = Documento(janela)
    documento.gravar_estado_da_janela()
    assert _avisos(caplog, "a geometria e os filtros da janela não ficaram guardados")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: "C:/livros/l.pdf")
    assert documento._perguntar_entrada("Abrir", []) == "C:/livros/l.pdf"
    assert _avisos(caplog, "não ficou guardada")


def test_a_preferencia_que_nao_se_le_fala(monkeypatch, caplog):
    from tkinter import filedialog

    from ui.documento import Documento

    documento = Documento(types.SimpleNamespace(_configuracoes=_falha, CHAVE_DA_JANELA="janela"))
    documento.restaurar_estado_da_janela()
    assert _avisos(caplog, "não se leram")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: "")
    documento._perguntar_entrada("Abrir", [])
    assert _avisos(caplog, "a pasta da última vez não se leu")


def test_as_opcoes_da_exportacao_que_nao_gravam_falam(caplog):
    from ui.dialogo_de_exportacao import DialogoDeExportacao

    caixa = DialogoDeExportacao.__new__(DialogoDeExportacao)
    caixa._settings = types.SimpleNamespace(set=lambda *a: None, save=_falha)
    caixa._guardar(types.SimpleNamespace(saida="x.epub", para_settings=dict))
    assert _avisos(caplog, "as opções desta exportação não ficaram guardadas")


def test_a_linha_que_nao_se_le_pelos_glifos_fala(caplog):
    from ui.dialogo_rotulagem import DialogoRotulagem

    caixa = DialogoRotulagem.__new__(DialogoRotulagem)
    caixa.app = types.SimpleNamespace(
        image=np.zeros((10, 10), np.uint8),
        learning_service=types.SimpleNamespace(load_predictor=lambda: True, ler_texto=_falha))
    assert caixa._ler_por_glifos([BoxEntry("", 1, 1, 5, 5)]) == ("", 0.0)
    assert _avisos(caplog, "a linha não se leu pelos glifos")


def test_a_sondagem_da_camada_que_falha_fala(monkeypatch, tmp_path, caplog):
    import fitz

    from core import pdf_nativo
    from ui.exportacao import Exportacao

    pdf = tmp_path / "l.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    monkeypatch.setattr(pdf_nativo, "amostrar", _falha)
    vistos = {}

    class Caixa:
        def __init__(self, parent, **kw):
            vistos.update(kw)

        def mostrar(self):
            return None

    janela = types.SimpleNamespace(
        parent=None, _idioma_do_livro=lambda *a, **k: ("en", True), _configuracoes=None,
        ocr_service=types.SimpleNamespace(tesseract_disponivel=lambda i: (True, "")),
        _esperar_sem_travar=lambda titulo, f: f(), DIALOGO_DE_EXPORTACAO=Caixa)
    Exportacao(janela)._preparar_exportacao(str(pdf), {}, "Exportar")
    assert vistos["camada"] is None and _avisos(caplog, "o livro vai ao OCR")


def test_os_motivos_da_suspeita_que_nao_se_leem_falam(caplog):
    from ui.editor.propriedades import PainelDePropriedades

    painel = PainelDePropriedades.__new__(PainelDePropriedades)
    painel.alvo = {"objeto": types.SimpleNamespace(origem=None, extras={"data-suspeito": "line_lost"})}
    painel.descrever_suspeita = _falha
    mostrado = []
    painel._fixo = lambda rotulo, texto, linha: mostrado.append(texto) or linha
    painel._acao = lambda *a: None
    painel._origem_e_suspeita(0)
    assert mostrado == ["line_lost"] and _avisos(caplog, "os motivos da suspeita não se leram")


def test_o_gancho_do_token_que_falha_fala_uma_vez(caplog):
    from ui.editor.texto_rico import TextoRico

    texto = TextoRico.__new__(TextoRico)
    texto.posicao = lambda: ("b1", 5)
    texto.ao_fechar_token = _falha
    for _ in range(3):
        texto._fechou_token()
    assert len(_avisos(caplog, "o gancho do token falhou")) == 1


# ----------------------------------------------------------------------
# A varredura
# ----------------------------------------------------------------------

#: Os `except` largos de corpo só `pass` que a RG-18 decidiu manter mudos, com o porquê.
MUDOS = {
    ("ui/editor/xadrez.py", "_instalar_painel"):
        "o rótulo de espera pode não existir: destruí-lo não muda nada que se veja",
}


def _mudos():
    achados = []
    for caminho in sorted((RAIZ / "ui").rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for funcao in [n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for no in ast.walk(funcao):
                largo = isinstance(no, ast.ExceptHandler) and (
                    no.type is None or ast.unparse(no.type) in ("Exception", "BaseException"))
                if largo and all(isinstance(x, ast.Pass) for x in no.body):
                    achados.append((caminho.relative_to(RAIZ).as_posix(), funcao.name))
    return achados


def test_em_ui_nao_ha_except_largo_que_so_passa():
    assert sorted(_mudos()) == sorted(MUDOS), json.dumps(_mudos(), indent=1)
    assert all(MUDOS.values())
