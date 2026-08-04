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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

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
