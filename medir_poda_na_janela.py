"""
A poda da geometria da linha na cadeia da janela, em livro que a janela não copia (F123).

    python medir_poda_na_janela.py
    python medir_poda_na_janela.py --manifesto benchmarks/ocr_corpus_v1.json

**Por que não só o `medir_cadeia.py --neural --geometria`.** Ele mede nas páginas
rotuladas, e ali a poda quase não tem o que fazer: o k-NN responde consultando a cópia
do próprio glifo (F23) e a rede treinou naquelas páginas (F117) — medido, 8 trocas em
11.486 boxes. O livro em que a janela vai ser usada é o que ela não viu, e as páginas
desse tipo que o projeto tem transcritas são as do corpus de referência
(`benchmarks/ocr_corpus_v1.json`, `preview_ocr/referencia`), sem `.box`.

**Sem `.box` não há verdade por box**, e a conta é a da F112 com o livro que o modelo
não viu: cada box que a poda mudou sai com a linha lida sem e com ela e o parágrafo da
transcrição de onde ela veio, e a conferência final é a olho. A `pista` é o primeiro
passe dessa conferência: a linha é alinhada ao parágrafo caractere a caractere, e o
caractere da transcrição naquele lugar diz se a troca foi `conserto`, `quebra` ou
`neutra` (errado antes e depois); `?` é onde o alinhamento não chega. Na página ruim a
pista erra para os dois lados, e é por isso que ela é pista.

A população é a da janela: a página a 300 dpi, a segmentação de produção com o
árbitro (`medir_paginas.segmentar`), as linhas e a cadeia neural de `medir_cadeia`
— rede, k-NN e EasyOCR com os limiares da ação —, e a linha do EasyOCR com a trava.
Sem cobertura de teste, como os outros `medir_*.py`; as peças de produção que ele
chama, `leitura_de_linha.ler_pagina` e `geometria_da_linha.poda_da_ancora`, têm a sua.
"""

import argparse
import difflib
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import fitz  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import medir_cadeia as mc  # noqa: E402
from core import diagrama, geometria_da_linha as gl, leitura_de_linha as ldl  # noqa: E402
from core.services.box_service import faixas_de_linha  # noqa: E402
from medir_paginas import segmentar  # noqa: E402

MANIFESTO = os.path.join(RAIZ, "benchmarks", "ocr_corpus_v1.json")


class PaginaDoCorpus:
    """Uma página do corpus como a janela a vê: segmentada, em linhas, sem rótulo."""

    def __init__(self, pdf, indice, arbitro, dpi=300):
        doc = fitz.open(pdf)
        try:
            pix = doc[indice - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        finally:
            doc.close()
        self.arr = np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height, pix.width).copy()
        _, self.boxes = segmentar(Image.fromarray(self.arr), "arbitrado",
                                  arbitro=arbitro)
        self.linhas = ldl.linhas_da_pagina(self.boxes)
        self.faixas = {id(b): faixa for uma in self.linhas
                       for b, faixa in zip(uma, faixas_de_linha(uma))}

    def recortes(self, b):
        return mc._recortes_do_box(self.arr, b, self.faixas)


def texto_da_linha(linha, chars):
    """
    `(texto, posição de cada box no texto)` — o espaço pela régua da linha (F107).

    O box vazio sai `·`, para a posição dos outros não andar.
    """
    limiar = diagrama.limiar_de_espaco(linha)
    partes, posicoes, n = [], [], 0
    for i, (b, c) in enumerate(zip(linha, chars)):
        if i and b.x1 - linha[i - 1].x2 > limiar:
            partes.append(" ")
            n += 1
        posicoes.append(n)
        partes.append(c or "·")
        n += len(c or "·")
    return "".join(partes), posicoes


def paragrafo_da_linha(texto, paragrafos):
    """
    O parágrafo da transcrição de onde a linha lida saiu.

    Pelo número de caracteres casados, e não pela razão do `difflib`: a linha é
    um pedaço do parágrafo, e a razão pune o parágrafo longo que a contém.
    """
    def casados(paragrafo):
        return sum(b.size for b in difflib.SequenceMatcher(
            None, texto, paragrafo, autojunk=False).get_matching_blocks())
    return max(paragrafos or [""], key=casados)


def _na_referencia(texto, posicao, paragrafo):
    """`(caractere da transcrição alinhado a `posicao`, se o trecho é igual)`."""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, texto, paragrafo, autojunk=False).get_opcodes():
        if i1 <= posicao < i2:
            if tag == "equal":
                return paragrafo[j1 + posicao - i1], True
            if tag == "replace" and i2 - i1 == j2 - j1:
                return paragrafo[j1 + posicao - i1], False
            return None, False
    return None, False


