"""
Correção do mapeamento de caracteres de um PDF (F2.5).

**O defeito não é de OCR, é de mapeamento.** Nos livros deste projeto a notação
está *certa* na tela — "1...♖xf3! 2.♕xd5" — e sai como `l2Jd7` ao copiar. As
fontes são Type0/Identity-H: o código do caractere é o número do glifo dentro da
fonte, e quem diz qual caractere aquele desenho representa é uma tabela à parte,
o `ToUnicode`. Nessas fontes o produtor do PDF **assumiu que não sabia** e
escreveu `U+FFFD` (o losango de interrogação) para cada figurina. Medido: 216
pares (fonte, glifo) marcados assim no Yusupov completo, 101 no Aagaard.

Daí a forma desta correção, que é diferente de tudo o mais nesta pasta: ela não
apaga nem redesenha nada na página. Reescreve **só a tabela**, e o resultado é um
PDF pixel a pixel idêntico ao original cujo texto passa a copiar e buscar certo.
Conferido comparando os pixmaps antes e depois — ver
`test_a_pagina_nao_muda_um_pixel`.

O que a página não diz, o desenho diz: cada glifo sem mapa é **recortado da
própria página renderizada e classificado** pelo modelo do projeto, que foi
treinado nestes mesmos livros. Vários recortes por glifo, e o símbolo só entra na
tabela com votação folgada — um glifo aparece dezenas de vezes no livro, e não há
razão para decidir com uma amostra só.

**Propõe, marca, não reescreve calado** (o contrato da F1.7): glifo cuja votação
não fecha continua `U+FFFD` e vai para o relatório com o motivo. Trocar `U+FFFD`
por um palpite errado seria pior que deixar como está — o losango pelo menos se
vê.
"""

import csv
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import fitz
import numpy as np


#: O caractere que o produtor do PDF escreve quando não soube mapear o glifo.
SEM_MAPA = "�"

#: Os símbolos que esta correção aceita escrever na tabela.
#:
#: São os cinco que o modelo distingue (`model_meta.json`: ♔♕♖♗♘, mais a
#: ligadura `♗x`), e são exatamente os que ganham letra em notação algébrica.
#: Restringir aqui é o que impede a ferramenta de reescrever, com base num
#: palpite de OCR, o mapeamento de um traço ou de uma aspa curva que também
#: caíram no `U+FFFD` — coisas que não são o problema que ela veio resolver.
SIMBOLOS_ACEITOS = frozenset("♔♕♖♗♘")


class MapeamentoInvalido(RuntimeError):
    """O PDF não tem a forma que esta correção sabe consertar."""


# ----------------------------------------------------------------------
# A tabela ToUnicode
# ----------------------------------------------------------------------

