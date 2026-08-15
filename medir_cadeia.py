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

from core import learner as core_learner
from core import leitura_de_linha as ldl
from core import vertical
from core.avaliacao_pagina import (EQUIVALENTES, carregar_box, comparar,
                                   normalizar)
from core.services.box_service import faixas_de_linha
from core.services.learning_service import LearningService
from core.services.ocr_service import OCRService
from ui import confidence as conf_ui
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar
from ui.main_window import (CONF_MAXIMA_PARA_A_LINHA,
                            CONF_MAXIMA_PARA_A_LINHA_HIBRIDO,
                            LEARNER_THRESHOLD_HIBRIDO,
                            LEARNER_THRESHOLD_NEURAL, NEURAL_THRESHOLD)


#: As faixas da tabela de roteamento. Apertadas em cima de propósito: é lá que
#: o k-NN vive. A base de referência foi colhida destes mesmos livros, então o
#: vizinho mais próximo costuma ser quase o mesmo PNG e a confiança encosta em 1.
FAIXAS = (0.0, 0.50, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.01)

#: As figurinas, para separar a causa da exclusão na tabela do alfabeto (F36).
#: Sai do mapa da avaliação em vez de ser reescrita: é lá que a lista mora.
FIGURINAS = frozenset(EQUIVALENTES)


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

    def vizinhos(self, crop, k=1):
        """Só o k-NN tem isto; a rede não é consultada por aqui."""
        chave = (k, crop.tobytes())
        if chave not in self._cache:
            self._cache[chave] = self._alvo.vizinhos(crop, k=k)
        return self._cache[chave]

    def margem(self, crop):
        """A alternativa que a F24 mediu e devolveu. Só o k-NN tem."""
        chave = ("margem", crop.tobytes())
        if chave not in self._cache:
            self._cache[chave] = self._alvo.margem_de_confianca(crop)
        return self._cache[chave]

    def voto(self, crop, k):
        """A outra alternativa da F24. Memorizada por `k`, como `vizinhos`."""
        chave = ("voto", k, crop.tobytes())
        if chave not in self._cache:
            self._cache[chave] = self._alvo.voto(crop, k=k)
        return self._cache[chave]


class _MemoCombinado:
    """
    `min(confiança de produção, margem)` — a ideia que a F24 deixou aberta.

    Se a absoluta detecta novidade e a margem detecta ambiguidade, o mínimo das
    duas acende nos dois casos. Envolve o memo em vez do k-NN: as duas metades
    já foram calculadas no aquecimento, então a varredura inteira não custa
    consulta nova nenhuma.
    """

    def __init__(self, memo):
        self._memo = memo
        self.loaded = True

    def predict(self, crop):
        char, conf = self._memo.predict(crop)
        return char, min(conf, self._memo.margem(crop))

    def vizinhos(self, crop, k=1):
        return self._memo.vizinhos(crop, k=k)

    def margem(self, crop):
        return self._memo.margem(crop)


class _MemoComDistancia:
    """
    O k-NN com outro `DISTANCIA_MAXIMA`, sem tocar em produção (F35).

    A confiança é `1 - d/D`, e `d` já está no cache do aquecimento — trocar `D`
    é recontar, não reconsultar, e é isso que torna a varredura barata.

    **A razão mudou na F38.** Na F35 este envelope era obrigatório: o `D` de
    produção era valor padrão de argumento, ligado em tempo de `def`, então
    trocar o global do módulo não teria efeito nenhum. Hoje `predict` lê o global
    na chamada e trocá-lo funcionaria — só que as respostas já estão memorizadas
    por bytes da imagem, e trocar o global não as invalidaria. O envelope fica
    por ser o jeito certo, e não por ser o único.
    """

    def __init__(self, memo, distancia_maxima):
        self._memo = memo
        self._D = float(distancia_maxima)
        self.loaded = True

    def predict(self, crop):
        char, _conf = self._memo.predict(crop)
        perto = self._memo.vizinhos(crop, k=1)
        d = perto[0][1] if perto else float("inf")
        return char, max(0.0, 1.0 - d / self._D) if d < self._D else 0.0

    def vizinhos(self, crop, k=1):
        return self._memo.vizinhos(crop, k=k)

    def margem(self, crop):
        return self._memo.margem(crop)


