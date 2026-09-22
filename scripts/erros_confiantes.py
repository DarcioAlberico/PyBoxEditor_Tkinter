"""Os erros confiantes da cadeia de glifos, contra a referência humana (OCR-14).

    python scripts/erros_confiantes.py "PDF/.../livro.pdf" --paginas 30 \
        --referencia preview_ocr/referencia/aagaard_calculation
    python scripts/erros_confiantes.py ... --recortes revisao_ocr14

Lê cada página **só pela cadeia própria** — sem o Tesseract, sem fusão: o que
se mede aqui é o classificador de glifos, que é o que a OCR-14 quer treinar —,
alinha o resultado com a referência (`core/ocr14.py`) e imprime:

- a tabela de confusão dos erros **confiantes** (≥ 0,90), do mais comum ao menos;
- quantos são troca, buraco e invenção, em lance e em prosa;
- as classes que mais ganhariam com amostra nova.

Com `--recortes <pasta>`, grava o recorte de cada troca confiante em
`<pasta>/<classe esperada>/`, no mesmo nome de pasta de `training_data`
(`core.learner.char_to_folder`). **A pasta é quarentena, não base de treino**:
o rótulo veio de um alinhamento, não de olho humano, e `core/coleta.py` explica
em detalhe por que rotular sozinho é treinar o modelo no próprio erro. Confira
os recortes e mova-os você mesmo para `training_data/`.

Só o interpretador do `.venv` tem o torch que o modelo pede.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import ocr14  # noqa: E402
from core.leitura_de_linha import quebrar_em_linhas  # noqa: E402


def caracteres_da_pagina(imagem, classificar, *, conf_minima: float,
                         boxes) -> list[ocr14.CaractereLido]:
    """A página lida pela cadeia, caractere a caractere, com caixa e confiança.

    É o mesmo caminho de `livro.extrair_pagina` — as mesmas caixas, a mesma
    quebra em linhas, o mesmo `_texto_da_linha` —, só que guardando de que box
    saiu cada caractere. O `marcador_confianca` existe para isto (F22): é por
    onde a confiança do glifo sai sem passar pelo texto.
    """
    from core import livro

    saida: list[ocr14.CaractereLido] = []
    for indice_linha, linha in enumerate(quebrar_em_linhas(boxes)):
        confiancas: dict[int, float] = {}
        texto, _fracos, _pesos, _lacunas, caixas = livro._texto_da_linha(
            imagem, linha, classificar, conf_minima,
            marcador_confianca=lambda i, _c, conf: confiancas.__setitem__(i, conf))
        for caractere, indice in zip(texto, caixas):
            box = linha[indice] if 0 <= indice < len(linha) else None
            saida.append(ocr14.CaractereLido(
                texto=caractere,
                confianca=confiancas.get(indice, 0.0) if box is not None else 0.0,
                caixa=(int(box.x1), int(box.y1), int(box.x2), int(box.y2))
                if box is not None else None,
                indice_do_box=int(indice), linha=indice_linha))
        saida.append(ocr14.CaractereLido("\n", 0.0, None, -1, indice_linha))
    return saida


def _gravar_recortes(erros, imagem, boxes_por_linha, destino: Path,
                     prefixo: str) -> int:
    from PIL import Image

    from core import vertical
    from core.learner import char_to_folder

    gravados = 0
    for erro in erros:
        if erro.especie != "troca" or not erro.confiante:
            continue
        linha = boxes_por_linha.get(erro.linha)
        if linha is None or not 0 <= erro.indice_do_box < len(linha):
            continue
        recorte = vertical.recorte_de_pe(imagem, linha[erro.indice_do_box])
        if not getattr(recorte, "size", 0):
            continue
        pasta = destino / char_to_folder(erro.esperado)
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"{prefixo}_l{erro.linha:03d}b{erro.indice_do_box:03d}.png"
        Image.fromarray(recorte).save(pasta / nome)
        gravados += 1
    return gravados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--paginas", type=int, nargs="+", required=True,
                        help="números de página como o livro os imprime (1 = a primeira)")
    parser.add_argument("--referencia", type=Path,
                        default=Path("preview_ocr/referencia"))
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--dominio", default="notation",
                        choices=("notation", "prose", "todos"),
                        help="o domínio que conta; o padrão é o lance, que é o "
                             "que a cadeia entrega ao livro depois da fusão")
    parser.add_argument("--recortes", type=Path, default=None,
                        help="pasta de quarentena para os recortes trocados")
    parser.add_argument("--saida", type=Path,
                        default=Path("preview_ocr/ocr14/relatorio.json"))
    args = parser.parse_args()

    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)

    import fitz

    from core import livro
    from core.services.learning_service import LearningService

    service = LearningService()
    if not service.load_predictor():
        raise RuntimeError(service.motivo_do_modelo())
    classificar = service.leitor_de_texto(args.idioma)

    documento = fitz.open(str(args.pdf))
    relatorio: dict = {"pdf": str(args.pdf), "paginas": {}, "piso": ocr14.PISO_DE_CONFIANCA}
    todos: list[ocr14.ErroConfiante] = []
    try:
        for numero in args.paginas:
            caminho = args.referencia / f"p{numero:03d}.txt"
            if not caminho.exists():
                print(f"página {numero}: sem referência em {caminho} — pulada")
                continue
            imagem = livro._pagina_cinza(documento[numero - 1], args.dpi)
            boxes, _tabuleiros, _escala, _respingos, _colunas = \
                livro.caixas_e_diagramas(imagem, classificar)
            lidos = caracteres_da_pagina(imagem, classificar,
                                         conf_minima=livro.CONF_MINIMA, boxes=boxes)
            pagina_inteira = ocr14.Resumo(ocr14.minerar(
                lidos, caminho.read_text(encoding="utf-8"), pagina=numero))
            resumo = pagina_inteira.no_dominio(args.dominio)
            todos.extend(resumo.erros)
            relatorio["paginas"][str(numero)] = {
                "dominio": args.dominio, **resumo.to_dict(),
                "pagina_inteira": {
                    "confiantes": len(pagina_inteira.confiantes),
                    "por_dominio": dict(pagina_inteira.por_dominio())}}

            print(f"\npágina {numero} — contra {caminho}")
            print(f"  domínio {args.dominio}: {len(resumo.erros)} erro(s), "
                  f"{len(resumo.confiantes)} confiante(s) "
                  f"(≥{ocr14.PISO_DE_CONFIANCA:.2f})  {dict(resumo.por_especie())}")
            print(f"  na página inteira: {len(pagina_inteira.confiantes)} "
                  f"confiante(s)  {dict(pagina_inteira.por_dominio())}")
            for (lido, esperado), vezes in \
                    ocr14.tabela_de_confusao(resumo.erros).most_common(12):
                print(f"    {vezes:3d}×  leu {lido!r:8s} onde é {esperado!r}")
            if args.recortes:
                por_linha = dict(enumerate(quebrar_em_linhas(boxes)))
                gravados = _gravar_recortes(
                    resumo.erros, imagem, por_linha, args.recortes,
                    f"{args.pdf.stem[:24]}_p{numero:03d}")
                print(f"  {gravados} recorte(s) em quarentena em {args.recortes}")
    finally:
        documento.close()

    geral = ocr14.Resumo(todos)
    relatorio["geral"] = {"dominio": args.dominio, **geral.to_dict()}
    print(f"\ntotal: {len(geral.confiantes)} erro(s) confiante(s) em "
          f"{len(args.paginas)} página(s)")
    for classe, vezes in geral.classes_a_treinar():
        print(f"  classe {classe!r}: {vezes} recorte(s) que o modelo lê errado")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    print(f"relatório: {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
