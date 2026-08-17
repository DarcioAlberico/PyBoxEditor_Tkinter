"""
As duas tabelas de NAGs: a do livro (barra rápida) e a do padrão PGN (menu).

O teste que importa aqui é o **da fonte**. Um símbolo acrescentado à tabela sem
conferir a cobertura vira caixa vazia na tela e no PDF, sem erro nenhum no
caminho — é o defeito do `·` da SPEC §4.2, onde a Helvetica trocava cada peça por
um ponto e o usuário só descobria ao abrir o PDF pronto. `missing_glyphs` já
existe justamente para isso.

O segundo que importa é o dos **pontos de código confundíveis**. `Δ` (U+0394) e
`∆` (U+2206) têm o mesmo desenho; se uma tabela usar um e a outra o outro, o
mesmo símbolo entra em `.box` com duas identidades e o modelo aprende duas
classes para um glifo só.

Rodar sem pytest:      python tests/test_nags.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

from core import nags
from core.chess_pdf_processor import (CHESS_FONT_CANDIDATES, FONTES_DE_SIMBOLO,
                                      missing_glyphs)
from ui.main_window import NAGS, NAGS_POR_FAMILIA


def _fontes_no_disco():
    """
    Todas as fontes que o programa consulta, **nas duas listas**.

    É a mesma pergunta que `nags.sem_glifo` faz — "alguma desenha?" —, e deixar a
    de recurso de fora daqui faria o teste acusar sem fonte justamente o `⯹` que
    ela foi embutida para desenhar.
    """
    return [p for p in list(CHESS_FONT_CANDIDATES) + list(FONTES_DE_SIMBOLO)
            if os.path.exists(p)]


def test_tabela_achatada_bate_com_as_familias():
    assert NAGS == [par for _, fam in NAGS_POR_FAMILIA for par in fam]


def test_sem_simbolo_repetido():
    """Dois botões com o mesmo símbolo seriam o mesmo botão duas vezes."""
    simbolos = [s for s, _ in NAGS]
    assert len(simbolos) == len(set(simbolos))


def test_toda_familia_tem_nome_e_conteudo():
    for titulo, familia in NAGS_POR_FAMILIA:
        assert titulo and familia


def test_todo_nag_tem_descricao():
    """A descrição é o tooltip e o rótulo do menu — sem ela o botão é charada."""
    assert all(desc.strip() for _, desc in NAGS)


def test_a_fonte_do_pdf_desenha_todos_os_simbolos():
    """
    Todo símbolo da barra tem alguma fonte que o desenhe.

    Conferido quando esta tabela cresceu para 23: `Segoe UI Symbol` desenhava os
    23; `MS Gothic`, a candidata seguinte, não tem `⩲`, `⩱` nem `⌓` — e também não
    tinha o `⨀`. Por isso a pergunta sempre foi se **alguma** cobre.

    **Com o `⯹` a pergunta deixou de poder ser feita fonte a fonte.** Nenhuma
    família desenha os 23: a única que tem o U+2BF9 não tem letra latina, e a que
    tem as letras não tem o U+2BF9 — é por isso que `searchable_pdf` embute duas e
    manda cada box para a que o desenha. O teste passou a percorrer os símbolos
    em vez das fontes, que é a garantia de verdade: nenhum símbolo da barra fica
    sem quem o escreva.
    """
    fontes = _fontes_no_disco()
    if not fontes:
        pytest.skip("nenhuma fonte candidata neste sistema")

    orfaos = {}
    for simbolo, _ in NAGS:
        for caminho in fontes:
            try:
                if not missing_glyphs(caminho, simbolo):
                    break
            except Exception:                       # fonte ilegível não é falha
                continue
        else:
            orfaos[simbolo] = [os.path.basename(c) for c in fontes]

    assert not orfaos, "símbolo da barra sem nenhuma fonte que o desenhe: %s" % orfaos


def test_a_fonte_do_rotulo_do_box_desenha_todos_os_simbolos():
    """
    O rótulo amarelo sob o box selecionado mostra o caractere lido, e mostra em
    **negrito** — é aí que mora a diferença. Medido: no peso normal o Tk ainda
    encontra o glifo ausente numa fonte de reserva, e por isso a lista lateral e
    os botões de NAG nunca sofreram disto; no negrito ele desiste e desenha o
    retângulo com "?" dentro.

    Com `Arial`, que era a fonte deste rótulo, isso atingia `⩲`, `⩱`, `∓`, `⇄`,
    `⌓` e `⨀`: o usuário digitava o símbolo e o rótulo respondia interrogação.

    **A pergunta mudou de forma quando o `⯹` entrou na barra**, e o teste
    acompanhou. Antes era "uma família cobre os 23?"; hoje não existe família que
    cubra, porque a única que desenha o `⯹` não tem letra latina. A pergunta que
    vale agora é por símbolo: *a família que `fonte_do_rotulo` escolhe para ele o
    desenha?* — que é a garantia que o usuário enxerga, e a antiga era só um jeito
    mais estreito de obtê-la.
    """
    from ui import fontes
    from ui.canvas_view import FONTE_ROTULO

    faltando = []
    for simbolo, _ in NAGS:
        familia = fontes.fonte_do_rotulo(simbolo, FONTE_ROTULO)[0]
        caminho = fontes.ARQUIVO_DA_FAMILIA.get(familia)
        assert caminho, (
            f"{familia!r} virou a fonte do rótulo sem passar pela medição: "
            "acrescente o arquivo dela em fontes.ARQUIVO_DA_FAMILIA")
        if not os.path.exists(caminho):
            pytest.skip(f"{familia} não disponível neste sistema")
        if missing_glyphs(caminho, simbolo):
            faltando.append((simbolo, familia))

    assert not faltando, (
        "o rótulo escolheu uma família que não desenha o símbolo: %s" % faltando)


# ----------------------------------------------------------------------
# A tabela do padrão PGN (core/nags.py), que alimenta o menu Notação
# ----------------------------------------------------------------------

#: Os códigos das duas listas da Wikipedia: a padrão (`$0`–`$139`), o que o
#: ChessPad acrescentou (`$140`–`$148`, `$220`–`$221`, `$238`–`$255`) e nada mais
#: — `$149`–`$219` e `$222`–`$237` são faixas reservadas sem definição.
CODIGOS_ESPERADOS = list(range(0, 149)) + [220, 221] + list(range(238, 256))


def test_a_tabela_pgn_tem_exatamente_os_codigos_das_listas():
    """Um código a mais é invenção; um a menos é linha perdida na transcrição."""
    assert [n.codigo for n in nags.TABELA] == CODIGOS_ESPERADOS


def test_tabela_pgn_achatada_bate_com_as_familias():
    assert nags.TABELA == [n for _, fam in nags.FAMILIAS for n in fam]
    assert nags.POR_CODIGO[14].simbolo == "⩲"


def test_todo_nag_pgn_tem_descricao():
    for n in nags.TABELA:
        assert n.descricao.strip(), f"${n.codigo} sem enunciado"


def test_toda_familia_pgn_tem_nome_e_conteudo():
    for titulo, familia in nags.FAMILIAS:
        assert titulo and familia


def test_o_par_brancas_negras_respeita_a_regra_do_padrao():
    """
    De `$14` em diante o padrão é simétrico: código par é das brancas, ímpar é a
    mesma frase para as negras. É o que `nags._lados` presume ao gerar as 100
    linhas simétricas — se a presunção cair, as descrições saem trocadas de lado.

    O símbolo, porém, só é privilégio do par **a partir de `$20`**. O bloco de
    avaliação (`$14`–`$19`) dá forma impressa aos dois lados — `⩲`/`⩱`, `±`/`∓`,
    `+-`/`-+` —, e é justamente por isso que esses seis estão escritos à mão na
    tabela em vez de saírem do gerador.
    """
    for n in nags.TABELA:
        if not 14 <= n.codigo <= 139:
            continue
        lado = "Negras" if n.codigo % 2 else "Brancas"
        assert lado.lower() in n.descricao.lower(), f"${n.codigo}: {n.descricao}"
        if n.codigo % 2 and n.codigo >= 20:
            assert not n.simbolo, f"${n.codigo} não deveria ter símbolo"


#: (o que o projeto usa, o gêmeo que a Wikipedia imprime). Mesmo desenho, outro
#: ponto de código — deixar os dois entrarem daria duas classes para um glifo.
CONFUNDIVEIS = [
    ("Δ", "∆"),        # U+0394 x U+2206, "com a ideia de" ($140)
    ("⇄", "⇆"),        # U+21C4 x U+21C6, contrajogo ($132)
    ("!!", "‼"),       # dois glifos x U+203C ($3)
    ("??", "⁇"),       # U+2047 ($4)
    ("!?", "⁉"),       # U+2049 ($5)
    ("?!", "⁈"),       # U+2048 ($6)
    ("+-", "+−"),      # hífen ASCII x U+2212 ($18)
    ("-+", "−+"),      # ($19)
    # A compensação ($44) saiu daqui: `≡` era o substituto de quando nenhuma
    # fonte desenhava o `⯹`, e agora a `NotoSansSymbols2` desenha. As duas
    # tabelas escrevem o U+2BF9, e é `test_a_compensacao_escreve_o_simbolo_
    # impresso` que trava isso.
]


def test_as_duas_tabelas_escolhem_o_mesmo_ponto_de_codigo():
    do_padrao = {n.simbolo for n in nags.TABELA}
    da_barra = {s for s, _ in NAGS}
    for usado, gemeo in CONFUNDIVEIS:
        assert gemeo not in do_padrao, (
            f"{gemeo!r} entrou na tabela PGN, mas o projeto já escreve {usado!r}")
        assert usado in do_padrao and usado in da_barra, (
            f"{usado!r} deveria estar nas duas tabelas")


def test_a_compensacao_escreve_o_simbolo_impresso():
    """
    O `⯹` (U+2BF9, um igual sobre um infinito) é o que a "Key to symbols used"
    destes livros imprime para "with compensation", logo acima do `∞` sozinho de
    *unclear*. O projeto escreveu `≡` no lugar enquanto nenhuma fonte do disco
    desenhava o U+2BF9 — medidas as 559 famílias de `C:\\Windows\\Fonts`, zero.

    O que desfez a troca foi a `NotoSansSymbols2` empacotada, e é ela que este
    teste guarda: sem o arquivo em `assets/fonts/`, o símbolo volta a não ter
    desenho e o botão da barra vira retângulo vazio — habilitado, porque o resto
    do programa acredita na medição.
    """
    from core.chess_pdf_processor import FONTES_DE_SIMBOLO

    assert nags.POR_CODIGO[44].simbolo == "⯹"
    assert "⯹" in {s for s, _ in NAGS}, "a barra rápida ficou com outro símbolo"
    assert "≡" not in {n.simbolo for n in nags.TABELA} | {s for s, _ in NAGS}, \
        "o substituto `≡` sobrou em alguma tabela: são duas classes num glifo"

    empacotada = next((p for p in FONTES_DE_SIMBOLO if os.path.exists(p)), "")
    assert empacotada, ("assets/fonts/ perdeu a fonte de recurso: sem ela o `⯹` "
                        "não tem desenho em nenhuma fonte deste sistema")
    assert missing_glyphs(empacotada, "⯹") == []
    assert "⯹" not in nags.sem_glifo()


def test_sem_glifo_aponta_so_o_que_nenhuma_fonte_desenha():
    """
    A medição vale para os dois lados: o que ela acusa tem de faltar em todas as
    fontes do disco, e o que ela libera tem de existir em pelo menos uma.
    """
    fontes = _fontes_no_disco()
    if not fontes:
        pytest.skip("nenhuma fonte candidata neste sistema")

    ausentes = nags.sem_glifo()
    for c in ausentes:
        assert all(missing_glyphs(f, c) for f in fontes), f"{c!r} tem fonte"

    alvo = {c for n in nags.TABELA for c in n.simbolo} - ausentes
    assert alvo, "nenhum símbolo desenhável: a medição está quebrada"
    for c in sorted(alvo):
        assert any(not missing_glyphs(f, c) for f in fontes), f"{c!r} sem fonte"


def test_os_simbolos_da_barra_rapida_continuam_desenhaveis():
    """
    A tabela PGN reaproveita os pontos de código da barra (`≡`, `Δ`, `⇄`). Se um
    deles perdesse a fonte, o menu o desligaria e a barra continuaria oferecendo
    o mesmo símbolo — duas respostas para a mesma pergunta.
    """
    if not _fontes_no_disco():
        pytest.skip("nenhuma fonte candidata neste sistema")

    ausentes = nags.sem_glifo()
    for simbolo, _ in NAGS:
        assert not (set(simbolo) & ausentes), f"{simbolo!r} na barra, sem fonte"


def test_o_menu_notacao_lista_tudo_e_desliga_o_que_nao_da_para_escrever():
    """
    Monta o menu de verdade e confere as três coisas que o usuário vê: toda
    família virou submenu, todo NAG virou item, e clicável é só quem tem símbolo
    **e** fonte.
    """
    import tkinter as tk
    from ui.main_window import MainWindow

    janela = raiz_tk()
    if janela is None:
        pytest.skip("sem display")
    try:
        win = MainWindow(janela)
        menubar = janela.nametowidget(janela.cget("menu"))
        # A barra é criada sem `tearoff=0`, então a entrada 0 é o tracejado de
        # destacar o menu e não tem rótulo nenhum. Perguntar pelo tipo evita o
        # `TclError: unknown option "-label"`.
        rotulos = {menubar.entrycget(i, "label"): i
                   for i in range(menubar.index("end") + 1)
                   if menubar.type(i) == "cascade"}
        assert "Notação" in rotulos

        m_nag = menubar.nametowidget(
            menubar.entrycget(rotulos["Notação"], "menu"))
        assert m_nag.index("end") + 1 == len(nags.FAMILIAS)

        ausentes = nags.sem_glifo()
        vistos, ligados = 0, 0
        for i, (titulo, familia) in enumerate(nags.FAMILIAS):
            assert m_nag.entrycget(i, "label") == titulo
            sub = m_nag.nametowidget(m_nag.entrycget(i, "menu"))
            assert sub.index("end") + 1 == len(familia)
            for k, nag in enumerate(familia):
                rotulo = sub.entrycget(k, "label")
                assert f"${nag.codigo}" in rotulo and nag.descricao in rotulo
                vistos += 1
                normal = sub.entrycget(k, "state") != "disabled"
                assert normal == nags.desenhavel(nag, ausentes), (
                    f"${nag.codigo} deveria estar "
                    f"{'ligado' if not normal else 'desligado'}")
                ligados += normal

        assert vistos == len(nags.TABELA)
        assert ligados, "nenhum NAG clicável: o menu não serve para nada"
    finally:
        janela.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ----------------------------------------------------------------------
# As figurinas de peça, ao lado dos NAGs
# ----------------------------------------------------------------------

def test_sao_as_cinco_pecas_que_ganham_letra():
    """
    Peão fica de fora (`e4` nunca leva figurina), e os codepoints pretos também:
    estes livros usam **um** conjunto para os dois lados. É a mesma regra de
    `searchable_pdf.PECAS`, e são as 5 classes que o modelo aprendeu.
    """
    from core.chess_pdf_processor import CHESS_UNICODE
    from ui.main_window import PECAS_RAPIDAS

    simbolos = [s for s, _ in PECAS_RAPIDAS[1]]
    assert simbolos == list(CHESS_UNICODE[:5])
    assert simbolos == list("♔♕♖♗♘")


def test_a_lista_de_pecas_bate_com_a_do_pdf():
    """Se uma das duas mudar sozinha, o botão escreve o que o PDF não desenha."""
    from core.searchable_pdf import PECAS
    from ui.main_window import PECAS_RAPIDAS

    assert {s for s, _ in PECAS_RAPIDAS[1]} == PECAS


def test_toda_peca_tem_nome_e_e_unico():
    from ui.main_window import PECAS_RAPIDAS

    titulo, pares = PECAS_RAPIDAS
    assert titulo
    assert all(d.strip() for _s, d in pares)
    assert len({d for _s, d in pares}) == len(pares)


def test_peca_nao_colide_com_nag():
    """Dois botões com o mesmo caractere seriam dois caminhos para o mesmo lugar."""
    from ui.main_window import PECAS_RAPIDAS

    assert not ({s for s, _ in PECAS_RAPIDAS[1]} & {s for s, _ in NAGS})


def test_a_fonte_do_pdf_desenha_as_pecas():
    from ui.main_window import PECAS_RAPIDAS

    fontes = _fontes_no_disco()
    if not fontes:
        pytest.skip("nenhuma fonte candidata neste sistema")

    alvo = "".join(s for s, _ in PECAS_RAPIDAS[1])
    assert any(missing_glyphs(f, alvo) == [] for f in fontes), (
        "nenhuma fonte candidata desenha as 5 peças — o botão escreveria "
        "retângulo vazio no PDF")


def test_os_botoes_de_peca_aparecem_na_janela():
    """
    Fecha o caminho que as asserções sobre a tabela não tocam: a peça tem que
    virar botão de verdade, e na segunda faixa — a primeira já leva 16 e é ela
    que define a largura mínima da janela.
    """
    import tkinter as tk
    from tkinter import messagebox

    from ui.main_window import MainWindow, PECAS_RAPIDAS

    info = messagebox.showinfo
    messagebox.showinfo = lambda *a, **k: None
    raiz = raiz_tk()
    try:
        janela = MainWindow(raiz)
        raiz.update_idletasks()

        faixas = []
        for filho in janela.winfo_children():
            netos = filho.winfo_children()
            if netos and all(isinstance(n, tk.Frame) for n in netos):
                textos = [[w.cget("text") for w in n.winfo_children()
                           if isinstance(w, tk.Button)] for n in netos]
                if any(textos):
                    faixas = textos
                    break

        assert faixas, "não achei as faixas de botões"
        esperadas = [s for s, _ in PECAS_RAPIDAS[1]]
        assert all(p in faixas[-1] for p in esperadas), (
            f"as peças não estão na última faixa: {faixas[-1]}")
        assert not any(p in faixas[0] for p in esperadas), (
            "peça foi parar na faixa que já define a largura da janela")
    finally:
        messagebox.showinfo = info
        try:
            janela.task.shutdown()
            raiz.destroy()
        except Exception:
            pass
