"""
Uma palavra de prosa em cinco sai com defeito — a régua que diz quais (F115).

A `docs/SPEC-CONVERSAO.md` §1 classificou as 20.625 palavras de prosa do DOCX
exportado do Yusupov em cinco famílias e chegou a **20,26% com defeito**. A
conta foi feita à mão, sobre um arquivo, e não sobrou instrumento: não havia
como refazê-la depois de mexer no código, que é justamente quando ela importa.

Este módulo é essa conta, escrita. Ele lê de três lugares — um DOCX, um EPUB, ou
o PDF relido com o modelo — e devolve a mesma tabela, mais as duas réguas
baratas que a spec pede ao lado dela (§1 e §2.7).

    python medir_prosa.py --docx "PDF/.../livro.docx"
    python medir_prosa.py --epub "Kasparov - The Dynamic Benko Gambit.epub"
    python medir_prosa.py --pdf "PDF/.../livro.pdf" --paginas 8-60

## As cinco famílias, e por que a ordem é essa

**A. o `i` partido em haste e pingo** (`Wh1.te`, `whz.ch`, `exercz.ses`). O
separador de glifo corta o `i` em dois, a haste sai `1`/`l`/`z` e o pingo sai
`.`. Ela vem primeiro porque a assinatura dela — ponto no **meio** da palavra —
é a mais específica das cinco, e `Wh1.te` também tem dígito, que é a família D.

**B. caixa homográfica** (`alSo`, `biShop`). O dicionário conhece a palavra e o
padrão de caixa não é nenhum dos três legítimos. É o que a F108 conserta, e
medi-la aqui é medir quanto dela ainda escapa.

**C. palavra colada** (`WThite`, `hDiagram`, `FundamentalSBy`). Fora do
dicionário, e vira palavra conhecida ou partindo em duas ou tirando de uma a
três letras de uma das pontas. As quatro formas são as que a spec classificou
uma a uma nas 544 que sobraram depois da F108.

**D. dígito espúrio dentro da palavra** (`y0u`, `g0t`, `po1nt`, `lut1`). Há
dígito onde devia haver letra, e o dicionário não é consultado — ver
`_tem_digito`. É a família B com outro alfabeto: `0`/`o` e `1`/`l` são o mesmo
desenho, e o que os separa é o tamanho relativo à linha, que o classificador não
vê (F107, F112).

**E. resto fora do dicionário** (`Diagrram`, `rspeat`). O que sobra.

## O que **não** é palavra de prosa

Notação (`notacao.parece_lance`), o núcleo de menos de três letras, e o que traz
caractere fora de letra-dígito-ponto — que é a linha de fonte de diagrama
vazando para a prosa. A spec mediu que ela é 6,6% do "fora do dicionário" do
Yusupov e contamina a conta.

**A palavra parte no hífen antes de ser julgada**, como a F108 parte:
`Kasparov-Karpov` tem maiúscula interna e está certo.

## As duas réguas ao lado

**A razão de caixa** (§1): `S/s` = 0,203 no Yusupov contra 0,047 no Kasparov,
que é o valor normal de um texto em inglês. Mede sem gabarito, num livro
inteiro, em segundos, e é preditiva.

**Os defeitos que o texto denuncia sozinho**, e que são o critério de aceitação
da F115: espaço duplo, e hífen de fim de linha que ainda forma palavra conhecida
quando as duas metades se juntam. Os dois têm de sair em zero.
"""

import argparse
import collections
import os
import re
import sys
import unicodedata
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import lexico, notacao

#: Menor núcleo que se julga. A spec disse "mais de dois caracteres".
MINIMO = 3

#: Quantas letras se pode tirar de uma ponta para achar a palavra de dentro.
#: A spec classificou `hDiagram` (uma na frente), `WThite` e `PKeres` (duas ou
#: três), `TroitzkyA` (uma atrás) e `FundamentalSBy` (sufixo).
COLADAS = 3

#: Quantas letras a palavra de dentro precisa ter para a colagem ser afirmada.
#:
#: **Não é gosto: com três, a família C engole a E inteira.** Medido no EPUB do
#: Kasparov, que é o livro bom do corpus, C dava 1.785 palavras (5,07%) e nelas
#: estavam `phoros` (por `ros`), `René` (por `Ren`) e `Dynam1C` (por `dyn`) —
#: nenhuma é colagem. Numa lista de 310.465 palavras quase todo trio de letras
#: existe, e afirmar colagem sobre ele é afirmar qualquer coisa. Com quatro, as
#: três somem e o `Dynam1C` cai na família D, que é onde ele é.
MINIMO_DA_SOBRA = 4