class _MemoComVoto:
    """
    O k-NN respondendo por **voto entre os k**, e não pelo mais próximo (F24).

    A confiança continua a do 1-NN: o voto muda quem vence, não o quanto o
    recorte se parece com a base, e trocar as duas coisas de uma vez mediria
    duas mudanças numa tabela só.

    **Precisa existir porque `predict` é 1-NN e não tem `k`.** O `--k` mexia em
    `core_learner.K_VIZINHOS`, que era valor padrão de argumento de `voto` e de
    `vizinhos` — ligado em tempo de `def` — e além disso nada no instrumento
    chamava `voto`. A F38 achou o botão desligado dos dois jeitos.
    """

    def __init__(self, memo, k):
        self._memo = memo
        self._k = int(k)
        self.loaded = True

    def predict(self, crop):
        _char, conf = self._memo.predict(crop)
        return self._memo.voto(crop, self._k), conf

    def vizinhos(self, crop, k=1):
        return self._memo.vizinhos(crop, k=k)

    def margem(self, crop):
        return self._memo.margem(crop)


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

    def leitor(self, pagina, caminho, learner_threshold, neural_threshold=None):
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
                neural_threshold=(NEURAL_THRESHOLD if neural_threshold is None
                                  else neural_threshold),
                learner_threshold=learner_threshold,
            )
            return (char, c, fonte)

        return hibrido if caminho == "hibrido" else neural

    def aquecer(self, pagina, com_rede, com_ocr=True):
        """
        Consulta cada modelo em cada box uma vez, antes de qualquer varredura.

        Não é só cache: a tabela de roteamento precisa da resposta do k-NN e da
        do EasyOCR **no mesmo box**, inclusive nos que a cadeia jamais mandaria
        para o segundo. Devolve `[(id, conf_knn, char_knn, char_ocr, dist)]`.

        `dist` é a distância ao vizinho mais próximo, crua. Ela existe porque a
        F24 trocou a confiança por margem e a coluna "já na base" da F23 estava
        definida como `conf >= 0,99` — na escala nova isso mede outra coisa
        ("o vencedor está 100x mais perto"), e não o que a coluna promete. Com a
        distância a definição é direta: zero é cópia exata da base.

        `com_ocr=False` pula o EasyOCR, que é 16 ms por caractere contra os 12
        do k-NN inteiro. É o que torna a varredura de `k` viável.
        """
        saida = []
        for b in pagina.boxes:
            justo, contexto = pagina.recortes(b)
            ck, fk = self.learner.predict(justo)
            perto = self.learner.vizinhos(justo, k=1)
            dist = perto[0][1] if perto else float("inf")
            co = ""
            if com_ocr:
                co, _ = self.ocr.easyocr_ocr_conf(justo, contexto=contexto)
            if com_rede:
                self.predictor.predict(justo)
            saida.append((id(b), fk, ck, co, dist,
                          self.learner.margem(justo)))
        if com_ocr:
            for uma in pagina.linhas:
                if ldl.em_bloco(uma):
                    tira = ldl.faixa_da_linha(pagina.arr, uma)
                    if tira is not None:
                        self.ocr.easyocr_linha_conf(tira)
        return saida


def rodar(cadeia, paginas, caminho, learner_threshold, trava,
          neural_threshold=None, deslocam=None):
    """
    `[(fonte, conf, lido, verdade, página)]` para cada box que casou com rótulo.

    `trava` segue `ler_pagina`: `None` é "a linha manda sempre" e `0.0` é "a
    linha não encosta em nada" — toda confiança é >= 0, então todo box fica
    travado e o resultado é idêntico a não ler linha nenhuma.

    `deslocam` é o filtro da F36, e o padrão `None` reproduz o que a ação fazia
    antes dela — que é o que as tabelas da F18 à F35 mediram.
    """
    saida = []
    for p in paginas:
        lidos = ldl.ler_pagina(
            p.arr, p.linhas,
            ler_faixa=cadeia.ocr.easyocr_linha_conf,
            ler_caractere=cadeia.leitor(p, caminho, learner_threshold,
                                        neural_threshold),
            deslocam=deslocam,
            conf_maxima_para_trocar=trava,
        )
        for b, char, conf, fonte in lidos:
            verdade = p.verdade.get(id(b))
            if verdade is not None:
                saida.append((fonte, conf, char, verdade, p.nome, id(b)))
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


def tabela_por_pagina(linhas, na_base):
    """
    O acerto página a página, e o quanto de cada uma o k-NN já tem na base.

    **A coluna da direita é o aviso, e ela não é decoração.** `na_base` são os
    boxes cujo vizinho mais próximo está a distância **zero** — o recorte já
    está em `training_data`, byte a byte. Ali o k-NN não generaliza, consulta a
    própria cópia, e o acerto medido não vale como previsão para página nova.

    É o que separa esta medição de uma boa notícia falsa: `training_data` foi
    colhida com "Aprender com Página Atual", e nada impede que as páginas
    rotuladas — que são as mesmas em que se aprendeu — estejam lá dentro.

    **A definição mudou na F24, e a mudança é o próprio assunto.** Na F23 esta
    coluna era `conf >= 0,99`, que valia enquanto a confiança fosse
    `1 - distância/2000`. Com a margem, 0,99 passou a querer dizer "o vencedor
    está 100x mais perto que a segunda classe" — verdadeiro em box fácil que a
    base nunca viu. O número não teria mudado de nome, só de significado.
    """
    por_pagina = {}
    for reg in linhas:
        por_pagina.setdefault(reg[4], []).append(reg)

    print(f"\n{'página':<52}{'boxes':>7}{'acerto':>9}{'já na base':>12}")
    for nome, parte in por_pagina.items():
        copias = sum(1 for reg in parte if reg[5] in na_base)
        curto = nome if len(nome) <= 50 else nome[:47] + "..."
        print(f"{curto:<52}{len(parte):>7}{acerto(parte):>8.2f}%"
              f"{100.0 * copias / len(parte):>11.1f}%")


