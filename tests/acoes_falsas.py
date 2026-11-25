"""
Dublês das ações de leitura da janela principal, para os testes olharem o que elas
**fazem** em vez de lerem a fonte delas (PD-26, R-39).

As duas ações «Detectar e Preencher» (`ui.reconhecimento.Reconhecimento`) pedem à
janela só uma dúzia de coisas; `janela_das_acoes` as dá sem Tk, com a segmentação
chamando o preenchimento na hora e o laço `_preencher_por_linha` gravando o pedido.
`rodar_o_laco` roda o laço de verdade com `leitura_de_linha.ler_pagina` espiado, e
`ler_uma_linha_do_pdf` roda o laço do PDF pesquisável (`searchable_pdf._ler_boxes`)
numa linha só, com a geometria trocada por respostas fixas.

Não é arquivo de teste (não começa por `test_`): o pytest não o coleta.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from core.box_model import BoxEntry


class Leitura(SimpleNamespace):
    """O que `ocr_service.fallback_chain_detalhado` devolve, no mínimo que as ações leem."""

    def __init__(self, char="a", confianca=0.9, fonte="learner", margem=0.5):
        super().__init__(char=char, confianca=confianca, fonte=fonte, margem=margem)


def tarefa():
    """O `h` que o `_run_task` passa ao trabalho."""
    return SimpleNamespace(cancelled=False, log=lambda *a: None, progress=lambda *a: None)


def boxes_de_uma_linha(texto="abc"):
    """Boxes lado a lado, numa linha só, com `texto` de caractere."""
    return [BoxEntry(c, 10 + 20 * i, 10, 26 + 20 * i, 40) for i, c in enumerate(texto)]


def janela_das_acoes():
    """
    `(janela, pedidos)`: a janela que as duas ações consomem e a lista em que o
    `_preencher_por_linha` dela grava `(titulo, preparar, resumo, opcoes)`.

    `janela.ocr_service.pedidos` guarda os argumentos de cada chamada da cadeia.
    """
    from ui.reconhecimento import Reconhecimento

    pedidos = []

    def candidatas(recorte, k=3):
        return []

    def cadeia(justo, **opcoes):
        ocr.pedidos.append(opcoes)
        return Leitura()

    ocr = SimpleNamespace(pedidos=[], fallback_chain_detalhado=cadeia)
    servico = SimpleNamespace(load_predictor=lambda: True, motivo_do_modelo=lambda: "sem modelo",
                              _get_learner=lambda: "base", _predictor="rede", candidatas=candidatas)
    janela = SimpleNamespace(
        _busy=lambda titulo: False, _avisar_do_modelo=lambda: None,
        learning_service=servico, ocr_service=ocr, boxes=boxes_de_uma_linha(),
        idioma_da_sessao=lambda: "en", _frase_do_idioma=Reconhecimento._frase_do_idioma,
        _recortes_do_box=lambda pagina, b, faixas: ("justo", "contexto"),
        generate_boxes_opencv=lambda ao_concluir: ao_concluir(),
        _preencher_por_linha=lambda titulo, preparar, resumo, **opcoes: pedidos.append(
            (titulo, preparar, resumo, opcoes)))
    return janela, pedidos


def rodar_o_laco(monkeypatch, poda=None):
    """
    Roda `Reconhecimento._preencher_por_linha` com `ler_pagina` espiado.

    Devolve `(ordem, argumentos)`: a ordem em que `preparar`, `poda` e `ler_pagina`
    foram chamados, e os argumentos nomeados que `ler_pagina` recebeu.
    """
    from core import leitura_de_linha
    from ui.reconhecimento import Reconhecimento

    ordem, argumentos = [], {}

    def ler_pagina(pagina, linhas, **opcoes):
        ordem.append("ler_pagina")
        argumentos.update(opcoes)
        return []

    def preparar(h, pagina, faixas, margens):
        ordem.append("preparar")
        return lambda b: ("", 0.0, "vazio")

    def podar(pagina):
        ordem.append("poda")
        return "o podar da página"

    monkeypatch.setattr(leitura_de_linha, "ler_pagina", ler_pagina)
    janela = SimpleNamespace(
        image=np.full((60, 100), 255, dtype=np.uint8), boxes=boxes_de_uma_linha(),
        _busy=lambda titulo: False, ocr_service=SimpleNamespace(),
        _run_task=lambda titulo, trabalho, aplicar: trabalho(tarefa()))
    Reconhecimento(janela)._preencher_por_linha(
        "Detectar e preencher", preparar, lambda fontes: "",
        poda=podar if poda else None)
    return ordem, argumentos


def ler_uma_linha_do_pdf(monkeypatch, lidos, texto_da_linha, conf_linha_maxima=0.70):
    """
    `(saida, chamadas_de_em_bloco)` de `searchable_pdf._ler_boxes` numa linha de
    `lidos` — `[(char, confiança)]` — que a leitura por linha lê como
    `texto_da_linha`. A linha é dada como em bloco e a faixa existe: o que se olha é
    o que o laço faz com a resposta, e com que argumentos pergunta.
    """
    from core import leitura_de_linha, searchable_pdf

    boxes = boxes_de_uma_linha("?" * len(lidos))
    leitura = {id(b): par for b, par in zip(boxes, lidos)}
    recortes = {}
    chamadas = []

    def recorte_de_pe(img, b):
        recorte = np.zeros((4, 4), dtype=np.uint8)
        recortes[id(recorte)] = b
        return recorte

    def em_bloco(*args, **opcoes):
        chamadas.append((args, opcoes))
        return True

    monkeypatch.setattr(searchable_pdf.vertical, "recorte_de_pe", recorte_de_pe)
    monkeypatch.setattr(leitura_de_linha, "em_bloco", em_bloco)
    monkeypatch.setattr(leitura_de_linha, "faixa_da_linha", lambda img, linha: np.zeros((4, 4)))
    resumo = {"corrigidos_pela_linha": 0}
    saida = searchable_pdf._ler_boxes(
        np.full((60, 100), 255, dtype=np.uint8), boxes,
        reconhecer=lambda recorte: leitura[id(recortes[id(recorte)])],
        ler_linha=lambda faixa: (texto_da_linha, 0.9),
        conf_linha_maxima=conf_linha_maxima, resumo=resumo)
    return [(char, conf) for _b, char, conf in saida], chamadas
