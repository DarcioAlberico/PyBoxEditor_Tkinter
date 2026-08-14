"""
A cadeia de preenchimento medida na página real: quem responde, e quanto acerta.

    python medir_cadeia.py                        # o híbrido como está em produção
    python medir_cadeia.py --neural               # o outro caminho, para comparar
    python medir_cadeia.py --learner 0.5 0.7 0.85 0.95   # varre o roteamento
    python medir_cadeia.py --trava 0.6 0.7 0.85          # varre a trava da F18
    python medir_cadeia.py --paginas 3            # limita a amostra (a F21 usou ~3)

**Por que este arquivo existe.** As tabelas da F18, F20, F21 e F22 saíram de
script que não ficou: nada em `medir_*.py` chama `fallback_chain`, e refazer
qualquer uma delas hoje é reescrever o instrumento antes de medir. Os três
limiares que roteiam a leitura — `NEURAL_THRESHOLD` e as duas travas — carregam
no comentário a tabela que os produziu, e não o meio de produzi-la de novo. É a
mesma lacuna que `medir_paginas.py` fechou para a segmentação.

## O que ele mede que as tabelas anteriores não diziam

Elas dão o acerto da cadeia inteira. O que falta para decidir onde mexer é a
**composição**: quantos boxes cada elo responde e quanto cada elo acerta nos
boxes que pegou. Uma cadeia a 95% pode ser k-NN a 96% em tudo, ou k-NN a 99% em
90% dos boxes e EasyOCR a 70% no resto — e o remédio é outro em cada caso.

E, principalmente, a **tabela de roteamento**: o k-NN e o EasyOCR respondendo os
*mesmos* boxes, separados por faixa de confiança do k-NN. É ela que diz onde o
`learner_threshold` deve cortar, que é a pergunta que a F21 e a F22 deixaram sem
instrumento — a F21 varreu a trava da linha, a F22 varreu o `neural_threshold`, e
o limiar do k-NN nunca foi varrido por ninguém.

## Os modelos rodam uma vez; o roteamento roda a cada ponto da varredura

Uma varredura ingênua reexecutaria a rede, o k-NN e o EasyOCR a cada limiar, e
o EasyOCR sozinho custa ~16 ms por caractere. Aqui cada modelo é consultado uma
vez por recorte e memorizado pelos bytes da imagem; **o `fallback_chain` e o
`ler_pagina` continuam sendo os de produção**, chamados de verdade a cada ponto,
só que sobre respostas já calculadas. O que varia entre dois pontos da tabela é
o roteamento, que é o que está sendo medido — e não uma reimplementação dele,
que foi o erro que a F1.5 registrou.

**Custo.** O k-NN e o EasyOCR são consultados em **todos** os boxes, e não só nos
que a cadeia mandaria para eles: é o que a tabela de roteamento exige. São
~16 ms por caractere, então uma página sai em ~30 s e as onze em poucos minutos.
`--paginas` limita.

## O que ele não mede

Segmentação — box espúrio ou perdido é assunto de `medir_paginas.py`, e a conta
aqui é sobre os boxes que casaram com um rótulo, como na F14. E não mede o
caminho do PDF pesquisável, que usa a mesma cadeia por outro laço.
"""

import argparse
import os
import sys
from dataclasses import replace

import numpy as np
from PIL import Image

from core import leitura_de_linha as ldl
from core import vertical
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from core.services.box_service import faixas_de_linha
from core.services.learning_service import LearningService
from core.services.ocr_service import OCRService
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar
from ui.main_window import (CONF_MAXIMA_PARA_A_LINHA,
                            CONF_MAXIMA_PARA_A_LINHA_HIBRIDO,
                            LEARNER_THRESHOLD_HIBRIDO, NEURAL_THRESHOLD)


#: As faixas da tabela de roteamento. Apertadas em cima de propósito: é lá que
#: o k-NN vive. A base de referência foi colhida destes mesmos livros, então o
#: vizinho mais próximo costuma ser quase o mesmo PNG e a confiança encosta em 1.
FAIXAS = (0.0, 0.50, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.01)

#: O `learner_threshold` do caminho neural ainda mora dentro do `preparar` da
#: ação, como literal, e por isso está copiado aqui. O do híbrido deixou de
#: estar: virou `LEARNER_THRESHOLD_HIBRIDO` na F23, e é importado.
LEARNER_NEURAL = 0.9