_BFCHAR = re.compile(r"beginbfchar(.*?)endbfchar", re.S)
_BFRANGE = re.compile(r"beginbfrange(.*?)endbfrange", re.S)
_PAR = re.compile(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>")
_FAIXA = re.compile(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>")
_ORDERING = re.compile(r"/Ordering\s*\((.*?)\)")
_CMAPNAME = re.compile(r"/CMapName\s*/(\S+)")


def _de_utf16(hexa: str) -> str:
    """O destino de um bfchar é UTF-16BE em hexadecimal."""
    if not hexa or len(hexa) % 4:
        return ""
    try:
        return bytes.fromhex(hexa).decode("utf-16-be")
    except (ValueError, UnicodeDecodeError):
        return ""


def _para_utf16(texto: str) -> str:
    return texto.encode("utf-16-be").hex().upper()


def ler_cmap(texto: str) -> Dict[int, str]:
    """
    {código -> texto} de um stream ToUnicode.

    Lê `bfrange` além de `bfchar` mesmo os três livros só usarem `bfchar`: a
    tabela é reescrita inteira a partir do que se leu aqui, e uma faixa que
    passasse batida sumiria do PDF de saída — a correção apagaria mapeamentos
    corretos para consertar os quebrados.
    """
    mapa: Dict[int, str] = {}

    for bloco in _BFRANGE.findall(texto):
        for lo, hi, dst in _FAIXA.findall(bloco):
            inicio, fim, alvo = int(lo, 16), int(hi, 16), _de_utf16(dst)
            if not alvo or fim < inicio or fim - inicio > 0xFFFF:
                continue
            base = ord(alvo[-1])
            for i, codigo in enumerate(range(inicio, fim + 1)):
                mapa[codigo] = alvo[:-1] + chr(base + i)

    for bloco in _BFCHAR.findall(texto):
        for src, dst in _PAR.findall(bloco):
            alvo = _de_utf16(dst)
            if alvo:
                mapa[int(src, 16)] = alvo

    return mapa


def escrever_cmap(mapa: Dict[int, str], ordering: str = "Adobe-Identity-UCS",
                  nome: str = "Adobe-Identity-UCS") -> str:
    """
    O stream ToUnicode inteiro, só com `bfchar`.

    Reescrever tudo, e não remendar o original, porque emenda é ambígua: um
    código definido duas vezes — uma na faixa que já existia, outra no `bfchar`
    novo — tem resultado que o padrão não define, e cada leitor de PDF escolhe
    um. Uma tabela só, sem repetição, não tem essa dúvida.
    """
    linhas = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo",
        "3 dict dup begin",
        "/Registry (Adobe) def",
        f"/Ordering ({ordering}) def",
        "/Supplement 0 def",
        "end def",
        f"/CMapName /{nome} def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]

    itens = sorted((c, t) for c, t in mapa.items() if t)
    # 100 por bloco é o limite do padrão para bfchar.
    for i in range(0, len(itens), 100):
        pedaco = itens[i:i + 100]
        linhas.append(f"{len(pedaco)} beginbfchar")
        linhas += [f"<{c:04X}> <{_para_utf16(t)}>" for c, t in pedaco]
        linhas.append("endbfchar")

    linhas += ["endcmap", "CMapName currentdict /CMap defineresource pop",
               "end", "end", ""]
    return "\n".join(linhas)


def _cabecalho_do_cmap(texto: str) -> Tuple[str, str]:
    ordering = _ORDERING.search(texto)
    nome = _CMAPNAME.search(texto)
    return (ordering.group(1) if ordering else "Adobe-Identity-UCS",
            nome.group(1) if nome else "Adobe-Identity-UCS")


# ----------------------------------------------------------------------
# Onde estão os glifos sem mapa
# ----------------------------------------------------------------------

#: O que vem depois de uma figurina em notação algébrica: coluna, fila ou a
#: captura. "♗e6", "♖f5", "♘xe6", "♕8" — nunca "♔" no meio de uma palavra.
DEPOIS_DE_FIGURINA = frozenset("abcdefgh12345678x")

_LETRAS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _colados(esquerda, direita, folga: float = 0.6) -> bool:
    """
    `direita` encosta em `esquerda`, ou há espaço/coluna entre as duas?

    O vão é medido em alturas de letra, e não em pontos, porque a mesma página
    tem corpo 9 e corpo 12. Isto é o que impede a última letra de uma coluna de
    virar vizinha da primeira da coluna ao lado.
    """
    alto = min(esquerda[3] - esquerda[1], direita[3] - direita[1])
    if alto <= 0:
        return False
    return -alto * 0.2 <= direita[0] - esquerda[2] <= alto * folga


def _linhas_da_pagina(fila):
    """
    Os caracteres da página agrupados em linhas, cada uma na ordem da leitura.

    **A ordem do `get_texttrace` não serve para achar vizinho.** Ele entrega um
    span por troca de fonte, e nestes PDFs a figurina está numa fonte e o `e6`
    que a segue está noutra — os dois saem em spans distantes, e "o próximo da
    fila" acaba sendo um caractere do outro lado da página. Medido: procurando
    vizinho na fila, 110 dos 125 glifos de peça ficavam com o vizinho da direita
    vazio e o filtro de posição derrubava todos.

    **A linha se agrupa pela linha de base, e não pelo centro da caixa.** O
    centro parece equivalente e não é: a caixa de um glifo de figurina é mais
    alta que a de uma letra, então o centro se desloca, e a tolerância que isso
    obriga a usar é larga o bastante para fundir a linha de uma coluna com a da
    coluna vizinha, que tem entrelinha própria. Medido na página 17 do Yusupov,
    três linhas viravam uma só — `'♖a8 2.♘e4t!+-or l.♗b5t ... 2• . x! '` — e a
    figurina acabava ao lado de um caractere que na página está a dez linhas
    dali. A linha de base é exata: `origem` é o mesmo ponto para todo caractere
    de uma linha, independentemente do corpo ou da fonte.
    """
    if not fila:
        return []

    itens = sorted(fila, key=lambda e: (e[4][1], e[3][0]))
    alturas = sorted(e[3][3] - e[3][1] for e in itens)
    altura = alturas[len(alturas) // 2] or 1.0

    linhas, atual, referencia = [], [itens[0]], itens[0][4][1]
    for e in itens[1:]:
        if abs(e[4][1] - referencia) <= altura * 0.2:
            atual.append(e)
        else:
            linhas.append(sorted(atual, key=lambda x: x[3][0]))
            atual, referencia = [e], e[4][1]
    linhas.append(sorted(atual, key=lambda x: x[3][0]))
    return linhas


@dataclass
class Ocorrencia:
    pagina: int
    bbox: Tuple[float, float, float, float]
    antes: str = ""
    depois: str = ""

    @property
    def parece_notacao(self) -> bool:
        """
        Esta ocorrência está onde uma figurina estaria?

        **É o filtro que a imagem pediu.** Sem ele, medido num trecho de 30
        páginas, 5 dos 125 glifos aceitos não eram peça nenhuma: o par `ag` de
        "Zakhodjakin", um `x` itálico, um `n` sujo de trama. O modelo devolveu
        ♔ com 1,00 de confiança para um deles, então nem confiança nem
        concordância separavam — e trocar `ag` por ♔ estragaria a palavra em
        todo o livro.

        O que separa é onde o glifo está: figurina abre um lance e é seguida de
        coluna, fila ou `x`; letra de palavra tem letra dos dois lados.
        """
        return (self.antes not in _LETRAS) and (self.depois in DEPOIS_DE_FIGURINA)


def ocorrencias_por_glifo(doc: fitz.Document,
                          paginas: Optional[Sequence[int]] = None,
                          ) -> Dict[Tuple[str, int], List[Ocorrencia]]:
    """
    {(fonte, glifo) -> onde ele aparece} — todo glifo de texto do documento.

    `get_texttrace` e não `get_text`: é o único que devolve o **número do glifo**
    junto do caractere e da caixa. O número é o que se corrige no ToUnicode; a
    caixa é de onde sai o recorte que diz qual símbolo aquele glifo desenha.
    """
    achados: Dict[Tuple[str, int], List[Ocorrencia]] = defaultdict(list)
    numeros = range(len(doc)) if paginas is None else paginas

    for numero in numeros:
        fila = []
        for span in doc[numero].get_texttrace():
            fonte = span.get("font", "")
            if not fonte:
                continue
            for ch in span.get("chars", []):
                # Glifo negativo é **continuação**, não caractere. Quando a
                # tabela manda um glifo para mais de um caractere — e é o que
                # ela faz aqui, `El` para a torre, `i.` para o bispo, `l2J`
                # para o cavalo —, o `get_texttrace` devolve um item por
                # caractere: o primeiro com o glifo e a caixa de verdade, os
                # demais com glifo -1 e largura zero. Deixá-los na fila põe um
                # fantasma de largura zero entre a figurina e o `g8` que a
                # segue, e foi o que fez o filtro de notação achar que figurina
                # nenhuma tinha vizinho à direita.
                if len(ch) >= 4 and ch[1] >= 0:
                    fila.append((fonte, ch[1],
                                 chr(ch[0]) if 0 <= ch[0] <= 0x10FFFF else "",
                                 tuple(float(v) for v in ch[3]),
                                 tuple(float(v) for v in ch[2])))

        for linha in _linhas_da_pagina(fila):
            for i, (fonte, glifo, _texto, bbox, _origem) in enumerate(linha):
                anterior = linha[i - 1] if i else None
                seguinte = linha[i + 1] if i + 1 < len(linha) else None
                achados[(fonte, glifo)].append(Ocorrencia(
                    numero, bbox,
                    antes=(anterior[2] if anterior
                           and _colados(anterior[3], bbox) else ""),
                    depois=(seguinte[2] if seguinte
                            and _colados(bbox, seguinte[3]) else "")))

    return dict(achados)


def mapas_atuais(doc: fitz.Document) -> Dict[str, Dict[int, str]]:
    """
    {chave da fonte -> {glifo -> texto que ela diz hoje}}, lido do PDF.

    A chave é a de `chave_da_fonte`, e não o nome cru: quem consulta este mapa
    tem em mãos o nome do `get_texttrace`, que não é o mesmo string.
    """
    mapas = {}
    for fonte, xref in _xref_por_fonte(doc).items():
        chave = doc.xref_get_key(xref, "ToUnicode")
        if not chave or chave[0] != "xref":
            continue
        try:
            mapas[fonte] = ler_cmap(
                doc.xref_stream(int(chave[1].split()[0])).decode("latin-1"))
        except Exception:
            continue
    return mapas


# ----------------------------------------------------------------------
# O que cada glifo desenha
# ----------------------------------------------------------------------

@dataclass
class Descoberta:
    """O veredito sobre um (fonte, glifo)."""
    fonte: str
    glifo: int
    atual: str = ""          # o que a tabela do PDF diz hoje
    simbolo: str = ""        # o que o desenho diz
    confianca: float = 0.0
    concordancia: float = 0.0
    notacao: float = 0.0     # fração das ocorrências em posição de figurina
    amostras: int = 0
    ocorrencias: int = 0
    votos: Dict[str, int] = field(default_factory=dict)
    aceita: bool = False
    motivo: str = ""


def _recorte(pagina_cinza: np.ndarray, bbox, escala: float,
             margem: int = 2) -> np.ndarray:
    """O glifo, recortado da página renderizada."""
    altura, largura = pagina_cinza.shape[:2]
    x1 = max(0, int(bbox[0] * escala) - margem)
    y1 = max(0, int(bbox[1] * escala) - margem)
    x2 = min(largura, int(bbox[2] * escala) + margem + 1)
    y2 = min(altura, int(bbox[3] * escala) + margem + 1)
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0), dtype=np.uint8)
    return pagina_cinza[y1:y2, x1:x2]


def _pagina_cinza(page: fitz.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def e_negativo(corte: np.ndarray) -> bool:
    """
    O recorte é claro sobre escuro?

    **Não é zelo, é o erro que apareceu.** Estes livros põem o nome dos
    jogadores em tarja preta, e um recorte branco-sobre-preto entregue ao modelo
    — que só viu preto-sobre-branco — volta com resposta confiante e errada:
    medido, `B.Goldenov` saiu `B.G♔lden♔v` e `L.Shamkovich` saiu `L.Sham♖♔v♖ch`,
    com 100% de concordância nas duas.

    A polaridade se lê na **borda** do recorte, que é fundo quase por definição:
    o miolo é o desenho do caractere e diria o contrário. É a mesma leitura que
    o `negativo.aplicar` faz da tarja inteira (F10), aqui no tamanho de um
    glifo.
    """
    if corte.size == 0 or min(corte.shape[:2]) < 3:
        return False
    borda = np.concatenate([corte[0, :], corte[-1, :], corte[:, 0], corte[:, -1]])
    return float(np.median(borda)) < 128.0


def _decidir(votos: Counter, confiancas: Dict[str, List[float]], atual: str,
             notacao: float, min_amostras: int, min_concordancia: float,
             min_confianca: float, min_notacao: float
             ) -> Tuple[str, float, float, bool, str]:
    """Do apurado, o veredito — e, quando é não, por quê."""
    total = sum(votos.values())
    if not total:
        return "", 0.0, 0.0, False, "nenhum recorte pôde ser classificado"

    simbolo, quantos = votos.most_common(1)[0]
    concordancia = quantos / total
    confianca = sum(confiancas[simbolo]) / len(confiancas[simbolo])

    # A ordem dos testes é a da conversa: primeiro "isto é peça?", que descarta
    # a esmagadora maioria dos glifos de um livro sem gastar mais nenhuma
    # verificação, depois "a tabela já não diz isso?", e só então os limiares.
    if simbolo not in SIMBOLOS_ACEITOS:
        return (simbolo, confianca, concordancia, False,
                f"o mais votado ({simbolo!r}) não é peça de xadrez")
    if atual == simbolo:
        return (simbolo, confianca, concordancia, False,
                "a tabela já diz isso")
    if notacao < min_notacao:
        return (simbolo, confianca, concordancia, False,
                f"só {notacao:.0%} das ocorrências estão em posição de "
                f"figurina, mínimo {min_notacao:.0%}")
    if total < min_amostras:
        return (simbolo, confianca, concordancia, False,
                f"{total} amostra(s), mínimo {min_amostras}")
    if concordancia < min_concordancia:
        return (simbolo, confianca, concordancia, False,
                f"concordância {concordancia:.0%}, mínimo {min_concordancia:.0%}")
    if confianca < min_confianca:
        return (simbolo, confianca, concordancia, False,
                f"confiança {confianca:.2f}, mínimo {min_confianca:.2f}")
    return simbolo, confianca, concordancia, True, ""


#: `sem_mapa` mexe só no que o produtor marcou `U+FFFD`; `tudo` examina todo
#: glifo do documento.
#:
#: **`tudo` é o padrão porque `sem_mapa` não resolve estes livros.** Medido num
#: trecho de 30 páginas do Yusupov: com `sem_mapa`, 266 ocorrências corrigidas e
#: a linha ainda saindo `l2Jd7`, `1Mfe7`, `i.e5` — figurinas cuja tabela não está
#: vazia, está **errada**, mapeada para a sequência de letras com que um OCR leu
#: o desenho. `U+FFFD` é só a metade do estrago que veio confessada.
#:
#: O que segura o `tudo` não é o escopo, é o alvo: `SIMBOLOS_ACEITOS` tem cinco
#: peças, então um glifo de prosa nunca vira candidato — para ser trocado, o
#: modelo tem de dizer "isto é uma torre", e com folga.
ESCOPOS = ("tudo", "sem_mapa")


#: Limiares de aceitação. **Apertados, e por medição.**
#:
#: A primeira passada usava 0,6 de concordância e 0,5 de confiança, e passou
#: limpa no *Chess Evolution 1* — folha de contato das 110 aceitas, nenhum erro.
#: No *Yusupov_Artur_Complete*, que tem 61 fontes de subset em vez de 4, o mesmo
#: ajuste escreveu ♖ onde a página mostra ♔ (`2.♔h1` virou `2.♖h1`, glifo com
#: 0,65 de confiança e 67% de concordância) e aceitou fragmentos de texto —
#: `dx`, `fx`, `cx`, `fa`.
#:
#: **Esses fragmentos são capturas de peão**, e nenhum filtro de posição os
#: separa: `dxc4` tem `.` antes e `x` depois, exatamente como `♖xc4`. Quem
#: separa é a confiança do modelo, e só ela.
#:
#: Custo medido de apertar, no livro de 2.612 páginas: de 85.351 para 82.506
#: ocorrências corrigidas — 3,3% a menos. Em troca, uma amostra visual de 60
#: recortes na faixa aceita saiu sem um erro sequer, contra ~14 em 84 na faixa
#: que ia embora.
CONCORDANCIA_MINIMA = 1.0
CONFIANCA_MINIMA = 0.95


def descobrir(doc: fitz.Document, ocorrencias, atuais, classificar: Callable,
              *, escopo: str = "tudo", dpi: int = 300, max_amostras: int = 6,
              min_amostras: int = 2,
              min_concordancia: float = CONCORDANCIA_MINIMA,
              min_confianca: float = CONFIANCA_MINIMA, min_notacao: float = 0.5,
              progress_callback=None) -> List[Descoberta]:
    """
    Classifica os glifos candidatos e devolve um veredito por (fonte, glifo).

    As amostras são agrupadas por página antes de qualquer coisa ser
    renderizada: um glifo frequente aparece em dezenas de páginas, e renderizar
    a 300 dpi uma vez por amostra seria pagar o custo caro do processo várias
    vezes pela mesma página.
    """
    if escopo not in ESCOPOS:
        raise ValueError(f"escopo inválido: {escopo!r} (use um de {ESCOPOS})")

    escala = dpi / 72.0

    def atual_de(fonte, glifo):
        return atuais.get(chave_da_fonte(fonte), {}).get(glifo, "")

    candidatos = {
        chave: ocs for chave, ocs in ocorrencias.items()
        if escopo == "tudo" or atual_de(*chave) in ("", SEM_MAPA)
    }

    # (fonte, glifo) -> as amostras escolhidas; e o índice inverso por página.
    por_pagina = defaultdict(list)
    for chave, ocs in candidatos.items():
        for o in ocs[:max_amostras]:
            por_pagina[o.pagina].append((chave, o.bbox))

    votos = defaultdict(Counter)
    confiancas = defaultdict(lambda: defaultdict(list))

    for i, numero in enumerate(sorted(por_pagina)):
        if progress_callback:
            progress_callback(i, len(por_pagina))
        cinza = _pagina_cinza(doc[numero], dpi)
        for chave, bbox in por_pagina[numero]:
            corte = _recorte(cinza, bbox, escala)
            # Recorte de tarja é descartado, e não invertido: figurina de
            # notação não mora dentro de tarja preta — lá só há nome de jogador
            # —, então jogar a amostra fora não custa nada e tira do caminho a
            # única família de erro confiante que a medição encontrou.
            if corte.size == 0 or e_negativo(corte):
                continue
            simbolo, confianca = classificar(corte)
            if not simbolo:
                continue
            votos[chave][simbolo] += 1
            confiancas[chave][simbolo].append(float(confianca))

    if progress_callback:
        progress_callback(len(por_pagina), len(por_pagina))

    resultado = []
    for chave in sorted(candidatos):
        fonte, glifo = chave
        atual = atual_de(fonte, glifo)
        ocs = candidatos[chave]
        # Sobre **todas** as ocorrências, não só as amostradas: ler o vizinho é
        # de graça — já veio no texttrace —, e quanto mais ocorrências entram na
        # conta, menos ela depende de quais seis foram sorteadas.
        notacao = sum(1 for o in ocs if o.parece_notacao) / len(ocs)
        simbolo, conf, conc, aceita, motivo = _decidir(
            votos[chave], confiancas[chave], atual, notacao,
            min_amostras, min_concordancia, min_confianca, min_notacao)
        resultado.append(Descoberta(
            fonte=fonte, glifo=glifo, atual=atual, simbolo=simbolo,
            confianca=conf, concordancia=conc, notacao=notacao,
            amostras=sum(votos[chave].values()),
            ocorrencias=len(ocs), votos=dict(votos[chave]),
            aceita=aceita, motivo=motivo))
    return resultado


# ----------------------------------------------------------------------
# Escrever a tabela corrigida
# ----------------------------------------------------------------------

#: Palavras de estilo que um lado do PyMuPDF traz e o outro não.
_ESTILOS = ("regular", "roman", "book", "bold", "italic", "oblique",
            "medium", "light")


def chave_da_fonte(nome: str) -> str:
    """
    A forma comparável de um nome de fonte.

    **Os dois lados do PyMuPDF nomeiam a mesma fonte diferente**, e sem
    normalizar os dois a descoberta acha os glifos e o `aplicar` não acha a
    tabela de nenhum deles:

        get_texttrace   `SegoeUISymbol`     `Fd350139`
        get_fonts       `Segoe UI Symbol Regular`   `Fd350139-Identity-H`
    """
    limpo = nome.split("+", 1)[-1]          # prefixo de subset ABCDEF+
    for sufixo in ("-Identity-H", "-Identity-V", "-UCS2"):
        if limpo.endswith(sufixo):
            limpo = limpo[:-len(sufixo)]
            break
    limpo = "".join(c for c in limpo if c.isalnum()).lower()
    for estilo in _ESTILOS:
        if limpo.endswith(estilo) and len(limpo) > len(estilo):
            return limpo[:-len(estilo)]
    return limpo


def _xref_por_fonte(doc: fitz.Document) -> Dict[str, int]:
    """
    {chave da fonte -> xref}. Chave repetida em dois xrefs é recusada.

    O xref é onde mora a tabela. Se a mesma fonte aparecesse em dois objetos
    diferentes, nada garante que os dois numerem os glifos igual, e corrigir
    pelo nome escreveria o símbolo certo no glifo errado. Recusar é o único
    desfecho seguro — e nos três livros do projeto isso não acontece: 30, 26 e
    73 fontes, um xref cada.
    """
    vistos = defaultdict(set)
    for pagina in doc:
        for xref, _nome, _tipo, base, *_ in pagina.get_fonts(full=True):
            vistos[chave_da_fonte(base)].add(xref)
    return {nome: xrefs.pop() for nome, xrefs in vistos.items() if len(xrefs) == 1}


def aplicar(doc: fitz.Document, descobertas: Sequence[Descoberta]) -> List[str]:
    """
    Reescreve o ToUnicode das fontes com descoberta aceita. Devolve os avisos.

    Só a tabela é tocada: nenhum operador de desenho da página muda, e por isso
    o PDF de saída renderiza igual ao original.
    """
    avisos = []
    porfonte = defaultdict(list)
    for d in descobertas:
        if d.aceita:
            porfonte[d.fonte].append(d)

    xrefs = _xref_por_fonte(doc)
    for fonte, itens in sorted(porfonte.items()):
        xref = xrefs.get(chave_da_fonte(fonte))
        if xref is None:
            avisos.append(f"{fonte}: fonte não encontrada, ou com mais de um "
                          f"objeto de fonte — {len(itens)} glifo(s) não corrigidos")
            continue

        chave = doc.xref_get_key(xref, "ToUnicode")
        if not chave or chave[0] != "xref":
            avisos.append(f"{fonte}: sem tabela ToUnicode — "
                          f"{len(itens)} glifo(s) não corrigidos")
            continue

        tu = int(chave[1].split()[0])
        try:
            original = doc.xref_stream(tu).decode("latin-1")
        except Exception as e:
            avisos.append(f"{fonte}: tabela ilegível ({e})")
            continue

        mapa = ler_cmap(original)
        if not mapa:
            avisos.append(f"{fonte}: tabela vazia ou em formato desconhecido")
            continue

        for d in itens:
            mapa[d.glifo] = d.simbolo
        ordering, nome = _cabecalho_do_cmap(original)
        doc.update_stream(tu, escrever_cmap(mapa, ordering, nome).encode("latin-1"))

    return avisos


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------

COLUNAS_CSV = ["fonte", "glifo", "atual", "simbolo", "confianca", "concordancia",
               "notacao", "amostras", "ocorrencias", "votos", "aceita", "motivo"]


def relevantes(descobertas: Sequence[Descoberta]) -> List[Descoberta]:
    """
    O que merece uma linha no relatório.

    Com `escopo="tudo"` o veredito cobre **todo** glifo do documento — milhares
    de linhas em que a resposta é "isto é a letra 'a'". Ficam as que dizem
    alguma coisa: a troca feita, e a que quase foi feita e não passou nos
    limiares — que é o que alguém revisando precisa ver para afrouxá-los ou não.
    """
    return [d for d in descobertas
            if d.aceita or (d.simbolo in SIMBOLOS_ACEITOS
                            and d.motivo != "a tabela já diz isso")]


@dataclass
class RelatorioMapa:
    arquivo_entrada: str = ""
    arquivo_saida: str = ""
    dry_run: bool = False
    escopo: str = "tudo"
    total_paginas: int = 0
    glifos_examinados: int = 0
    descobertas: List[Descoberta] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def aceitas(self) -> List[Descoberta]:
        return [d for d in self.descobertas if d.aceita]

    @property
    def recusadas(self) -> List[Descoberta]:
        return [d for d in self.descobertas if not d.aceita]

    @property
    def ocorrencias_corrigidas(self) -> int:
        return sum(d.ocorrencias for d in self.aceitas)

    @property
    def ocorrencias_pendentes(self) -> int:
        return sum(d.ocorrencias for d in self.recusadas)

    def por_simbolo(self) -> Dict[str, int]:
        conta = Counter()
        for d in self.aceitas:
            conta[d.simbolo] += d.ocorrencias
        return dict(sorted(conta.items()))

    def resumo(self) -> str:
        modo = "SIMULAÇÃO (nada foi gravado)" if self.dry_run else "correção"
        linhas = [f"{modo}: {self.total_paginas} página(s), "
                  f"{self.glifos_examinados} glifo(s) examinados"]

        if not self.glifos_examinados:
            linhas.append("ATENÇÃO: o documento não tem texto com glifos "
                          "identificáveis — não há tabela a corrigir")
            return "; ".join(linhas)

        linhas.append(f"{len(self.aceitas)} figurina(s) corrigida(s), "
                      f"{self.ocorrencias_corrigidas} ocorrência(s) no texto")
        if self.por_simbolo():
            linhas.append(" ".join(f"{s}×{n}" for s, n in self.por_simbolo().items()))
        if self.recusadas:
            linhas.append(f"{len(self.recusadas)} candidata(s) recusada(s) "
                          f"por votação fraca")
        if not self.aceitas:
            linhas.append("ATENÇÃO: nenhuma figurina foi identificada — nada mudou")
        return "; ".join(linhas)


def caminhos_do_relatorio(saida_pdf: str, dry_run: bool = False) -> Tuple[str, str]:
    base = os.path.splitext(saida_pdf)[0]
    sufixo = "_mapa_simulacao" if dry_run else "_mapa"
    return base + sufixo + ".json", base + sufixo + ".csv"


def gravar(saida_pdf: str, rel: RelatorioMapa) -> Tuple[str, str]:
    cj, cc = caminhos_do_relatorio(saida_pdf, rel.dry_run)
    pasta = os.path.dirname(os.path.abspath(cj))
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    with open(cj, "w", encoding="utf-8") as f:
        json.dump({
            "arquivo_entrada": rel.arquivo_entrada,
            "arquivo_saida": rel.arquivo_saida,
            "dry_run": rel.dry_run,
            "escopo": rel.escopo,
            "total_paginas": rel.total_paginas,
            "glifos_examinados": rel.glifos_examinados,
            "corrigidos": len(rel.aceitas),
            "ocorrencias_corrigidas": rel.ocorrencias_corrigidas,
            "ocorrencias_pendentes": rel.ocorrencias_pendentes,
            "por_simbolo": rel.por_simbolo(),
            "avisos": rel.avisos,
            "descobertas": [asdict(d) for d in rel.descobertas],
        }, f, ensure_ascii=False, indent=1)

    # utf-8-sig pelo mesmo motivo do relatório da F2.3: sem BOM o Excel do
    # Windows lê como cp1252 e os símbolos de peça viram lixo.
    with open(cc, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV)
        escritor.writeheader()
        for d in rel.descobertas:
            escritor.writerow({
                "fonte": d.fonte, "glifo": d.glifo, "atual": d.atual,
                "simbolo": d.simbolo, "confianca": round(d.confianca, 4),
                "concordancia": round(d.concordancia, 4),
                "notacao": round(d.notacao, 4),
                "amostras": d.amostras, "ocorrencias": d.ocorrencias,
                "votos": " ".join(f"{k}={v}" for k, v in sorted(d.votos.items())),
                "aceita": int(d.aceita), "motivo": d.motivo,
            })
    return cj, cc


# ----------------------------------------------------------------------
# A operação inteira
# ----------------------------------------------------------------------

def mesmo_arquivo(a: str, b: str) -> bool:
    """Dois caminhos apontam para o mesmo arquivo no disco?"""
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
        os.path.realpath(b))


def corrigir_mapeamento(input_pdf: str, output_pdf: str, *,
                        classificar: Callable, escopo: str = "tudo",
                        dpi: int = 300, max_amostras: int = 6,
                        min_amostras: int = 2,
                        min_concordancia: float = CONCORDANCIA_MINIMA,
                        min_confianca: float = CONFIANCA_MINIMA,
                        min_notacao: float = 0.5,
                        dry_run: bool = False, gravar_relatorio: bool = True,
                        progress_callback=None) -> RelatorioMapa:
    """
    Escreve em `output_pdf` uma cópia de `input_pdf` com o ToUnicode corrigido.

    O original **nunca é aberto para escrita**: o documento é modificado em
    memória e gravado noutro caminho. Com `dry_run=True` nem isso — a descoberta
    roda inteira e o relatório sai igual, sem nenhum PDF ser gravado.

    `classificar(recorte_cinza) -> (simbolo, confiança)`.
    """
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")
    if not dry_run and mesmo_arquivo(input_pdf, output_pdf):
        # A alternativa é o PyMuPDF recusar com "save to original must be
        # incremental" já no fim do trabalho, e o ponto desta operação é
        # justamente sair com uma cópia e o original intacto.
        raise MapeamentoInvalido(
            "o arquivo de saída é o próprio original.\n"
            "Escolha outro nome: a correção grava uma cópia e não altera a entrada.")

    doc = fitz.open(input_pdf)
    rel = RelatorioMapa(arquivo_entrada=input_pdf,
                        arquivo_saida="" if dry_run else output_pdf,
                        dry_run=dry_run, escopo=escopo, total_paginas=len(doc))
    try:
        vereditos = descobrir(
            doc, ocorrencias_por_glifo(doc), mapas_atuais(doc), classificar,
            escopo=escopo, dpi=dpi, max_amostras=max_amostras,
            min_amostras=min_amostras, min_concordancia=min_concordancia,
            min_confianca=min_confianca, min_notacao=min_notacao,
            progress_callback=progress_callback)
        rel.glifos_examinados = len(vereditos)
        rel.descobertas = relevantes(vereditos)

        if not dry_run:
            rel.avisos = aplicar(doc, rel.descobertas)
            doc.save(output_pdf, garbage=3, deflate=True)
    finally:
        doc.close()

    if gravar_relatorio and output_pdf:
        gravar(output_pdf, rel)
    return rel
