"""
Contagem de palavras e as estatísticas do livro (ED-06; SPEC_EDITOR §8.15).

A contagem é sobre o **modelo**: palavras e caracteres do texto dos parágrafos (o
`texto_de`, que junta os trechos e conta a quebra suave como um caractere), mais o
que só se conta — blocos, diagramas, figuras, tabelas, notas, lances, páginas do
impresso. Um capítulo que só existe em `texto_cru` é contado pelo texto sem as tags,
como a barra de status já fazia (ED-02). A palavra é o `\\w+` do Python, o mesmo da
barra de status, para os dois números baterem (AC-ED06-5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Any

from core.editor import modelo
from core.editor.modelo import (Capitulo, Diagrama, Figura, Lista, Livro, MarcaDePagina, Paragrafo, Tabela, Titulo,
                                Trecho)

_RE_PALAVRA = re.compile(r"\w+")
_RE_TAG = re.compile(r"<[^>]*>")
_RE_ESPACO = re.compile(r"\s")


@dataclass
class Contagem:
    palavras: int = 0
    caracteres: int = 0
    caracteres_sem_espacos: int = 0
    paragrafos: int = 0               # parágrafos e títulos com texto, contando os internos
    titulos: int = 0
    blocos: int = 0                   # os blocos de cima
    diagramas: int = 0
    figuras: int = 0
    tabelas: int = 0
    listas: int = 0
    notas: int = 0
    lances: int = 0                   # trechos com `papel="lance"`
    paginas: int = 0                  # marcas de página do impresso
    capitulos: int = 0
    avisos: list[str] = field(default_factory=list)

    def somar(self, outra: "Contagem") -> "Contagem":
        for campo in fields(self):
            if campo.name == "avisos":
                self.avisos.extend(outra.avisos)
            else:
                setattr(self, campo.name, getattr(self, campo.name) + getattr(outra, campo.name))
        return self

    def linhas(self) -> list[str]:
        """O texto da caixa "Estatísticas", uma linha por número."""
        def n(valor: int) -> str:
            return f"{valor:,}".replace(",", ".")

        saida = [f"Palavras: {n(self.palavras)}", f"Caracteres: {n(self.caracteres)} "
                 f"({n(self.caracteres_sem_espacos)} sem espaços)",
                 f"Parágrafos: {n(self.paragrafos)} · Títulos: {n(self.titulos)} · Blocos: {n(self.blocos)}",
                 f"Diagramas: {n(self.diagramas)} · Figuras: {n(self.figuras)} · Tabelas: {n(self.tabelas)} · "
                 f"Listas: {n(self.listas)}",
                 f"Notas: {n(self.notas)} · Lances marcados: {n(self.lances)} · Páginas do impresso: "
                 f"{n(self.paginas)}"]
        if self.capitulos:
            saida.insert(0, f"Capítulos: {n(self.capitulos)}")
        return saida


def _contar_texto(texto: str, contagem: Contagem) -> None:
    contagem.palavras += len(_RE_PALAVRA.findall(texto))
    contagem.caracteres += len(texto)
    contagem.caracteres_sem_espacos += len(_RE_ESPACO.sub("", texto))


def _paragrafos(blocos: Any):
    for bloco in blocos:
        if isinstance(bloco, Paragrafo):
            yield bloco
        elif isinstance(bloco, Lista):
            for item in bloco.itens:
                yield from _paragrafos(item.paragrafos)
                if item.filhos is not None:
                    yield from _paragrafos([item.filhos])
        elif isinstance(bloco, Tabela):
            for fila in bloco.filas:
                for celula in fila:
                    yield from _paragrafos(celula.blocos)
        elif isinstance(bloco, modelo.Citacao):
            yield from _paragrafos(bloco.blocos)


def contar_capitulo(cap: Capitulo) -> Contagem:
    c = Contagem()
    if cap.texto_cru is not None:
        _contar_texto(_RE_TAG.sub(" ", cap.texto_cru), c)
        c.avisos.append(f"{cap.arquivo}: contado pelo texto cru (modo código)")
        return c
    c.blocos = len(cap.blocos)
    for bloco in modelo.blocos_do_capitulo(cap):
        if isinstance(bloco, Diagrama):
            c.diagramas += 1
        elif isinstance(bloco, Figura):
            c.figuras += 1
        elif isinstance(bloco, Tabela):
            c.tabelas += 1
        elif isinstance(bloco, Lista):
            c.listas += 1
        elif isinstance(bloco, MarcaDePagina):
            c.paginas += 1
        for trecho in modelo._todos_os_trechos(bloco):
            if trecho.papel == "lance":
                c.lances += 1
            if trecho.pagina is not None:
                c.paginas += 1
    for p in _paragrafos(cap.blocos):
        texto = modelo.texto_de(p)
        if texto.strip():
            c.paragrafos += 1
        if isinstance(p, Titulo):
            c.titulos += 1
        _contar_texto(texto, c)
    for bloco in cap.blocos:
        if isinstance(bloco, (Figura, Diagrama, Tabela)) and bloco.legenda:
            _contar_texto("".join(t.texto for t in bloco.legenda), c)
    c.notas = len(cap.notas)
    for nota in cap.notas:
        for p in nota.blocos:
            _contar_texto(modelo.texto_de(p), c)
    return c


def contar_livro(livro: Livro) -> Contagem:
    total = Contagem()
    for cap in livro.capitulos:
        total.somar(contar_capitulo(cap))
    total.capitulos = len(livro.capitulos)
    return total


def palavras_de(texto: str) -> int:
    """A contagem de palavras de um texto solto (a da barra de status)."""
    return len(_RE_PALAVRA.findall(texto))


def trechos_com_texto(trechos: list[Trecho]) -> int:
    return sum(1 for t in trechos if t.texto)


__all__ = ["Contagem", "contar_capitulo", "contar_livro", "palavras_de"]
