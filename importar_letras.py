"""
Cria classe para a letra que o modelo não tem — colhendo do livro, ou da fonte (F94).

**Um caractere sem classe é um erro garantido, e não há como sair disso pelo
OCR.** A rede só pode emitir uma das classes que tem; se `š` não é classe, todo
`š` do livro sai como outra coisa, com confiança alta, e nem a revisão o pega —
o recorte cai na pasta de `s` e ali ele *parece* certo. O ciclo normal do
projeto (coletar → revisar → promover) não fecha esse buraco: ele colhe o que o
modelo leu, e o modelo não leu.

Então a classe tem de nascer de fora do OCR, e há duas fontes, nesta ordem:

1. **A camada de texto do livro.** Onde o PDF diz `š`, o retângulo daquele
   caractere é recortado da página renderizada. É a melhor amostra possível: a
   fonte real, o corpo real, a renderização real. E o rótulo não é palpite de
   modelo nenhum — é o que o editor do livro escreveu.

2. **As fontes de texto do sistema.** Para a letra que os livros em mãos não
   têm. Medido nos seis PDFs do projeto: `Å` aparece 111 vezes e `Ń` **nenhuma**
   — não há livro aqui de onde tirá-la, e esperar por um é deixar o buraco
   aberto. Quinze faces serifadas do Windows desenham as 16 letras pedidas.

**A amostra sintética é semente, não substituto**, e a diferença importa: ela
faz a classe existir e o modelo parar de errar por não ter para onde errar, mas
quem ensina a letra como o livro a imprime é a amostra do livro. Assim que um
PDF com a letra aparecer, colha dele — é o que o modo `--faltantes` existe para
avisar.

**E a camada de texto destes livros mente**, então o rótulo dela não entra sem
passar pelo modelo: ver `avalizado`. Sem esse portão a primeira rodada desta
ferramenta colheu 54 desenhos de rei e os chamou de `Å`; com ele numa versão
frouxa, 31 borrões em 58. A régua que sobrou está medida no `avalizado`.

**Nada vai direto para `training_data`.** Sai na quarentena da F2.7, e por dois
motivos: o retângulo da camada de texto pode pegar o vizinho, e a face do
sistema pode não ser a do livro. Os dois erros são invisíveis num CSV e óbvios
numa grade de miniaturas — que é exatamente o argumento da F2.7. Depois,
'Promover recortes revistos para a base'.

    python importar_letras.py --faltantes PDF/*/*.pdf
    python importar_letras.py --pdf "PDF/.../livro.pdf" --letras "Šš"
    python importar_letras.py --pdf PDF/*/*.pdf --letras "ŃńŠšŽžČčĆćÅåŞşØø"
    python importar_letras.py --letras "Ńń" --so-fonte      # sem livro nenhum
    python importar_letras.py ... --conferir                # a saúde da camada

Reproduz a F94 no ROADMAP.
"""

import argparse
import csv
import glob
import json
import os
import sys
import unicodedata
from collections import Counter

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import coleta
from core.learner import char_to_folder

#: O dpi da renderização da página. O mesmo do `livro.extrair`, e é o que faz a
#: amostra colhida ter o mesmo porte das que o OCR produz.
DPI = 300

#: Quantas amostras uma classe nova precisa ter para valer alguma coisa.
#:
#: É o `MIN_AMOSTRAS_POR_CLASSE` do treino, que não exclui a classe rara mas
#: avisa que ela "generaliza pouco". Abaixo disto a semente de fonte entra para
#: completar; acima, o livro basta.
MINIMO_POR_LETRA = 12

#: As faces do sistema de onde a semente é desenhada.
#:
#: **Serifadas primeiro, e é a razão de a lista ser esta.** O texto destes livros
#: é serifado, e uma classe semeada só em Arial ensina um `š` de outro mundo. As
#: três sem serifa ficam no fim e entram por último: uma variedade a mais não
#: atrapalha quando as serifadas já formaram a maioria da classe.
FACES = [
    "times.ttf", "timesbd.ttf", "timesi.ttf", "georgia.ttf", "georgiab.ttf",
    "cambria.ttc", "constan.ttf", "pala.ttf", "BOOKOS.TTF", "GARA.TTF",
    "CENTURY.TTF", "sylfaen.ttf",
    "calibri.ttf", "segoeui.ttf", "arial.ttf",
]

