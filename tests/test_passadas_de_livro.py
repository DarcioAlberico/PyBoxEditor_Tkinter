"""As passadas de livro num lugar, com guarda por página (RG-14, R-20).

- Uma página que levanta derrubava a exportação do livro inteiro: agora a da camada cai para
  o OCR e a do OCR sai como página com falha, num campo que a conclusão e a fila mostram.
- O cancelamento no meio da página continua cancelando (F119).
- `juntar_entre_paginas` e `lados_pelos_lances` só rodavam no caminho sem OCR; agora os dois
  chamam `pdf_nativo.passadas_de_livro`.
- O registro que vem da página seguinte vira `-1`: ele indexa o roteamento de outra página.
"""

import logging
import os

import fitz
import pytest

from core import lado_a_jogar, livro, pdf_nativo
from core.editorial_adapters import (pagina_editorial_para_extraida, pagina_extraida_para_pagina,
                                     paginas_extraidas_para_documento)
from core.editorial_review import build_review_queue
from core.lexico import Lexico
from core.ocr_runtime import OCRCancelled
from core.pagina import Figura, PaginaExtraida, Paragrafo
from core.services.task_service import Cancelled
from tests.test_f26_livro import _App, _pdf_de_uma_pagina


def _classificar(_recorte, referencia=None):
    return ("a", 0.99)


def _pdf(caminho, paginas=3):
    with fitz.open() as doc:
        for n in range(paginas):
            p = doc.new_page(width=300, height=200)
            for i in range(4):
                p.insert_text((30, 40 + i * 16), f"Uma linha de prosa comum, pagina {n + 1}.",
                              fontsize=10)
        doc.save(caminho)
    return str(caminho)


def _quebrar(monkeypatch, modulo, numeros, erro):
    """`modulo.extrair_pagina` levanta `erro` nas páginas de `numeros`."""
    original = modulo.extrair_pagina

    def extrair_pagina(page, *args, **kwargs):
        if kwargs.get("numero") in numeros:
            raise erro
        return original(page, *args, **kwargs)

    monkeypatch.setattr(modulo, "extrair_pagina", extrair_pagina)


# ----------------------------------------------------------------------
# O guarda por página
# ----------------------------------------------------------------------

def test_a_pagina_do_ocr_que_levanta_nao_derruba_o_livro(tmp_path, monkeypatch, caplog):
    _quebrar(monkeypatch, livro, {1}, ValueError("recorte vazio"))
    with caplog.at_level(logging.WARNING):
        paginas = livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, dpi=150)
    assert [p.numero for p in paginas] == [0, 1, 2]
    assert [bool(p.falha) for p in paginas] == [False, True, False]
    assert "ValueError: recorte vazio" in paginas[1].falha
    # O conteúdo não some: a página entra como imagem, e é o que a fila mostra.
    [figura] = paginas[1].blocos
    assert isinstance(figura, Figura) and figura.origem == "pagina" and figura.png
    assert all(p.caracteres > 0 for p in (paginas[0], paginas[2]))
    assert any("gina 2" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_a_pagina_da_camada_que_levanta_vai_ao_ocr(tmp_path, monkeypatch, caplog):
    _quebrar(monkeypatch, pdf_nativo, {1}, ValueError("fonte estranha"))
    with caplog.at_level(logging.WARNING):
        paginas = livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, dpi=150, camada="sempre")
    assert [p.leitura for p in paginas] == ["camada", "imagem", "camada"]
    assert not any(p.falha for p in paginas) and paginas[1].caracteres > 0
    assert any("vai ao OCR" in r.getMessage() for r in caplog.records)


def test_o_reparo_pela_camada_que_levanta_deixa_a_pagina_como_o_ocr_a_leu(tmp_path, monkeypatch):
    original = pdf_nativo.avaliar_pagina

    def clearscan(page, **kwargs):
        veredito = original(page, **kwargs)
        return pdf_nativo.Veredito(veredito.numero, False, pdf_nativo.MOTIVO_CLEARSCAN, veredito.caracteres,
                                   veredito.fontes, veredito.tipografica)

    monkeypatch.setattr(pdf_nativo, "avaliar_pagina", clearscan)
    _quebrar(monkeypatch, pdf_nativo, {0, 1, 2}, ValueError("sem camada"))
    paginas = livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, dpi=150, camada="auto")
    assert all(p.caracteres > 0 and not p.falha for p in paginas)


