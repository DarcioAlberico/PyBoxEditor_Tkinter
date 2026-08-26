"""
Os motores de **linha**, medidos lado a lado nas mesmas faixas.

    python medir_linha.py                       # todos os motores disponíveis
    python medir_linha.py --motores easyocr tesseract7
    python medir_linha.py --paginas 3           # limita a amostra
    python medir_linha.py --so 0108             # só as páginas cujo nome casa
    python medir_linha.py --listar              # o que está instalado, e sai

**Por que este arquivo existe.** A SPEC §7.1 comparava seis motores de linha por
licença, runtime e entrada de treino, e nenhuma linha daquela tabela tinha
**número medido nestes livros**. O único motor de linha que este projeto já
havia medido era o EasyOCR (F17: 72,9% para 89,5%), e a tabela da F18 decidiu a
trava com esse número sozinho. Comparar os candidatos exige rodá-los na mesma
faixa, contra a mesma verdade, no mesmo processo — que é o que faltava.

A tabela medida está na §7.1, sob "E agora a tabela tem número", e saiu daqui.
Os cinco motores deste arquivo entraram nela. **O EasyOCR com âncora própria deu 89,54% contra os 89,5%
da F17** — é a validação deste instrumento, e é o motivo de a âncora ser um
argumento e não uma escolha enterrada no código.

**E o mais barato de todos já estava instalado.** O `tesseract --version` deste
ambiente responde 5.5.0, que é LSTM, isto é, um reconhecedor de linha. O
`core/services/ocr_service.py` o chama com `--psm 10` — "trate a imagem como um
único caractere". Não é defeito: os dois chamadores são de caractere
(`auto_fill_characters` e a ação de box selecionado), e para eles o `psm 10` é o
modo certo. Mas a capacidade de linha nunca foi exercida, e exercê-la custa uma
string. É o `tesseract7` daqui.

## A barra, que este script imprime para ninguém ter de lembrar

A rede responde 98,9% dos boxes e a cadeia acerta 97,6%. A trava da F18 existe
porque a linha a 89,5% por cima da rede regride 7,3 pontos. **Um motor de linha
só muda produção se passar de 97,6%** — abaixo disso ele é melhor que o EasyOCR
e a trava continua onde está. O script diz isso na cara, por motor.

## A âncora, que é o que quase saiu errado daqui

O `ler_pagina` distribui a string da linha sobre os boxes alinhando-a contra a
**âncora** — uma leitura com exatamente um item por box. **O 89,5% da F17 foi
medido com o EasyOCR por caractere nesse papel**, e não sem âncora nenhuma:
*"A leitura por caractere é a âncora, e resolve"*. Trocar isso muda o número em
quinze pontos, então o script oferece as duas e diz qual usou.

- `--ancora propria` (padrão) — cada motor ancora em **si mesmo**, lido caractere
  a caractere. É o que a F17 mediu e o que as duas ações de menu fazem, então é
  o número comparável ao 89,5%. Custa o dobro: a âncora é uma consulta por box.
- `--ancora vazia` — sem âncora, a linha se distribui pela posição. É mais duro e
  mais barato, mede o motor sem muleta, e **não** se compara com o 89,5%.

Motor sem modo por caractere (o `rapidocr` e o `doctr`) cai na âncora vazia, e o
relatório o marca com `*`.

## As duas populações, que não são a mesma

- **acerto por box** — todos os boxes que casaram com um rótulo, pelo
  `ler_pagina` de produção. Ele carrega o custo das linhas que o `em_bloco`
  recusa: linha de um box só, girada ou negativa não é lida, e os boxes dela
  contam como erro. O cabeçalho diz quantas foram.
- **CER e linha exata** — só as **linhas completas**, aquelas em que todo box tem
  rótulo, e **independem da âncora**: são a string crua do motor contra a
  verdade. É a coluna que compara motor com motor sem passar pela distribuição.
  Numa linha com buraco a verdade é mais curta que a faixa, o motor lê o que
  está lá e a distância de edição cobra dele um caractere que ele acertou —
  medir CER ali mediria a rotulação, não o motor.

## O que ele não mede

A cadeia. Aqui os motores correm **sozinhos**, que é a pergunta "algum deles
passa da rede?". Plugar o vencedor na cadeia é `medir_cadeia.py`, trocando o
`ler_faixa=cadeia.ocr.easyocr_linha_conf` do `rodar` — e a tabela que sai de lá
é a da F18, com a trava varrida.

## O que cada motor recebe, e o que o docTR não recebe

Os cinco rodaram. O `rapidocr` e o `doctr` foram escritos a partir da
documentação, com o pacote ausente, e passaram de primeira — nenhum precisou de
conserto. Um motor que não carrega aparece como indisponível com a exceção ao
lado, em vez de derrubar a corrida.

**O docTR está em desvantagem estrutural aqui, e o número dele é um piso.** O
`crnn_vgg16_bn` declara `input_shape (3, 32, 128)` — 128 pixels de largura. Ele
reconhece **palavra**, e a faixa de linha destes livros passa de mil pixels: entra
esmagada em oito vezes, e o CTC responde repetindo trecho. A lição da F17 de
pular o detector vale para reconhecedor de linha, que é o que o `english_g2` e o
PP-OCR são; para um de palavra, o detector é quem parte a linha no tamanho que o
modelo espera. O número justo dele sairia do `ocr_predictor` inteiro sobre a
faixa, e este arquivo não faz isso.
"""

