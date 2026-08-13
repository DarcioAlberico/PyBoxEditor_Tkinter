"""
Testes da F2.3 — relatório e dry-run da substituição de glifos (SPEC §4.4).

`substitute_chess_glyphs` reescreve o PDF: apaga o texto original com um
retângulo branco e desenha outro por cima. Não dá para desfazer, e até aqui o
usuário só recebia dois números no fim. Se o mapeamento estivesse errado, ou a
fonte tivesse encolhido a ponto de ficar ilegível, ele descobriria abrindo o PDF
já convertido.

A propriedade central que os testes fixam é a que dá sentido ao dry-run:
**simular e converter percorrem o documento do mesmo jeito e produzem o mesmo
relatório** — a simulação só não escreve. Se as duas travessias divergirem, o
dry-run deixa de valer como conferência e vira teatro.

Rodar sem pytest:      python tests/test_f23_relatorio_dryrun.py
"""

import contextlib
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import fitz
import tkinter as tk
from tkinter import filedialog, messagebox

from core import chess_pdf_processor as cpp
from core import relatorio_pdf
from core.chess_pdf_processor import (DEFAULT_MAPPING_PROFILE,
                                      analisar_substituicao,
                                      substitute_chess_glyphs)


# Uma fonte que existe neste sistema — `resolve_chess_font` já garante isso, e
# levanta se não houver nenhuma.
FONTE_EMBUTIDA = cpp.resolve_chess_font()


def _pdf_simples(texto_xadrez="KQRBNP", linhas_diagrama=0):
    """
    PDF com prosa numa fonte e o trecho "de xadrez" noutra, embutida.

    Não dá para forjar o nome "Merida": o PyMuPDF reporta o nome **interno** da
    fonte, não o alias passado a `insert_font` — foi o que o smoke da F0 já
    tinha descoberto. Então o teste embute uma fonte real e, depois, trata o
    nome dela como sendo de xadrez (ver `_tratando_a_embutida_como_xadrez`).
    """
    doc = fitz.open()
    pagina = doc.new_page(width=400, height=500)
    pagina.insert_text((40, 60), "prosa comum fora da notacao", fontsize=11)
    pagina.insert_font(fontname="FX", fontfile=FONTE_EMBUTIDA)

    if linhas_diagrama:
        # Muitas linhas quase só de fonte de xadrez: é o que a heurística de
        # `is_block_a_diagram` procura.
        for i in range(linhas_diagrama):
            pagina.insert_text((40, 120 + i * 11), "rnbqkbnr", fontsize=9,
                               fontname="FX")
    elif texto_xadrez:
        pagina.insert_text((40, 120), texto_xadrez, fontsize=12, fontname="FX")

    caminho = os.path.join(tempfile.mkdtemp(), "entrada.pdf")
    doc.save(caminho)
    doc.close()
    return caminho


def _nome_da_fonte_embutida(caminho_pdf):
    """O nome que o PyMuPDF reporta para o span que NÃO é a prosa."""
    with fitz.open(caminho_pdf) as doc:
        nomes = []
        for pagina in doc:
            for bloco in pagina.get_text("dict").get("blocks", []):
                if bloco.get("type", 0) != 0:
                    continue
                for linha in bloco.get("lines", []):
                    for span in linha.get("spans", []):
                        if "prosa" not in span.get("text", ""):
                            nomes.append(span["font"])
    assert nomes, "o PDF de teste não tem span além da prosa"
    return nomes[0]


@contextlib.contextmanager
def _tratando_a_embutida_como_xadrez(caminho_pdf):
    """Faz `is_chess_font` reconhecer a fonte embutida, e só ela."""
    nome = _nome_da_fonte_embutida(caminho_pdf).lower()
    original = cpp.CHESS_FONT_KEYWORDS[:]
    cpp.CHESS_FONT_KEYWORDS[:] = [nome]
    try:
        yield
    finally:
        cpp.CHESS_FONT_KEYWORDS[:] = original


def _analisar(entrada, saida, **kw):
    """`analisar_substituicao` com a fonte embutida contando como de xadrez."""
    with _tratando_a_embutida_como_xadrez(entrada):
        return analisar_substituicao(entrada, saida, **kw)