class _BoxFalso:
    """O mínimo que `ui.confidence` olha num box, para não copiar a regra."""

    __slots__ = ("char", "source", "confidence")

    def __init__(self, reg):
        self.char = reg[2]
        self.source = reg[0] if reg[2] else ""
        self.confidence = reg[1]


def tabela_fila_e_linha(ancora, producao):
    """
    O que a corroboração da linha faz com a **fila de revisão**.

    Um box abaixo da trava numa linha lida não fica com a própria confiança:
    recebe `confianca(concordam, conf_linha, cf)`, que é o **máximo** dos dois
    quando as duas leituras concordam (F17). Uma leitura a 0,30 corroborada
    sobe para a confiança da linha e **sai da fila**.

    O desenho se sustenta — corroboração é informação, e foi medida como tal —,
    mas ele nunca foi olhado do lado da revisão. As duas perguntas são:

    - dos boxes que a linha tirou da fila, quantos estavam **errados**? Cada um
      é um erro que o revisor deixou de ver por causa de uma segunda leitura que
      errou junto;
    - e a conta líquida, porque a linha também **empurra** box para a fila:
      quando as duas leituras divergem vale a menor, e aí a confiança cai.

    `ancora` tem de vir de uma corrida com `trava=0.0`, que é o que faz
    `ler_pagina` devolver a confiança crua de cada box.
    """
    saiu = saiu_errado = entrou = entrou_errado = 0
    for a, p in zip(ancora, producao):
        antes = conf_ui.precisa_revisao(_BoxFalso(a))
        depois = conf_ui.precisa_revisao(_BoxFalso(p))
        if antes == depois:
            continue
        errado = normalizar(p[2]) != normalizar(p[3])
        if antes and not depois:
            saiu += 1
            saiu_errado += errado
        else:
            entrou += 1
            entrou_errado += errado

    print(f"\nA linha e a fila de revisão (corte em "
          f"{conf_ui.LIMIAR_ALTO:.2f}):")
    print(f"  saíram da fila por corroboração: {saiu:>5}"
          f"   dos quais errados: {saiu_errado}")
    print(f"  entraram na fila por divergência:{entrou:>5}"
          f"   dos quais errados: {entrou_errado}")
    print(f"  saldo de erros visíveis ao revisor: "
          f"{entrou_errado - saiu_errado:+d}")


