"""
Testes da F1.7 — validação da notação contra as regras do xadrez.

Três coisas medidas antes de escrever o módulo estão travadas aqui, porque as
três contrariam o que o item do ROADMAP dizia:

1. **A tabela de exemplos do item estava errada.** Ela afirmava que, após
   `1.e4 e5 2.Nf3 Nc6`, a legalidade separaria `Bb4`/`Bh4` e `Nf3`/`Nf8`. Nessa
   posição os dois lados de todos os pares são ilegais.

2. **Espaço não dá para inferir só pela lacuna** — os algarismos desta fonte têm
   avanço tabular, e "15" vira "1 5" em qualquer limiar que preserve os espaços
   de verdade.

3. **Reconhecer o lance por expressão regular quebra no primeiro caractere
   errado**, que é justamente o caso que interessa corrigir.

Rodar sem pytest:      python tests/test_f17_notacao.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from core import notacao
from core.box_model import BoxEntry


# ----------------------------------------------------------------------
# Ajuda: montar uma linha de boxes a partir de um texto
# ----------------------------------------------------------------------

LARG, ALT, ESPACO = 10, 20, 12


def _linha(texto, y=0, x0=0, conf=1.0, larguras=None):
    """
    Boxes de uma linha. Espaço no texto vira lacuna larga; caracteres coladinhos
    ficam com lacuna 1 px.
    """
    boxes = []
    x = x0
    for i, ch in enumerate(texto):
        if ch == " ":
            x += ESPACO
            continue
        w = (larguras or {}).get(i, LARG)
        boxes.append(BoxEntry(ch, x, y, x + w, y + ALT, confidence=conf,
                              source="neural"))
        x += w + 1
    return boxes


def _boxes(*linhas):
    saida = []
    for n, texto in enumerate(linhas):
        saida.extend(_linha(texto, y=n * (ALT + 10)))
    return saida


# ----------------------------------------------------------------------
# A premissa do item
# ----------------------------------------------------------------------

def test_a_posicao_do_roadmap_nao_separava_nada():
    """
    Documenta o erro: em 1.e4 e5 2.Nf3 Nc6 os dois lados de cada par são
    ilegais — 'Nf3' porque o cavalo já está em f3.
    """
    b = chess.Board()
    for m in ["e4", "e5", "Nf3", "Nc6"]:
        b.push_san(m)
    for san in ("Bb4", "Bh4", "Nf3", "Nf8", "Rf3", "Qh5"):
        try:
            b.parse_san(san)
            legal = True
        except Exception:
            legal = False
        assert not legal, f"{san} deveria ser ilegal nesta posição"


def test_a_legalidade_separa_nas_posicoes_certas():
    """O princípio vale; só os exemplos do item é que não tinham sido rodados."""
    b = chess.Board()
    for m in ["e4", "e5"]:
        b.push_san(m)
    assert b.parse_san("Nf3")
    for ruim in ("Nf8", "Rf3"):
        try:
            b.parse_san(ruim)
            raise AssertionError(f"{ruim} deveria ser ilegal")
        except (chess.IllegalMoveError, chess.InvalidMoveError):
            pass

    b = chess.Board()
    for m in ["d4", "Nf6", "c4", "e6", "Nc3"]:
        b.push_san(m)
    assert b.parse_san("Bb4")
    try:
        b.parse_san("Bh4")
        raise AssertionError("Bh4 deveria ser ilegal")
    except (chess.IllegalMoveError, chess.InvalidMoveError):
        pass


# ----------------------------------------------------------------------
# Do box ao texto
# ----------------------------------------------------------------------

def test_texto_respeita_espacos():
    assert notacao.texto_da_pagina(_boxes("1.d4 Nf6")) == "1.d4 Nf6"


def test_linhas_separadas():
    assert notacao.texto_da_pagina(_boxes("1.d4", "2.c4")) == "1.d4\n2.c4"


def test_numero_partido_pela_lacuna_e_remontado():
    """
    O caso medido: nos algarismos desta fonte a lacuna depois de '1' é 10 px,
    contra 1-2 px depois de letras, e "15" sai como "1 5".
    """
    assert notacao.texto_da_pagina(_boxes("1 5.Bf4")) == "15.Bf4"
    assert notacao.texto_da_pagina(_boxes("2 1 .Nb5")) == "21.Nb5"


def test_remontagem_nao_encosta_em_prosa():
    """"Game 85" tem que continuar com o espaço: 'Game' não é numérica."""
    assert notacao.texto_da_pagina(_boxes("Game 85")) == "Game 85"
    assert notacao.texto_da_pagina(_boxes("Bucharest 2008")) == "Bucharest 2008"


def test_box_vazio_nao_abre_espaco():
    """
    Esvaziar um box é como a correção remove um glifo fantasma. A lacuna que ele
    deixa não pode virar espaço, senão "Nf6" vira "N f6".
    """
    boxes = _boxes("N?f6")
    boxes[1].char = ""
    assert notacao.texto_da_pagina(boxes) == "Nf6"


def test_figurina_vira_letra():
    """O livro usa um conjunto só para os dois lados (F1.1); a cor vem da vez."""
    assert notacao.texto_da_pagina(_boxes("1.d4 ♘f6")) == "1.d4 Nf6"


# ----------------------------------------------------------------------
# Peneira de lance
# ----------------------------------------------------------------------

def test_parece_lance_aceita_lance():
    for s in ("Nf6", "exd5", "O-O", "0-0-0", "Qh4+", "exd8=Q", "N□f6", "Rb7"):
        assert notacao.parece_lance(s), s


def test_parece_lance_recusa_prosa():
    for s in ("counterplay", "Bucharest", "Antakya2010", "with", "Xue-", ""):
        assert not notacao.parece_lance(s), s


def test_prosa_com_casa_dentro_nao_passa_por_tamanho():
    """'Antakya2010' tem 'a2' dentro; o tamanho e a inicial é que barram."""
    assert notacao.RE_CASA.search("Antakya2010")
    assert not notacao.parece_lance("Antakya2010")


# ----------------------------------------------------------------------
# Custo da troca
# ----------------------------------------------------------------------

def test_troca_identica_custa_zero():
    assert notacao.custo_da_troca("Nf6", "Nf6", [1.0, 1.0, 1.0]) == 0.0


def test_caractere_confiante_custa_mais_para_trocar():
    alto = notacao.custo_da_troca("Nf6", "Nf5", [1.0, 1.0, 1.0])
    baixo = notacao.custo_da_troca("Nf6", "Nf5", [1.0, 1.0, 0.2])
    assert baixo < alto


def test_caractere_perdido_e_barato():
    """Na página real o erro dominante é glifo perdido: 'Bxe5' lido 'Be5'."""
    perdido = notacao.custo_da_troca("Be5", "Bxe5", [1.0, 1.0, 1.0])
    trocado = notacao.custo_da_troca("Be5", "Bd5", [1.0, 1.0, 1.0])
    assert perdido < trocado


# ----------------------------------------------------------------------
# Análise
# ----------------------------------------------------------------------

def test_partida_limpa_sai_toda_legal():
    boxes = _boxes("1.d4 Nf6 2.c4 e6 3.Nc3 Bb4")
    a = notacao.analisar(boxes)
    assert [l.situacao for l in a.lances] == ["legal"] * 6
    assert a.correcoes == []


def test_corrige_glifo_fantasma_no_meio_do_lance():
    """
    Medido na página real: o separador de glifos parte o 'N' em negrito e o
    segundo pedaço é lido como '□'. A legalidade devolve 'Nf6'.
    """
    boxes = _boxes("1.d4 N□f6 2.c4")
    a = notacao.analisar(boxes)
    assert a.contar("corrigido") == 1
    assert a.lances[1].correto == "Nf6"
    assert len(a.correcoes) == 1
    assert (a.correcoes[0].de, a.correcoes[0].para) == ("□", "")


def test_corrige_caractere_trocado():
    boxes = _boxes("1.d4 Nf6 2.c4 e6 3.Nc3 Bh4")   # Bh4 é ilegal; Bb4 não
    a = notacao.analisar(boxes)
    assert a.lances[-1].situacao == "corrigido"
    assert a.lances[-1].correto == "Bb4"
    assert [(c.de, c.para) for c in a.correcoes] == [("h", "b")]


def test_nao_corrige_quando_dois_lances_legais_casam_igual():
    """A legalidade estreita o conjunto; nem sempre decide."""
    b = chess.Board()
    for m in ["d4", "Nf6", "c4", "e6", "Nf3", "d5", "Nc3", "c5"]:
        b.push_san(m)
    # 'Nd2' é ambíguo entre Nbd2 e Nfd2 nesta posição
    assert sum(1 for m in b.legal_moves if b.san(m).endswith("d2")) >= 2


def test_aplicar_escreve_e_marca_a_origem():
    boxes = _boxes("1.d4 Nf6 2.c4 e6 3.Nc3 Bh4")
    a = notacao.analisar(boxes)
    assert notacao.aplicar(boxes, a.correcoes) == 1
    assert notacao.texto_da_pagina(boxes).endswith("Bb4")
    alterado = boxes[a.correcoes[0].indice_box]
    assert alterado.source == "xadrez" and alterado.confidence == 1.0


def test_aplicar_ignora_correcao_de_box_ja_mexido():
    boxes = _boxes("1.d4 Nf6 2.c4 e6 3.Nc3 Bh4")
    a = notacao.analisar(boxes)
    boxes[a.correcoes[0].indice_box].char = "z"     # usuário editou antes
    assert notacao.aplicar(boxes, a.correcoes) == 0


def test_prosa_no_meio_nao_derruba_o_tabuleiro():
    """
    "14.b3 e6 with counterplay" — a prosa termina a notação, mas os lances de
    antes continuam válidos e os de depois voltam a ser conferidos.
    """
    boxes = _boxes("1.d4 Nf6 with counterplay 2.c4 e6")
    a = notacao.analisar(boxes)
    assert a.contar("legal") == 4
    assert a.contar("perdido") == 0


def test_variante_rebobina_em_vez_de_seguir_em_frente():
    """
    "12...Ra6; 12...Ra7" são alternativas ao lance jogado. Lidas em sequência,
    a segunda seria ilegal e o corretor produziria lixo.
    """
    boxes = _boxes("1.d4 Nf6 2.c4 e6 2...c5 2...d5 3.Nc3")
    a = notacao.analisar(boxes)
    assert a.contar("legal") == 7, [(l.texto, l.situacao) for l in a.lances]


def test_nao_corrige_com_a_posicao_incerta():
    """
    Depois de uma variante o texto volta à linha principal sem avisar. Com mais
    de uma posição possível, nada é corrigido — só reportado. Foi assim que uma
    correção falsa ('e6' virando 'e5') deixou de acontecer na página real.
    """
    # A variante "3...Nf6" volta a um número já jogado; a partir daí "4." tanto
    # continua a variante quanto retoma a principal, e as duas posições diferem.
    boxes = _boxes("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 3...Nf6 4.O-O Bh4")
    a = notacao.analisar(boxes)
    assert a.correcoes == []
    assert a.lances[-1].situacao == "ambiguo"
    assert a.lances[-1].correto == "Bb4"   # sabe qual seria, mas não aplica


def test_sem_comeco_de_partida_nao_ha_o_que_conferir():
    """Sem um '1.' não há posição de onde partir; nada é inventado."""
    a = notacao.analisar(_boxes("15.Bf4 Nge5"))
    assert a.lances == [] and a.correcoes == []


def test_pagina_sem_notacao():
    a = notacao.analisar(_boxes("Bucharest 2008", "Savchenko,Stanislav"))
    assert a.lances == []
    assert "Nenhuma notação" in a.resumo()


def test_resumo_conta_tudo():
    a = notacao.analisar(_boxes("1.d4 Nf6 2.c4 e6 3.Nc3 Bh4"))
    assert "6 lances lidos" in a.resumo()
    assert "1 corrigidos" in a.resumo()


def test_espaco_perdido_entre_lance_e_numero():
    """"Rb7 25.Rd2" pode sair colado; o corte válido deixa um lance à esquerda."""
    pedacos = notacao._fatiar(notacao.Palavra(
        [notacao.Simbolo(c, i) for i, c in enumerate("Rb725.Rd2")]))
    assert [(p.tipo, p.texto) for p in pedacos] == [
        ("lance", "Rb7"), ("numero", "25."), ("lance", "Rd2")]


def test_boxes_vazios_nao_quebram():
    assert notacao.analisar([]).lances == []
    assert notacao.texto_da_pagina([]) == ""


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
