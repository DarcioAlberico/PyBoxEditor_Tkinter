"""O log do PyBoxEditor: uma raiz, um nome por módulo, um arquivo (item 5 da análise de 2026-10-06).

Até aqui `core` não tinha uma chamada de logging: o que uma exceção engolia — a fonte que
não embutiu, a página que não renderizou, o `wordfreq` que faltou e desligou um corretor —
sumia sem rastro, e foi nessa classe de silêncio que o "Exportar travando" da F119 se
escondeu. A interface já tinha o logger `pyboxeditor.editor`, que o painel Mensagens do
editor ecoa (`ui/editor/mensagens.py`). Este módulo dá a todos o mesmo tronco:

- `logger(__name__)` devolve o logger do módulo, filho de `pyboxeditor`. Os módulos do
  editor (`core.editor.*`, `ui.editor.*`) entram **sob** `pyboxeditor.editor`, para que o
  que eles avisam chegue ao painel Mensagens, que é onde o usuário do editor olha.
- `configurar()` pendura na raiz um arquivo rotativo na pasta de dados do usuário
  (`pyboxeditor.log`, 1 MB × 3) e sobe o nível para INFO. O `appy.main` chama uma vez; a
  suíte não chama, e sem handler o `logging` só mostra WARNING ou pior no stderr.
- `uma_vez(log, chave, nivel, mensagem)` registra uma mensagem uma única vez por processo:
  é para o aviso que sairia a cada parágrafo ("sem `wordfreq`, a correção de junções está
  desligada") e só precisa sair na primeira.

O nível é a regra de quem lê o arquivo: **WARNING** quando a saída mudou sem o usuário
saber (fonte não embutida, metadado não lido, página sem imagem); **INFO** para o que é
degradação esperada e visível (sem `subset_fonts` o PDF fica maior); **DEBUG** para o que
só interessa a quem depura (temporário que não apagou, cache ilegível refeito, tecla que
o Tk não aceita). Um `except` que já reporta por relatório, fila ou retorno não precisa
de log — o rastro já existe.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ = "pyboxeditor"
EDITOR = "pyboxeditor.editor"
NOME_DO_ARQUIVO = "pyboxeditor.log"
FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
TAMANHO_MAXIMO = 1_000_000
COPIAS = 3

_ja_registradas: set[tuple[str, str]] = set()


def logger(nome: str) -> logging.Logger:
    """O logger do módulo `nome` (normalmente `__name__`), filho de `pyboxeditor`.

    `core.editor.fontes` → `pyboxeditor.editor.core.fontes`; `ui.editor.janela` →
    `pyboxeditor.editor.ui.janela`; `core.exportar` → `pyboxeditor.core.exportar`. Um nome
    que já começa por `pyboxeditor` volta como está.
    """
    if nome == RAIZ or nome.startswith(RAIZ + "."):
        return logging.getLogger(nome)
    for prefixo, pacote in (("core.editor.", "core"), ("ui.editor.", "ui")):
        if nome.startswith(prefixo):
            return logging.getLogger(f"{EDITOR}.{pacote}.{nome[len(prefixo):]}")
    return logging.getLogger(f"{RAIZ}.{nome}")


def configurar(caminho: str | Path | None = None, nivel: int = logging.INFO) -> Path:
    """Pendura na raiz o arquivo rotativo e sobe o nível; chamar de novo não duplica.

    Sem `caminho`, o arquivo é `pyboxeditor.log` na pasta de dados do usuário
    (`config.paths.ensure_data_dir`). Devolve o caminho usado.
    """
    if caminho is None:
        from config.paths import ensure_data_dir

        caminho = ensure_data_dir() / NOME_DO_ARQUIVO
    destino = Path(caminho)
    raiz = logging.getLogger(RAIZ)
    for existente in raiz.handlers:
        if getattr(existente, "pyboxeditor_arquivo", None) == destino:
            break
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(destino, maxBytes=TAMANHO_MAXIMO, backupCount=COPIAS,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter(FORMATO))
        handler.pyboxeditor_arquivo = destino  # type: ignore[attr-defined]
        raiz.addHandler(handler)
    if raiz.level == logging.NOTSET or raiz.level > nivel:
        raiz.setLevel(nivel)
    return destino


def desconfigurar(caminho: str | Path) -> None:
    """Tira da raiz o arquivo pendurado por `configurar(caminho)` — para a suíte não vazar."""
    destino = Path(caminho)
    raiz = logging.getLogger(RAIZ)
    for existente in list(raiz.handlers):
        if getattr(existente, "pyboxeditor_arquivo", None) == destino:
            raiz.removeHandler(existente)
            existente.close()


def uma_vez(log: logging.Logger, chave: str, nivel: int, mensagem: str, *args: object) -> bool:
    """Registra `mensagem` uma vez por processo para (`log.name`, `chave`); diz se registrou."""
    marca = (log.name, chave)
    if marca in _ja_registradas:
        return False
    _ja_registradas.add(marca)
    log.log(nivel, mensagem, *args)
    return True


def esquecer() -> None:
    """Apaga a memória de `uma_vez` — só a suíte precisa."""
    _ja_registradas.clear()
