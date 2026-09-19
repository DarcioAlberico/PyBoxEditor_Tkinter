"""
O relatório e as opções que toda conversão do editor compartilha (SPEC_EDITOR §10.8).

`epub`, `html_io`, `docx_io`, `txt_io`, `pdf_io` e `importar_ir` devolvem o mesmo
`RelatorioDeConversao` — leitura como escrita —, e é ele que a caixa de conclusão
mostra com "Abrir arquivo" e "Abrir pasta". Um relatório por formato, com campos
diferentes, foi o que a v1.1 da spec tinha e a revisão derrubou: quem lê o
resultado não deveria ter de saber de onde ele veio.

Nasce na ED-00 porque a ED-01 (EPUB) e a ED-09 (DOCX), que correm em ondas
diferentes mas antes uma da outra, já o devolvem.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RelatorioDeConversao:
    """As oito contagens da §10.8, os avisos e os arquivos — para todo formato."""

    formato: str
    arquivos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    capitulos: int = 0
    blocos: int = 0
    diagramas_png: int = 0
    diagramas_fonte: int = 0
    figuras: int = 0
    notas: int = 0
    ilhas: int = 0
    fontes_embutidas: list[str] = field(default_factory=list)
    tempo_s: float = 0.0
    metadados: dict[str, Any] = field(default_factory=dict)

    def contar(self, livro: Any) -> "RelatorioDeConversao":
        """Preenche as contagens a partir de um `Livro` (sem `tempo_s`)."""
        from core.editor import modelo

        self.capitulos = len(livro.capitulos)
        self.blocos = self.diagramas_png = self.diagramas_fonte = 0
        self.figuras = self.notas = self.ilhas = 0
        for cap in livro.capitulos:
            self.notas += len(cap.notas)
            for bloco in modelo.blocos_do_capitulo(cap):
                self.blocos += 1
                if isinstance(bloco, modelo.Diagrama):
                    if bloco.modo == "fonte":
                        self.diagramas_fonte += 1
                    else:
                        self.diagramas_png += 1
                elif isinstance(bloco, modelo.Figura):
                    self.figuras += 1
                elif isinstance(bloco, modelo.IlhaBruta):
                    self.ilhas += 1
            for trecho in modelo.trechos_do_capitulo(cap):
                if trecho.ilha:
                    self.ilhas += 1
        return self

    def aviso(self, texto: str) -> None:
        self.avisos.append(str(texto))

    def resumo(self) -> str:
        """As linhas que a caixa de conclusão mostra."""
        linhas = [
            f"Formato: {self.formato}",
            f"Capítulos: {self.capitulos}",
            f"Blocos: {self.blocos}",
            f"Diagramas: {self.diagramas_png} em imagem, {self.diagramas_fonte} em fonte",
            f"Figuras: {self.figuras}",
            f"Notas: {self.notas}",
            f"Ilhas (fora do dialeto): {self.ilhas}",
            f"Fontes embutidas: {', '.join(self.fontes_embutidas) or 'nenhuma'}",
            f"Tempo: {self.tempo_s:.1f} s",
        ]
        if self.avisos:
            linhas.append(f"Avisos: {len(self.avisos)}")
            linhas.extend(f"  - {a}" for a in self.avisos[:20])
            if len(self.avisos) > 20:
                linhas.append(f"  … e mais {len(self.avisos) - 20}")
        return "\n".join(linhas)


class Cronometro:
    """`with Cronometro(relatorio):` grava `tempo_s` ao sair."""

    def __init__(self, relatorio: RelatorioDeConversao):
        self.relatorio = relatorio

    def __enter__(self) -> "Cronometro":
        self.inicio = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.relatorio.tempo_s = time.perf_counter() - self.inicio


@dataclass
class OpcoesDeConversao:
    """
    O que uma conversão pergunta ao usuário, num objeto só (§10.3, §10.5).

    `modo_de_diagrama` vale para o DOCX e para o PDF; no EPUB cada `Diagrama` tem o
    seu. `notas` decide se as notas saem no rodapé ou no fim; `sumario` põe o campo
    TOC no DOCX; `ncx` escreve o `toc.ncx` de compatibilidade no EPUB.
    """

    modo_de_diagrama: str = "png"
    corpo_pt: float = 16.0
    fonte: str = "SkakNew-Diagram"
    moldura: str = "simples"
    cantos: str = "reto"
    sumario: bool = True
    notas: str = "rodape"
    hifenizacao: bool = False
    idioma: str = ""
    ncx: bool = True
    pasta_de_imagens: str = "Images"

    def __post_init__(self) -> None:
        if self.modo_de_diagrama not in ("png", "fonte"):
            raise ValueError(f"modo de diagrama inválido: {self.modo_de_diagrama!r}")
        if self.notas not in ("rodape", "fim"):
            raise ValueError(f"notas inválidas: {self.notas!r}")
        self.corpo_pt = float(self.corpo_pt)
