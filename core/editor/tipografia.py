"""
Tipografia (ED-06b; SPEC_EDITOR §8.14): aspas curvas por idioma, reticências, travessão
em intervalos e resultados, espaço inseparável entre número e lance e depois de
"Diagrama", hífen inseparável no roque — com as exceções de xadrez —, "Juntar palavras
hifenizadas" e a hifenização (`FormatoDePagina.hifenizar` → `hyphens: auto` na folha).

## Propor, e só depois aplicar

Nada aqui muda o texto por conta própria: `propor` devolve `Troca`s (posição, o que sai,
o que entra, o motivo) sobre o texto de um alvo (`busca.Alvo`), e é a caixa "Tipografia…"
que mostra cada uma com o contexto e deixa desmarcar (prévia por ocorrência). `aplicar`
faz as trocas de trás para a frente, num capítulo fechado pelo modelo (um ponto de
desfazer por capítulo, como a busca) e no aberto pelo widget.

## As exceções de xadrez

`O-O`, `O-O-O`, `0-0` e `0-0-0` são roques e levam hífen **inseparável** (U+2011), nunca
travessão; `+-` e `-+` são NAGs e ficam como estão; `1-0`, `0-1`, `½-½` e `1/2-1/2` são
resultados e levam meia-risca (U+2013), como um intervalo `1990–1995`. O espaço entre o
número do lance e o lance (`12.Nf3` → `12.`+NBSP+`Nf3`, `12. Nf3` idem) só entra quando o
que segue tem cara de lance — `2012. Now` não é lance.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Sequence

from core.editor import busca, modelo, ortografia
from core.editor.busca import Alvo, Ocorrencia
from core.editor.modelo import Capitulo, Livro, Paragrafo

NBSP = chr(0xA0)
HIFEN_INSEPARAVEL = chr(0x2011)
MEIA_RISCA = chr(0x2013)
TRAVESSAO = chr(0x2014)
RETICENCIAS = chr(0x2026)
#: `(abre duplas, fecha duplas, abre simples, fecha simples)` por idioma.
ASPAS = {
    "pt": ("“", "”", "‘", "’"), "en": ("“", "”", "‘", "’"),
    "es": ("“", "”", "‘", "’"), "it": ("“", "”", "‘", "’"),
    "de": ("„", "“", "‚", "‘"),
    "fr": ("«" + NBSP, NBSP + "»", "‹" + NBSP, NBSP + "›"),
}
REGRAS = ("aspas", "reticencias", "travessao", "roque", "espaco_lance", "espaco_rotulo")
ROTULOS_DAS_REGRAS = {"aspas": "aspas curvas", "reticencias": "reticências", "travessao": "meia-risca e travessão",
                      "roque": "hífen inseparável no roque", "espaco_lance": "espaço inseparável antes do lance",
                      "espaco_rotulo": "espaço inseparável depois de Diagrama/Figura/Tabela"}
_ABRE_ANTES = " \t\n([{—–-/«“‘"
_RE_ASPA = re.compile(r"[\"']")
_RE_RETICENCIAS = re.compile(r"(?<!\.)\.\.\.(?!\.)")
_RE_ROQUE = re.compile(r"(?<![\w-])([O0])-([O0])(?:-([O0]))?(?![\w-])")
_RE_RESULTADO = re.compile(r"(?<![\w½/])(1-0|0-1|½-½|1/2-1/2)(?![\w½/])")
_RE_INTERVALO = re.compile(r"(?<![\w-])(\d+)-(\d+)(?![\w-])")
_RE_HIFEN_ESPACADO = re.compile(r"(?<=\S) - (?=\S)")
_LANCE = r"(?:[KQRBN♔♕♖♗♘]?[a-h]?[1-8]?x?[a-h][1-8]|[O0]-[O0])"
_RE_NUMERO_E_LANCE = re.compile(r"(?<![\w.])(\d{1,3}\.(?:\.\.)?)([ " + NBSP + r"]?)(?=" + _LANCE + r"(?![\w]))")
_RE_ROTULO = re.compile(r"\b(Diagramas?|Figuras?|Tabelas?|Cap[ií]tulos?|P[áa]ginas?|Partidas?|Lances?|Diagrams?|"
                        r"Figures?|Tables?|Chapters?|Pages?|Games?|Moves?)( )(\d+)\b")
MARCA_DA_HIFENIZACAO = "/* pybox:hifenizar */"
FIM_DA_HIFENIZACAO = "/* /pybox:hifenizar */"
REGRA_DA_HIFENIZACAO = (f"{MARCA_DA_HIFENIZACAO}\np {{ hyphens: auto; -webkit-hyphens: auto; -epub-hyphens: auto; }}\n"
                        f"{FIM_DA_HIFENIZACAO}\n")


@dataclass
class Troca:
    ini: int
    fim: int
    de: str
    para: str
    motivo: str

    def contexto(self, texto: str, folga: int = 24) -> tuple[str, str]:
        """`(antes, depois)`: o trecho em volta, como está e como fica."""
        a, b = max(0, self.ini - folga), min(len(texto), self.fim + folga)
        antes = texto[a:b]
        depois = texto[a:self.ini] + self.para + texto[self.fim:b]
        return antes.replace("\n", "⏎"), depois.replace("\n", "⏎")


def _aspas(texto: str, idioma: str) -> list[Troca]:
    abre_d, fecha_d, abre_s, fecha_s = ASPAS.get((idioma or "pt").split("-")[0].lower(), ASPAS["pt"])
    saida: list[Troca] = []
    for m in _RE_ASPA.finditer(texto):
        i = m.start()
        anterior = texto[i - 1] if i > 0 else " "
        seguinte = texto[i + 1] if i + 1 < len(texto) else " "
        if m.group(0) == '"':
            abre = anterior in _ABRE_ANTES
            saida.append(Troca(i, i + 1, '"', abre_d if abre else fecha_d, "aspas"))
            continue
        if anterior.isalpha() and seguinte.isalpha():
            saida.append(Troca(i, i + 1, "'", "’", "aspas"))           # o apóstrofo: Black's
        elif anterior in _ABRE_ANTES and not seguinte.isspace():
            saida.append(Troca(i, i + 1, "'", abre_s, "aspas"))
        else:
            saida.append(Troca(i, i + 1, "'", fecha_s, "aspas"))
    return saida


def _reticencias(texto: str) -> list[Troca]:
    return [Troca(m.start(), m.end(), "...", RETICENCIAS, "reticencias") for m in _RE_RETICENCIAS.finditer(texto)]


def _roques(texto: str) -> list[Troca]:
    saida = []
    for m in _RE_ROQUE.finditer(texto):
        de = m.group(0)
        para = de.replace("-", HIFEN_INSEPARAVEL)
        if para != de:
            saida.append(Troca(m.start(), m.end(), de, para, "roque"))
    return saida


def _travessoes(texto: str) -> list[Troca]:
    saida = []
    for m in _RE_RESULTADO.finditer(texto):
        saida.append(Troca(m.start(), m.end(), m.group(0), m.group(0).replace("-", MEIA_RISCA), "travessao"))
    for m in _RE_INTERVALO.finditer(texto):
        if _RE_ROQUE.fullmatch(m.group(0)):
            continue
        saida.append(Troca(m.start(), m.end(), m.group(0), f"{m.group(1)}{MEIA_RISCA}{m.group(2)}", "travessao"))
    for m in _RE_HIFEN_ESPACADO.finditer(texto):
        saida.append(Troca(m.start(), m.end(), " - ", f" {MEIA_RISCA} ", "travessao"))
    return saida


def _espaco_no_lance(texto: str) -> list[Troca]:
    saida = []
    for m in _RE_NUMERO_E_LANCE.finditer(texto):
        if m.group(2) == NBSP:
            continue
        saida.append(Troca(m.start(), m.end(), m.group(0), m.group(1) + NBSP, "espaco_lance"))
    return saida


def _espaco_no_rotulo(texto: str) -> list[Troca]:
    return [Troca(m.start(2), m.end(2), " ", NBSP, "espaco_rotulo") for m in _RE_ROTULO.finditer(texto)]


def propor(texto: str, idioma: str = "pt", regras: Sequence[str] = REGRAS) -> list[Troca]:
    """As trocas propostas para `texto`, em ordem de posição, sem sobreposição (a primeira vence)."""
    ativas = set(regras)
    candidatas: list[Troca] = []
    if "roque" in ativas:
        candidatas += _roques(texto)
    if "travessao" in ativas:
        candidatas += _travessoes(texto)
    if "aspas" in ativas:
        candidatas += _aspas(texto, idioma)
    if "reticencias" in ativas:
        candidatas += _reticencias(texto)
    if "espaco_lance" in ativas:
        candidatas += _espaco_no_lance(texto)
    if "espaco_rotulo" in ativas:
        candidatas += _espaco_no_rotulo(texto)
    candidatas.sort(key=lambda t: (t.ini, t.fim))
    saida: list[Troca] = []
    fim_anterior = -1
    for t in candidatas:
        if t.ini < fim_anterior or t.de == t.para:
            continue
        saida.append(t)
        fim_anterior = t.fim
    return saida


def aplicar(texto: str, trocas: Sequence[Troca]) -> str:
    """O texto com as trocas feitas (elas não podem se sobrepor)."""
    partes: list[str] = []
    andado = 0
    for t in sorted(trocas, key=lambda t: t.ini):
        partes.append(texto[andado:t.ini])
        partes.append(t.para)
        andado = t.fim
    partes.append(texto[andado:])
    return "".join(partes)


# ----------------------------------------------------------------------
# No capítulo
# ----------------------------------------------------------------------

def _fora_do_texto(cap: Capitulo, alvo: Alvo, troca: Troca) -> bool:
    """A troca cai em código ou ilha (que a tipografia não toca)?"""
    paragrafo = busca.paragrafo_do_alvo(cap, alvo)
    if paragrafo is None:
        return False
    for ini, fim, trecho in ortografia.mapa_de_formato(paragrafo):
        if ini < troca.fim and troca.ini < fim and (trecho.codigo or trecho.ilha):
            return True
    return False


def propor_capitulo(cap: Capitulo, idioma: str = "", regras: Sequence[str] = REGRAS) -> list[tuple[Alvo, Troca]]:
    """As propostas do capítulo inteiro, alvo a alvo (nada num capítulo só em `texto_cru`)."""
    if cap.texto_cru is not None:
        return []
    idioma = cap.idioma or idioma or "pt"
    saida: list[tuple[Alvo, Troca]] = []
    for alvo in busca.alvos_do_capitulo(cap):
        for troca in propor(alvo.texto, idioma, regras):
            if not _fora_do_texto(cap, alvo, troca):
                saida.append((alvo, troca))
    return saida


def propor_livro(livro: Livro, regras: Sequence[str] = REGRAS) -> dict[str, list[tuple[Alvo, Troca]]]:
    saida = {}
    for cap in livro.capitulos:
        propostas = propor_capitulo(cap, livro.metadados.idioma, regras)
        if propostas:
            saida[cap.arquivo] = propostas
    return saida


def aplicar_no_capitulo(cap: Capitulo, pares: Sequence[tuple[Alvo, Troca]], historico: Any = None,
                        rotulo: str = "tipografia") -> int:
    """
    As trocas no modelo do capítulo fechado, de trás para a frente por alvo; **um** ponto
    de desfazer por capítulo, com os blocos e as notas tocados. Devolve quantas fez.
    """
    if not pares:
        return 0
    antes: dict[str, Any] = {}
    depois: dict[str, Any] = {}
    indices: dict[str, int] = {}
    feitas = 0
    ordenados = sorted(pares, key=lambda par: (par[0].indice, par[1].ini), reverse=True)
    for alvo, troca in ordenados:
        ocorrencia = Ocorrencia(cap.arquivo, troca.ini, troca.fim, troca.de, alvo)
        if alvo.caminho[0] == "nota":
            nota = cap.nota(alvo.caminho[1])
            if nota is None:
                continue
            antes.setdefault(nota.id, copy.deepcopy(nota))
            indices.setdefault(nota.id, cap.notas.index(nota))
            nova = busca.nota_substituida(cap, ocorrencia, troca.para)
            cap.notas[cap.notas.index(nota)] = nova
            depois[nota.id] = nova
        else:
            bloco = cap.bloco(alvo.bloco_id)
            if bloco is None:
                continue
            antes.setdefault(bloco.id, copy.deepcopy(bloco))
            indices.setdefault(bloco.id, cap.blocos.index(bloco))
            novo = busca.bloco_substituido(cap, ocorrencia, troca.para)
            cap.blocos[cap.blocos.index(bloco)] = novo
            depois[bloco.id] = novo
        feitas += 1
    if historico is not None and antes:
        ids = list(antes)
        historico.ponto(cap.arquivo, ids, [antes[i] for i in ids], [depois[i] for i in ids], rotulo=rotulo,
                        indices=indices)
    return feitas


# ----------------------------------------------------------------------
# Juntar palavras hifenizadas (§8.14, `lexico.juntar_hifenizadas`)
# ----------------------------------------------------------------------

_RE_QUEBRA_COM_HIFEN = re.compile(r"([^\W\d_]+)([-‐‑])\n\s*([^\W\d_]+)")
_RE_FIM_COM_HIFEN = re.compile(r"([^\W\d_]+)([-‐‑])$")
_RE_COMECO = re.compile(r"^([^\W\d_]+)( ?)")


def propor_juncoes(cap: Capitulo, lex: Any) -> list[tuple[Alvo, Troca]]:
    """
    As palavras partidas por hífen no fim de uma linha — numa quebra suave dentro do
    parágrafo, ou entre um parágrafo e o seguinte — que `lexico.juntar_hifenizadas`
    aceita remontar. Entre parágrafos saem duas trocas: a do fim do primeiro (a palavra
    inteira) e a do começo do segundo (o pedaço que sobe, com o espaço).
    """
    from core import lexico

    if cap.texto_cru is not None or lex is None or getattr(lex, "vazio", True):
        return []
    saida: list[tuple[Alvo, Troca]] = []
    alvos = busca.alvos_do_capitulo(cap)
    for alvo in alvos:
        for m in _RE_QUEBRA_COM_HIFEN.finditer(alvo.texto):
            juncoes = lexico.juntar_hifenizadas([[m.group(1) + m.group(2)], [m.group(3)]], lex)
            if juncoes:
                saida.append((alvo, Troca(m.start(), m.end(), m.group(0), juncoes[0].texto, "juncao")))
    de_cima = [a for a in alvos if a.caminho == ("bloco",) and isinstance(cap.bloco(a.bloco_id), Paragrafo)]
    for atual, seguinte in zip(de_cima, de_cima[1:]):
        m1 = _RE_FIM_COM_HIFEN.search(atual.texto)
        m2 = _RE_COMECO.match(seguinte.texto)
        if not m1 or not m2:
            continue
        juncoes = lexico.juntar_hifenizadas([[m1.group(0)], [m2.group(1)]], lex)
        if not juncoes:
            continue
        saida.append((atual, Troca(m1.start(), m1.end(), m1.group(0), juncoes[0].texto, "juncao")))
        saida.append((seguinte, Troca(0, m2.end(), m2.group(0), "", "juncao")))
    return saida


# ----------------------------------------------------------------------
# Hifenização na folha padrão
# ----------------------------------------------------------------------

def folha_com_hifenizacao(css: str, ligar: bool) -> str:
    """A folha com o bloco marcado `pybox:hifenizar` posto (ou tirado), sem tocar no resto."""
    ini = css.find(MARCA_DA_HIFENIZACAO)
    if ini != -1:
        fim = css.find(FIM_DA_HIFENIZACAO, ini)
        fim = len(css) if fim == -1 else fim + len(FIM_DA_HIFENIZACAO)
        if fim < len(css) and css[fim] == "\n":
            fim += 1
        css = css[:ini] + css[fim:]
    if not ligar:
        return css
    if css and not css.endswith("\n"):
        css += "\n"
    return css + REGRA_DA_HIFENIZACAO


def aplicar_hifenizacao(livro: Livro, ler_recurso: Any = None) -> bool:
    """
    `FormatoDePagina.hifenizar` → `hyphens: auto` na folha padrão do livro (e o DOCX e o
    PDF leem o mesmo campo). `ler_recurso(recurso) -> str` lê a folha que ainda está no
    zip. Devolve se a folha mudou.
    """
    if not livro.folhas:
        return False
    recurso = livro.recurso(livro.folhas[0])
    if recurso is None:
        return False
    if recurso.texto_cru is not None:
        atual = recurso.texto_cru
    elif ler_recurso is not None:
        atual = ler_recurso(recurso)
    elif recurso.dados is not None:
        atual = recurso.dados.decode("utf-8", errors="replace")
    else:
        return False
    nova = folha_com_hifenizacao(atual, livro.pagina.hifenizar)
    if nova == atual:
        return False
    recurso.texto_cru = nova
    return True


def texto_de(bloco: Any) -> str:
    return modelo.texto_de(bloco)


__all__ = ["Troca", "REGRAS", "ROTULOS_DAS_REGRAS", "ASPAS", "NBSP", "HIFEN_INSEPARAVEL", "MEIA_RISCA", "TRAVESSAO",
           "RETICENCIAS", "propor", "aplicar", "propor_capitulo", "propor_livro", "aplicar_no_capitulo",
           "propor_juncoes", "folha_com_hifenizacao", "aplicar_hifenizacao", "REGRA_DA_HIFENIZACAO"]
