"""
A CSS que o modo texto lê (SPEC_EDITOR §6.4) — e só ela.

Não é um motor CSS e não pretende ser. Lê seletores de **elemento**, **classe** e
**elemento.classe** (com uma ou mais classes), e só as propriedades que a tela
sabe desenhar: peso, itálico, versalete, corpo, família, alinhamento, recuo,
margens, entrelinha, cor, fundo, sublinhado, borda (presença). `@font-face` é lido
para mapear família → arquivo. Tudo o mais — `@media`, `@import`, `p > span.x`,
`:first-child`, `!important` (tolerado, e tratado como normal) — é **pulado sem
perder**: `escrever` só substitui as regras que o editor tocou e devolve o resto
do texto byte a byte, comentários incluídos.

**Por que não uma biblioteca.** `tinycss2` daria um parser completo por uma
dependência nova para ler dezesseis propriedades; a política do projeto
(`requirements.txt`) recusa a troca. O que este módulo perde em cobertura ele
declara: `Folha.ignoradas` lista o que pulou.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

PROPRIEDADES = frozenset({
    "font-weight", "font-style", "font-variant", "font-size", "font-family", "text-align",
    "text-indent", "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "line-height", "color", "background-color", "background", "text-decoration", "border",
    "border-top", "border-bottom", "border-left", "border-right",
})

_RE_SELETOR = re.compile(r"^(?P<el>[a-zA-Z][\w-]*)?(?P<classes>(?:\.[\w-]+)+)?$")
_RE_COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
_RE_FAMILIA = re.compile(r"font-family\s*:\s*([^;]+)", re.I)
_RE_SRC = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)


@dataclass
class Regra:
    """Uma regra simples: seletor, declarações, e onde ela mora no texto original."""

    seletor: str
    elemento: str
    classes: tuple[str, ...]
    declaracoes: dict[str, str]
    inicio: int = 0
    fim: int = 0
    modificada: bool = False
    #: Vazio quando a regra veio do texto; o nome da folha quando é de `cascata`.
    origem: str = ""


@dataclass
class FonteFace:
    familia: str
    arquivo: str


@dataclass
class Folha:
    regras: list[Regra] = field(default_factory=list)
    fontes: list[FonteFace] = field(default_factory=list)
    ignoradas: list[str] = field(default_factory=list)
    texto: str = ""
    novas: list[Regra] = field(default_factory=list)

    def estilo_de(self, elemento: str, classes: Iterable[str] = ()) -> dict[str, str]:
        """
        A cascata para `<elemento class="…">`: regras de elemento, depois de classe,
        depois de elemento.classe, cada grupo na ordem do texto — a última vence.
        """
        classes = set(classes)
        por_peso: list[tuple[int, int, Regra]] = []
        for i, regra in enumerate(self.regras + self.novas):
            if regra.elemento and regra.elemento != elemento:
                continue
            if regra.classes and not set(regra.classes) <= classes:
                continue
            peso = (1 if regra.elemento else 0) + 10 * len(regra.classes)
            por_peso.append((peso, i, regra))
        saida: dict[str, str] = {}
        for _peso, _i, regra in sorted(por_peso, key=lambda item: (item[0], item[1])):
            saida.update(regra.declaracoes)
        return saida

    def regra(self, seletor: str) -> Regra | None:
        """A **última** regra deste seletor — a que vence na cascata, e a que se edita."""
        seletor = seletor.strip()
        for regra in reversed(self.regras + self.novas):
            if regra.seletor == seletor:
                return regra
        return None

    def definir(self, seletor: str, **declaracoes: str) -> Regra:
        """Cria ou altera a regra de `seletor`; é o que o painel Estilos chama."""
        regra = self.regra(seletor)
        if regra is None:
            casamento = _RE_SELETOR.match(seletor.strip())
            if not casamento:
                raise ValueError(f"seletor fora da CSS mínima: {seletor!r}")
            regra = Regra(seletor.strip(), casamento.group("el") or "",
                          tuple(c for c in (casamento.group("classes") or "").split(".") if c), {})
            self.novas.append(regra)
        regra.declaracoes.update({k.replace("_", "-"): v for k, v in declaracoes.items()})
        regra.modificada = True
        return regra

    def familia_da_fonte(self, familia: str) -> str | None:
        familia = familia.strip().strip("\"'")
        for fonte in self.fontes:
            if fonte.familia == familia:
                return fonte.arquivo
        return None


def _sem_comentarios(css: str) -> str:
    """O texto com os comentários trocados por espaços — os deslocamentos não mudam."""
    return _RE_COMENTARIO.sub(lambda m: " " * len(m.group(0)), css)


def _fim_do_bloco(texto: str, abre: int) -> int:
    """O índice do `}` que fecha o `{` em `abre`, respeitando blocos aninhados."""
    nivel = 0
    for i in range(abre, len(texto)):
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return i
    return len(texto) - 1


def _declaracoes(miolo: str) -> dict[str, str]:
    saida: dict[str, str] = {}
    for parte in miolo.split(";"):
        if ":" not in parte:
            continue
        nome, _, valor = parte.partition(":")
        nome = nome.strip().lower()
        valor = valor.strip()
        if valor.lower().endswith("!important"):
            valor = valor[:-len("!important")].strip()
        if nome in PROPRIEDADES and valor:
            saida[nome] = valor
    return saida


def ler(css: str) -> Folha:
    """As regras que a tela sabe usar, com o resto listado em `ignoradas`."""
    folha = Folha(texto=css)
    limpo = _sem_comentarios(css)
    i = 0
    n = len(limpo)
    while i < n:
        if limpo[i].isspace():
            i += 1
            continue
        if limpo[i] == "@":
            fim_da_linha = limpo.find(";", i)
            abre = limpo.find("{", i)
            if abre == -1 or (fim_da_linha != -1 and fim_da_linha < abre):
                # `@import …;`, `@charset …;`
                fim = fim_da_linha if fim_da_linha != -1 else n - 1
                folha.ignoradas.append(limpo[i:fim + 1].strip())
                i = fim + 1
                continue
            fecha = _fim_do_bloco(limpo, abre)
            cabeca = limpo[i:abre].strip()
            if cabeca.lower().startswith("@font-face"):
                miolo = limpo[abre + 1:fecha]
                familia = _RE_FAMILIA.search(miolo)
                src = _RE_SRC.search(miolo)
                if familia and src:
                    folha.fontes.append(FonteFace(familia.group(1).strip().strip("\"'"), src.group(1).strip()))
            else:
                folha.ignoradas.append(cabeca)
            i = fecha + 1
            continue
        abre = limpo.find("{", i)
        if abre == -1:
            break
        fecha = _fim_do_bloco(limpo, abre)
        seletores = limpo[i:abre]
        declaracoes = _declaracoes(limpo[abre + 1:fecha])
        for seletor in seletores.split(","):
            seletor = seletor.strip()
            casamento = _RE_SELETOR.match(seletor)
            if not casamento or not seletor:
                folha.ignoradas.append(seletor)
                continue
            classes = tuple(c for c in (casamento.group("classes") or "").split(".") if c)
            folha.regras.append(Regra(seletor, casamento.group("el") or "", classes,
                                      dict(declaracoes), i, fecha + 1))
        i = fecha + 1
    return folha


def cascata(folhas: Sequence[Folha], nomes: Sequence[str] = ()) -> Folha:
    """As folhas de um capítulo, na ordem dos `<link>`: a última vence."""
    saida = Folha()
    for k, folha in enumerate(folhas):
        nome = nomes[k] if k < len(nomes) else str(k)
        for regra in folha.regras + folha.novas:
            copia = Regra(regra.seletor, regra.elemento, regra.classes, dict(regra.declaracoes),
                          regra.inicio, regra.fim, regra.modificada, origem=nome)
            saida.regras.append(copia)
        saida.fontes.extend(folha.fontes)
        saida.ignoradas.extend(folha.ignoradas)
    return saida


def _texto_da_regra(regra: Regra) -> str:
    miolo = "; ".join(f"{k}: {v}" for k, v in regra.declaracoes.items())
    return f"{regra.seletor} {{ {miolo}; }}" if miolo else f"{regra.seletor} {{ }}"


def escrever(folha: Folha, css_original: str | None = None) -> str:
    """
    O texto da folha com **só** as regras tocadas reescritas, e as novas no fim.

    Uma regra que veio de um seletor com vírgula (`p.legenda, figcaption { … }`) é
    reescrita inteira quando qualquer uma das partes mudou, porque as duas
    dividem o mesmo bloco no texto.
    """
    texto = folha.texto if css_original is None else css_original
    tocadas = [r for r in folha.regras if r.modificada]
    # De trás para a frente, para os deslocamentos anteriores continuarem valendo;
    # regras que dividem o mesmo bloco são agrupadas pelo `inicio`.
    por_bloco: dict[int, list[Regra]] = {}
    for regra in tocadas:
        por_bloco.setdefault(regra.inicio, []).append(regra)
    for inicio in sorted(por_bloco, reverse=True):
        grupo = por_bloco[inicio]
        fim = grupo[0].fim
        irmas = [r for r in folha.regras if r.inicio == inicio]
        novo = "\n".join(_texto_da_regra(r) for r in irmas)
        texto = texto[:inicio] + novo + texto[fim:]
    if folha.novas:
        if texto and not texto.endswith("\n"):
            texto += "\n"
        texto += "".join(_texto_da_regra(r) + "\n" for r in folha.novas)
    return texto