def tabela_revisao(linhas):
    """
    A fila de revisão (F3.2) medida **como fila**: custo para achar os erros.

    O outro uso da confiança, e o que nunca foi medido em separado. A F14 mediu
    os cortes contra a rede sozinha; aqui a página vem da cadeia, e a cadeia
    mistura fontes cuja confiança **não está na mesma régua** — softmax
    calibrado a T = 2,19 na rede (F22), `1 - distância/2000` no k-NN, a do CRNN
    no EasyOCR. `ui/confidence.py` aplica o mesmo 0,90 às três.

    A segunda tabela é o teste dessa suspeita. Se a régua fosse comum, ordenar
    a fila pela confiança crua e ordená-la pelo **percentil dentro da própria
    fonte** dariam curvas parecidas. Se a do percentil for melhor, as fontes
    estão descalibradas entre si e o número único está custando revisão.
    """
    por_fonte = {}
    for reg in linhas:
        por_fonte.setdefault(reg[0], []).append(reg)

    print(f"\n{'fonte':<16}{'boxes':>7}{'erros':>7}{'mediana':>19}"
          f"{'':>4}{'abaixo de 0,90':>16}{'erros pegos':>13}")
    print(f"{'':<16}{'':>7}{'':>7}{'erro':>9}{'acerto':>10}")
    for fonte, parte in sorted(por_fonte.items(), key=lambda kv: -len(kv[1])):
        erros = [r for r in parte if normalizar(r[2]) != normalizar(r[3])]
        acertos = [r for r in parte if normalizar(r[2]) == normalizar(r[3])]
        abaixo = [r for r in parte if r[1] < conf_ui.LIMIAR_ALTO]
        pegos = sum(1 for r in abaixo
                    if normalizar(r[2]) != normalizar(r[3]))
        me = float(np.median([r[1] for r in erros])) if erros else float("nan")
        ma = (float(np.median([r[1] for r in acertos]))
              if acertos else float("nan"))
        print(f"{fonte:<16}{len(parte):>7}{len(erros):>7}{me:>9.4f}{ma:>10.4f}"
              f"{'':>4}{len(abaixo):>16}{pegos:>13}")

    # A fila ordenada de dois jeitos. `certos` acompanha para o custo sair em
    # "acertos revisados à toa", que é o que o revisor paga.
    def custo(ordenados):
        total_erros = sum(1 for ok in ordenados if not ok)
        if not total_erros:
            return [None, None, None]
        saida, pegos, toa, restantes = [], 0, 0, [0.25, 0.50, 0.75]
        for ok in ordenados:
            if ok:
                toa += 1
            else:
                pegos += 1
            while restantes and pegos >= restantes[0] * total_erros:
                saida.append(toa)
                restantes.pop(0)
        return saida + [None] * len(restantes)

    def ok(reg):
        return normalizar(reg[2]) == normalizar(reg[3])

    crua = [ok(r) for r in sorted(linhas, key=lambda r: r[1])]

    # Percentil dentro da fonte: a posição relativa do box entre os da mesma
    # origem. Tira a régua de cada uma e deixa só a ordem.
    percentil = {}
    for parte in por_fonte.values():
        ordenada = sorted(parte, key=lambda r: r[1])
        for i, reg in enumerate(ordenada):
            percentil[reg[5]] = i / max(1, len(ordenada) - 1)
    por_percentil = [ok(r)
                     for r in sorted(linhas, key=lambda r: percentil[r[5]])]

    print(f"\n{'ordenação da fila':<22}" + "".join(
        f"{f'{p}% dos erros':>18}" for p in (25, 50, 75)))
    for nome, ordenados in (("confiança crua (hoje)", crua),
                            ("percentil por fonte", por_percentil)):
        celulas = "".join(f"{('—' if c is None else f'{c} à toa'):>18}"
                          for c in custo(ordenados))
        print(f"{nome:<22}{celulas}")


def tabela_do_knn(aquecidos, verdade):
    """
    O elo do k-NN sozinho: acerto, e o quanto a confiança denuncia o erro.

    A segunda metade é a tabela da F14 aplicada a este elo, e ela mede o outro
    uso da confiança — a fila de revisão da F3.2, que ordena por ela. As duas
    colunas comparam a de produção (distância absoluta) com a margem, que a F24
    mediu e devolveu.
    """
    medidos = [(fk, ck, margem, verdade[chave])
               for chave, fk, ck, _co, _d, margem in aquecidos
               if chave in verdade]
    if not medidos:
        return
    certos = [normalizar(ck) == normalizar(vd) for _fk, ck, _m, vd in medidos]
    print(f"\nO k-NN sozinho, em {len(medidos)} boxes: "
          f"**{100.0 * sum(certos) / len(medidos):.2f}%**")

    print(f"\n{'corte':>8}{'':>4}{'produção (distância)':>26}{'':>4}"
          f"{'margem (F24, fora)':>26}")
    print(f"{'':>8}{'':>4}{'pega':>8}{'à toa':>9}{'escapa':>9}{'':>4}"
          f"{'pega':>8}{'à toa':>9}{'escapa':>9}")
    for corte in (0.30, 0.50, 0.70, 0.90, 0.99):
        celulas = []
        for conf_de in (lambda r: r[0], lambda r: r[2]):
            pega = toa = escapa = 0
            for reg, ok in zip(medidos, certos):
                abaixo = conf_de(reg) < corte
                if not ok and abaixo:
                    pega += 1
                elif not ok:
                    escapa += 1
                elif abaixo:
                    toa += 1
            celulas.append(f"{pega:>8}{toa:>9}{escapa:>9}")
        print(f"{corte:>8.2f}{'':>4}{celulas[0]}{'':>4}{celulas[1]}")

    # A tabela de cortes acima serve para escolher um limiar, **não** para
    # comparar as duas fórmulas: as escalas são outras, e o mesmo 0,70 corta em
    # lugares diferentes da distribuição. A comparação justa é a recall igual —
    # para pegar a mesma fração dos erros, quantos acertos vão para a revisão à
    # toa. É a única forma de o número não depender de onde se corta.
    alvos = (0.25, 0.50, 0.75)
    print(f"\n{'para pegar':<14}" + "".join(f"{f'{int(a*100)}% dos erros':>18}"
                                           for a in alvos))
    for nome, conf_de in (("produção", lambda r: r[0]),
                          ("margem", lambda r: r[2]),
                          ("mín. das duas", lambda r: min(r[0], r[2]))):
        custos = _custo_por_recall(medidos, certos, conf_de, alvos)
        celulas = "".join(f"{('—' if c is None else f'{c} à toa'):>18}"
                          for c in custos)
        print(f"{nome:<14}{celulas}")

    for nome, conf_de in (("produção", lambda r: r[0]),
                          ("margem", lambda r: r[2])):
        erros = [conf_de(r) for r, ok in zip(medidos, certos) if not ok]
        acertos = [conf_de(r) for r, ok in zip(medidos, certos) if ok]
        me = float(np.median(erros)) if erros else float("nan")
        ma = float(np.median(acertos)) if acertos else float("nan")
        print(f"  {nome:<16} mediana de um erro {me:.4f}, de um acerto {ma:.4f}")


