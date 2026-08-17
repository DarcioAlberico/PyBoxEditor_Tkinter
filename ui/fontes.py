"""
As fontes que a tela usa, e como uma fonte empacotada chega até o Tk.

**Arquivo em `assets/fonts/` o Tk não vê.** O PyMuPDF abre o `.ttf` pelo caminho
e por isso `nags.sem_glifo` e o PDF exportado já enxergavam a
`NotoSansSymbols2`; a tela, não — o Tk pede a fonte ao Windows pelo *nome da
família*, e o Windows só conhece o que está registrado. Sem o registro, o botão
do `⯹` na barra rápida desenharia o retângulo vazio da SPEC §4.2 mesmo com o
arquivo ali do lado.

`AddFontResourceExW` com `FR_PRIVATE` resolve isso **sem instalar nada**: o
registro vale para este processo, morre com ele, não pede administrador, não
escreve no registro do Windows e não aparece para os outros programas. Medido: a
família passa a existir em `tkinter.font.families()` na mesma execução, mesmo com
a raiz Tk já criada, e o `⯹` mede 31 px onde o `hmtx` da fonte prevê 30,6 — é o
glifo dela, e não a caixa de faltante.

## Por que a tela escolhe a família por texto

Nenhuma fonte deste disco desenha as duas coisas. A `Segoe UI Symbol` cobre as
letras e 36 dos 37 símbolos da tabela; a `NotoSansSymbols2` cobre o `⯹` e não tem
uma letra latina sequer. Um rótulo de box é curto — um caractere, ou uma ligadura
de dois —, e o mesmo vale para o texto de um botão da barra, então dá para
escolher a família por texto, que é o que `fonte_do_rotulo` faz. A regra é a mesma
do exportador: **a principal manda, e a de recurso só recebe o que ela não
desenha**.

**A troca acontece pelo que foi medido, e não pelo nome da família.** Perguntar
"a `Segoe UI` cobre este caractere?" exigiria saber de que arquivo ela sai, e a
tela pede fonte por nome — o Tk não diz a origem. A pergunta que dá para
responder é outra e é mais forte: *nenhuma* fonte de
`chess_pdf_processor.CHESS_FONT_CANDIDATES` desenha este caractere? Se nenhuma
desenha, a família base também não desenha, seja ela qual for — e aí a de recurso
é a única saída. Hoje isso é exatamente o bloco U+2BF0–U+2BFD.
"""

import ctypes
import os
import sys
from typing import Dict, Optional, Tuple

from core.chess_pdf_processor import (CHESS_FONT_CANDIDATES, FONTES_DE_SIMBOLO,
                                      missing_glyphs)

#: Registro só para este processo — ver o cabeçalho.
FR_PRIVATE = 0x10

#: A família da fonte de recurso, como o Tk a chama.
#:
#: **É o nome da família, e não o do arquivo nem o que o PyMuPDF reporta.** O
#: `fitz.Font(...).name` devolve `'Noto Sans Symbols2 Regular'` — com o peso no
#: fim —, e pedir isso ao Tk não acha nada. Quem confere se o registro pegou é
#: `familia_registrada()`, que pergunta ao próprio Tk em vez de acreditar nesta
#: linha.
FAMILIA_SIMBOLOS = "Noto Sans Symbols2"

#: De qual arquivo sai cada família que a tela pede pelo nome.
#:
#: Existe para que a cobertura de uma família possa ser **medida**: o Tk aceita o
#: nome e não diz de onde ele veio. `tests/test_nags.py` consome este mapa para
#: conferir que a fonte do rótulo desenha o que a barra oferece.
ARQUIVO_DA_FAMILIA: Dict[str, str] = {
    "Segoe UI Symbol": r"C:\Windows\Fonts\seguisym.ttf",
    FAMILIA_SIMBOLOS: (FONTES_DE_SIMBOLO[0] if FONTES_DE_SIMBOLO else ""),
}

_registradas: Optional[Tuple[str, ...]] = None
_so_recurso_cache: Dict[str, bool] = {}


