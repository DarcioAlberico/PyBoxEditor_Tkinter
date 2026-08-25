"""
A confusão de caracteres de um livro **inteiro**, sem gabarito (F104).

O `medir_confusao.py` compara com `.box` feito à mão, e por isso mede dezenas de
páginas. Este mede novecentas: a verdade não é um gabarito, é o dicionário de
310.465 palavras da F9, e a suposição — que é o contrato 1 da SPEC §5.8 — de que
palavra de prosa fora dele foi lida errado.

    python medir_confusao_no_livro.py --docx "livro.docx"
    python medir_confusao_no_livro.py --pdf "livro.pdf" --cache paginas.pkl
    python medir_confusao_no_livro.py --docx "livro.docx" --exemplos 30

**O prior é a parte que não dá para pular.** Achado o núcleo fora do dicionário,
qual palavra era ele? Distância de edição sozinha não decide: para `quicHy` ela
escolhe `quiche` com a mesma facilidade com que escolhe `quickly`. Quem desempata
é a frequência **no próprio livro** — `quickly` aparece ali, `quiche` não. O
léxico deste projeto é alfabético e não traz frequência, e é por isso que o prior
tem de sair do texto medido.

**O que o método não vê, e está no relatório.** Erro que produz outra palavra
real é invisível ao dicionário — é limite do método, não do instrumento. E a
palavra que este livro nunca acertou fica com prior zero e não se decide: no
Aagaard são 222 ocorrências, entre elas `quickiy`, cujas 88 leituras saíram todas
erradas. O relatório imprime as duas fatias em vez de escondê-las no total.

**Uma rodada de realimentação foi tentada e recusada.** Deixar o que a matriz já
confirma explicar o caso duvidoso recupera 15% a mais de ocorrências e erra:
resolve `quicHy` como `quiche`, porque `e→y` já é troca confirmada e `kl→H` não.
Fica registrado para quem pensar nela de novo.

**A peneira da notação é escrita à mão, e o cabeçalho do `e_notacao_truncada`
diz por quê**: a versão elegante, que perguntava ao `parece_lance`, escondia
erros de leitura no balde dos lances.

Medido no Aagaard (898 páginas, 130.194 palavras de prosa): 1,01% saem erradas, e
o achado não é a taxa. É que o erro se concentra em **par de letras**, e não em
glifo:

    t → r    23,5% de tudo, em SEIS palavras: two, between, twice, Botvinnik
    l → nada  7,2%, quase tudo `ll` depois de `A`: Although, Allowing, Already
    y → u     2,7%, em quatro palavras, quase tudo o `gy` de strategy
    z → nada  2,4%, numa palavra: zugzwang
    n → h     1,1%, no `Kn` de Knowing, Knights, Knight

Espalhados de verdade — defeito de glifo, e não de contexto — só há dois: o
`l → I` (34 palavras) e o `c → e` (23).
"""

import argparse
import collections
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import lexico, notacao

#: Até onde procurar a palavra certa. Além de duas edições a atribuição deixa de
#: ser leitura errada e vira palpite — medido, a distância 2 já responde por
#: menos de 1% das atribuições.
DISTANCIA = 2

#: Palavra mais curta que isto não se corrige: `hxg` e `Nf` são notação, e
#: `the` errado vira outra palavra de três letras com a mesma facilidade.
MINIMO = 3

#: Sufixos regulares. Palavra conhecida mais um deles é quase sempre buraco do
#: dicionário, e não leitura errada: `increment` está na lista e `increments`
#: não. São 5,5% do que fica de fora no Aagaard.
SUFIXOS = ("s", "es", "ed", "d", "ing", "ly", "er", "est", "'s", "ness")


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ----------------------------------------------------------------------
# Distância, vizinhança e alinhamento
# ----------------------------------------------------------------------