def _custo_por_recall(medidos, certos, conf_de, alvos):
    """
    Quantos acertos entram na revisão até pegar cada fração dos erros.

    Percorre os boxes do menos confiante para o mais confiante — que é a ordem
    em que o revisor os veria (F3.2) — e anota o custo acumulado ao cruzar cada
    alvo. `None` quando o alvo não é alcançável.
    """
    pares = sorted((conf_de(r), ok) for r, ok in zip(medidos, certos))
    total_erros = sum(1 for _c, ok in pares if not ok)
    if not total_erros:
        return [None] * len(alvos)

    saida, pegos, toa = [], 0, 0
    restantes = list(alvos)
    for _c, ok in pares:
        if ok:
            toa += 1
        else:
            pegos += 1
        while restantes and pegos >= restantes[0] * total_erros:
            saida.append(toa)
            restantes.pop(0)
    return saida + [None] * len(restantes)


#: Faixas de distância crua do vizinho mais próximo (F35).
#:
#: É a tabela de roteamento **sem escala**: quem decide o corte é a distância, e
#: `DISTANCIA_MAXIMA` com o `learner_threshold` são só uma parametrização dela —
#: `conf > t` é `d < D(1-t)`, então os dois limiares têm um grau de liberdade só.
#: Em unidade de distância a pergunta fica direta: **até onde o k-NN ainda ganha
#: do EasyOCR?**
DISTANCIAS = (0, 200, 500, 800, 1000, 1200, 1400, 1700, 2000, 2500, 3000,
              float("inf"))