import argparse
import sys
import time
from typing import Optional, Tuple

import numpy as np

from core import leitura_de_linha as ldl
from core.avaliacao_pagina import normalizar
from core.notacao import _alinhar
from core.services.learning_service import LearningService
from core.services.ocr_service import OCRService
from medir_cadeia import Pagina
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas


#: O que a cadeia acerta hoje, nas páginas rotuladas (F18). É a barra: abaixo
#: dela, um motor de linha melhor não move a trava e não muda produção.
BARRA_DA_CADEIA = 97.6

#: O que o EasyOCR sozinho deu na F17, com alinhamento e **âncora própria**. É a
#: linha de base contra a qual os candidatos novos se comparam — e só se compara
#: com uma corrida em `--ancora propria`, que é por isso que a tabela some com
#: esta linha quando a âncora é a vazia.
BASE_DA_F17 = 89.5


def _console_em_utf8():
    """
    O console do Windows é cp1252, e este relatório tem `♗` e travessão dentro.

    Sem isto o script morre de `UnicodeEncodeError` no meio da tabela, e morre
    justamente na coluna de exemplo de erro, que é a que interessa.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _rgb(faixa: np.ndarray) -> np.ndarray:
    """Cinza para três canais. O docTR e o RapidOCR esperam imagem de câmera."""
    if faixa.ndim == 3:
        return faixa
    return np.repeat(faixa[:, :, None], 3, axis=2)


# ----------------------------------------------------------------------
# Os motores, todos com o contrato do `ler_faixa`
# ----------------------------------------------------------------------

class Motor:
    """
    `(texto, confiança)` a partir de uma faixa de linha — o contrato do
    `ler_faixa` que o `ler_pagina` chama, e o mesmo do `easyocr_linha_conf`.

    A resposta é **memorizada pelos bytes da faixa**, como o `_Memo` do
    `medir_cadeia.py` e pela mesma razão: cada faixa é lida duas vezes por
    corrida — uma pelo `ler_pagina`, para o acerto por box, e outra pela conta
    de CER —, e um motor de linha custa dezenas de milissegundos. O tempo
    reportado é o da consulta de verdade, não o da segunda leitura.
    """

    nome = "?"
    sobre = ""

    def __init__(self):
        self._cache = {}
        self.ms = 0.0
        self.consultas = 0
        self.falhas = 0
        self.ultimo_erro = ""

    def preparar(self):
        """Carrega o modelo. Estourar aqui marca o motor como indisponível."""

    def _ler(self, faixa: np.ndarray) -> Tuple[str, float]:
        raise NotImplementedError

    def por_caractere(self, justo: np.ndarray,
                      contexto: np.ndarray) -> Optional[Tuple[str, float]]:
        """
        A âncora do motor: um caractere por box, ou `None` se ele não tiver
        modo por caractere.

        `contexto` é o mesmo box esticado até a faixa vertical da linha, e quem
        souber usá-lo deve usá-lo — é a F14, e sem ele a caixa se perde.
        """
        return None

    def __call__(self, faixa: np.ndarray) -> Tuple[str, float]:
        chave = faixa.tobytes()
        if chave not in self._cache:
            t0 = time.perf_counter()
            try:
                self._cache[chave] = self._ler(faixa)
            except Exception as erro:                 # noqa: BLE001
                # Um motor que estoura numa faixa não derruba a corrida: a
                # linha conta como não lida, que é o que ela é.
                self._cache[chave] = ("", 0.0)
                self.falhas += 1
                self.ultimo_erro = f"{type(erro).__name__}: {erro}"
            self.ms += (time.perf_counter() - t0) * 1000.0
            self.consultas += 1
        return self._cache[chave]


class MotorEasyOCR(Motor):
    nome = "easyocr"
    sobre = "english_g2, `recognize` sem detector — o caminho de produção (F17)"

    def preparar(self):
        self._svc = OCRService()
        self._svc._init_easyocr()

    def _ler(self, faixa):
        return self._svc.easyocr_linha_conf(faixa)

    def por_caractere(self, justo, contexto):
        # Com `contexto`, que é o que a F14 mediu valer 66,9% -> 74,2%. A F17
        # ancorou no caminho por caractere de produção, e este é ele.
        return self._svc.easyocr_ocr_conf(justo, contexto=contexto)


class MotorTesseract(Motor):
    """
    O Tesseract 5 lendo **linha**, que é o que ele é.

    `--psm 7` é "a single text line" e `--psm 13` é "raw line", que pula a
    análise de layout. Os dois entram porque a diferença entre eles é
    exatamente o que se quer saber numa faixa já recortada — é a mesma pergunta
    que a F17 respondeu do lado do EasyOCR, quando trocar `readtext` por
    `recognize` levou 53,6% para 66,7%.

    Sem whitelist de propósito: o EasyOCR corre sem uma, e o
    `auto_fill_characters` passa a dele no caminho de caractere. Duas mudanças
    numa tabela só não se separam depois.
    """

    def __init__(self, psm: int):
        super().__init__()
        self._psm = psm
        self.nome = f"tesseract{psm}"
        self.sobre = ("linha única, com layout" if psm == 7
                      else "raw line, sem análise de layout")

    def preparar(self):
        import pytesseract
        self._pt = pytesseract
        self._svc = OCRService()
        pytesseract.get_tesseract_version()   # estoura aqui se o exe faltar

    def _ler(self, faixa):
        from PIL import Image
        dados = self._pt.image_to_data(
            Image.fromarray(faixa), config=f"--psm {self._psm}",
            output_type=self._pt.Output.DICT)

        # Junta os tokens sem espaço e fica com a **menor** confiança, como o
        # `easyocr_linha_conf` faz: o `ler_pagina` apaga os espaços logo em
        # seguida, e a confiança da linha é a do elo mais fraco dela.
        pedacos, confs = [], []
        for texto, conf in zip(dados.get("text", []), dados.get("conf", [])):
            texto = (texto or "").strip()
            if not texto:
                continue
            pedacos.append(texto)
            try:
                confs.append(float(conf))
            except (TypeError, ValueError):
                confs.append(-1.0)
        if not pedacos:
            return "", 0.0
        return "".join(pedacos), max(0.0, min(confs)) / 100.0

    def por_caractere(self, justo, _contexto):
        # O `--psm 10` de produção, chamado pelo serviço em vez de recriado
        # aqui: é o mesmo caminho que o `auto_fill_characters` usa.
        from PIL import Image
        return self._svc.tesseract_ocr_conf(Image.fromarray(justo))


class MotorRapidOCR(Motor):
    """
    Os modelos do PP-OCR sobre ONNXRuntime, sem o paddlepaddle (SPEC §7.1).

    **Reconhece sem detectar.** A faixa já veio recortada, e rodar o detector
    de novo é o erro que a F17 mediu do lado do EasyOCR — o CRAFT não achava
    texto num recorte e 18% das leituras saíam vazias. Aqui isso é
    `use_det=False`.

    **Escrito da documentação, não executado** — ver o aviso do topo.
    """

    nome = "rapidocr"
    sobre = "PP-OCR em ONNXRuntime, rec sem det"

    def preparar(self):
        from rapidocr import RapidOCR
        self._engine = RapidOCR()

    def _ler(self, faixa):
        r = self._engine(_rgb(faixa), use_det=False, use_cls=False, use_rec=True)
        txts = getattr(r, "txts", None)
        scores = getattr(r, "scores", None)
        if not txts:
            return "", 0.0
        texto = "".join(t or "" for t in txts)
        conf = min(float(s) for s in scores) if scores else 0.0
        return texto, max(0.0, min(1.0, conf))


class MotorDocTR(Motor):
    """
    O docTR no caminho de **reconhecimento puro**, pelo mesmo motivo do
    RapidOCR: a faixa já é a linha, e o detector só teria como atrapalhar.

    **Escrito da documentação, não executado** — ver o aviso do topo.
    """

    nome = "doctr"
    sobre = "crnn_vgg16_bn pré-treinado, recognition_predictor"

    def preparar(self):
        from doctr.models import recognition_predictor
        self._pred = recognition_predictor(pretrained=True)

    def _ler(self, faixa):
        saida = self._pred([_rgb(faixa)])
        if not saida:
            return "", 0.0
        texto, conf = saida[0][0], saida[0][1]
        return (texto or ""), max(0.0, min(1.0, float(conf)))


def motores_conhecidos():
    return [MotorEasyOCR(), MotorTesseract(7), MotorTesseract(13),
            MotorRapidOCR(), MotorDocTR()]


# ----------------------------------------------------------------------
# A verdade, por linha
# ----------------------------------------------------------------------

def verdade_da_linha(pagina, linha) -> Tuple[str, bool]:
    """
    `(texto rotulado, a linha está completa)`.

    Completa quer dizer que **todo** box da linha casou com um rótulo. Só essas
    entram na conta de CER — ver o cabeçalho do módulo.
    """
    pedacos, completa = [], True
    for b in linha:
        vd = pagina.verdade.get(id(b))
        if vd is None:
            completa = False
            continue
        pedacos.append(normalizar(vd))
    return "".join(pedacos), completa


def distancia_de_edicao(lido: str, correto: str) -> int:
    """
    Substituições + sobras + faltas, contadas a partir do alinhamento de
    produção.

    O `_alinhar` da `core.notacao` já é a DP de distância de edição — é ela que
    o `distribuir` usa desde a F17. Contar os passos que ela devolve dá a
    distância sem uma segunda implementação dela neste arquivo, que é o defeito
    que a F1.5 registrou.
    """
    d = 0
    for pos, ch in _alinhar(lido, correto):
        if pos is None:            # caractere sem box: falta na leitura
            d += 1
        elif not ch:               # box sobrando: caractere a mais na leitura
            d += 1
        elif lido[pos] != ch:      # troca
            d += 1
    return d


# ----------------------------------------------------------------------
# A corrida
# ----------------------------------------------------------------------

def _ancora_vazia(_b):
    """
    A âncora que não responde nada, para o motor correr **sozinho**.

    O `ler_pagina` distribui o texto da linha sobre os boxes usando a âncora
    como referência de alinhamento; com ela vazia sobra a posição, que é o que
    a F17 mediu quando o EasyOCR era o único leitor.
    """
    return "", 0.0, "vazio"


def _legivel(linha):
    """
    `em_bloco` com a âncora vazia desta corrida.

    A lista de vazios é o que a âncora responderia — sem ela, `em_bloco` cai no
    `b.char`, que aqui está vazio pelo mesmo motivo, mas por acidente. Passar a
    leitura é o que a F36 consertou, e o acidente não é contrato.
    """
    return ldl.em_bloco(linha, None, ["" for _ in linha])


def _ancora_do_motor(motor, pagina):
    """
    `ler_caractere` que consulta o **próprio motor**, caractere a caractere.

    É o papel que o EasyOCR fez na F17. A resposta é memorizada pelos bytes do
    recorte, como a da faixa e pelo mesmo motivo: o `ler_pagina` pede a âncora
    uma vez por box, e um motor por caractere custa ~16 ms.
    """
    cache = {}

    def ler(b):
        justo, contexto = pagina.recortes(b)
        chave = justo.tobytes()
        if chave not in cache:
            try:
                r = motor.por_caractere(justo, contexto)
            except Exception as erro:                 # noqa: BLE001
                motor.falhas += 1
                motor.ultimo_erro = f"{type(erro).__name__}: {erro}"
                r = None
            cache[chave] = r or ("", 0.0)
        char, conf = cache[chave]
        return char, conf, (motor.nome if char else "vazio")

    return ler


def tem_ancora_propria(motor) -> bool:
    """O motor sabe ler caractere? `Motor.por_caractere` devolve `None` se não."""
    return type(motor).por_caractere is not Motor.por_caractere


def medir(motor, paginas, ancora="propria"):
    """
    `(por_box, por_linha)` para um motor.

    `por_box`   — `[(lido, verdade)]`, um item por box com rótulo.
    `por_linha` — `[(lido, verdade, completa)]`, um item por linha lida.

    `ancora` é `"propria"` ou `"vazia"` — ver o cabeçalho do módulo. Motor sem
    modo por caractere cai na vazia, e quem chama descobre por
    `tem_ancora_propria`.
    """
    propria = ancora == "propria" and tem_ancora_propria(motor)
    por_box, por_linha = [], []
    for p in paginas:
        lidos = ldl.ler_pagina(
            p.arr, p.linhas,
            ler_faixa=motor,
            ler_caractere=_ancora_do_motor(motor, p) if propria else _ancora_vazia,
            conf_maxima_para_trocar=None,     # a linha manda: é ela que se mede
        )
        for b, char, _conf, _fonte in lidos:
            vd = p.verdade.get(id(b))
            if vd is not None:
                por_box.append((char, vd))

        for linha in p.linhas:
            if not _legivel(linha):
                continue
            tira = ldl.faixa_da_linha(p.arr, linha)
            if tira is None:
                continue
            texto, _c = motor(tira)           # sai do cache: já foi lida acima
            vd, completa = verdade_da_linha(p, linha)
            por_linha.append((texto.replace(" ", ""), vd, completa))
    return por_box, por_linha


def acerto(por_box):
    if not por_box:
        return 0.0
    certos = sum(1 for lido, vd in por_box
                 if normalizar(lido) == normalizar(vd))
    return 100.0 * certos / len(por_box)


def cer_e_exatas(por_linha):
    """`(CER%, linhas exatas%, quantas linhas entraram)` — só as completas."""
    completas = [(l, v) for l, v, c in por_linha if c and v]
    if not completas:
        return float("nan"), float("nan"), 0
    erros = sum(distancia_de_edicao(l, v) for l, v in completas)
    chars = sum(len(v) for _l, v in completas)
    exatas = sum(1 for l, v in completas if normalizar(l) == normalizar(v))
    return (100.0 * erros / chars if chars else float("nan"),
            100.0 * exatas / len(completas),
            len(completas))


def piores_linhas(por_linha, quantas=5):
    """As linhas completas de maior distância, para olhar o que o motor faz."""
    completas = [(l, v) for l, v, c in por_linha if c and v]
    ranking = sorted(completas,
                     key=lambda par: -distancia_de_edicao(par[0], par[1]))
    return ranking[:quantas]


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------

def tabela(resultados, ancora):
    print("\n" + "=" * 76)
    print(f"O MOTOR DE LINHA SOZINHO — âncora {ancora}")
    print("=" * 76)
    print(f"{'motor':<13}{'acerto/box':>12}{'CER':>9}{'linha exata':>13}"
          f"{'ms/linha':>10}{'passa?':>9}")
    print("-" * 76)
    caiu = False
    for nome, por_box, por_linha, ms_linha, propria in resultados:
        a = acerto(por_box)
        cer, exatas, _n = cer_e_exatas(por_linha)
        passa = "SIM" if a > BARRA_DA_CADEIA else "não"
        marca = "" if propria or ancora == "vazia" else " *"
        caiu = caiu or bool(marca)
        print(f"{nome + marca:<13}{a:>11.2f}%{cer:>8.2f}%{exatas:>12.1f}%"
              f"{ms_linha:>10.1f}{passa:>9}")
    print("-" * 76)
    print(f"{'(a cadeia)':<13}{BARRA_DA_CADEIA:>11.2f}%")
    if ancora == "propria":
        print(f"{'(F17)':<13}{BASE_DA_F17:>11.2f}%")
    if caiu:
        print("\n* sem modo por caractere: este motor correu com âncora vazia, e\n"
              "  o acerto por box dele **não** se compara com o dos outros.")
    if resultados:
        n = cer_e_exatas(resultados[0][2])[2]
        print(f"\nCER e linha exata saem de {n} linha(s) completa(s) e não "
              f"dependem da\nâncora; o acerto por box sai de todos os boxes com "
              f"rótulo e depende dela.")
    if ancora == "vazia":
        print("\nCom âncora vazia o 89,5% da F17 não entra na tabela: ele foi "
              "medido com\no EasyOCR por caractere de âncora, e comparar os dois "
              "seria erro.")
    print("\nA coluna `passa?` é contra a cadeia, e não contra o EasyOCR: um motor\n"
          "melhor que o EasyOCR e pior que a rede não move a trava da F18, e não\n"
          "muda produção. Ver a SPEC §7.1.")


def main():
    _console_em_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--motores", nargs="*", default=None,
                    help="quais medir; sem isto, todos os que carregarem")
    ap.add_argument("--paginas", type=int, default=None,
                    help="mede só as N primeiras páginas rotuladas")
    ap.add_argument("--so", nargs="*", default=None,
                    help="mede só as páginas cujo nome contém um destes pedaços")
    ap.add_argument("--ancora", choices=("propria", "vazia"), default="propria",
                    help="'propria' ancora cada motor na leitura por caractere "
                         "dele, que e o que a F17 mediu (padrao, e custa o "
                         "dobro); 'vazia' distribui a linha pela posicao")
    ap.add_argument("--erros", type=int, default=0,
                    help="mostra as N piores linhas de cada motor")
    ap.add_argument("--listar", action="store_true",
                    help="diz o que está instalado e sai, sem medir nada")
    args = ap.parse_args()

    escolhidos = motores_conhecidos()
    if args.motores:
        pedidos = set(args.motores)
        escolhidos = [m for m in escolhidos if m.nome in pedidos]
        faltando = pedidos - {m.nome for m in escolhidos}
        if faltando:
            print("motor desconhecido:", ", ".join(sorted(faltando)))
            print("conhecidos:", ", ".join(m.nome for m in motores_conhecidos()))
            return 1

    print("Carregando motores...")
    prontos = []
    for m in escolhidos:
        try:
            m.preparar()
            prontos.append(m)
            print(f"  {m.nome:<13} ok     {m.sobre}")
        except Exception as erro:                    # noqa: BLE001
            print(f"  {m.nome:<13} fora   {type(erro).__name__}: {erro}")

    if args.listar:
        return 0
    if not prontos:
        print("\nnenhum motor carregou — nada a medir")
        return 1

    # A segmentação é a de produção, com o árbitro da F1.5b: medir noutra
    # população daria uma tabela que não se compara com a do `medir_cadeia.py`.
    svc = LearningService()
    if not svc.load_predictor():
        print("\nsem modelo treinado — o árbitro do separador (F1.5b) precisa")
        print("dele, e sem ele a população de boxes não é a de produção.")
        return 1
    arbitro = svc._predictor.predict

    achadas = paginas_rotuladas()
    if args.so:
        achadas = [(i, c) for i, c in achadas
                   if any(pedaco in i for pedaco in args.so)]
    if args.paginas:
        achadas = achadas[:args.paginas]
    if not achadas:
        print("\nnenhuma página rotulada encontrada")
        return 1

    print(f"\nPreparando {len(achadas)} página(s)...")
    paginas = []
    for caminho_img, caminho_box in achadas:
        p = Pagina(caminho_img, caminho_box, arbitro)
        if len(p.rotulados) < MIN_ROTULADOS:
            continue
        paginas.append(p)
        print(f"  {p.nome[-30:]:<32} {p.medidos:>5} de {len(p.boxes)} boxes "
              f"com rótulo, {len(p.linhas)} linha(s)", flush=True)

    if not paginas:
        print("nenhuma página com rótulos suficientes")
        return 1

    # Quantas linhas o `em_bloco` recusa, para o acerto por box ser legível: os
    # boxes de uma linha recusada contam como erro em todos os motores.
    total_linhas = sum(len(p.linhas) for p in paginas)
    legiveis = sum(1 for p in paginas for l in p.linhas if _legivel(l))
    print(f"\n{legiveis} de {total_linhas} linha(s) são legíveis em bloco; as "
          f"{total_linhas - legiveis} restantes\nnão são lidas por motor nenhum, "
          f"e os boxes delas contam como erro em todos.")

    resultados = []
    for m in prontos:
        print(f"\nMedindo {m.nome}...", flush=True)
        por_box, por_linha = medir(m, paginas, args.ancora)
        ms_linha = m.ms / m.consultas if m.consultas else 0.0
        resultados.append((m.nome, por_box, por_linha, ms_linha,
                           args.ancora == "propria" and tem_ancora_propria(m)))
        if m.falhas:
            print(f"  {m.falhas} faixa(s) estouraram — última: {m.ultimo_erro}")

    tabela(resultados, args.ancora)

    if args.erros:
        for nome, _pb, por_linha, _ms, _pr in resultados:
            print(f"\nPiores linhas — {nome}")
            for lido, vd in piores_linhas(por_linha, args.erros):
                print(f"  esperado  {vd}")
                print(f"  lido      {lido}")
                print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