@pytest.mark.parametrize("modulo, camada", [(livro, "nunca"), (pdf_nativo, "sempre")])
def test_o_cancelamento_no_meio_da_pagina_cancela(tmp_path, monkeypatch, modulo, camada):
    _quebrar(monkeypatch, modulo, {1}, OCRCancelled())
    with pytest.raises(Cancelled):
        livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, dpi=150, camada=camada)


def test_o_cancelamento_no_caminho_sem_ocr_cancela(tmp_path, monkeypatch):
    _quebrar(monkeypatch, pdf_nativo, {1}, OCRCancelled())
    with pytest.raises(Cancelled):
        pdf_nativo.extrair(_pdf(tmp_path / "l.pdf"), forcar=True)


def test_o_livro_em_que_nenhuma_pagina_se_le_levanta(tmp_path, monkeypatch):
    """O modelo que não carrega falha em todas: o livro vazio não sai como pronto."""
    _quebrar(monkeypatch, livro, {0, 1, 2}, RuntimeError("modelo quebrado"))
    with pytest.raises(RuntimeError, match="modelo quebrado"):
        livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, dpi=150)


# ----------------------------------------------------------------------
# As passadas, nos dois caminhos
# ----------------------------------------------------------------------

def _lexico():
    return Lexico(palavras={"has", "and", "read", "so", "the"})


def _paginas_falsas(monkeypatch, paginas):
    monkeypatch.setattr(livro, "extrair_pagina",
                        lambda page, classificar, *, numero, **k: paginas[numero])


def test_o_paragrafo_partido_entre_paginas_volta_a_ser_um_no_ocr(tmp_path, monkeypatch):
    a = PaginaExtraida(0, [Paragrafo("a game by the Dutch grandmaster, who clearly",
                                     inicios=[0, 20], registros=[0, 1])],
                       roteamento=[{"texto": "x"}, {"texto": "y"}])
    b = PaginaExtraida(1, [Paragrafo("has read the books.", inicios=[0], registros=[0]),
                           Paragrafo("Another one.", inicios=[0], registros=[1])],
                       roteamento=[{"texto": "z"}, {"texto": "w"}])
    _paginas_falsas(monkeypatch, [a, b])
    livro.extrair(_pdf(tmp_path / "l.pdf", 2), _classificar, lex=_lexico())
    [junto] = a.blocos
    assert junto.texto == "a game by the Dutch grandmaster, who clearly has read the books."
    # O registro da página seguinte não indexa o roteamento desta.
    assert junto.registros == [0, 1, -1]
    assert [p.texto for p in b.blocos] == ["Another one."]


@pytest.mark.parametrize("comeco, lex", [
    ("olutions 8.♕xg7+", Lexico(palavras={"has"})),      # o título sem a inicial
    ("xercises for you", Lexico(palavras={"has"})),
    ("nn", Lexico(palavras={"has", "nn"})),                 # o dicionário tem `nn`
    ("has read the books.", None),                          # sem dicionário não há prova
])
def test_o_titulo_sem_a_inicial_nao_continua_a_pagina_anterior(tmp_path, monkeypatch, comeco, lex):
    """Medido no Yusupov inteiro: as quatro junções da régua da minúscula eram títulos."""
    a = PaginaExtraida(0, [Paragrafo("7...♔f4 8.♕h6#")])
    b = PaginaExtraida(1, [Paragrafo(comeco)])
    _paginas_falsas(monkeypatch, [a, b])
    livro.extrair(_pdf(tmp_path / "l.pdf", 2), _classificar, lex=lex)
    assert [p.texto for p in a.blocos] == ["7...♔f4 8.♕h6#"]
    assert [p.texto for p in b.blocos] == [comeco]