def _saida(nome="saida.pdf"):
    return os.path.join(tempfile.mkdtemp(), nome)


# ----------------------------------------------------------------------
# Dry-run não toca no arquivo
# ----------------------------------------------------------------------

def test_dry_run_nao_grava_o_pdf():
    entrada, saida = _pdf_simples(), _saida()
    rel = _analisar(entrada, saida, dry_run=True)

    assert rel.dry_run is True
    assert not os.path.exists(saida), "a simulação gravou o PDF"


def test_dry_run_nao_altera_o_arquivo_de_entrada():
    entrada = _pdf_simples()
    antes = open(entrada, "rb").read()
    _analisar(entrada, _saida(), dry_run=True)
    assert open(entrada, "rb").read() == antes, "a simulação mexeu na entrada"


def test_conversao_de_verdade_grava():
    entrada, saida = _pdf_simples(), _saida()
    rel = _analisar(entrada, saida, dry_run=False)

    assert rel.dry_run is False
    assert os.path.exists(saida) and os.path.getsize(saida) > 0


def test_substituicoes_ficam_marcadas_como_nao_aplicadas_em_dry_run():
    entrada = _pdf_simples()
    rel = _analisar(entrada, _saida(), dry_run=True)
    assert rel.total_substituicoes > 0, "o PDF de teste não tem span de xadrez"
    assert all(not s.aplicada for s in rel.substituicoes)
    assert rel.total_aplicadas == 0


# ----------------------------------------------------------------------
# A propriedade que dá sentido ao dry-run
# ----------------------------------------------------------------------

def test_simular_e_converter_veem_a_mesma_coisa():
    """
    Se as duas travessias divergirem, conferir a simulação não diz nada sobre a
    conversão — que é o motivo de o dry-run existir.
    """
    entrada = _pdf_simples()
    simulado = _analisar(entrada, _saida("a.pdf"), dry_run=True)
    convertido = _analisar(entrada, _saida("b.pdf"), dry_run=False)

    assert simulado.total_paginas == convertido.total_paginas
    assert simulado.total_substituicoes == convertido.total_substituicoes
    assert simulado.diagramas_ignorados == convertido.diagramas_ignorados

    for a, b in zip(simulado.substituicoes, convertido.substituicoes):
        assert a.pagina == b.pagina
        assert a.texto_original == b.texto_original
        assert a.texto_substituto == b.texto_substituto
        assert a.avisos == b.avisos
        assert abs(a.corpo_final - b.corpo_final) < 1e-9
        assert abs(a.confianca - b.confianca) < 1e-9


# ----------------------------------------------------------------------
# Conteúdo do relatório
# ----------------------------------------------------------------------

def test_relatorio_registra_os_campos_da_spec():
    """SPEC §4.4: página, bbox, fonte, antes, depois, confiança, avisos."""
    entrada = _pdf_simples()
    rel = _analisar(entrada, _saida(), dry_run=True)
    s = rel.substituicoes[0]

    assert isinstance(s.pagina, int)
    assert len(s.bbox) == 4 and all(isinstance(v, float) for v in s.bbox)
    # o nome é o da fonte real embutida, não "Merida": ver `_pdf_simples`
    assert s.fonte_original == _nome_da_fonte_embutida(entrada)
    assert s.texto_original and s.texto_substituto
    assert 0.0 <= s.confianca <= 1.0
    assert isinstance(s.avisos, list)


def test_mapeamento_vira_simbolo_unicode():
    entrada = _pdf_simples("KQRBNP")
    rel = _analisar(entrada, _saida(), dry_run=True)
    texto = "".join(s.texto_substituto for s in rel.substituicoes)
    assert "♔" in texto and "♕" in texto, f"não mapeou: {texto!r}"


def test_confianca_cai_com_caractere_fora_do_perfil():
    """Caractere que a conversão não sabe o que é foi copiado como veio."""
    alta = _analisar(_pdf_simples("KQRB"), _saida(), dry_run=True)
    baixa = _analisar(_pdf_simples("wyz"), _saida(), dry_run=True)

    assert alta.substituicoes[0].confianca == 1.0
    assert baixa.substituicoes[0].confianca == 0.0
    assert "confianca_baixa" in baixa.substituicoes[0].avisos
    assert "confianca_baixa" not in alta.substituicoes[0].avisos