def levenshtein(a: str, b: str, teto: int = DISTANCIA) -> int:
    """Distância de edição, desistindo assim que passa do teto."""
    if abs(len(a) - len(b)) > teto:
        return teto + 1
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1,
                             anterior[j - 1] + (ca != cb)))
        if min(atual) > teto:
            return teto + 1
        anterior = atual
    return anterior[-1]


def deletes(palavra: str) -> set:
    """A palavra com um caractere a menos, em cada posição."""
    return {palavra[:i] + palavra[i + 1:] for i in range(len(palavra))}


def trocas(alvo: str, lido: str) -> list:
    """
    `[(pedaço da verdade, pedaço lido)]` — o que separa uma palavra da outra.

    Sai do `difflib`, e não de uma comparação posição a posição: `quickly` lido
    `quicHy` é o par `kl` virando `H`, e não duas trocas independentes. Perder
    isso mandaria procurar dois defeitos onde há um.
    """
    return [(alvo[i1:i2], lido[j1:j2])
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, alvo, lido, autojunk=False).get_opcodes()
            if tag != "equal"]


class Vizinhanca:
    """
    O dicionário indexado para achar palavra parecida (SymSpell).

    A chave é a palavra e cada uma das suas supressões de um caractere.
    Comparar as supressões dos **dois** lados alcança distância 2 com um índice
    de distância 1 — 2,2 milhões de chaves em vez das dezenas de milhões que a
    vizinhança de distância 2 pediria.
    """

    def __init__(self, palavras):
        self.vocabulario = sorted(p for p in palavras
                                  if MINIMO <= len(p) <= 22 and p.isalpha())
        self.indice = collections.defaultdict(list)
        for i, palavra in enumerate(self.vocabulario):
            self.indice[palavra].append(i)
            for corte in deletes(palavra):
                self.indice[corte].append(i)

    def perto(self, consulta: str) -> list:
        """`[(distância, palavra)]`, ordenado, dentro de `DISTANCIA`."""
        vistos = set()
        for chave in {consulta} | deletes(consulta):
            vistos.update(self.indice.get(chave, ()))
        achados = []
        for i in vistos:
            palavra = self.vocabulario[i]
            d = levenshtein(consulta, palavra)
            if d <= DISTANCIA:
                achados.append((d, palavra))
        return sorted(achados)


# ----------------------------------------------------------------------
# A triagem
# ----------------------------------------------------------------------

#: A captura de peão sem o algarismo: coluna, o `x`, coluna.
#:
#: **O `u` está aí porque o modelo o põe no lugar do `x`**, e não por simetria:
#: medido neste livro, `guf`, `guh` e `gug` somam 177 ocorrências, todas com `g`
#: antes — o `x` depois do `g` é o caso em que ele se perde.
CAPTURA_SEM_ALGARISMO = re.compile(r"^[a-h][xu][a-h]$")


def e_notacao_truncada(nucleo: str) -> bool:
    """
    `hxg` é `hxg5` sem o algarismo — captura de peão cujo dígito se perdeu.

    **Sem esta peneira a matriz sai dominada por notação**, e é o que o contrato
    1 da SPEC §5.8 proíbe: dicionário não decide sobre lance. No Aagaard são
    cerca de 700 ocorrências.

    **O padrão é escrito aqui e não vem do `parece_lance`**, e isso custou uma
    medição errada antes de ficar assim. `parece_lance(nucleo + algarismo)`
    parecia a peneira elegante — e ela aceita `endgame1`, `fine1` e `ed1`:
    20.277 palavras reais do dicionário passariam por lance. No livro ela levou
    junto `dgame` (140 ocorrências, que é `endgame`), `Khowing`, `beeause` e
    `exampIe` — erros de leitura escondidos no balde da notação.
    """
    return bool(CAPTURA_SEM_ALGARISMO.match(nucleo.lower()))