#: Dígito e a letra que ele desenha igual. **É documentação, e não código.**
#:
#: A família D não consulta o dicionário (ver `_tem_digito`), então este mapa não
#: é lido por ninguém. Ele fica porque é a **causa** da família: sem ele, "há
#: dígito no meio da palavra" parece uma régua arbitrária, e com ele se vê que
#: `y0u` e `po1nt` são o par homográfico que a F107 mediu, com outro alfabeto.
SOSIAS = {"0": "o", "1": "li", "5": "s", "9": "g", "8": "b", "6": "b", "2": "z"}

#: O que pode aparecer numa palavra de prosa. Fora disto é fonte de diagrama.
PROSA = re.compile(r"^[0-9A-Za-zÀ-ÿ.'’-]+$")


def _console_em_utf8():
    """O `cp1252` do console do Windows não escreve `♗` nem `⩲`."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


# ----------------------------------------------------------------------
# De onde o texto vem
# ----------------------------------------------------------------------

def texto_do_docx(caminho: str) -> str:
    """Os parágrafos do DOCX, um por linha. Tabela fica de fora — não é prosa."""
    from docx import Document

    return "\n".join(p.text for p in Document(caminho).paragraphs)


def texto_do_epub(caminho: str) -> str:
    """Os `<p>` do EPUB. O `<h2>` fica de fora pelo mesmo motivo da tabela."""
    import html

    partes = []
    with zipfile.ZipFile(caminho) as z:
        nomes = sorted(n for n in z.namelist() if n.endswith(".xhtml"))
        for nome in nomes:
            pagina = z.read(nome).decode("utf-8", "replace")
            for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", pagina, re.S):
                partes.append(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))))
    return "\n".join(partes)


def paginas_do_pdf(caminho: str, paginas=None, lex=None, idioma=None):
    """
    As `PaginaExtraida` do caminho de produção, com o modelo de verdade.

    `idioma` liga a máscara de alfabeto (F109 §1), como a exportação liga.
    """
    from core import livro
    from core.services.learning_service import LearningService

    servico = LearningService()
    if not servico.load_predictor():
        raise SystemExit(f"sem modelo: {servico.motivo_do_modelo()}")

    def progresso(atual, total):
        if atual % 10 == 0 or atual == total:
            print(f"  ... {atual}/{total} páginas", flush=True)

    return livro.extrair(caminho, servico.leitor_de_texto(idioma),
                         paginas=paginas, lex=lex,
                         progress_callback=progresso)


def texto_das_paginas(paginas) -> str:
    """Só os parágrafos que não são título, que é o que a spec chamou prosa."""
    from core.livro import Paragrafo

    return "\n".join(b.texto for p in paginas for b in p.blocos
                     if isinstance(b, Paragrafo) and not b.titulo)


# ----------------------------------------------------------------------
# As cinco famílias
# ----------------------------------------------------------------------

def _e_prosa(pedaco: str) -> bool:
    return bool(PROSA.match(pedaco)) and not notacao.parece_lance(pedaco)


def palavras_de_prosa(texto: str):
    """
    As palavras que se julgam, já partidas no hífen.

    **Sai a pontuação das pontas, e o dígito fica** — que é a diferença entre
    esta régua e `lexico.nucleo`, e ela vale 224 palavras neste livro. O núcleo
    tira das pontas tudo o que não é letra, de propósito: é o que vai a uma
    consulta de dicionário. Mas ele leva o dígito junto, e o dígito **na ponta**
    é metade da família D — `lut1` vira `lut` e `1nto` vira `nto`, e as duas
    somem para a família E como se o defeito fosse outro. Quem pergunta ao
    dicionário continua usando o núcleo; quem pergunta "há dígito onde devia
    haver letra" pergunta aqui.
    """
    for bruto in texto.split():
        if not _e_prosa(bruto):
            continue
        for pedaco in re.split(r"[-‐‑]", bruto):
            palavra = pedaco.strip(lexico.BORDAS)
            nuc, _ini = lexico.nucleo(palavra)
            if len(nuc) < MINIMO or sum(c.isalpha() for c in nuc) < 2:
                continue
            if notacao.parece_lance(nuc) or notacao.parece_lance(palavra):
                continue
            yield palavra


def _e_i_partido(nuc: str, lex) -> bool:
    """
    `Wh1.te` → `White`: todo `X.` do meio da palavra era um `i`.

    A remontagem precisa de `MINIMO_DA_SOBRA` letras pelo mesmo motivo que a
    colagem precisa: sem isso `e.g` "remonta" em `ig`, que a lista de 310.465
    palavras contém, e a abreviatura mais comum de um livro técnico vira a
    família A inteira — medidas 192 no Nunn, quase todas `e.g`.
    """
    if "." not in nuc[1:-1]:
        return False
    candidato = re.sub(r".\.", "i", nuc)
    return len(candidato) >= MINIMO_DA_SOBRA and lex.conhece(candidato)


def _e_colada(nuc: str, lex) -> bool:
    """Fora do dicionário, e a palavra de dentro aparece tirando uma ponta."""
    if lexico.cortes_possiveis(nuc, lex):
        return True
    baixo = nuc.lower()
    for n in range(1, COLADAS + 1):
        if len(baixo) - n < MINIMO_DA_SOBRA:
            break
        if lex.conhece(baixo[n:]) or lex.conhece(baixo[:-n]):
            return True
    return False


def _tem_digito(nuc: str) -> bool:
    """
    `y0u`, `g0t`, `po1nt`, `lut1`: há dígito no meio de uma palavra de prosa.

    **Não pergunta ao dicionário, e é de propósito.** A primeira versão exigia
    que trocar o dígito pelo sósia desse palavra conhecida, e com isso media 142
    onde a spec mediu 1.651: `lut1` não vira `lutl` nem `luti`, e continua sendo
    um dígito onde devia haver letra. O núcleo já começa e termina em letra por
    construção (`lexico.nucleo`) e a notação já saiu pelo `parece_lance` — o que
    sobra com dígito no meio é erro de leitura, e o dicionário não tem o que
    acrescentar a isso.

    Os sósias continuam documentados em `SOSIAS` porque são a **causa**: `0`/`o`
    e `1`/`l` são o mesmo desenho, e o que os separa é o tamanho relativo à
    linha, que o classificador não vê (F107, F112).
    """
    return any(c.isdigit() for c in nuc)


FAMILIAS = ("A. o `i` partido em haste e pingo",
            "B. caixa homográfica",
            "C. palavra colada",
            "D. dígito espúrio dentro da palavra",
            "E. resto fora do dicionário")


def classificar(palavra: str, lex):
    """
    A família desta palavra, ou `None` se ela está limpa.

    **A ordem do teste não é a ordem da tabela**, e é a da assinatura mais
    específica para a menos: o `Wh1.te` tem ponto no meio *e* dígito, o
    `Dynam1C` tem dígito *e* decompõe em `dyn`. Quem decide é quem afirma mais.
    A tabela sai na ordem da spec, que é a de quem lê.

    O dicionário é consultado pelo **núcleo** e o dígito é procurado na
    **palavra** — ver `palavras_de_prosa`.
    """
    nuc, _ini = lexico.nucleo(palavra)
    if _e_i_partido(palavra, lex):
        return FAMILIAS[0]
    if lex.conhece(nuc):
        return FAMILIAS[1] if lexico.caixa_estranha(nuc) else None
    if _tem_digito(palavra):
        return FAMILIAS[3]
    if _e_colada(nuc, lex):
        return FAMILIAS[2]
    return FAMILIAS[4]


# ----------------------------------------------------------------------
# As réguas ao lado
# ----------------------------------------------------------------------

#: Os pares que são o mesmo desenho, e por isso só o tamanho separa (F107).
PARES_DE_CAIXA = "SWJVZKPCOU"


def razao_de_caixa(texto: str):
    """{letra: (maiúsculas, minúsculas, razão)} dos pares homográficos."""
    conta = collections.Counter(texto)
    saida = {}
    for alta in PARES_DE_CAIXA:
        cima, baixo = conta[alta], conta[alta.lower()]
        if alta == "O":
            cima += conta["0"]
        saida[alta] = (cima, baixo, cima / baixo if baixo else float("inf"))
    return saida


#: A fila de coordenadas que escapou da margem do diagrama (F109 §3): uma
#: linha só de letras `a`–`h` soltas, três ou mais.
FILA_DE_COORDENADAS = re.compile(r"^[a-h]( [a-h]){2,}$", re.MULTILINE)


def letras_fora_do_ascii(texto: str):
    """`{letra: vezes}` das letras latinas acentuadas — a máscara da F109 §1."""
    conta = collections.Counter(
        c for c in texto
        if ord(c) > 127 and c.isalpha()
        and unicodedata.name(c, "").startswith("LATIN "))
    return conta


def taxa_de_titlecase(palavras):
    """
    `{letra: (Capitalizadas, total)}` por inicial — a inicial trocada (F109 §6).

    É o erro de caixa que nenhum instrumento vê: `Also` por `also` é padrão
    legítimo, `caixa_estranha` não acende, `conhece` não acende, e a razão
    `S/s` mal se move. O que o denuncia é a taxa por letra contra um livro
    nativo — `S` dá 21,5% no DOCX do Yusupov e 3,7% no EPUB do Kasparov,
    enquanto `T` dá 16% nos dois (é o `The`), e portanto é inocente.
    """
    conta = collections.defaultdict(lambda: [0, 0])
    for palavra in palavras:
        inicial = palavra[:1]
        if not inicial.isalpha():
            continue
        par = conta[inicial.lower()]
        par[1] += 1
        par[0] += inicial.isupper()
    return {k: tuple(v) for k, v in conta.items()}


def defeitos_do_texto(texto: str, lex):
    """
    Os dois defeitos que o próprio texto denuncia, e que a F115 zera.

    **A remontagem é a de `lexico.juntar_hifenizadas`, letra por letra**, e não
    uma aproximação dela. A primeira versão casava `([A-Za-zÀ-ÿ]{2,})[-‐‑] `
    contra as letras iniciais do token seguinte, e com isso contava `nor- mal1y`
    como junção de `normal` — mas o núcleo daquele token é `mal1y` inteiro, e a
    remontagem verdadeira dá `normal1y`, que não é palavra. Medido no Nunn, a
    régua frouxa dizia 13 junções pendentes onde havia **1**.

    Continua sendo um **teto**, e o texto não permite mais: o léxico só junta
    palavra partida entre **duas linhas**, e a linha não sobrevive ao parágrafo.
    """
    duplos = len(re.findall(r"[^\S\n]{2,}", texto))
    hifens = 0
    for m in re.finditer(r"(\S+[-‐‑]) (\S+)", texto):
        nuc_e, _i = lexico.nucleo(m.group(1).rstrip(lexico.HIFENS))
        nuc_d, _j = lexico.nucleo(m.group(2))
        if nuc_e and nuc_d and lex.conhece(nuc_e + nuc_d):
            hifens += 1
    return duplos, hifens


# ----------------------------------------------------------------------
# O relatório
# ----------------------------------------------------------------------

def relatar(texto: str, lex, exemplos: int = 4) -> None:
    nucleos = list(palavras_de_prosa(texto))
    total = len(nucleos)
    if not total:
        print("nenhuma palavra de prosa — o filtro comeu tudo?")
        return

    contagem = collections.Counter()
    amostra = collections.defaultdict(list)
    for palavra in nucleos:
        familia = classificar(palavra, lex)
        if familia is None:
            continue
        contagem[familia] += 1
        if len(amostra[familia]) < exemplos:
            amostra[familia].append(palavra)

    print(f"\npalavras de prosa: {total}")
    print(f"{'família':38s} {'palavras':>9s} {'%':>7s}  exemplos")
    com_defeito = 0
    for familia in FAMILIAS:
        n = contagem[familia]
        com_defeito += n
        print(f"{familia:38s} {n:9d} {100 * n / total:6.2f}%  "
              f"{', '.join(amostra[familia])}")
    print(f"{'com defeito':38s} {com_defeito:9d} "
          f"{100 * com_defeito / total:6.2f}%")
    print(f"{'limpas':38s} {total - com_defeito:9d} "
          f"{100 * (total - com_defeito) / total:6.2f}%")

    print("\nrazão de caixa (o mesmo desenho; só o tamanho separa)")
    print(f"{'par':6s} {'maiúsc.':>9s} {'minúsc.':>9s} {'razão':>8s}")
    for alta, (cima, baixo, razao) in razao_de_caixa(texto).items():
        rotulo = "(O+0)/o" if alta == "O" else f"{alta}/{alta.lower()}"
        print(f"{rotulo:6s} {cima:9d} {baixo:9d} {razao:8.3f}")

    duplos, hifens = defeitos_do_texto(texto, lex)
    print("\ndefeitos que o texto denuncia sozinho (a F115 zera os dois)")
    print(f"  espaço duplo                          {duplos:7d}")
    print(f"  hífen de fim de linha que ainda junta {hifens:7d}")

    # As três réguas da F109 que o texto sozinho mede.
    filas = len(FILA_DE_COORDENADAS.findall(texto))
    acentos = letras_fora_do_ascii(texto)
    print(f"  fila de coordenadas solta (a b c d…)  {filas:7d}")
    print(f"  letra latina fora do ASCII            "
          f"{sum(acentos.values()):7d}  em {len(acentos)} letras: "
          + ", ".join(f"{l}×{n}" for l, n in acentos.most_common(8)))

    print("\ninicial maiúscula por letra (a inicial trocada só aparece "
          "contra um livro nativo)")
    taxas = taxa_de_titlecase(nucleos)
    print(f"{'letra':6s} {'Capit.':>8s} {'total':>8s} {'%':>7s}")
    for letra, (cima, total_l) in sorted(
            taxas.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1]))[:10]:
        if total_l < 100:
            continue
        print(f"{letra:6s} {cima:8d} {total_l:8d} {100 * cima / total_l:6.1f}%")


def main(argv=None) -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    fonte = ap.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--docx", help="um DOCX já escrito (segundos)")
    fonte.add_argument("--epub", help="um EPUB já escrito (segundos)")
    fonte.add_argument("--pdf", help="o PDF, relendo com o modelo (minutos)")
    fonte.add_argument("--texto", help="um texto já gravado por `--salvar`")
    ap.add_argument("--paginas", default=None,
                    help="faixa 1-based do PDF, ex.: 8-60")
    ap.add_argument("--lista", default=None, help="outro arquivo de léxico")
    ap.add_argument("--sem-lexico", action="store_true",
                    help="relê o PDF sem passar o léxico ao `livro.extrair`")
    ap.add_argument("--idioma", default=None, choices=("en", "pt"),
                    help="liga a máscara de alfabeto da F109 na releitura")
    ap.add_argument("--exemplos", type=int, default=4)
    ap.add_argument("--salvar", default=None,
                    help="grava o texto lido, para remedir sem reler o PDF")
    args = ap.parse_args(argv)

    lex = lexico.carregar(args.lista) if args.lista else lexico.carregar()
    print(f"léxico: {len(lex)} palavras")

    if args.pdf:
        paginas = None
        if args.paginas:
            a, _, z = args.paginas.partition("-")
            paginas = range(int(a) - 1, int(z or a))
        # **O léxico vai para dentro da extração**, e é o que a F115 mudou de
        # lugar: os reparos acontecem no parágrafo. `--sem-lexico` mede o que
        # sairia sem eles, que é a coluna "antes" da tabela.
        extraidas = paginas_do_pdf(args.pdf, paginas,
                                   None if args.sem_lexico else lex,
                                   args.idioma)
        texto = texto_das_paginas(extraidas)
        print(f"páginas: {len(extraidas)}")
        # O que `retirar_cabecalhos` tirou (F109 §5), para o olho conferir que
        # era cabeçalho: a régua é a repetição, e a repetição não sabe ler.
        retirados = collections.Counter()
        for p in extraidas:
            retirados.update(p.cabecalhos)
        numeros = sum(n for t, n in retirados.items() if t.strip().isdigit())
        sem_letra = sum(n for t, n in retirados.items()
                        if not any(c.isalpha() for c in t))
        print(f"cabeçalhos e rodapés de página retirados: "
              f"{sum(retirados.values())} em {len(retirados)} textos — "
              f"{numeros} só número de página, {sem_letra - numeros} só "
              f"símbolo, e os com letra:")
        for t, n in retirados.most_common():
            if any(c.isalpha() for c in t):
                print(f"  {n:4d}×  {t!r}")
    elif args.docx:
        texto = texto_do_docx(args.docx)
    elif args.epub:
        texto = texto_do_epub(args.epub)
    else:
        # Reler o PDF custa minutos, e a régua da classificação muda mais que a
        # leitura: `--salvar` grava o texto e `--texto` o traz de volta, para
        # afinar a régua sem pagar o OCR outra vez.
        with open(args.texto, encoding="utf-8") as f:
            texto = f.read()

    if args.salvar:
        with open(args.salvar, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"texto gravado em {args.salvar}")

    relatar(texto, lex, args.exemplos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