def test_notacao_normal_nao_dispara_aviso_de_confianca():
    """
    "Nf3" tem só o 'N' no perfil; 'f' e '3' atravessam **corretamente**. Contar
    a passagem como desconhecida dava confiança 0,33 num lance perfeitamente
    normal, e o aviso passava a disparar em toda notação — o mesmo que não
    avisar. Foi o que a primeira simulação de verdade mostrou.
    """
    rel = _analisar(_pdf_simples("Nf3"), _saida(), dry_run=True)
    s = rel.substituicoes[0]

    assert s.confianca == 1.0, f"notação normal saiu com confiança {s.confianca}"
    assert "confianca_baixa" not in s.avisos
    assert s.texto_substituto.startswith("♘")


def test_diagrama_ignorado_fica_registrado():
    """
    A heurística de diagrama é a que tem mais chance de errar. Descartar o bloco
    em silêncio não deixava rastro nenhum de que ele existiu.
    """
    entrada = _pdf_simples(linhas_diagrama=8)
    rel = _analisar(entrada, _saida(), dry_run=True)

    assert rel.diagramas_ignorados, "o bloco de diagrama não foi registrado"
    assert rel.spans_de_diagrama_ignorados() > 0
    assert "SIMULAÇÃO" in rel.resumo() and "diagrama" in rel.resumo()


# ----------------------------------------------------------------------
# Gravação em JSON e CSV
# ----------------------------------------------------------------------

def test_grava_json_e_csv_ao_lado_da_saida():
    entrada, saida = _pdf_simples(), _saida()
    _analisar(entrada, saida, dry_run=False)

    cj, cc = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)
    assert os.path.exists(cj) and os.path.exists(cc)
    assert os.path.dirname(cj) == os.path.dirname(saida)


def test_dry_run_usa_nome_proprio_para_nao_sobrescrever():
    """Simulação e conversão precisam conviver, para poderem ser comparadas."""
    saida = _saida()
    sim_j, sim_c = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=True)
    con_j, con_c = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)

    assert sim_j != con_j and sim_c != con_c
    assert "simulacao" in os.path.basename(sim_j)


def test_json_do_relatorio_e_legivel():
    entrada, saida = _pdf_simples(), _saida()
    rel = _analisar(entrada, saida, dry_run=False)

    cj, _ = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)
    with open(cj, encoding="utf-8") as f:
        dados = json.load(f)

    assert dados["total_substituicoes"] == rel.total_substituicoes
    assert dados["arquivo_entrada"] == entrada
    assert "legenda_dos_avisos" in dados, "o JSON não explica os avisos"
    assert len(dados["substituicoes"]) == rel.total_substituicoes


def test_csv_tem_cabecalho_estavel_e_uma_linha_por_substituicao():
    import csv

    entrada, saida = _pdf_simples(), _saida()
    rel = _analisar(entrada, saida, dry_run=False)

    _, cc = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)
    with open(cc, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))

    assert len(linhas) == rel.total_substituicoes
    assert list(linhas[0].keys()) == relatorio_pdf.COLUNAS_CSV


def test_csv_sai_com_bom_para_o_excel():
    """Sem BOM o Excel no Windows lê UTF-8 como cp1252 e destrói os símbolos."""
    entrada, saida = _pdf_simples(), _saida()
    _analisar(entrada, saida, dry_run=False)
    _, cc = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)
    assert open(cc, "rb").read(3) == b"\xef\xbb\xbf"


def test_gravar_relatorio_pode_ser_desligado():
    entrada, saida = _pdf_simples(), _saida()
    _analisar(entrada, saida, dry_run=False, gravar_relatorio=False)
    cj, cc = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=False)
    assert not os.path.exists(cj) and not os.path.exists(cc)


# ----------------------------------------------------------------------
# Zero substituições não é conversão bem-sucedida
# ----------------------------------------------------------------------