def e_pedaco_de_palavra(nucleo: str, prior) -> str:
    """
    A palavra da qual esta forma é só o começo ou só o fim, se houver uma.

    `dgame` é `endgame` sem as duas primeiras letras, e `ustrative` é
    `illustrative` sem as três. **Isso não é confusão de caractere, é pedaço de
    palavra perdido** — segmentação, ou a linha que começou cortada. Pô-lo na
    matriz daria `nada → d` com o peso de 140 leituras, apontando para um
    defeito que não existe.

    O corte é de **duas** letras, e não de uma: `Exchang` é `Exchange` sem o
    `e` final, e aquilo é uma leitura errada de um caractere, que é justamente o
    que se quer medir. Só se procura entre as palavras que este livro usa — sem
    isso, todo pedaço acha alguma palavra do dicionário que o contenha.
    """
    if len(nucleo) < 4:
        return ""
    for palavra, vezes in prior.items():
        if not vezes or len(palavra) - len(nucleo) < 2:
            continue
        if palavra.endswith(nucleo) or palavra.startswith(nucleo):
            return palavra
    return ""


def e_flexao_ausente(nucleo: str, lx) -> bool:
    """A leitura é palavra conhecida mais sufixo regular: o dicionário é curto."""
    return any(nucleo.endswith(s) and len(nucleo) - len(s) >= MINIMO
               and lx.conhece(nucleo[:-len(s)]) for s in SUFIXOS)


def parte_em_conhecidas(nucleo: str, lx):
    """`ofthe` → `('of', 'the')`, quando o espaço entre as duas se perdeu."""
    for i in range(2, len(nucleo) - 1):
        if lx.conhece(nucleo[:i]) and lx.conhece(nucleo[i:]):
            return nucleo[:i], nucleo[i:]
    return None


def contar(palavras, lx):
    """
    `(conhecidas, formas fora do dicionário, prior)` de um texto já tokenizado.

    O prior são as palavras que o livro **acertou**, e é ele que decide o
    empate lá adiante. Sai daqui e não de fora porque o léxico do projeto é
    alfabético: não há frequência em lugar nenhum deste repositório.
    """
    conhecidas, fora, prior = 0, collections.Counter(), collections.Counter()
    for pedaco in palavras:
        nucleo, _ = lexico.nucleo(pedaco)
        if (not nucleo or len(nucleo) < MINIMO or not nucleo.isalpha()
                or notacao.parece_lance(pedaco) or notacao.parece_lance(nucleo)):
            continue
        if lx.conhece(nucleo):
            conhecidas += 1
            prior[nucleo.lower()] += 1
        else:
            fora[nucleo] += 1
    return conhecidas, fora, prior


def medir(fora, prior, lx, vizinhanca):
    """
    `(categorias, confusão, atribuídas, indecisas)`.

    `confusão` é `{(verdade, lido): vezes}` e é o produto; o resto está aí para
    o relatório poder dizer sobre quanto ele foi medido, que é metade do que uma
    medição sem gabarito precisa dizer.
    """
    categorias = collections.Counter()
    confusao = collections.Counter()
    atribuidas, indecisas = [], []

    for forma, n in fora.items():
        baixo = forma.lower()
        if e_notacao_truncada(forma):
            categorias["notação sem o algarismo"] += n
            continue
        if e_flexao_ausente(baixo, lx):
            categorias["flexão que falta no dicionário"] += n
            continue
        inteira = e_pedaco_de_palavra(baixo, prior)
        if inteira:
            categorias["pedaço de palavra perdido"] += n
            indecisas.append((n, forma, [f"de {inteira}"]))
            continue

        achados = vizinhanca.perto(baixo)
        partido = parte_em_conhecidas(baixo, lx)
        if not achados:
            categorias["espaço perdido" if partido else "sem candidato"] += n
            continue

        perto = achados[0][0]
        empatados = [p for d, p in achados if d == perto]
        alvo = max(empatados, key=lambda p: prior.get(p, 0))
        if prior.get(alvo, 0) == 0:
            # Nenhum dos candidatos aparece neste livro. Não há como decidir, e
            # chutar seria pôr ruído na matriz — ver o cabeçalho.
            if partido:
                categorias["espaço perdido"] += n
            else:
                categorias["sem prior para decidir"] += n
                indecisas.append((n, forma, empatados[:3]))
            continue

        # **O alinhamento é na caixa original**: `BIack` contra `Black` é
        # `l → I`, e é um `I` maiúsculo. Em minúsculo viraria `l → i`, que é
        # outra troca e mandaria procurar outro defeito.
        if forma[:1].isupper():
            alvo = alvo[:1].upper() + alvo[1:]
        categorias[f"atribuída (distância {perto})"] += n
        atribuidas.append((n, forma, alvo))
        for troca in trocas(alvo, forma):
            confusao[troca] += n
    return categorias, confusao, atribuidas, indecisas