def _console_em_utf8():
    """O console do Windows é cp1252, e este relatório tem `♗` e `½` dentro."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ----------------------------------------------------------------------
# Memória dos modelos
# ----------------------------------------------------------------------

class _Memo:
    """
    Envelope que consulta o modelo uma vez por recorte e guarda a resposta.

    A chave são os bytes da imagem, e não o `id` do box: o mesmo box é
    consultado com dois recortes diferentes (justo e faixa da linha), e dois
    boxes distintos nunca produzem o mesmo recorte.
    """

    def __init__(self, alvo, loaded=True):
        self._alvo = alvo
        self._cache = {}
        self.loaded = loaded        # o `fallback_chain` pergunta isto ao preditor

    def predict(self, crop):
        chave = crop.tobytes()
        if chave not in self._cache:
            self._cache[chave] = self._alvo.predict(crop)
        return self._cache[chave]


class ServicoMemorizado(OCRService):
    """
    O serviço de produção, com o EasyOCR consultado uma vez por recorte.

    `_ler_easyocr` é `classmethod` no original e vira método de instância aqui —
    as duas chamadas do serviço passam por `self`, então a substituição pega.
    """

    def __init__(self):
        super().__init__()
        self._cache_char = {}
        self._cache_faixa = {}

    def _ler_easyocr(self, reader, imagem):
        chave = imagem.tobytes()
        if chave not in self._cache_char:
            self._cache_char[chave] = OCRService._ler_easyocr(reader, imagem)
        return self._cache_char[chave]

    def easyocr_linha_conf(self, faixa_np, *args, **kwargs):
        chave = faixa_np.tobytes()
        if chave not in self._cache_faixa:
            self._cache_faixa[chave] = super().easyocr_linha_conf(
                faixa_np, *args, **kwargs)
        return self._cache_faixa[chave]


# ----------------------------------------------------------------------
# A página, preparada como a ação prepara
# ----------------------------------------------------------------------

def _recortes_do_box(pagina, b, faixas):
    """
    `(justo, com a faixa da linha)` — espelha `MainWindow._recortes_do_box`.

    São seis linhas copiadas de dentro da classe da janela, e é a única cópia
    deste arquivo: importar a UI para medir traria o Tk junto. O resto — a
    cadeia, o laço por linha, os limiares — é o código de produção chamado.
    """
    justo = vertical.recorte_de_pe(pagina, b)
    topo, base = faixas[id(b)]
    if (topo, base) == (b.y1, b.y2):
        return justo, justo
    return justo, vertical.recorte_de_pe(pagina, replace(b, y1=topo, y2=base))


class Pagina:
    """Uma página rotulada, já segmentada e cortada em linhas."""

    def __init__(self, caminho_img, caminho_box, arbitro):
        img = Image.open(caminho_img).convert("L")
        self.nome = os.path.basename(caminho_img)
        self.rotulados = carregar_box(caminho_box, img.size[1])
        self.arr = np.array(img)

        # O modo de produção: separador com árbitro (F1.5b). O híbrido não usa a
        # rede para ler, mas usa para cortar — `_arbitro_de_corte` é o mesmo nas
        # duas ações, e medir com outra segmentação mediria outra população.
        _, self.boxes = segmentar(img, "arbitrado", arbitro=arbitro)

        self.linhas = ldl.linhas_da_pagina(self.boxes)
        self.faixas = {id(b): faixa
                       for uma in self.linhas
                       for b, faixa in zip(uma, faixas_de_linha(uma))}

        r = comparar(self.boxes, self.rotulados)
        self.verdade = {id(self.boxes[i]): self.rotulados[j].char
                        for i, j in r.pares}

    @property
    def medidos(self):
        return len(self.verdade)

    def recortes(self, b):
        return _recortes_do_box(self.arr, b, self.faixas)


# ----------------------------------------------------------------------
# Os dois caminhos, como as duas ações os montam
# ----------------------------------------------------------------------

class Cadeia:
    """Os modelos carregados e memorizados, e as duas leituras por caractere."""

    def __init__(self, com_rede):
        self.ocr = ServicoMemorizado()
        svc = LearningService()
        self.learner = _Memo(svc._get_learner())
        self.predictor = None
        if com_rede:
            if not svc.load_predictor():
                raise SystemExit("sem modelo treinado — o caminho neural precisa dele")
            self.predictor = _Memo(svc._predictor)

    def leitor(self, pagina, caminho, learner_threshold):
        """
        `ler_caractere(box)` da ação pedida, com os limiares que ela usa.

        Espelha o `preparar` de `generate_and_fill_combined` e o de
        `generate_and_fill_neural`, inclusive o zeramento do híbrido: fonte que
        não é `learner` nem `easyocr` vira box vazio com confiança 0,0 — que é o
        que a F21 registrou como o lugar onde a linha mais tem a dizer.
        """
        def hibrido(b):
            justo, contexto = pagina.recortes(b)
            char, fonte, c = self.ocr.fallback_chain(
                justo, learner=self.learner, contexto=contexto,
                neural_threshold=learner_threshold,
                learner_threshold=learner_threshold,
            )
            if fonte not in ("learner", "easyocr"):
                return ("", 0.0, "vazio")
            return (char, c, fonte)

        def neural(b):
            justo, contexto = pagina.recortes(b)
            char, fonte, c = self.ocr.fallback_chain(
                justo, predictor=self.predictor, learner=self.learner,
                contexto=contexto,
                neural_threshold=NEURAL_THRESHOLD,
                learner_threshold=learner_threshold,
            )
            return (char, c, fonte)

        return hibrido if caminho == "hibrido" else neural

    def aquecer(self, pagina, com_rede):
        """
        Consulta cada modelo em cada box uma vez, antes de qualquer varredura.

        Não é só cache: a tabela de roteamento precisa da resposta do k-NN e da
        do EasyOCR **no mesmo box**, inclusive nos que a cadeia jamais mandaria
        para o segundo. Devolve `[(id, conf_knn, char_knn, char_ocr)]`.
        """
        saida = []
        for b in pagina.boxes:
            justo, contexto = pagina.recortes(b)
            ck, fk = self.learner.predict(justo)
            co, _ = self.ocr.easyocr_ocr_conf(justo, contexto=contexto)
            if com_rede:
                self.predictor.predict(justo)
            saida.append((id(b), fk, ck, co))
        for uma in pagina.linhas:
            if ldl.em_bloco(uma):
                tira = ldl.faixa_da_linha(pagina.arr, uma)
                if tira is not None:
                    self.ocr.easyocr_linha_conf(tira)
        return saida


def rodar(cadeia, paginas, caminho, learner_threshold, trava):
    """
    `[(fonte, conf, lido, verdade, página)]` para cada box que casou com rótulo.

    `trava` segue `ler_pagina`: `None` é "a linha manda sempre" e `0.0` é "a
    linha não encosta em nada" — toda confiança é >= 0, então todo box fica
    travado e o resultado é idêntico a não ler linha nenhuma.
    """
    saida = []
    for p in paginas:
        lidos = ldl.ler_pagina(
            p.arr, p.linhas,
            ler_faixa=cadeia.ocr.easyocr_linha_conf,
            ler_caractere=cadeia.leitor(p, caminho, learner_threshold),
            conf_maxima_para_trocar=trava,
        )
        for b, char, conf, fonte in lidos:
            verdade = p.verdade.get(id(b))
            if verdade is not None:
                saida.append((fonte, conf, char, verdade, p.nome))
    return saida


def acerto(linhas):
    """A fração de `[(fonte, conf, lido, verdade, página)]` lida certo."""
    if not linhas:
        return 0.0
    certos = sum(1 for reg in linhas
                 if normalizar(reg[2]) == normalizar(reg[3]))
    return 100.0 * certos / len(linhas)


# ----------------------------------------------------------------------
# As tabelas
# ----------------------------------------------------------------------

def tabela_composicao(linhas):
    """Quem respondeu quantos boxes, e quanto acertou nos que pegou."""
    por_fonte = {}
    for reg in linhas:
        por_fonte.setdefault(reg[0], []).append(reg)

    print(f"\n{'fonte':<16}{'boxes':>8}{'':>4}{'%':>7}{'acerto':>10}")
    for fonte in sorted(por_fonte, key=lambda f: -len(por_fonte[f])):
        parte = por_fonte[fonte]
        pct = 100.0 * len(parte) / len(linhas)
        a = f"{acerto(parte):>9.2f}%" if fonte != "vazio" else f"{'—':>10}"
        print(f"{fonte:<16}{len(parte):>8}{'':>4}{pct:>6.1f}%{a}")


def tabela_por_pagina(linhas):
    """
    O acerto página a página, e o quanto de cada uma o k-NN já tem na base.

    **A coluna da direita é o aviso, e ela não é decoração.** A confiança do
    k-NN é `1 - distância/2000`, então 0,99 quer dizer distância abaixo de 20 em
    1.024 pixels — meio nível de cinza por pixel, ou seja, o recorte já está na
    base de referência, byte a byte ou quase. Numa página assim o k-NN não está
    generalizando, está consultando a própria cópia, e o acerto medido não vale
    como previsão para página nova.

    É o que separa esta medição de uma boa notícia falsa: `training_data` foi
    colhida com "Aprender com Página Atual", e nada impede que as páginas
    rotuladas — que são as mesmas em que se aprendeu — estejam lá dentro.
    """
    por_pagina = {}
    for reg in linhas:
        por_pagina.setdefault(reg[4], []).append(reg)

    print(f"\n{'página':<52}{'boxes':>7}{'acerto':>9}{'já na base':>12}")
    for nome, parte in por_pagina.items():
        na_base = sum(1 for reg in parte
                      if reg[0] == "learner" and reg[1] >= 0.99)
        curto = nome if len(nome) <= 50 else nome[:47] + "..."
        print(f"{curto:<52}{len(parte):>7}{acerto(parte):>8.2f}%"
              f"{100.0 * na_base / len(parte):>11.1f}%")


def tabela_roteamento(aquecidos, verdade):
    """
    O k-NN e o EasyOCR nos **mesmos** boxes, por faixa de confiança do k-NN.

    É a tabela que decide o `learner_threshold`: onde a coluna do k-NN cai
    abaixo da do EasyOCR, mandar o box para o EasyOCR compra acerto; acima
    dela, custa. O limiar de hoje (0,85 no híbrido) nunca foi conferido contra
    isto — veio de ser o mesmo número da trava da linha.
    """
    print(f"\n{'confiança do k-NN':<20}{'boxes':>8}{'k-NN':>10}{'EasyOCR':>10}"
          f"{'':>4}{'quem ganha':<12}")
    for lo, hi in zip(FAIXAS, FAIXAS[1:]):
        parte = [(ck, co, verdade[chave]) for chave, fk, ck, co in aquecidos
                 if lo <= fk < hi and chave in verdade]
        if not parte:
            continue
        knn = 100.0 * sum(1 for c, _o, v in parte
                          if normalizar(c) == normalizar(v)) / len(parte)
        ocr = 100.0 * sum(1 for _c, o, v in parte
                          if normalizar(o) == normalizar(v)) / len(parte)
        ganha = "k-NN" if knn > ocr else ("EasyOCR" if ocr > knn else "empate")
        rotulo = f"{lo:.2f} – {min(hi, 1.0):.2f}"
        print(f"{rotulo:<20}{len(parte):>8}{knn:>9.1f}%{ocr:>9.1f}%"
              f"{'':>4}{ganha:<12}")


def tabela_linha(sem_linha, com_linha):
    """
    O que a linha trocou, e se cada troca foi conserto ou quebra.

    A F21 reportou o saldo (+0,44 ponto) e a contagem de trocas (42). O que
    falta para saber se dá para melhorar é a razão entre as duas metades: 42
    trocas com 42 consertos e 0 quebras é um teto; 60 consertos e 18 quebras é
    um alvo.
    """
    consertos = quebras = neutras = 0
    for reg0, reg1 in zip(sem_linha, com_linha):
        antes, vd, depois = reg0[2], reg0[3], reg1[2]
        if normalizar(antes) == normalizar(depois):
            continue
        certo_antes = normalizar(antes) == normalizar(vd)
        certo_depois = normalizar(depois) == normalizar(vd)
        if certo_depois and not certo_antes:
            consertos += 1
        elif certo_antes and not certo_depois:
            quebras += 1
        else:
            neutras += 1

    total = consertos + quebras + neutras
    print(f"\nA linha trocou {total} boxes: {consertos} conserto(s), "
          f"{quebras} quebra(s), {neutras} errado antes e depois.")
    if total:
        print(f"Saldo: {consertos - quebras:+d} caractere(s).")


def tabela_varredura(titulo, colunas, linhas_da_tabela):
    print(f"\n--- {titulo} ---")
    print(f"{'':<14}" + "".join(f"{c:>14}" for c in colunas))
    for rotulo, valores in linhas_da_tabela:
        celulas = "".join(f"{v:>13.2f}%" if isinstance(v, float)
                          else f"{v:>14}" for v in valores)
        print(f"{rotulo:<14}{celulas}")


# ----------------------------------------------------------------------

def main():
    _console_em_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--neural", action="store_true",
                    help="mede o caminho com a rede em vez do híbrido")
    ap.add_argument("--learner", type=float, nargs="*", default=None,
                    help="varre o learner_threshold (o roteamento do k-NN)")
    ap.add_argument("--trava", type=float, nargs="*", default=None,
                    help="varre a trava da linha (F18); 'sem linha' e 'sempre' "
                         "entram sozinhas na tabela")
    ap.add_argument("--paginas", type=int, default=None,
                    help="mede só as N primeiras páginas rotuladas")
    ap.add_argument("--so", nargs="*", default=None,
                    help="mede só as páginas cujo nome contém um destes "
                         "pedaços — é assim que se isola uma página limpa da "
                         "base de referência (ver `tabela_por_pagina`)")
    ap.add_argument("--limiar", type=float, default=None,
                    help="troca o learner_threshold desta ação, para a rodada "
                         "de produção e para a varredura da trava")
    args = ap.parse_args()

    caminho = "neural" if args.neural else "hibrido"
    padrao_learner = LEARNER_NEURAL if args.neural else LEARNER_THRESHOLD_HIBRIDO
    if args.limiar is not None:
        padrao_learner = args.limiar
    padrao_trava = (CONF_MAXIMA_PARA_A_LINHA if args.neural
                    else CONF_MAXIMA_PARA_A_LINHA_HIBRIDO)

    svc = LearningService()
    if not svc.load_predictor():
        print("sem modelo treinado — o árbitro do separador (F1.5b) precisa dele,\n"
              "e sem ele a população de boxes não é a de produção.")
        return 1
    arbitro = svc._predictor.predict

    achadas = paginas_rotuladas()
    if args.so:
        achadas = [(i, c) for i, c in achadas
                   if any(pedaco in i for pedaco in args.so)]
    if args.paginas:
        achadas = achadas[:args.paginas]
    if not achadas:
        print("nenhuma página rotulada encontrada")
        return 1

    cadeia = Cadeia(com_rede=args.neural)

    print(f"Preparando {len(achadas)} página(s)...")
    paginas, aquecidos = [], []
    for caminho_img, caminho_box in achadas:
        p = Pagina(caminho_img, caminho_box, arbitro)
        if len(p.rotulados) < MIN_ROTULADOS:
            continue
        paginas.append(p)
        aquecidos.extend(cadeia.aquecer(p, com_rede=args.neural))
        print(f"  {p.nome}  {p.medidos} de {len(p.boxes)} boxes com rótulo",
              flush=True)

    if not paginas:
        print("nenhuma página com rótulos suficientes")
        return 1

    verdade = {}
    for p in paginas:
        verdade.update(p.verdade)
    total = sum(p.medidos for p in paginas)

    print(f"\n=========== {total} caracteres em {len(paginas)} página(s), "
          f"caminho {caminho} ===========")

    producao = rodar(cadeia, paginas, caminho, padrao_learner, padrao_trava)
    ancora = rodar(cadeia, paginas, caminho, padrao_learner, 0.0)

    print(f"\nComo está em produção "
          f"(learner_threshold {padrao_learner}, trava {padrao_trava}): "
          f"**{acerto(producao):.2f}%**")
    print(f"Só a âncora, sem a leitura por linha: {acerto(ancora):.2f}%")

    tabela_composicao(producao)
    tabela_por_pagina(producao)
    tabela_linha(ancora, producao)
    tabela_roteamento(aquecidos, verdade)

    if args.learner is not None:
        limiares = args.learner or [0.5, 0.7, 0.8, 0.85, 0.9, 0.95]
        linhas_da_tabela = []
        for lt in limiares:
            so_ancora = rodar(cadeia, paginas, caminho, lt, 0.0)
            # A trava acompanha o limiar: a razão do 0,85 de hoje é ser o mesmo
            # número do `learner_threshold`, para a linha agir exatamente onde o
            # k-NN se recusou (F21). Movido um, o outro tem de mover junto.
            com_linha = rodar(cadeia, paginas, caminho, lt, lt)
            linhas_da_tabela.append(
                (f"{lt:.2f}", [acerto(so_ancora), acerto(com_linha)]))
        tabela_varredura("learner_threshold (o roteamento do k-NN)",
                         ["âncora", "com a linha"], linhas_da_tabela)

    if args.trava is not None:
        valores = [("sem linha", 0.0)]
        valores += [(f"{t:.2f}", t) for t in (args.trava or
                                              [0.6, 0.7, 0.8, 0.85, 0.9, 0.95])]
        valores.append(("sempre", None))
        linhas_da_tabela = []
        for rotulo, t in valores:
            r = rodar(cadeia, paginas, caminho, padrao_learner, t)
            trocados = sum(1 for reg in r if reg[0] == "easyocr_linha")
            linhas_da_tabela.append((rotulo, [acerto(r), trocados]))
        tabela_varredura("trava da leitura por linha (F18)",
                         ["acerto", "trocados"], linhas_da_tabela)

    return 0


if __name__ == "__main__":
    sys.exit(main())