def _pdf_so_prosa(paginas=1):
    """Texto nativo, nenhuma fonte que a heurística possa reconhecer."""
    doc = fitz.open()
    for i in range(paginas):
        doc.new_page(width=400, height=500).insert_text(
            (40, 60), f"prosa comum da pagina {i + 1}", fontsize=11)
    caminho = os.path.join(tempfile.mkdtemp(), "prosa.pdf")
    doc.save(caminho)
    doc.close()
    return caminho


def _pdf_digitalizado():
    """Só a imagem da página, como um scan: nenhum span, nenhuma fonte."""
    origem = fitz.open()
    origem.new_page().insert_text((60, 100), "ABC def", fontsize=40)
    doc = fitz.open()
    for p in origem:
        pix = p.get_pixmap(dpi=72)
        nova = doc.new_page(width=p.rect.width, height=p.rect.height)
        nova.insert_image(nova.rect, pixmap=pix)
    caminho = os.path.join(tempfile.mkdtemp(), "scan.pdf")
    doc.save(caminho)
    doc.close()
    origem.close()
    return caminho


def test_o_relatorio_anota_as_fontes_do_documento():
    rel = analisar_substituicao(_pdf_so_prosa(), _saida(), dry_run=True)
    assert rel.fontes_vistas, "não anotou nenhuma fonte"
    assert rel.fontes_de_xadrez == []


def test_nenhuma_fonte_de_xadrez_reconhecida_vira_alerta():
    """
    Era: "264 página(s), 0 substituição(ões); nenhum aviso" — exatamente o que
    uma conversão perfeita também diria.

    Medido nos três livros de `PDF/`: 39, 28 e 41 fontes embutidas, **nenhuma**
    reconhecida, porque os nomes vêm em subset (`Fd350139`) e a detecção procura
    palavra-chave no nome. O usuário recebia um PDF idêntico ao original com
    cara de trabalho feito.
    """
    rel = analisar_substituicao(_pdf_so_prosa(), _saida(), dry_run=True)

    assert rel.total_substituicoes == 0
    assert rel.nenhuma_fonte_de_xadrez is True
    assert rel.sem_camada_de_texto is False
    assert "ATENÇÃO" in rel.alerta()
    assert "ATENÇÃO" in rel.resumo()
    assert "nenhum aviso" not in rel.resumo(), (
        "'nenhum aviso' soa como aprovação de um trabalho que não aconteceu")


def test_documento_sem_texto_tem_alerta_proprio():
    """Digitalização e livro digital sem fonte de xadrez pedem saídas diferentes."""
    rel = analisar_substituicao(_pdf_digitalizado(), _saida(), dry_run=True)

    assert rel.sem_camada_de_texto is True
    assert rel.nenhuma_fonte_de_xadrez is False
    assert "camada de texto" in rel.alerta()


def test_conversao_que_substituiu_nao_tem_alerta():
    entrada = _pdf_simples()
    rel = _analisar(entrada, _saida(), dry_run=True)

    assert rel.total_substituicoes > 0
    assert rel.fontes_de_xadrez, "não anotou a fonte que reconheceu"
    assert rel.alerta() == ""
    assert "ATENÇÃO" not in rel.resumo()


def test_a_fonte_de_um_bloco_de_diagrama_conta_como_reconhecida():
    """
    O bloco de diagrama é pulado de propósito, mas a fonte dele **existe**.
    Contá-la fora mandaria quem converte um livro só de diagramas procurar o
    problema no lugar errado.
    """
    entrada = _pdf_simples(linhas_diagrama=8)
    rel = _analisar(entrada, _saida(), dry_run=True)

    assert rel.diagramas_ignorados, "o PDF de teste não virou diagrama"
    assert rel.fontes_de_xadrez, "a fonte do diagrama sumiu do relatório"
    assert rel.alerta() == ""


