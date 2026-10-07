"""
A prosa do ClearScan contra a do leitor de produção (PD-14).

A F110 deixou registrado: nos livros que passaram pelo ClearScan do Acrobat, a
camada de texto tem a prosa quase limpa e a notação ilegível, e ler a prosa da
camada com o lance do OCR na mesma linha "precisa de medida antes". Esta é a
medida, nas páginas do corpus de referência que têm camada ClearScan.

Três leituras de cada página, contra a referência transcrita, pela régua da
rodada do corpus (`ocr_ab.medir_por_dominio`, CER e WER por domínio):

- **produção** — `livro.extrair`, o que a exportação entrega hoje;
- **camada** — o texto do ClearScan, montado em parágrafos e colunas pelo
  `pdf_nativo.extrair_pagina` (sem a régua que o recusaria);
- **combinada** — os tokens das duas alinhados; onde a produção lê notação,
  fica a produção, e no resto fica a camada;
- **reparada** — a produção, com a palavra de prosa que o léxico não conhece
  trocada pela da camada alinhada a ela, quando a da camada é conhecida;
- **com léxico** — `livro.extrair` com o léxico e a camada desligada: a
  linha de base honesta da de baixo;
- **exportação** — `livro.extrair` com `camada="auto"`, que faz a reparada
  dentro do leitor (`livro.reparar_pela_camada`), parágrafo a parágrafo.

    python scripts/medir_prosa_da_camada.py
"""

import argparse
import glob
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import fitz  # noqa: E402

from core import pdf_nativo  # noqa: E402
from core.ocr_ab import (_dominio_do_token, alinhar_tokens,  # noqa: E402
                         medir_por_dominio, normalizar_tipografia)

#: As páginas do corpus de referência que têm camada ClearScan: pasta da
#: referência, padrão do PDF em `PDF/`, página (base 1).
PAGINAS = (
    ("nunn_secrets_of_rook_endings", "PDF/Nunn*/*.pdf", 237),
    ("yusupov_chess_evolution_1", "PDF/Artur*/*.pdf", 34),
    ("yusupov_chess_evolution_1", "PDF/Artur*/*.pdf", 47),
)


def combinar(producao: str, camada: str) -> str:
    """A notação da produção, e o resto da camada, token a token.

    Alinha as duas leituras como a régua alinha referência e predição. Onde a
    produção lê um lance (`_dominio_do_token`), fica o lance dela — o ClearScan
    não lê figurina; onde não, fica a palavra da camada. Token que só uma das
    duas tem fica se for do domínio em que ela é a boa.
    """
    p = normalizar_tipografia(producao).split()
    c = normalizar_tipografia(camada).split()
    saida = []
    for lido_p, lido_c in alinhar_tokens(p, c):
        if lido_p is not None and _dominio_do_token(lido_p) == "notation":
            saida.append(lido_p)
        elif lido_c is not None:
            if _dominio_do_token(lido_c) == "prose":
                saida.append(lido_c)
        elif lido_p is not None:
            saida.append(lido_p)
    return " ".join(saida)


#: Quanto a palavra da camada tem de se parecer com a lida para trocar
#: (`difflib.SequenceMatcher.ratio`). Sem trava nenhuma, o alinhamento que cruza
#: colunas trocava a palavra desconhecida por uma conhecida de outro lugar, e a
#: p. 34 do Yusupov piorava de 3,28% para 5,74%.
SEMELHANCA_MINIMA = float(os.environ.get("SEMELHANCA_MINIMA", "0.6"))


