"""
Abrir páginas de um PDF no editor (ED-17; docs/ANALISE_JANELA_EDITOR.md §4.4) — a parte sem Tk.

O OCR roda fora do processo do editor (`scripts/pdf_para_editor.py`, DEC-07): aqui mora o
que o editor precisa para pedir e acompanhar essa leitura — a faixa de páginas que o
usuário digita ("30-45, 60"), a linha de comando, o JSON de saída ao lado do PDF, e a
`Tarefa`, que roda o processo, lê o canal de eventos (uma linha JSON por evento) numa
thread e os entrega à janela, que os busca pelo `after` sem nunca bloquear.

O resultado é o documento editorial em JSON; a janela o abre como **livro novo**
(decisão do usuário, 2026-09-30) pela ponte da ED-11.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Sequence

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(RAIZ, "scripts", "pdf_para_editor.py")

#: Como ler: rótulo → valor de `--camada`.
LEITURAS = (("Automático (texto do PDF onde ele servir, OCR no resto)", "auto"),
            ("Só OCR (ignora o texto do PDF)", "nunca"),
            ("Só o texto do PDF", "sempre"))
IDIOMAS = ("en", "pt", "es", "de", "fr", "it", "ru", "nl")


@dataclass
class Pedido:
    """O que o diálogo devolve: o PDF, as páginas (1-based), como ler e onde gravar."""

    pdf: str
    paginas: list[int]
    idioma: str = "en"
    camada: str = "auto"
    reparar: bool = False
    dividir: str = "pagina"
    saida: str = ""

    def __post_init__(self) -> None:
        if not self.saida:
            self.saida = saida_padrao(self.pdf, self.paginas)


def faixa_de(texto: str, total: int | None = None) -> list[int]:
    """`"30-45, 60"` → `[30, …, 45, 60]` (1-based, sem repetição, em ordem). Vazio → todas (com `total`)."""
    texto = (texto or "").strip()
    if not texto:
        if total is None:
            raise ValueError("diga as páginas (ex.: 30-45, 60)")
        return list(range(1, total + 1))
    paginas: set[int] = set()
    for parte in re.split(r"[,;\s]+", texto):
        if not parte:
            continue
        achado = re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?", parte)
        if not achado:
            raise ValueError(f"página inválida: {parte!r} (use 30-45, 60)")
        inicio = int(achado.group(1))
        fim = int(achado.group(2) or inicio)
        if inicio < 1 or fim < inicio:
            raise ValueError(f"faixa inválida: {parte!r}")
        if total is not None and fim > total:
            raise ValueError(f"o PDF tem {total} página(s); {parte!r} passa do fim")
        paginas.update(range(inicio, fim + 1))
    return sorted(paginas)


def texto_da_faixa(paginas: Sequence[int]) -> str:
    """`[30, 31, 32, 60]` → `"30-32, 60"`."""
    partes: list[str] = []
    ordenadas = sorted(set(int(p) for p in paginas))
    k = 0
    while k < len(ordenadas):
        inicio = fim = ordenadas[k]
        while k + 1 < len(ordenadas) and ordenadas[k + 1] == fim + 1:
            k += 1
            fim = ordenadas[k]
        partes.append(str(inicio) if inicio == fim else f"{inicio}-{fim}")
        k += 1
    return ", ".join(partes)


def saida_padrao(pdf: str, paginas: Sequence[int]) -> str:
    """O JSON ao lado do PDF: `<nome>_p30-45.json` (o diário da revisão fica ao lado dele)."""
    base, _ext = os.path.splitext(os.path.abspath(pdf))
    faixa = texto_da_faixa(paginas).replace(", ", "_") if paginas else "todas"
    return f"{base}_p{faixa}.json"


def comando(pedido: Pedido, python: str | None = None) -> list[str]:
    """A linha de comando do processo de leitura."""
    argv = [python or sys.executable, SCRIPT, os.path.abspath(pedido.pdf), "-o", os.path.abspath(pedido.saida),
            "--idioma", pedido.idioma, "--camada", pedido.camada]
    if pedido.paginas:
        argv += ["--paginas", *[str(p) for p in pedido.paginas]]
    if pedido.reparar:
        argv.append("--reparar")
    return argv


def informacoes(pdf: str, amostra: int = 12) -> dict[str, Any]:
    """`{"paginas": n, "com_texto": k, "amostradas": m}` — só `fitz`, sem o leitor (o veredito fino é do pipeline)."""
    import fitz

    with fitz.open(pdf) as doc:
        n = len(doc)
        passo = max(1, n // max(1, amostra))
        numeros = list(range(0, n, passo))[:amostra]
        com_texto = sum(1 for k in numeros if len(doc[k].get_text("text").strip()) >= 200)
    return {"paginas": n, "com_texto": com_texto, "amostradas": len(numeros)}


@dataclass
class Tarefa:
    """
    O processo de leitura e o seu canal. `iniciar()` o dispara; `eventos()` devolve o que
    chegou desde a última chamada (dicionários do canal; uma linha que não é JSON vira
    `{"evento": "texto", ...}`); `cancelar()` mata o processo; `terminou` e `codigo` dizem
    como acabou.
    """

    argv: list[str]
    processo: Any = None
    cancelada: bool = False
    _fila: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    _leitor: threading.Thread | None = None
    _erro: list[str] = field(default_factory=list)

    def iniciar(self) -> "Tarefa":
        opcoes: dict[str, Any] = {}
        if sys.platform.startswith("win"):
            opcoes["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.processo = subprocess.Popen(self.argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL, env=ambiente, cwd=RAIZ, **opcoes)
        self._leitor = threading.Thread(target=self._ler, name="leitura-de-pdf", daemon=True)
        self._leitor.start()
        threading.Thread(target=self._ler_erros, name="leitura-de-pdf-stderr", daemon=True).start()
        return self

    def _ler(self) -> None:
        assert self.processo is not None and self.processo.stdout is not None
        for linha in self.processo.stdout:
            texto = linha.decode("utf-8", errors="replace").strip()
            if not texto:
                continue
            try:
                evento = json.loads(texto)
                if not isinstance(evento, dict):
                    raise ValueError
            except ValueError:
                evento = {"evento": "texto", "texto": texto}
            self._fila.put(evento)

    def _ler_erros(self) -> None:
        assert self.processo is not None and self.processo.stderr is not None
        for linha in self.processo.stderr:
            self._erro.append(linha.decode("utf-8", errors="replace").rstrip())
            del self._erro[:-40]            # as últimas linhas bastam para dizer o que houve

    def eventos(self) -> list[dict]:
        saida: list[dict] = []
        while True:
            try:
                saida.append(self._fila.get_nowait())
            except queue.Empty:
                return saida

    @property
    def terminou(self) -> bool:
        """O processo saiu **e** o canal foi lido até o fim."""
        if self.processo is None or self.processo.poll() is None:
            return False
        return self._leitor is None or not self._leitor.is_alive()

    @property
    def codigo(self) -> int | None:
        return None if self.processo is None else self.processo.poll()

    def stderr(self) -> str:
        return "\n".join(self._erro)

    def cancelar(self) -> None:
        self.cancelada = True
        if self.processo is not None and self.processo.poll() is None:
            self.processo.kill()

    def esperar(self, segundos: float | None = None) -> int | None:
        if self.processo is None:
            return None
        try:
            self.processo.wait(segundos)
        except subprocess.TimeoutExpired:
            return None
        if self._leitor is not None:
            self._leitor.join(5)
        return self.processo.returncode


__all__ = ["Pedido", "Tarefa", "faixa_de", "texto_da_faixa", "saida_padrao", "comando", "informacoes",
           "LEITURAS", "IDIOMAS", "SCRIPT"]