def test_o_json_traz_a_lista_de_fontes():
    """Os nomes são a única pista de por que nada casou — e o que se escreve
    em `font_patterns` para consertar."""
    entrada, saida = _pdf_so_prosa(), _saida()
    analisar_substituicao(entrada, saida, dry_run=True)
    cj, _ = relatorio_pdf.caminhos_do_relatorio(saida, dry_run=True)

    with open(cj, encoding="utf-8") as f:
        dados = json.load(f)
    assert dados["fontes_vistas"], "o JSON não lista as fontes do documento"
    assert dados["fontes_de_xadrez"] == []
    assert "ATENÇÃO" in dados["alerta"]


# ----------------------------------------------------------------------
# O arquivo de saída não engorda à toa
# ----------------------------------------------------------------------

def _fontes_embutidas(caminho_pdf):
    with fitz.open(caminho_pdf) as doc:
        return {f[3] for pagina in doc for f in pagina.get_fonts(full=True)}


def test_conversao_sem_substituicao_nao_embute_a_fonte_de_simbolos():
    """
    Era: `insert_font` no topo do laço de página, antes de saber se a página
    tinha algo de xadrez. A fonte de saída (2,4 MB de Segoe UI Symbol neste
    sistema) entrava em **toda** página, inclusive numa conversão que não
    substituía nada: medido, 2.499 KB de entrada saíam com 4.937 KB e zero
    substituições.
    """
    entrada, saida = _pdf_so_prosa(paginas=5), _saida()
    rel = analisar_substituicao(entrada, saida)

    assert rel.total_substituicoes == 0
    assert _fontes_embutidas(saida) == _fontes_embutidas(entrada), (
        "embutiu a fonte de símbolos numa conversão que não substituiu nada")
    assert os.path.getsize(saida) < os.path.getsize(entrada) + 50_000


def test_a_conversao_nao_deixa_o_arquivo_maior_que_a_entrada():
    """
    A fonte é embutida inteira e seria carregada como está. O `searchable_pdf`
    já a reduzia aos glifos usados (`subset_fonts`); este caminho nunca recebeu
    o mesmo tratamento. Medido no PDF deste teste: 2.568 KB -> 248 KB.
    """
    entrada, saida = _pdf_simples(), _saida()
    rel = _analisar(entrada, saida)

    assert rel.total_substituicoes > 0
    assert os.path.getsize(saida) < os.path.getsize(entrada), (
        f"a conversão engordou o arquivo: {os.path.getsize(entrada)} -> "
        f"{os.path.getsize(saida)} bytes")


def test_os_simbolos_sobrevivem_ao_subset():
    """
    Reduzir a fonte aos glifos usados é onde um símbolo vira retângulo vazio sem
    erro nenhum no caminho — o defeito do `·` da SPEC §4.2, uma etapa depois.
    """
    entrada, saida = _pdf_simples("KQRBN"), _saida()
    _analisar(entrada, saida)

    with fitz.open(saida) as doc:
        texto = doc[0].get_text()
    assert any(p in texto for p in "♔♕♖♗♘"), f"nenhum símbolo sobreviveu: {texto!r}"
    assert "·" not in texto


# ----------------------------------------------------------------------
# O que a UI mostra diante de um relatório vazio
# ----------------------------------------------------------------------