@pytest.mark.parametrize("fen, antes, depois, lado", [
    # Diagramas do Yusupov, com o lado que o livro imprime ao lado de cada um.
    ("3r2k1/p6p/1p1n2p1/2pb1P2/N2p1P2/1P1P2P1/PR3K2/2Q1N2r w - - 0 1",
     "9.♘e1 ♗d5 10.♖b2 ♖h1+ 11.♔f2", "11...♘xf5!? 12.g4 ♘e3", "b"),             # p. 31
    ("8/p3R3/5P2/1p4P1/8/1P3k1K/8/3r4 w - - 0 1",
     "11...♖d1+ 12.♔h2 ♖d2+ 13.♔h3 ♖d1", "14.♖e3+! Winning", "w"),                # p. 51
    ("r3k2r/pp2bpp1/1qp2n2/8/2Qp3p/3P2P1/PP2PPBP/R1B2RK1 w - - 0 1",
     "15...♘xc4 16.♕xc4", "16...♘g4! The knight", "b"),                           # p. 59
    ("4r1k1/p2b1p2/1p4BR/n3q3/3N4/6QP/P4PPK/3Rr3 w - - 0 1",
     "27.♔h2 ♕e5", "28.♗xf7+! This", "w"),                                        # p. 89
    # O lance que "continua" não se joga na posição: o texto de antes é de uma variante.
    ("5rk1/p2brp2/1p1q2pR/n2P4/3N4/3Q3P/P4PP1/1B1R2K1 w - - 0 1",
     "21.♘f5 22...♔g8", "23.♕d3 g6 23...f5", None),                               # p. 88
    ("r4rk1/pp1qnpb1/3p2pp/2p5/3nPB2/P1NP2P1/1PP3QP/1R2NRK1 w - - 0 1",
     "13.f4 ♘d4 14.♖b1", "14...exf4 15.♗xf4", None),                              # p. 179
])
def test_o_lance_de_depois_tem_de_ser_jogavel(fen, antes, depois, lado):
    assert lado_a_jogar.pelo_lance(antes, fen, depois) == lado


@pytest.mark.parametrize("fen, lado, san, legal", [
    ("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1", "w", "exd6", True),       # en passant
    ("4k3/8/8/4P3/8/8/8/4K3 w - - 0 1", "w", "exd6", False),
    ("4k2r/8/8/8/8/8/8/4K3 w - - 0 1", "b", "0–0", True),
    ("4k3/8/8/8/8/8/8/4K3 w - - 0 1", "b", "0–0", False),
    ("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1", "w", "b8=Q", True),
    ("4k3/8/8/8/8/8/8/R3K2R w - - 0 1", "w", "Rad1", True),
    ("4k3/8/8/8/8/8/8/R3K2R w - - 0 1", "w", "Rbd1", False),
])
def test_o_lance_jogavel(fen, lado, san, legal):
    assert lado_a_jogar._lance_legal(fen, lado, san) is legal


def test_o_paragrafo_com_o_cabecalho_cortado_tambem_se_junta(tmp_path, monkeypatch):
    """`_cortar` devolvia `ndarray`, e a soma dos vetores levantava fora do guarda: a
    passada entre páginas derrubaria o livro que tem cabeçalho corrente."""
    from core import negrito

    paginas = []
    for n in range(3):
        cabeca, corpo = "Attacking Manual ", "and so the game went on, as it was"
        texto = cabeca + corpo
        paginas.append(PaginaExtraida(n, [Paragrafo(
            texto, pesos=negrito.vetor([0.1] * len(texto)), lacunas=negrito.vetor([1.0] * len(texto)),
            topo=5, pe=60, inicios=[0, len(cabeca)], registros=[0, 1])], altura=1000, largura=700))
    _paginas_falsas(monkeypatch, paginas)
    livro.extrair(_pdf(tmp_path / "l.pdf"), _classificar, lex=_lexico())
    junto = paginas[0].blocos[-1]
    assert paginas[0].cabecalhos == ["Attacking Manual"]
    assert junto.texto.startswith("and so the game went on, as it was and so")
    assert len(junto.pesos) == len(junto.lacunas) == len(junto.texto)


def test_o_lado_pelo_lance_da_pagina_anterior_no_ocr(tmp_path, monkeypatch):
    from tests.test_camada_quality_chess import FEN_DO_ROQUE
    figura = Figura(png=b"", largura=1, altura=1, fen=FEN_DO_ROQUE, origem="recorte")
    a = PaginaExtraida(0, [Paragrafo("11.♘f3 ♘xc4 12.♕xc4 ♗g4 13.♕b3 0–0–0")])
    b = PaginaExtraida(1, [figura, Paragrafo("14.♖e1?!")])
    _paginas_falsas(monkeypatch, [a, b])
    livro.extrair(_pdf(tmp_path / "l.pdf", 2), _classificar)
    assert (figura.fen.split()[1], figura.lado_origem) == ("w", "lance")