# ----------------------------------------------------------------------
# De onde vem o texto
# ----------------------------------------------------------------------

def palavras_do_docx(caminho: str):
    """As palavras de um DOCX já escrito — segundos, e sem modelo nenhum."""
    from docx import Document

    doc = Document(caminho)
    for paragrafo in doc.paragraphs:
        yield from paragrafo.text.split()
    for tabela in doc.tables:
        for fila in tabela.rows:
            for celula in fila.cells:
                for paragrafo in celula.paragraphs:
                    yield from paragrafo.text.split()


def palavras_do_pdf(caminho: str, cache=None, paginas=None):
    """
    As palavras que a extração lê do PDF — minutos, e com o modelo carregado.

    É o caminho honesto quando se quer medir o **modelo** e não um arquivo que
    talvez tenha sido escrito por outra versão dele. O `cache` guarda as páginas
    extraídas: a segunda medição do mesmo livro custa segundos.
    """
    import pickle

    from core import livro

    if cache and os.path.exists(cache):
        with open(cache, "rb") as f:
            extraidas = pickle.load(f)
    else:
        from core.services.learning_service import LearningService

        servico = LearningService()
        if not servico.load_predictor():
            raise SystemExit(servico.motivo_do_modelo())

        def progresso(atual, total):
            if atual % 25 == 0 or atual == total:
                print(f"  {atual}/{total}", flush=True)

        extraidas = livro.extrair(caminho, servico.predict_neural,
                                  paginas=paginas, diagramas="recorte",
                                  progress_callback=progresso)
        if cache:
            with open(cache, "wb") as f:
                pickle.dump(extraidas, f)

    for pagina in extraidas:
        for bloco in pagina.blocos:
            if isinstance(bloco, livro.Paragrafo):
                yield from bloco.texto.split()


# ----------------------------------------------------------------------
# O relatório
# ----------------------------------------------------------------------