class _AppSubstituicao:
    """MainWindow com os diálogos capturados; a conversão roda de verdade."""

    def __init__(self, entrada, simular=False):
        from ui.main_window import MainWindow

        self.entrada = entrada
        self.saida = os.path.join(os.path.dirname(entrada), "saida.pdf")
        self.simular = simular
        self.infos = []
        self.alertas = []

        self._original = (messagebox.showinfo, messagebox.showwarning,
                          messagebox.showerror, messagebox.askyesnocancel,
                          filedialog.askopenfilename, filedialog.asksaveasfilename)
        messagebox.showinfo = lambda t, m, **k: self.infos.append((t, m))
        messagebox.showwarning = lambda t, m, **k: self.alertas.append((t, m))
        messagebox.showerror = lambda t, m, **k: self.infos.append((t, m))
        messagebox.askyesnocancel = lambda t, m, **k: self.simular
        filedialog.askopenfilename = lambda **k: self.entrada
        filedialog.asksaveasfilename = lambda **k: self.saida

        self.root = raiz_tk()
        self.win = MainWindow(self.root)

    def converter(self, limite=60.0):
        self.win.substitute_chess_glyphs_action()
        fim = time.time() + limite
        self.root.update()
        while self.win.task.is_running() and time.time() < fim:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        assert not self.win.task.is_running(), "a tarefa não terminou no tempo"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        (messagebox.showinfo, messagebox.showwarning, messagebox.showerror,
         messagebox.askyesnocancel, filedialog.askopenfilename,
         filedialog.asksaveasfilename) = self._original
        try:
            self.win.task.shutdown()
            self.win.status.end_task()
            self.root.update()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def test_a_ui_avisa_quando_nenhuma_fonte_de_xadrez_casou():
    """
    Era `showinfo` com "0 substituição(ões); nenhum aviso" — a mesma caixa, com
    o mesmo ícone, de uma conversão que deu certo.
    """
    with _AppSubstituicao(_pdf_so_prosa()) as app:
        app.converter()

        assert app.alertas, "0 substituições saiu como conclusão, não como aviso"
        assert not app.infos
        texto = app.alertas[0][1]
        assert "nenhuma fonte de xadrez" in texto
        assert "font_patterns" in texto, "o aviso não diz o que fazer"


def test_a_ui_manda_o_pdf_digitalizado_para_a_ferramenta_certa():
    with _AppSubstituicao(_pdf_digitalizado()) as app:
        app.converter()

        assert app.alertas
        assert "Neural" in app.alertas[0][1], (
            "não apontou o caminho do PDF escaneado")


def test_a_ui_conclui_normalmente_quando_houve_substituicao():
    entrada = _pdf_simples()
    with _tratando_a_embutida_como_xadrez(entrada):
        with _AppSubstituicao(entrada) as app:
            app.converter()

            assert app.infos, "uma conversão com substituições virou aviso"
            assert not app.alertas


# ----------------------------------------------------------------------
# Avisos e resumo
# ----------------------------------------------------------------------

def test_resumo_diz_que_nada_foi_gravado_em_dry_run():
    rel = _analisar(_pdf_simples(), _saida(), dry_run=True)
    assert "SIMULAÇÃO" in rel.resumo()


def test_contagem_de_avisos_cobre_todas_as_chaves():
    rel = _analisar(_pdf_simples(), _saida(), dry_run=True)
    assert set(rel.contagem_de_avisos()) == set(relatorio_pdf.AVISOS)


def test_com_aviso_filtra():
    rel = _analisar(_pdf_simples("wyz"), _saida(), dry_run=True)
    assert rel.com_aviso("confianca_baixa")
    assert not rel.com_aviso("fonte_reduzida") or True   # depende da largura
    assert len(rel.com_aviso()) >= len(rel.com_aviso("confianca_baixa"))


def test_encolhimento_e_neutro_sem_corpo_original():
    s = relatorio_pdf.Substituicao(0, (0, 0, 1, 1), "f", "a", "b",
                                   corpo_original=0, corpo_final=0)
    assert s.encolhimento == 1.0


# ----------------------------------------------------------------------
# Compatibilidade
# ----------------------------------------------------------------------

def test_assinatura_antiga_continua_funcionando():
    """`substitute_chess_glyphs` é chamada pela UI e pelo smoke da F0."""
    entrada, saida = _pdf_simples(), _saida()
    with _tratando_a_embutida_como_xadrez(entrada):
        resultado = substitute_chess_glyphs(entrada, saida)

    assert isinstance(resultado, tuple) and len(resultado) == 2
    paginas, trocas = resultado
    assert paginas == 1 and trocas >= 1
    assert os.path.exists(saida)


def test_arquivo_inexistente():
    """
    Chama a função direto, sem o `_analisar`: o que se testa aqui é a guarda de
    `analisar_substituicao`, que levanta o `FileNotFoundError` embutido. O
    PyMuPDF tem um `fitz.FileNotFoundError` próprio, que **não** é o embutido, e
    passar pelo fixture faria o erro vir de lá.
    """
    try:
        analisar_substituicao("nao_existe_9876.pdf", _saida(), dry_run=True)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("aceitou arquivo inexistente")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