def test_os_dois_caminhos_chamam_a_mesma_funcao(tmp_path, monkeypatch):
    chamadas = []
    original = pdf_nativo.passadas_de_livro

    def espia(paginas, **kwargs):
        chamadas.append(len(paginas))
        return original(paginas, **kwargs)

    monkeypatch.setattr(pdf_nativo, "passadas_de_livro", espia)
    caminho = _pdf(tmp_path / "l.pdf")
    pdf_nativo.extrair(caminho, forcar=True)
    livro.extrair(caminho, _classificar, dpi=150)
    assert chamadas == [3, 3]


def test_a_pagina_com_falha_nao_se_junta_nem_passa_o_lance_adiante():
    from tests.test_camada_quality_chess import FEN_DO_ROQUE
    a = PaginaExtraida(0, [Paragrafo("13.♕b3 0–0–0")])
    quebrada = PaginaExtraida(1, [Paragrafo("[página 2 não lida]")], falha="ValueError: x")
    figura = Figura(png=b"", largura=1, altura=1, fen=FEN_DO_ROQUE, origem="recorte")
    c = PaginaExtraida(2, [Paragrafo("continua assim."), figura, Paragrafo("14.♖e1?!")])
    assert pdf_nativo.juntar_entre_paginas([a, quebrada, c]) == 0
    assert pdf_nativo.lados_pelos_lances([a, quebrada, c]) == 0


# ----------------------------------------------------------------------
# A falha aparece: na fila e na conclusão
# ----------------------------------------------------------------------

def _com_falha():
    return PaginaExtraida(1, [Figura(png=b"png", largura=1, altura=1, origem="pagina")],
                          falha="ValueError: recorte vazio")


def test_a_pagina_com_falha_vai_para_a_fila_e_volta_do_ir():
    documento = paginas_extraidas_para_documento(
        [PaginaExtraida(0, [Paragrafo("Prosa.")]), _com_falha()], document_id="livro")
    [item] = build_review_queue(documento).items
    assert item.page_index == 1 and "page_failed" in item.reason_codes
    assert any("recorte vazio" in m for m in item.motivos)
    assert any("recorte vazio" in aviso for aviso in documento.pages[1].warnings)
    assert pagina_editorial_para_extraida(documento.pages[1]).falha == "ValueError: recorte vazio"
    # O IR da página sem falha continua o de antes.
    assert "falha" not in documento.pages[0].observations["legacy_page"]


def test_o_registro_menos_um_nao_aponta_linha_nenhuma():
    pagina = PaginaExtraida(0, [Paragrafo("um dois tres", inicios=[0, 3, 8], registros=[0, 1, -1])],
                            roteamento=[{"texto": "um"}, {"texto": "dois"}])
    bloco = pagina_extraida_para_pagina(pagina).blocks[0]
    assert [linha["registro"] for linha in bloco.metadata["linhas"]] == [0, 1]


@pytest.mark.parametrize("acao", ["rodar", "rodar_editorial"])
def test_a_conclusao_diz_as_paginas_com_falha(tmp_path, monkeypatch, acao):
    entrada = str(tmp_path / "livro.pdf")
    _pdf_de_uma_pagina(entrada)
    png = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 4, 4), False).tobytes("png")
    monkeypatch.setattr(livro, "extrair", lambda *a, **k: [
        PaginaExtraida(0, [Paragrafo("Prosa comum.")]),
        PaginaExtraida(1, [Figura(png=png, largura=4, altura=4, origem="pagina")],
                       falha="ValueError: recorte vazio")])
    with _App(entrada, os.path.join(str(tmp_path), "s.epub")) as app:
        getattr(app, acao)()
        assert not app.erros, app.erros
        texto = "\n".join(str(a) for a in app.avisos)
    assert "1 página(s) não puderam ser lidas" in texto and "2" in texto, texto
    assert "recorte vazio" in texto