def relatar(conhecidas, fora, categorias, confusao, atribuidas, indecisas,
            exemplos=0):
    prosa = conhecidas + sum(fora.values())
    total_fora = sum(fora.values())
    atrib = sum(n for c, n in categorias.items() if c.startswith("atribuída"))

    print(f"palavras de prosa (>= {MINIMO} letras, fora da notação): {prosa:,}")
    print(f"  no dicionário {conhecidas:,}   fora dele {total_fora:,} "
          f"em {len(fora):,} formas\n")

    print(f"=== o que são as {total_fora:,} de fora ===")
    for chave, n in categorias.most_common():
        print(f"  {chave:32s} {n:6,}  {n / max(1, total_fora) * 100:5.1f}%")
    if not atrib:
        print("\nnada foi atribuído — sem prior não há o que medir")
        return 0

    espalhamento = collections.defaultdict(collections.Counter)
    for n, forma, alvo in atribuidas:
        for troca in trocas(alvo, forma):
            espalhamento[troca][alvo] += n

    print(f"\n=== confusão de caracteres, sobre {atrib:,} leituras erradas ===")
    print(f"{'verdade':>9s} → {'lido':<9s} {'vezes':>6s} {'%':>6s} "
          f"{'formas':>7s}   onde")
    for (verdade, lido), n in confusao.most_common(30):
        onde = ", ".join(f"{p}({q})"
                         for p, q in espalhamento[(verdade, lido)].most_common(3))
        print(f"{repr(verdade) if verdade else '(nada)':>9s} → "
              f"{repr(lido) if lido else '(nada)':<9s} {n:6,} "
              f"{n / atrib * 100:5.1f}% "
              f"{len(espalhamento[(verdade, lido)]):7d}   {onde}")

    print("\n=== somando por caractere da verdade ===")
    por_verdade = collections.Counter()
    for (verdade, _lido), n in confusao.items():
        if len(verdade) == 1:
            por_verdade[verdade] += n
    for caractere, n in por_verdade.most_common(10):
        destinos = sorted(((k[1] or "sumiu"), q) for k, q in confusao.items()
                          if k[0] == caractere)
        destinos.sort(key=lambda x: -x[1])
        print(f"  {caractere!r:4s} errado {n:5,}× → "
              + ", ".join(f"{d}×{q}" for d, q in destinos[:4]))

    sem_prior = categorias["sem prior para decidir"]
    if indecisas:
        print(f"\n=== as {sem_prior:,} que o prior não decide ===")
        print("  (nenhum candidato aparece neste livro — a palavra certa pode "
              "nunca ter sido lida certa)")
        for n, forma, candidatos in sorted(indecisas, reverse=True)[:10]:
            print(f"  {n:4d}×  {forma:16s}  candidatos: "
                  f"{'/'.join(candidatos)}")

    if exemplos:
        print(f"\n=== {exemplos} atribuições, para conferir com o olho ===")
        for n, forma, alvo in sorted(atribuidas, reverse=True)[:exemplos]:
            print(f"  {n:4d}×  {forma:18s} → {alvo}")

    invisivel = (total_fora - categorias["notação sem o algarismo"]
                 - categorias["flexão que falta no dicionário"])
    print(f"\ntaxa de erro medida:  {atrib / prosa * 100:.2f}%  "
          f"({atrib:,} de {prosa:,} palavras de prosa)")
    print(f"teto, se tudo o que sobrou também for erro: "
          f"{invisivel / prosa * 100:.2f}%")
    print("abaixo do piso fica o erro que produz outra palavra real, que "
          "dicionário nenhum vê.")
    return 0


def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    fonte = ap.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--docx", help="um DOCX já escrito (segundos)")
    fonte.add_argument("--pdf", help="o PDF, relendo com o modelo (minutos)")
    ap.add_argument("--cache", default=None,
                    help="onde guardar/reler as páginas extraídas do PDF")
    ap.add_argument("--paginas", default=None,
                    help="só estas páginas do PDF, 0-based: 10,40,80")
    ap.add_argument("--exemplos", type=int, default=0,
                    help="quantas atribuições imprimir para conferência")
    ap.add_argument("--lista", default=None, help="outro arquivo de léxico")
    args = ap.parse_args()

    lx = lexico.carregar(args.lista)
    if lx.vazio:
        print("léxico vazio — sem dicionário não há o que medir")
        return 1
    print(f"léxico: {len(lx):,} palavras", flush=True)

    if args.docx:
        palavras = palavras_do_docx(args.docx)
    else:
        quais = ([int(p) for p in args.paginas.split(",")]
                 if args.paginas else None)
        palavras = palavras_do_pdf(args.pdf, args.cache, quais)

    conhecidas, fora, prior = contar(palavras, lx)
    if not fora:
        print("nenhuma palavra fora do dicionário")
        return 0
    print(f"indexando a vizinhança...", flush=True)
    vizinhanca = Vizinhanca(lx.palavras | lx.do_usuario)
    print(f"  {len(vizinhanca.vocabulario):,} palavras, "
          f"{len(vizinhanca.indice):,} chaves\n", flush=True)

    return relatar(conhecidas, fora,
                   *medir(fora, prior, lx, vizinhanca), exemplos=args.exemplos)


if __name__ == "__main__":
    sys.exit(main())