def reparar_pela_camada(producao: str, camada: str, lex) -> str:
    """Só a palavra de prosa que o léxico **não** conhece troca pela da camada,
    e só quando a da camada, alinhada a ela, é conhecida. O resto — a notação,
    a ordem, toda palavra que já existe — é o da produção."""
    from difflib import SequenceMatcher

    from core.lexico import nucleo

    p = normalizar_tipografia(producao).split()
    c = normalizar_tipografia(camada).split()
    saida = []
    for lido_p, lido_c in alinhar_tokens(p, c):
        if lido_p is None:
            continue
        if (lido_c is not None and _dominio_do_token(lido_p) == "prose"
                and not lex.conhece(nucleo(lido_p)[0])
                and lex.conhece(nucleo(lido_c)[0])
                and SequenceMatcher(None, lido_p.lower(), lido_c.lower()).ratio()
                >= SEMELHANCA_MINIMA):
            saida.append(lido_c)
        else:
            saida.append(lido_p)
    return " ".join(saida)


def texto_da_camada(pdf: str, pagina: int) -> str:
    with fitz.open(pdf) as doc:
        extraida = pdf_nativo.extrair_pagina(doc[pagina - 1], numero=pagina - 1)
    return extraida.texto


def texto_da_producao(pdf: str, pagina: int, idioma: str = "en") -> str:
    sys.path.insert(0, RAIZ)
    import medir_prosa

    [extraida] = medir_prosa.paginas_do_pdf(pdf, [pagina - 1], idioma=idioma)
    return extraida.texto


def texto_da_exportacao(pdf: str, pagina: int, lex, idioma: str = "en",
                        camada: str = "auto") -> str:
    """O caminho da exportação: `livro.extrair` com a camada ligada, que é o que
    liga `livro.reparar_pela_camada` nas páginas do ClearScan."""
    from core import livro
    from core.services.learning_service import LearningService

    servico = LearningService()
    servico.load_predictor()
    [extraida] = livro.extrair(pdf, servico.leitor_de_texto(idioma),
                               paginas=[pagina - 1], lex=lex,
                               candidatas=servico.candidatas, camada=camada)
    return extraida.texto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.parse_args(argv)
    somas = {nome: {d: [0, 0] for d in ("prose", "notation", "total")}
             for nome in ("produção", "camada", "combinada", "reparada",
                          "com léxico", "exportação")}
    from core import lexico
    lex = lexico.carregar()
    for pasta, padrao, pagina in PAGINAS:
        pdfs = glob.glob(os.path.join(RAIZ, padrao))
        ref_caminho = os.path.join(RAIZ, "preview_ocr", "referencia", pasta,
                                   f"p{pagina:03d}.txt")
        if not pdfs or not os.path.exists(ref_caminho):
            print(f"{pasta} p. {pagina}: sem PDF ou sem referência")
            continue
        referencia = open(ref_caminho, encoding="utf-8").read()
        producao = texto_da_producao(pdfs[0], pagina)
        camada = texto_da_camada(pdfs[0], pagina)
        leituras = {"produção": producao, "camada": camada,
                    "combinada": combinar(producao, camada),
                    "reparada": reparar_pela_camada(producao, camada, lex),
                    "com léxico": texto_da_exportacao(pdfs[0], pagina, lex,
                                                      camada="nunca"),
                    "exportação": texto_da_exportacao(pdfs[0], pagina, lex)}
        print(f"\n{pasta} p. {pagina}")
        print(f"  {'leitura':<11}{'CER prosa':>11}{'CER notação':>13}{'CER total':>11}")
        for nome, texto in leituras.items():
            m = medir_por_dominio(referencia, texto)
            for d in ("prose", "notation", "total"):
                somas[nome][d][0] += m[d]["erros_de_caractere"]
                somas[nome][d][1] += m[d]["caracteres"]
            print(f"  {nome:<11}{m['prose']['cer']:>10.2%}{m['notation']['cer']:>13.2%}"
                  f"{m['total']['cer']:>11.2%}")
    print("\nponderado pelas páginas")
    print(f"  {'leitura':<11}{'CER prosa':>11}{'CER notação':>13}{'CER total':>11}")
    for nome, dominios in somas.items():
        cer = {d: e / max(1, n) for d, (e, n) in dominios.items()}
        print(f"  {nome:<11}{cer['prose']:>10.2%}{cer['notation']:>13.2%}"
              f"{cer['total']:>11.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
