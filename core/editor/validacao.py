"""
Validar o EPUB com o `epubcheck` (ED-08; SPEC_EDITOR §9 "Validate with epubcheck",
`Alt+F9`): sem Java, uma mensagem clara; com Java, os erros com **arquivo e linha**
(AC-ED08-8) — e, antes dele, a estrutura que `epub.validar_estrutura` confere sem Java.

O `epubcheck` é o `.jar` do pacote Python `epubcheck` (extra `epub-validacao`), ou um
`epubcheck` no PATH; roda com `--json -`, que devolve cada mensagem com o caminho dentro
do EPUB, a linha e a coluna. O caminho volta como o `href` relativo ao OPF (é assim que o
livro conhece os arquivos), para o painel Validação abrir a aba certa.
"""

from __future__ import annotations

import json
import os
import posixpath
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from core.editor import epub

GRAVIDADES = ("FATAL", "ERROR", "WARNING", "USAGE", "INFO", "SUPPRESSED")


@dataclass
class Mensagem:
    codigo: str
    gravidade: str                 # "FATAL" | "ERROR" | "WARNING" | "USAGE" | "INFO"
    arquivo: str                   # href relativo ao OPF ("" quando é do livro inteiro)
    linha: int                     # 0 quando não há
    coluna: int
    texto: str

    @property
    def onde(self) -> str:
        if self.linha:
            return f"linha {self.linha}" + (f", col {self.coluna}" if self.coluna else "")
        return ""

    def __str__(self) -> str:
        return f"{self.gravidade}({self.codigo}) {self.arquivo}{' ' + self.onde if self.onde else ''}: {self.texto}"


@dataclass
class Resultado:
    valido: bool
    mensagens: list[Mensagem] = field(default_factory=list)
    sem_java: bool = False
    estrutura: list[str] = field(default_factory=list)
    saida: str = ""
    versao: str = ""

    @property
    def erros(self) -> list[Mensagem]:
        return [m for m in self.mensagens if m.gravidade in ("FATAL", "ERROR")]

    @property
    def avisos(self) -> list[Mensagem]:
        return [m for m in self.mensagens if m.gravidade == "WARNING"]

    def resumo(self) -> str:
        if self.sem_java:
            return "epubcheck não rodou (sem Java ou sem o epubcheck)"
        return (f"epubcheck: {len(self.erros)} erro(s), {len(self.avisos)} aviso(s)"
                + (f" — estrutura: {len(self.estrutura)} problema(s)" if self.estrutura else ""))


def comando_do_epubcheck() -> list[str] | None:
    """`["java", "-jar", jar]` do pacote `epubcheck`, ou `["epubcheck"]` do PATH; `None` sem nenhum."""
    java = shutil.which("java")
    if java:
        try:
            import epubcheck as pacote

            jar = os.path.join(os.path.dirname(pacote.__file__), "epubcheck.jar")
            if os.path.exists(jar):
                return [java, "-jar", jar]
        except ImportError:
            pass
    exe = shutil.which("epubcheck")
    if exe:
        return [exe]
    return None


def _href_de(caminho: str, nome_do_epub: str, opf: str) -> str:
    """O `path` do epubcheck (`livro.epub/OEBPS/Text/c.xhtml`, ou só `OEBPS/Text/c.xhtml`) → href relativo ao OPF."""
    caminho = caminho.replace("\\", "/")
    if nome_do_epub and caminho.startswith(nome_do_epub):
        caminho = caminho[len(nome_do_epub):].lstrip("/")
    elif nome_do_epub and ("/" + nome_do_epub + "/") in caminho:
        caminho = caminho.split("/" + nome_do_epub + "/", 1)[1]
    if not caminho or caminho.endswith(".epub"):
        return ""
    pasta = posixpath.dirname(opf)
    if pasta and caminho.startswith(pasta + "/"):
        return caminho[len(pasta) + 1:]
    return caminho


def mensagens_do_json(dados: dict, opf: str = "") -> list[Mensagem]:
    """As mensagens do JSON do epubcheck (`--json`), com os caminhos como href relativo ao OPF."""
    nome = str(dados.get("checker", {}).get("filename", "") or "")
    saida: list[Mensagem] = []
    for m in dados.get("messages", []):
        locais = m.get("locations") or [{"path": "", "line": -1, "column": -1}]
        for local in locais:
            linha = int(local.get("line", -1) or -1)
            coluna = int(local.get("column", -1) or -1)
            saida.append(Mensagem(str(m.get("ID", "")), str(m.get("severity", "")).upper(),
                                  _href_de(str(local.get("path", "") or ""), nome, opf),
                                  max(0, linha), max(0, coluna), str(m.get("message", ""))))
    return saida


def validar(caminho: str, opf: str | None = None, timeout: float = 300, comando: list[str] | None = None,
            correr: Any = subprocess.run) -> Resultado:
    """
    A estrutura (sem Java) e o `epubcheck` (com). `comando` e `correr` são injetáveis para
    o teste não precisar do Java: `None` descobre o epubcheck, `[]` é "sem epubcheck".
    """
    caminho = os.fspath(caminho)
    estrutura = epub.validar_estrutura(caminho)
    if opf is None:
        opf = _opf_do(caminho)
    comando = comando if comando is not None else comando_do_epubcheck()
    if not comando:
        return Resultado(valido=not estrutura, sem_java=True, estrutura=estrutura,
                         saida="Instale o Java e o pacote epubcheck (pip install epubcheck) para validar com o "
                               "epubcheck; a estrutura foi conferida sem ele.")
    try:
        processo = correr(comando + ["--json", "-", "-q", caminho], capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as erro:
        return Resultado(valido=False, sem_java=True, estrutura=estrutura, saida=f"epubcheck não rodou: {erro}")
    texto = processo.stdout or ""
    inicio = texto.find("{")
    try:
        dados = json.loads(texto[inicio:]) if inicio != -1 else {}
    except json.JSONDecodeError:
        dados = {}
    if not dados:
        return Resultado(valido=False, sem_java=True, estrutura=estrutura,
                         saida=f"epubcheck não devolveu JSON: {(processo.stderr or texto)[:500]}")
    mensagens = mensagens_do_json(dados, opf)
    versao = str(dados.get("checker", {}).get("checkerVersion", "") or "")
    valido = processo.returncode == 0 and not any(m.gravidade in ("FATAL", "ERROR") for m in mensagens)
    return Resultado(valido=valido and not estrutura, mensagens=mensagens, estrutura=estrutura,
                     saida=texto, versao=versao)


def _opf_do(caminho: str) -> str:
    import zipfile

    try:
        with zipfile.ZipFile(caminho) as z:
            container = z.read("META-INF/container.xml").decode("utf-8", errors="replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    import re

    m = re.search(r'full-path="([^"]+)"', container)
    return m.group(1) if m else ""


def java_disponivel() -> bool:
    return shutil.which("java") is not None and sys.platform is not None


__all__ = ["Mensagem", "Resultado", "validar", "comando_do_epubcheck", "mensagens_do_json", "GRAVIDADES"]