def registrar_empacotadas() -> Tuple[str, ...]:
    """
    Põe as fontes de `assets/fonts/` ao alcance do Tk, neste processo.

    Idempotente e silenciosa por opção: fonte que não registra deixa o símbolo
    desligado — que é o caminho que `nags.sem_glifo` já sabe tratar —, e não é
    motivo para o programa não abrir.

    Fora do Windows não faz nada: lá o Tk resolve fonte pelo fontconfig, que é
    outra conversa, e nenhum destes livros foi editado fora do Windows.
    """
    global _registradas
    if _registradas is not None:
        return _registradas

    if not sys.platform.startswith("win"):
        _registradas = ()
        return _registradas

    feitas = []
    for caminho in FONTES_DE_SIMBOLO:
        if not os.path.exists(caminho):
            continue
        try:
            n = ctypes.windll.gdi32.AddFontResourceExW(
                ctypes.c_wchar_p(os.path.abspath(caminho)), FR_PRIVATE, 0)
        except Exception:
            continue
        if n:
            feitas.append(caminho)
    _registradas = tuple(feitas)
    return _registradas


def familia_registrada(familia: str = FAMILIA_SIMBOLOS) -> bool:
    """O Tk consegue pedir esta família agora? Pergunta ao Tk, não ao mapa."""
    try:
        import tkinter.font as tkfont
        return familia in tkfont.families()
    except Exception:      # sem display, sem Tk — a resposta é não
        return False


def desenha(familia: str, texto: str) -> bool:
    """Esta família tem glifo para todos os caracteres deste texto?"""
    caminho = ARQUIVO_DA_FAMILIA.get(familia, "")
    if not caminho or not os.path.exists(caminho):
        return False
    try:
        return not missing_glyphs(caminho, texto)
    except Exception:      # fonte ilegível não condena o rótulo
        return False


def so_a_de_recurso_desenha(texto: str) -> bool:
    """
    Este texto só existe na fonte empacotada?

    Duas condições, e a primeira é a que dispensa saber o nome da família base:
    **nenhuma** fonte de `CHESS_FONT_CANDIDATES` desenha algum caractere daqui
    (então nenhuma família do sistema desenha, seja qual for a que a tela esteja
    pedindo), e a de recurso desenha todos.

    O resultado fica em cache por texto: a medição abre o arquivo da fonte, e
    este caminho roda a cada redesenho do canvas.
    """
    if texto in _so_recurso_cache:
        return _so_recurso_cache[texto]

    resposta = False
    if texto and desenha(FAMILIA_SIMBOLOS, texto):
        faltam = set(texto)
        for caminho in CHESS_FONT_CANDIDATES:
            if not faltam:
                break
            if not os.path.exists(caminho):
                continue
            try:
                faltam &= set(missing_glyphs(caminho, "".join(sorted(faltam))))
            except Exception:
                continue
        resposta = bool(faltam)

    _so_recurso_cache[texto] = resposta
    return resposta


def fonte_do_rotulo(texto: str, base: Tuple[str, int, str]) -> Tuple[str, int, str]:
    """
    A fonte para **este** texto — mesmo tamanho, mesmo peso, outra família.

    Devolve `base` em quase todo caso: letra, dígito, figurina e 36 dos 37
    símbolos da tabela. Troca só para o que nenhuma fonte do sistema desenha e a
    empacotada desenha — hoje o bloco U+2BF0–U+2BFD, que é onde mora o `⯹`.

    Serve ao rótulo amarelo do box e ao botão da barra rápida, que são os dois
    lugares onde um símbolo aparece sozinho. O negrito é o que torna isto
    necessário e não só desejável: medido dentro do app, no peso normal o Tk
    ainda acha o glifo numa fonte de reserva, e **no negrito ele desiste e
    desenha o retângulo com "?"** — e o rótulo do box é negrito.
    """
    familia, tamanho, peso = base
    # A condição é o **registro**, e não `familia_registrada()`: aquela pergunta
    # ao Tk, e perguntar ao Tk exige uma raiz criada. Um teste que só quer saber
    # qual família o rótulo escolheria não deveria precisar abrir janela, e o
    # registro é o que de fato decide se o Tk vai achar a família.
    if so_a_de_recurso_desenha(texto) and registrar_empacotadas():
        return (FAMILIA_SIMBOLOS, tamanho, peso)
    return base


registrar_empacotadas()