def pista(antes, depois, posicao, paragrafo):
    """
    O primeiro passe da conferência: o caractere da transcrição naquele lugar.

    A linha é alinhada à transcrição duas vezes, com a leitura de antes e com a
    de depois, porque o que cerca a troca costuma ter outro erro (o pingo do
    `i` em box próprio faz `Th1.s` e `Thi.s`): o trecho igual de um dos dois
    alinhamentos é o que decide.
    """
    alvo_d, igual_d = _na_referencia(depois, posicao, paragrafo)
    if igual_d:
        return "conserto"
    alvo_a, igual_a = _na_referencia(antes, posicao, paragrafo)
    if igual_a:
        return "quebra"
    alvo = alvo_d if alvo_d is not None else alvo_a
    return "neutra" if alvo is not None else "?"


def na_fila(lidos):
    """Quantos boxes a fila de revisão da janela mostraria (`precisa_revisao`)."""
    return sum(1 for _b, char, conf, fonte in lidos
               if mc.conf_ui.precisa_revisao(
                   mc._BoxFalso((fonte, conf, char, None, None))))


def medir_pagina(cadeia, pagina, referencia, topk):
    """
    `([(texto antes, texto depois, linha da referência, [trocas])], fila antes,
    fila depois)` da página.
    """
    ler = cadeia.leitor(pagina, "neural", mc.LEARNER_THRESHOLD_NEURAL)
    comum = dict(ler_faixa=cadeia.ocr.easyocr_linha_conf, ler_caractere=ler,
                 conf_maxima_para_trocar=mc.CONF_MAXIMA_PARA_A_LINHA,
                 fontes_sem_trava=mc.FONTES_SEM_TRAVA)
    sem = ldl.ler_pagina(pagina.arr, pagina.linhas, podar=None, **comum)
    com = ldl.ler_pagina(pagina.arr, pagina.linhas,
                         podar=gl.poda_da_ancora(pagina.arr, topk), **comum)
    linhas_ref = [l.strip() for l in referencia.splitlines() if l.strip()]
    saida, i = [], 0
    for linha in pagina.linhas:
        a, d = sem[i:i + len(linha)], com[i:i + len(linha)]
        i += len(linha)
        mudou = [j for j in range(len(linha)) if a[j][1] != d[j][1]]
        if not mudou:
            continue
        antes, _ = texto_da_linha(linha, [x[1] for x in a])
        depois, posicoes = texto_da_linha(linha, [x[1] for x in d])
        ref = paragrafo_da_linha(antes, linhas_ref)
        # A troca da poda é de um caractere por um: a posição do box é a mesma
        # nos dois textos, e só anda se a linha do EasyOCR mudou outro box junto.
        trocas = [(a[j][1], d[j][1], a[j][3], d[j][3],
                   pista(antes, depois, posicoes[j], ref))
                  for j in mudou]
        saida.append((antes, depois, ref, trocas))
    return saida, na_fila(sem), na_fila(com)


def main(argv=None):
    mc._console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--manifesto", default=MANIFESTO,
                    help="o manifesto do corpus (pyboxeditor.ocr-corpus/v1)")
    args = ap.parse_args(argv)

    from pathlib import Path

    from rodada_do_corpus import paginas_do_manifesto
    from core.services.learning_service import LearningService

    servico = LearningService()
    if not servico.load_predictor():
        print(servico.motivo_do_modelo())
        return 1
    arbitro = servico._predictor.predict
    paginas = paginas_do_manifesto(Path(args.manifesto))
    if not paginas:
        print("o manifesto não tem página com referência")
        return 1

    cadeias = {}
    total = {"trocas": 0, "boxes": 0, "fila antes": 0, "fila depois": 0}
    pistas = {}
    for p in paginas:
        idioma = p["idioma"]
        if idioma not in cadeias:
            cadeias[idioma] = mc.Cadeia(com_rede=True, idioma=idioma)
        cadeia = cadeias[idioma]

        def topk(recorte, k, _c=cadeia):
            return _c.predictor.predict_topk(recorte, k=k)

        pagina = PaginaDoCorpus(str(p["pdf"]), p["page_index"], arbitro)
        referencia = Path(p["referencia"]).read_text(encoding="utf-8")
        mudancas, fila_antes, fila_depois = medir_pagina(cadeia, pagina,
                                                         referencia, topk)
        n = sum(len(t) for *_x, t in mudancas)
        print(f"\n===== {p['id']}: {len(pagina.boxes)} boxes, "
              f"{len(pagina.linhas)} linhas, {n} troca(s); "
              f"na fila de revisão {fila_antes} -> {fila_depois}")
        total["fila antes"] += fila_antes
        total["fila depois"] += fila_depois
        for antes, depois, ref, trocas in mudancas:
            print(f"  antes:  {antes}")
            print(f"  depois: {depois}")
            print(f"  ref:    {ref[:160]}")
            for lida, nova, fonte, fonte_nova, dica in trocas:
                print(f"    {lida!r} -> {nova!r}  ({fonte} -> {fonte_nova})  {dica}")
                pistas[dica] = pistas.get(dica, 0) + 1
        total["trocas"] += n
        total["boxes"] += len(pagina.boxes)
    print(f"\n{total['trocas']} troca(s) em {total['boxes']} boxes; na fila de "
          f"revisão {total['fila antes']} -> {total['fila depois']}; pista: "
          + ", ".join(f"{k} {v}" for k, v in sorted(pistas.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