def tabela_por_distancia(aquecidos, verdade):
    """O k-NN contra o EasyOCR nos mesmos boxes, por distância crua."""
    print(f"\n{'distância ao vizinho':<24}{'boxes':>8}{'k-NN':>9}{'EasyOCR':>10}"
          f"{'':>4}{'quem ganha':<12}")
    for lo, hi in zip(DISTANCIAS, DISTANCIAS[1:]):
        parte = [(ck, co, verdade[chave])
                 for chave, _fk, ck, co, dist, _m in aquecidos
                 if lo <= dist < hi and chave in verdade]
        if not parte:
            continue
        knn = 100.0 * sum(1 for c, _o, v in parte
                          if normalizar(c) == normalizar(v)) / len(parte)
        ocr = 100.0 * sum(1 for _c, o, v in parte
                          if normalizar(o) == normalizar(v)) / len(parte)
        ganha = "k-NN" if knn > ocr else ("EasyOCR" if ocr > knn else "empate")
        rotulo = f"{lo} – {'∞' if hi == float('inf') else int(hi)}"
        print(f"{rotulo:<24}{len(parte):>8}{knn:>8.1f}%{ocr:>9.1f}%"
              f"{'':>4}{ganha:<12}")


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
        parte = [(ck, co, verdade[chave])
                 for chave, fk, ck, co, _d, _m in aquecidos
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


class _ForaDoAlfabeto:
    """
    `ch in isto` é "o `english_g2` não escreve `ch`" — o filtro **largo** da F36.

    Existe para `em_bloco` ter uma polaridade só: ele pergunta "este glifo
    desloca?", e o filtro largo responde por complemento. Sem isto o parâmetro
    teria de aceitar as duas leituras, que é como se escreve um `if` invertido
    seis meses depois.
    """

    def __init__(self, alfabeto):
        self._alfabeto = set(alfabeto)

    def __contains__(self, ch):
        return bool(ch) and ch not in self._alfabeto


def tabela_alfabeto(cadeia, paginas, caminho, learner_threshold, trava):
    """
    Os dois filtros contra nenhum, nos mesmos boxes (F36).

    O filtro tira do modo bloco a linha cuja **âncora** leu um glifo que o
    reconhecedor de linha não escreve casa a casa. A linha que sai do bloco não
    fica sem leitura: cai no modo por caractere, que é a âncora sozinha.

    **São dois filtros e não um, e a diferença entre eles é a fase inteira.**

    - **largo** — tudo que está fora do alfabeto do `english_g2`. Foi a primeira
      tentativa, e é o que o cabeçalho da F17 sugere ao falar em "alfabeto".
    - **estreito** — só o que gasta um número de casas diferente de um: figurina
      e ligadura. Um `±` ou uma aspa curva estão fora do alfabeto e saem como
      **um** caractere errado, que é o erro comum — o alinhamento absorve e a
      trava filtra.

    As três contas que decidem:

    - **quantas linhas cada um tira**, com a causa separada. A F17 estimou 19%
      das linhas por causa de figurina; o que passar muito disso é o filtro
      pegando outra coisa;
    - **o saldo em caracteres**, separado em melhorou e piorou. Um filtro que
      conserta 30 e quebra 28 tem saldo 2 e não é o mesmo que um que conserta 2
      e não quebra nenhum;
    - **o acerto**, que é o que decide, mas só depois das duas de cima — em
      10.484 caracteres, um ponto decimal é uma dúzia de casos.
    """
    largo = _ForaDoAlfabeto(ldl.ALFABETO_EASYOCR)
    estreito = ldl.GLIFOS_QUE_DESLOCAM
    filtros = [("sem filtro", None), ("estreito (F36)", estreito),
               ("largo (alfabeto)", largo)]

    corridas = {nome: rodar(cadeia, paginas, caminho, learner_threshold, trava,
                            deslocam=d)
                for nome, d in filtros}

    # As linhas, contadas sobre a mesma âncora que a cadeia leu. Tudo aqui já
    # está memorizado pelo aquecimento, então a contagem não custa consulta.
    dentro = 0
    fora = {nome: 0 for nome, _d in filtros[1:]}
    causas = {"ligadura": 0, "figurina": 0, "outro símbolo": 0}
    for p in paginas:
        leitor = cadeia.leitor(p, caminho, learner_threshold)
        for uma in p.linhas:
            chars = [leitor(b)[0] for b in uma]
            if not ldl.em_bloco(uma, None, chars):
                continue
            dentro += 1
            for nome, d in filtros[1:]:
                if not ldl.em_bloco(uma, d, chars):
                    fora[nome] += 1
            if ldl.em_bloco(uma, largo, chars):
                continue
            # A causa é do **largo**, que é o que tira mais: é a decomposição
            # dele que mostra o que o estreito deixa de tirar, e por quê.
            culpados = [c for c in chars if c and (len(c) > 1 or c in largo)]
            if any(len(c) > 1 for c in culpados):
                causas["ligadura"] += 1
            elif any(c in FIGURINAS for c in culpados):
                causas["figurina"] += 1
            else:
                causas["outro símbolo"] += 1

    print("\n--- Os filtros da F36 ---")
    print(f"linhas lidas em bloco, sem filtro{'':<6}{dentro:>8}")
    for nome, _d in filtros[1:]:
        pct = 100.0 * fora[nome] / dentro if dentro else 0.0
        print(f"  que o {nome:<26}tira{fora[nome]:>8}   ({pct:.1f}%)")
    print("a causa da exclusão, no largo:")
    for causa, n in causas.items():
        print(f"    {causa:<20}{n:>8}")

    base = corridas["sem filtro"]
    linhas_da_tabela = []
    for nome, _d in filtros:
        r = corridas[nome]
        melhorou = piorou = mudou = 0
        for a, b in zip(base, r):
            if a[2] == b[2]:
                continue
            mudou += 1
            antes = normalizar(a[2]) == normalizar(a[3])
            depois = normalizar(b[2]) == normalizar(b[3])
            if depois and not antes:
                melhorou += 1
            elif antes and not depois:
                piorou += 1
        trocados = sum(1 for reg in r if reg[0] == "easyocr_linha")
        linhas_da_tabela.append(
            (nome, [acerto(r), trocados, mudou, melhorou, piorou]))
    tabela_varredura(
        "o filtro da linha (F36), contra a corrida sem filtro",
        ["acerto", "trocados", "mudaram", "consertos", "quebras"],
        linhas_da_tabela)


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
    ap.add_argument("--k", type=int, default=None,
                    help="quantos vizinhos votam no k-NN (F24); sem isto, o "
                         "`K_VIZINHOS` de produção")
    ap.add_argument("--knn", action="store_true",
                    help="mede só o elo do k-NN, sem carregar o EasyOCR — é a "
                         "rodada rápida, e é como se varre o --k")
    ap.add_argument("--rede", type=float, nargs="*", default=None,
                    help="varre o NEURAL_THRESHOLD (a tabela da F22), com a "
                         "composição da cadeia em cada ponto")
    ap.add_argument("--distancia", type=float, nargs="*", default=None,
                    help="varre o DISTANCIA_MAXIMA do k-NN (F35), recontando a "
                         "confiança a partir da distância já medida")
    ap.add_argument("--alfabeto", action="store_true",
                    help="mede os dois filtros da linha (F36) contra nenhum, "
                         "nos mesmos boxes: o estreito de produção e o largo "
                         "que foi tentado antes dele")
    ap.add_argument("--com-filtro", action="store_true",
                    help="liga o filtro de glifo da F36 em todas as tabelas; "
                         "produção não o passa, então o padrão é sem")
    ap.add_argument("--combinada", action="store_true",
                    help="varre o roteamento com min(absoluta, margem) **e** com "
                         "a de produção, no mesmo processo e na mesma base — a "
                         "ideia aberta na F24")
    args = ap.parse_args()

    caminho = "neural" if args.neural else "hibrido"
    padrao_learner = (LEARNER_THRESHOLD_NEURAL if args.neural
                      else LEARNER_THRESHOLD_HIBRIDO)
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

    # Guardado antes de envelopar: o cabeçalho precisa do tamanho da base, e a
    # partir daqui `cadeia.learner` pode não ser mais o memo cru.
    learner_cru = cadeia.learner._alvo

    # O voto envolve o memo, e não o k-NN: as distâncias do aquecimento já estão
    # no cache, então varrer `k` não custa consulta nova nenhuma. É a mesma forma
    # de `_MemoComDistancia`, e pela mesma razão.
    k_efetivo = core_learner.K_VIZINHOS if args.k is None else args.k
    if args.k is not None:
        cadeia.learner = _MemoComVoto(cadeia.learner, args.k)

    print(f"Preparando {len(achadas)} página(s)...")
    paginas, aquecidos = [], []
    for caminho_img, caminho_box in achadas:
        p = Pagina(caminho_img, caminho_box, arbitro)
        if len(p.rotulados) < MIN_ROTULADOS:
            continue
        paginas.append(p)
        aquecidos.extend(cadeia.aquecer(p, com_rede=args.neural,
                                        com_ocr=not args.knn))
        print(f"  {p.nome}  {p.medidos} de {len(p.boxes)} boxes com rótulo",
              flush=True)

    if not paginas:
        print("nenhuma página com rótulos suficientes")
        return 1

    verdade = {}
    for p in paginas:
        verdade.update(p.verdade)
    total = sum(p.medidos for p in paginas)

    na_base = {chave for chave, _fk, _ck, _co, dist, _m in aquecidos if dist == 0.0}

    # O tamanho da base entra no cabeçalho porque **duas rodadas só são
    # comparáveis se ele não mudou**, e ele muda sozinho: "Aprender com Página
    # Atual" escreve em `training_data` enquanto a medição roda. Foi assim que a
    # F24 quase concluiu que uma reversão fiel tinha mudado um caractere — a
    # base tinha crescido de 70.755 para 73.900 entre uma rodada e a outra, e
    # nada na saída dizia isso.
    print(f"\n=========== {total} caracteres em {len(paginas)} página(s), "
          f"caminho {caminho}, k = {k_efetivo}, "
          f"{learner_cru.total} referências ===========")

    if args.knn:
        tabela_do_knn(aquecidos, verdade)
        return 0

    # O padrão espelha produção, que **não** passa filtro — a F36 mediu e
    # desligou. `--com-filtro` liga em todas as tabelas, para quem quiser ver o
    # efeito dele em outra coluna que não a do `--alfabeto`.
    deslocam = ldl.GLIFOS_QUE_DESLOCAM if args.com_filtro else None
    producao = rodar(cadeia, paginas, caminho, padrao_learner, padrao_trava,
                     deslocam=deslocam)
    ancora = rodar(cadeia, paginas, caminho, padrao_learner, 0.0,
                   deslocam=deslocam)

    print(f"\nComo está em produção "
          f"(learner_threshold {padrao_learner}, trava {padrao_trava}): "
          f"**{acerto(producao):.2f}%**")
    print(f"Só a âncora, sem a leitura por linha: {acerto(ancora):.2f}%")

    tabela_composicao(producao)
    tabela_por_pagina(producao, na_base)
    tabela_linha(ancora, producao)
    tabela_revisao(producao)
    tabela_fila_e_linha(ancora, producao)
    tabela_do_knn(aquecidos, verdade)
    tabela_roteamento(aquecidos, verdade)
    tabela_por_distancia(aquecidos, verdade)

    if args.alfabeto:
        tabela_alfabeto(cadeia, paginas, caminho, padrao_learner, padrao_trava)

    if args.learner is not None or args.combinada:
        limiares = args.learner or [0.5, 0.7, 0.8, 0.85, 0.9, 0.95]
        # Com `--combinada` as duas confianças são varridas na mesma base e no
        # mesmo processo. É o cuidado que a F24 aprendeu à força: comparar com
        # uma tabela de outra rodada é comparar com outra base.
        confiancas = [("o roteamento do k-NN", cadeia.learner)]
        if args.combinada:
            confiancas.append(("min(absoluta, margem)",
                               _MemoCombinado(cadeia.learner)))

        original = cadeia.learner
        for nome, memo in confiancas:
            cadeia.learner = memo
            linhas_da_tabela = []
            for lt in limiares:
                so_ancora = rodar(cadeia, paginas, caminho, lt, 0.0,
                                  deslocam=deslocam)
                # **A trava acompanha o limiar só no híbrido**, e a distinção é
                # a F39. Lá os dois são o mesmo número por desenho: a trava
                # existe para a linha agir exatamente onde o k-NN se recusou, e
                # `CONF_MAXIMA_PARA_A_LINHA_HIBRIDO` é literalmente
                # `LEARNER_THRESHOLD_HIBRIDO` (F21/F23). No caminho neural são
                # independentes — a trava é 0,70 e o limiar do k-NN é outro
                # número —, e amarrá-los aqui punha na tabela uma configuração
                # que produção nunca roda.
                trava_do_ponto = lt if caminho == "hibrido" else padrao_trava
                com_linha = rodar(cadeia, paginas, caminho, lt, trava_do_ponto,
                                  deslocam=deslocam)
                linhas_da_tabela.append(
                    (f"{lt:.2f}", [acerto(so_ancora), acerto(com_linha)]))
            coluna = ("com a linha" if caminho == "hibrido"
                      else f"linha @{padrao_trava:.2f}")
            tabela_varredura(f"learner_threshold — {nome}",
                             ["âncora", coluna], linhas_da_tabela)
        cadeia.learner = original

    if args.rede is not None:
        if not args.neural:
            print("\n--rede só faz sentido com --neural: o caminho híbrido não "
                  "carrega a rede.")
        else:
            # A tabela da F22, com a composição junto: no platô o que muda é
            # **quem responde**, não o acerto, e sem a composição o platô parece
            # empate quando na verdade é o k-NN sendo desligado como segunda
            # opinião.
            linhas_da_tabela = []
            for nt in (args.rede or [0.4, 0.6, 0.7, 0.8, 0.9]):
                r = rodar(cadeia, paginas, caminho, padrao_learner,
                          padrao_trava, neural_threshold=nt,
                          deslocam=deslocam)
                conta = {}
                for reg in r:
                    conta[reg[0]] = conta.get(reg[0], 0) + 1
                linhas_da_tabela.append((f"{nt:.2f}", [
                    acerto(r), conta.get("neural", 0), conta.get("learner", 0),
                    conta.get("easyocr", 0)]))
            tabela_varredura("NEURAL_THRESHOLD (F22, remedido)",
                             ["acerto", "rede", "k-NN", "EasyOCR"],
                             linhas_da_tabela)

    if args.distancia is not None:
        # O corte efetivo é `D * (1 - t)`, e é ele que roteia. A coluna existe
        # para a tabela poder ser lida sem refazer a conta de cabeça.
        linhas_da_tabela = []
        for D in (args.distancia or [1000, 1500, 2000, 3000, 5000]):
            memo = cadeia.learner
            cadeia.learner = _MemoComDistancia(memo, D)
            r = rodar(cadeia, paginas, caminho, padrao_learner, padrao_trava,
                      deslocam=deslocam)
            cadeia.learner = memo
            conta = {}
            for reg in r:
                conta[reg[0]] = conta.get(reg[0], 0) + 1
            linhas_da_tabela.append((f"{D:.0f}", [
                acerto(r), int(round(D * (1 - padrao_learner))),
                conta.get("learner", 0), conta.get("easyocr", 0)]))
        tabela_varredura(
            f"DISTANCIA_MAXIMA (F35), com learner_threshold {padrao_learner}",
            ["acerto", "corte efetivo", "k-NN", "EasyOCR"], linhas_da_tabela)

    if args.trava is not None:
        valores = [("sem linha", 0.0)]
        valores += [(f"{t:.2f}", t) for t in (args.trava or
                                              [0.6, 0.7, 0.8, 0.85, 0.9, 0.95])]
        valores.append(("sempre", None))
        linhas_da_tabela = []
        for rotulo, t in valores:
            r = rodar(cadeia, paginas, caminho, padrao_learner, t,
                      deslocam=deslocam)
            trocados = sum(1 for reg in r if reg[0] == "easyocr_linha")
            linhas_da_tabela.append((rotulo, [acerto(r), trocados]))
        tabela_varredura("trava da leitura por linha (F18)",
                         ["acerto", "trocados"], linhas_da_tabela)

    return 0


if __name__ == "__main__":
    sys.exit(main())