#: Os corpos em que cada face é desenhada.
#:
#: Três, e não um, porque o antialiasing muda com o corpo: a mesma face em 28 e
#: em 56 dá dois 32x32 diferentes depois do recorte justo, e a diferença é do
#: mesmo tipo que a que separa duas impressões do mesmo livro. O que for igual
#: demais a dedução tira — ver `coleta._impressao`.
CORPOS = (28, 40, 56)

ONDE_FICAM_AS_FONTES = os.path.join(os.environ.get("WINDIR", "C:/Windows"),
                                    "Fonts")

COLUNAS = ["arquivo", "letra", "origem", "pagina"]


# ----------------------------------------------------------------------
# O recorte justo, que é a convenção da base
# ----------------------------------------------------------------------

def apertar(img, minimo=3):
    """
    O retângulo da tinta dentro do recorte, ou `None` se não há tinta.

    **A base é de recorte justo**, e não de recorte folgado: as amostras de
    `training_data` têm margem de 0 a 2 px em volta do glifo, porque nasceram de
    componente conexo. O retângulo da camada de texto é o do *avanço* — inclui a
    lateral em branco e a caixa inteira da linha —, e promover isso encheria a
    classe de amostras que o `learn` esticaria de um jeito que nenhuma amostra
    de OCR é esticada. Apertar aqui é o que faz as duas procedências caberem na
    mesma classe.
    """
    if img is None or img.size == 0:
        return None
    _, binaria = cv2.threshold(img, 0, 255,
                               cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    ys, xs = np.where(binaria > 0)
    if not len(xs):
        return None
    corte = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if min(corte.shape[:2]) < minimo:
        return None
    return corte


# ----------------------------------------------------------------------
# 1. Colher do livro
# ----------------------------------------------------------------------

def caracteres_do_pdf(caminho, paginas=None):
    """`Counter` do que a camada de texto do PDF diz que há nele."""
    import fitz

    doc = fitz.open(caminho)
    try:
        conta = Counter()
        for n in range(doc.page_count if paginas is None
                       else min(paginas, doc.page_count)):
            conta.update(doc[n].get_text())
        return conta
    finally:
        doc.close()


def faltantes(caminhos, paginas=None, so_letras=True):
    """
    `[(letra, quantas, [livros])]` do que os PDFs têm e o modelo não conhece.

    **É o gatilho do resto.** O ciclo normal nunca acusa uma letra ausente,
    porque ele só vê o que o modelo leu; quem sabe que o livro tem `š` é a
    camada de texto do próprio livro, e ela sabe antes de qualquer OCR rodar.

    **`so_letras` é o padrão, e o motivo é a F2.5.** Sem filtro esta lista sai
    com 709 caracteres nos seis PDFs do projeto, encabeçada por `·` (19.331),
    `>` (18.573) e `\\` (4.711) — nenhum dos quais está impresso em página
    nenhuma. São ♔♕♖♗♘ com o `ToUnicode` trocado, e a lista inteira vira ruído
    que esconde as quatro letras que importam. Filtrar por categoria de letra
    corta a maior parte — mas **não corta tudo**, e é honesto dizer: `ʘ` é uma
    letra para o Unicode (LATIN LETTER BILABIAL CLICK) e aparece 514 vezes, e é
    o rei. Quem corta o resto é o `avalizado`, recorte a recorte, e ele é caro
    demais para rodar aqui: esta lista é o aviso, não o veredito.
    """
    with open("model_meta.json", encoding="utf-8") as f:
        conhecidas = set(json.load(f)["idx_to_char"].values())

    conta, onde = Counter(), {}
    for caminho in caminhos:
        do_livro = caracteres_do_pdf(caminho, paginas)
        for ch, n in do_livro.items():
            if ch in conhecidas or not ch.strip() or len(ch) != 1:
                continue
            categoria = unicodedata.category(ch)
            # Controle e formatação nunca são classe de glifo.
            if categoria[0] in "CZ":
                continue
            if so_letras and categoria[0] != "L":
                continue
            conta[ch] += n
            onde.setdefault(ch, set()).add(os.path.basename(caminho))
    return [(ch, n, sorted(onde[ch])) for ch, n in conta.most_common()]


def _alvos_da_pagina(page, letras):
    """`[(letra, fonte, bbox)]` do que a camada de texto declara na página."""
    bruto = page.get_text("rawdict")
    return [(c["c"], s.get("font", "?"), c["bbox"])
            for b in bruto.get("blocks", []) if b.get("type") == 0
            for l in b.get("lines", []) for s in l.get("spans", [])
            for c in s.get("chars", []) if c["c"] in letras]


def _recortar(arr, bbox, escala, folga=2):
    alt, larg = arr.shape[:2]
    x1 = max(0, int(bbox[0] * escala) - folga)
    y1 = max(0, int(bbox[1] * escala) - folga)
    x2 = min(larg, int(bbox[2] * escala) + folga + 1)
    y2 = min(alt, int(bbox[3] * escala) + folga + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    return apertar(arr[y1:y2, x1:x2])


#: As letras com que a camada de texto é interrogada. Comuns, e o modelo as tem
#: com milhares de amostras: se ela erra **nestas**, não é o modelo que está
#: errado.
CONTROLE = "aeoinstrbdgh"

#: Concordância mínima, por fonte, para a camada de texto daquela fonte servir
#: de rótulo.
#:
#: **Este número não é usado para decidir nada, e a razão é o que esta fase
#: aprendeu.** A primeira versão filtrava por fonte: media a concordância nas
#: letras de controle e colhia só das fontes que passassem. No Aagaard, cinco
#: fontes passaram com 85% a 97% — e as 54 amostras de `Å` colhidas delas eram
#: **54 desenhos de rei**. O portão não podia funcionar: a face mapeia as letras
#: certo e as figurinhas errado, então a concordância no `a` e no `e` não diz
#: nada sobre o glifo que o produtor do PDF chamou de `Å`. Quem decide é o
#: `avalizado`, recorte a recorte. Isto fica como diagnóstico (`--conferir`).
#:
#: E a medição que o derruba de vez está aqui: o Yusupov Complete, de onde
#: saíram **31 dos 31** recortes de lixo, tem 89,9% de concordância nas letras
#: de controle — praticamente a mesma do Dvoretsky (91,2%), de onde saíram os 27
#: bons. A camada está alinhada e bem mapeada nos dois livros; o que mente é uma
#: fonte que as letras de controle nunca visitam.
CONFIANCA_DA_CAMADA = 0.85


# ----------------------------------------------------------------------
# O portão que funciona: perguntar ao modelo, recorte a recorte
# ----------------------------------------------------------------------

#: Letras sem decomposição Unicode, cuja letra-base tem de ser dita à mão.
#:
#: O `Å` decompõe em `A` + anel e o `š` em `s` + caron, então a letra-base sai
#: do `NFD`. O `ø` e o `æ` não decompõem — para o Unicode são letras próprias —,
#: e sem esta tabela ficariam sem base e o portão os recusaria sempre.
BASE_A_MAO = {"ø": "o", "Ø": "O", "æ": "a", "Æ": "A", "ł": "l", "Ł": "L",
              "đ": "d", "Đ": "D", "þ": "b", "Þ": "P", "ß": "B", "ı": "i",
              "ŋ": "n", "œ": "o", "Œ": "O", "ð": "o", "Ð": "D"}

def leituras_plausiveis(ch):
    """
    O que o modelo pode ler num recorte desta letra sem que isso a desminta.

    O modelo **não tem a classe** da letra que se está criando — é por isso que
    ela está sendo criada. Então ele nunca vai confirmá-la; o mais que pode
    fazer é reconhecer a letra-base, e é o que ele faz num `š` de verdade: lê
    `s`, porque é o mais parecido que ele conhece.
    """
    base = BASE_A_MAO.get(ch) or unicodedata.normalize("NFD", ch)[0]
    return {ch, base, base.lower(), base.upper()}


def avalizado(ch, lido, conf=None):
    """
    O recorte pode entrar? Só se o modelo ler nele a letra-base.

    **A presunção é contra o recorte, e isso foi medido.** A versão anterior
    presumia a favor: entrava tudo, exceto o que o modelo *contradissesse* com
    confiança alta. O argumento era bom — "hesitação não desmente; recusar por
    ela jogaria fora o recorte estranho, que é o que a classe nova mais precisa"
    — e está errado. Nas 58 amostras colhidas dos seis PDFs, rotuladas a olho:

        régua                                  dos 27 bons   dos 31 de lixo
        presume a favor (contradição >= 0,90)          27              31
        presume contra (leitura plausível)             17               0

    **O lixo mora justamente na hesitação**, e tinha de morar: um borrão de
    trama ou um pedaço de régua não pertence a classe nenhuma, então o softmax
    se espalha. O `♗` mais confiante da pilha deu 0,871 e passava por baixo do
    limiar. Não há limiar que resolva: baixá-lo até pegá-lo mataria o `å` que o
    modelo lê como `ä` com 0,590, que é bom.

    O preço é 10 amostras boas em 27, e é o preço certo aqui. Isto **semeia uma
    classe**: uma amostra errada na semente ensina a letra errada e não tem
    quem a pegue depois — a classe é nova, não há com o que comparar. Volume
    quem dá é a fonte.

    `conf` é aceito e ignorado, para quem chamava com ele não quebrar: a
    medição diz que a leitura sozinha separa, e um piso de confiança só tiraria
    amostra boa (metade das boas está entre 0,26 e 0,41).
    """
    return bool(lido) and lido in leituras_plausiveis(ch)


def conferir_camada(caminho, classificar, controle=CONTROLE, por_fonte=60,
                    paginas=40, dpi=DPI):
    """
    `{fonte: (conferidas, acertos)}` — quanto a camada de texto de cada fonte vale.

    **A camada de texto destes livros mente, e é preciso saber onde.** É o
    defeito inteiro da F2.5: as fontes de figurinha são Type0/Identity-H e o
    produtor do PDF escreveu qualquer coisa no `ToUnicode` — nos seis PDFs deste
    projeto, `·` aparece 19.331 vezes, `>` 18.573, `ʘ` 514. Nenhum deles está na
    página; são ♔♕♖♗♘ com o mapa trocado. Colher com esse rótulo encheria a
    classe de `·` com desenhos de rei.

    Então não se confia na camada: pergunta-se a ela por letras que o modelo
    **sabe** ler, e mede-se a concordância. Onde ela acerta o `a`, o `e` e o
    `o`, o rótulo dela vale para o `š` também — é a mesma tabela. Onde ela erra,
    aquela fonte fica de fora, e o `--faltantes` que a acusou era ruído.

    A pergunta é por fonte porque o defeito é por fonte: no mesmo livro, o texto
    corrido mapeia certo e a figurinha não.
    """
    import fitz

    from core import livro

    doc = fitz.open(caminho)
    escala = dpi / 72.0
    conferidas, acertos = Counter(), Counter()
    alvo = set(controle)
    try:
        for n in range(min(paginas, doc.page_count)):
            alvos = [t for t in _alvos_da_pagina(doc[n], alvo)
                     if conferidas[t[1]] < por_fonte]
            if not alvos:
                continue
            arr = livro._pagina_cinza(doc[n], dpi)
            for ch, fonte, bbox in alvos:
                corte = _recortar(arr, bbox, escala)
                if corte is None:
                    continue
                conferidas[fonte] += 1
                lido, _conf = classificar(corte)
                if lido == ch:
                    acertos[fonte] += 1
            if all(conferidas[f] >= por_fonte for f in conferidas) and conferidas:
                # Nada a ganhar em varrer o livro inteiro depois que toda fonte
                # vista já respondeu o bastante.
                if n >= 8:
                    break
    finally:
        doc.close()
    return {f: (conferidas[f], acertos[f]) for f in conferidas}


def fontes_confiaveis(medida, minimo=CONFIANCA_DA_CAMADA, minimo_de_amostras=10):
    """As fontes cuja camada de texto acertou o bastante para servir de rótulo."""
    return {f for f, (n, ok) in medida.items()
            if n >= minimo_de_amostras and ok / n >= minimo}


def colher_do_pdf(caminho, letras, classificar, dpi=DPI, folga=2):
    """
    `(letra, página, recorte)` de cada ocorrência das `letras` no PDF.

    **Só sai o que o modelo avaliza** — ver `avalizado`. O `classificar` é
    obrigatório de propósito: colher sem ele é colher rei chamado de `Å`, e foi
    o que a primeira versão fez.

    O que foi recusado sai pelo atributo `recusas` do gerador — um `Counter` de
    `(letra, o que o modelo leu)`, porque saber *como* a camada mente é o dado
    que manda colher noutro livro.
    """
    import fitz

    from core import livro

    recusas = Counter()
    colher_do_pdf.recusas = recusas

    doc = fitz.open(caminho)
    escala = dpi / 72.0
    try:
        for n in range(doc.page_count):
            alvos = _alvos_da_pagina(doc[n], letras)
            if not alvos:
                continue
            arr = livro._pagina_cinza(doc[n], dpi)
            for ch, _fonte, bbox in alvos:
                corte = _recortar(arr, bbox, escala, folga)
                if corte is None:
                    continue
                lido, conf = classificar(corte)
                if not avalizado(ch, lido, conf):
                    recusas[(ch, lido)] += 1
                    continue
                yield ch, n, corte
    finally:
        doc.close()


# ----------------------------------------------------------------------
# 2. Semear da fonte
# ----------------------------------------------------------------------

def faces_disponiveis(pasta=ONDE_FICAM_AS_FONTES, controle="aso"):
    """
    As faces de `FACES` que existem e **desenham de verdade**.

    O controle não é zelo: `ImageFont` aceita a face, e uma letra que ela não
    tem sai como retângulo vazio ou como `.notdef` — que apertado vira um
    quadrado, e um quadrado promovido para a classe de `ń` ensina que `ń` é um
    quadrado. Exigir tinta nas três letras de controle **e** na letra pedida
    fecha isso; a primeira versão desta função perguntava `has_glyph` à fonte e
    ela respondeu "sim" para as 16 letras de um subset que não desenhava nem o
    `a`.
    """
    boas = []
    for nome in FACES:
        caminho = os.path.join(pasta, nome)
        if not os.path.exists(caminho):
            continue
        if all(desenhar(caminho, c, 40) is not None for c in controle):
            boas.append(caminho)
    return boas


def desenhar(caminho_da_face, ch, corpo):
    """O glifo desenhado e apertado, ou `None` se a face não o desenha."""
    try:
        face = ImageFont.truetype(caminho_da_face, corpo)
    except Exception:
        return None
    tela = Image.new("L", (corpo * 3, corpo * 3), 255)
    ImageDraw.Draw(tela).text((corpo, corpo), ch, font=face, fill=0)
    return apertar(np.array(tela))


def semear_da_fonte(letras, faces=None, corpos=CORPOS):
    """`(letra, face, recorte)` para cada letra, face e corpo que der."""
    for caminho in (faces if faces is not None else faces_disponiveis()):
        nome = os.path.splitext(os.path.basename(caminho))[0]
        for ch in letras:
            for corpo in corpos:
                corte = desenhar(caminho, ch, corpo)
                if corte is not None:
                    yield ch, nome, corte


# ----------------------------------------------------------------------
# Gravar na quarentena
# ----------------------------------------------------------------------

class Deposito:
    """
    Grava na quarentena, sem repetir, e anota de onde cada amostra veio.

    **A procedência fica no nome do arquivo**, e não só no índice: o `promover`
    passa pelo `learner.learn`, que renomeia tudo para UUID, então o índice é o
    único lugar onde ela sobrevive à promoção — e é durante a revisão, olhando
    a pasta, que ela precisa estar visível. Um `fonte-times_…` no meio de
    `pdf-dvoretsky_…` diz, sem abrir nada, qual amostra é semente e qual é
    livro.
    """

    def __init__(self, pasta, minimo=MINIMO_POR_LETRA):
        self.pasta = pasta
        self.minimo = minimo
        self.gravados = Counter()
        self.repetidos = 0
        self.linhas = []
        self._impressoes = {}

    def por_letra(self, ch):
        return self.gravados[ch]

    def guardar(self, ch, corte, origem, pagina=None):
        impressao = coleta._impressao(corte)
        vistas = self._impressoes.setdefault(ch, set())
        if impressao in vistas:
            self.repetidos += 1
            return None
        vistas.add(impressao)

        classe = char_to_folder(ch)
        destino = os.path.join(self.pasta, classe)
        os.makedirs(destino, exist_ok=True)
        nome = f"{origem}_{impressao[:8]}.png"
        caminho = os.path.join(destino, nome)
        # imencode + tofile: o imwrite falha calado em caminho não-ASCII no
        # Windows, e a pasta de destino é escolhida pelo usuário.
        ok, buf = cv2.imencode(".png", corte)
        if not ok:
            return None
        buf.tofile(caminho)

        self.gravados[ch] += 1
        self.linhas.append({"arquivo": os.path.join(classe, nome), "letra": ch,
                            "origem": origem,
                            "pagina": "" if pagina is None else pagina + 1})
        return caminho

    def gravar_indice(self):
        if not self.linhas:
            return None
        caminho = os.path.join(self.pasta, coleta.NOME_DO_INDICE)
        novo = not os.path.exists(caminho)
        with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS,
                                      extrasaction="ignore")
            if novo:
                escritor.writeheader()
            escritor.writerows(self.linhas)
        return caminho


def folha_de_contato(deposito, saida, lado=48, por_linha=24):
    """
    Uma folha por letra, para a revisão ser olhar e não abrir 40 arquivos.

    É a grade de miniaturas da F2.7 num PNG só: o `š` que saiu com meio `k` do
    lado, ou o quadrado que uma face devolveu no lugar do glifo, aparece aqui
    sem ninguém procurar.
    """
    saidas = []
    for classe in sorted(os.listdir(deposito.pasta)):
        pasta = os.path.join(deposito.pasta, classe)
        if not os.path.isdir(pasta):
            continue
        arquivos = sorted(f for f in os.listdir(pasta) if f.endswith(".png"))
        if not arquivos:
            continue
        linhas = (len(arquivos) + por_linha - 1) // por_linha
        folha = np.full((linhas * lado, por_linha * lado), 235, dtype=np.uint8)
        for i, arquivo in enumerate(arquivos):
            img = cv2.imdecode(np.fromfile(os.path.join(pasta, arquivo),
                                           dtype=np.uint8),
                               cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            m = cv2.resize(img, (lado - 6, lado - 6))
            y, x = (i // por_linha) * lado + 3, (i % por_linha) * lado + 3
            folha[y:y + lado - 6, x:x + lado - 6] = m
        caminho = os.path.join(saida, f"{classe}.png")
        os.makedirs(saida, exist_ok=True)
        cv2.imencode(".png", folha)[1].tofile(caminho)
        saidas.append((classe, len(arquivos), caminho))
    return saidas


# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", nargs="+", default=[],
                    help="PDFs de onde colher (aceita curinga)")
    ap.add_argument("--letras",
                    help="as letras a criar; sem isto, as que os PDFs têm e o "
                         "modelo não conhece")
    ap.add_argument("--faltantes", nargs="+",
                    help="só listar o que estes PDFs têm e o modelo não conhece")
    ap.add_argument("--tudo", action="store_true",
                    help="no --faltantes, não filtrar por categoria de letra")
    ap.add_argument("--destino", default=coleta.PASTA_PADRAO,
                    help=f"onde gravar (padrão {coleta.PASTA_PADRAO})")
    ap.add_argument("--minimo", type=int, default=MINIMO_POR_LETRA,
                    help="abaixo disto a semente de fonte completa a classe")
    ap.add_argument("--so-fonte", action="store_true",
                    help="não colher de PDF nenhum, só semear da fonte")
    ap.add_argument("--conferir", action="store_true",
                    help="mostrar a saúde da camada de texto por fonte "
                         "(diagnóstico; não decide nada — ver CONFIANCA_DA_CAMADA)")
    ap.add_argument("--sem-folha", action="store_true",
                    help="não gravar a folha de contato")
    args = ap.parse_args()

    if args.faltantes:
        alvos = [c for p in args.faltantes for c in glob.glob(p)] or args.faltantes
        achados = faltantes(alvos, so_letras=not args.tudo)
        if not achados:
            print("Nada: o modelo conhece todo caractere destes PDFs.")
            return 0
        print(f"{len(achados)} caractere(s) que o modelo não conhece:\n")
        print(f"{'char':<5} {'código':<9} {'vezes':>6}  nome / livros")
        for ch, n, livros in achados:
            nome = unicodedata.name(ch, "?")[:36]
            print(f"{ch:<5} U+{ord(ch):04X}{'':<3} {n:>6}  {nome}")
            print(f"{'':<21} {', '.join(l[:34] for l in livros[:3])}")
        return 0

    pdfs = [c for p in args.pdf for c in glob.glob(p)] or args.pdf
    if args.letras:
        letras = [c for c in args.letras if c.strip()]
    elif pdfs:
        letras = [ch for ch, _n, _l in faltantes(pdfs)]
        print(f"Sem --letras: usando as {len(letras)} que os PDFs têm e o "
              f"modelo não conhece.")
    else:
        print("Diga --letras, ou --pdf de onde deduzi-las.")
        return 1
    if not letras:
        print("Nenhuma letra a criar.")
        return 0

    deposito = Deposito(args.destino, minimo=args.minimo)
    alvo = set(letras)

    if pdfs and not args.so_fonte:
        from core.services.learning_service import LearningService

        servico = LearningService()
        if not servico.load_predictor():
            print(servico.motivo_do_modelo())
            print("\nA colheita precisa do modelo para conferir a camada de "
                  "texto. Sem ele, use --so-fonte.")
            return 1

        print("Colhendo. A camada de texto destes livros mente nas figurinhas "
              "(F2.5), então cada recorte passa pelo modelo antes de entrar.\n")
        for caminho in pdfs:
            if args.conferir:
                print(f"  {os.path.basename(caminho)[:46]} — camada por fonte:")
                for fonte, (n, ok) in sorted(
                        conferir_camada(caminho, servico.predict_neural).items(),
                        key=lambda kv: -kv[1][0])[:8]:
                    print(f"     {fonte[:34]:<36} {ok:>3}/{n:<3} "
                          f"{100.0 * ok / max(1, n):>5.1f}%")

            nome = os.path.splitext(os.path.basename(caminho))[0]
            marca = "pdf-" + "".join(c for c in nome.lower()[:18]
                                     if c.isalnum() or c == "-")
            antes = sum(deposito.gravados.values())
            for ch, pagina, corte in colher_do_pdf(caminho, alvo,
                                                   servico.predict_neural):
                deposito.guardar(ch, corte, f"{marca}_p{pagina + 1:04d}", pagina)
            recusas = getattr(colher_do_pdf, "recusas", Counter())
            detalhe = ", ".join(f"{ch}→{lido!r}×{n}"
                                for (ch, lido), n in recusas.most_common(6))
            print(f"  {os.path.basename(caminho)[:44]:<46} "
                  f"+{sum(deposito.gravados.values()) - antes}"
                  f"{'  recusadas ' + str(sum(recusas.values())) if recusas else ''}"
                  f"{'  (' + detalhe + ')' if detalhe else ''}", flush=True)

    curtas = [ch for ch in letras if deposito.por_letra(ch) < args.minimo]
    if curtas:
        faces = faces_disponiveis()
        print(f"\n{len(curtas)} letra(s) abaixo de {args.minimo}: semeando de "
              f"{len(faces)} face(s) — {''.join(curtas)}")
        if not faces:
            print("  Nenhuma face utilizável; a semente não roda.")
        for ch, face, corte in semear_da_fonte(curtas, faces):
            deposito.guardar(ch, corte, f"fonte-{face.lower()}")

    print(f"\n{sum(deposito.gravados.values())} amostra(s) em "
          f"{len(deposito.gravados)} classe(s); "
          f"{deposito.repetidos} repetida(s) descartada(s).\n")
    print(f"{'letra':<6} {'classe':<12} {'total':>6} {'do livro':>9} {'de fonte':>9}")
    do_livro = Counter(l["letra"] for l in deposito.linhas
                       if l["origem"].startswith("pdf-"))
    for ch in letras:
        n = deposito.por_letra(ch)
        aviso = "  <- ainda pouca" if n < args.minimo else ""
        print(f"{ch:<6} {char_to_folder(ch):<12} {n:>6} {do_livro[ch]:>9} "
              f"{n - do_livro[ch]:>9}{aviso}")

    indice = deposito.gravar_indice()
    print(f"\nEm: {os.path.abspath(args.destino)}")
    if indice:
        print(f"Índice: {indice}")
    if not args.sem_folha and deposito.linhas:
        print("\nFolhas de contato — **olhe estas antes de promover**:")
        for classe, n, caminho in folha_de_contato(deposito, os.path.join(
                args.destino, "_folhas")):
            print(f"  {classe:<12} {n:>4} amostras  {caminho}")
    print("\nOlhe antes de promover: Ferramentas → 'Promover recortes "
          "revistos para a base'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
