"""
O proxy do comando Tcl de um `tk.Text`: um `proc` Tcl no lugar do comando do widget,
que avisa o Python **antes** de `insert`/`delete` e **depois** de alguns comandos
(ED-04; usado pelo `TextoRico` da ED-03 e pelo `EditorDeCodigo` da ED-07).

## Por que um `proc` Tcl, e não um comando Python

A ED-03 e a ED-07 trocavam o comando do widget por um comando Python
(`createcommand`) que chamava o original e anotava o que a edição tocou. Só que
um erro Tcl dentro de um comando Python — `index sel.first` sem seleção, que
`selecao()` provoca e captura — deixa o `_tkinter` com a exceção pendente
(`errorInCmd`) mesmo quando o Python a captura, e o `mainloop` **morre** na volta
do evento seguinte. Medido: um `try/except TclError` em volta de `index("sel.first")`
captura o erro e, ainda assim, `mainloop()` levanta o mesmo `TclError` logo depois.

Com o `proc`, o comando original corre no Tcl e o erro dele volta como erro Tcl
comum (`return -options`), sem passar pelo Python. Os ganchos Python (`antes`,
`depois`) só observam, e engolem qualquer exceção própria (registrando-a), porque
uma exceção deles teria o mesmo efeito.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable

_log = logging.getLogger("pyboxeditor.editor")

#: Os comandos avisados depois de executados (os que movem o cursor ou rolam).
COMANDOS_DEPOIS = ("insert", "delete", "mark", "yview", "xview")

_PROC = """
proc %(w)s {cmd args} {
    if {$cmd eq "insert" || $cmd eq "delete"} {
        %(w)s_antes $cmd {*}$args
    }
    set code [catch {%(w)s_orig $cmd {*}$args} result options]
    if {$code} {
        return -options $options $result
    }
    if {$cmd in {%(depois)s}} {
        %(w)s_depois $cmd {*}$args
    }
    return $result
}
"""


def instalar(texto: tk.Text, antes: Callable[[str, tuple[str, ...]], Any] | None,
             depois: Callable[[str, tuple[str, ...]], Any] | None) -> str:
    """
    Põe o proxy no widget; devolve o nome do comando original (`<w>_orig`). `antes(cmd,
    args)` corre antes de `insert`/`delete`; `depois(cmd, args)` depois dos
    `COMANDOS_DEPOIS` que não falharam. Nenhum dos dois pode derrubar o widget.
    """
    w = texto._w
    original = w + "_orig"
    tcl = texto.tk

    def protegido(gancho: Callable[[str, tuple[str, ...]], Any] | None) -> Callable[..., None]:
        def chamar(cmd: str, *args: Any) -> None:
            if gancho is None:
                return
            try:
                gancho(str(cmd), tuple(str(a) for a in args))
            except Exception:      # noqa: BLE001 — um gancho que falha não pode matar o mainloop
                _log.exception("gancho do proxy de %s falhou em %s", w, cmd)
        return chamar

    tcl.call("rename", w, original)
    tcl.createcommand(w + "_antes", protegido(antes))
    tcl.createcommand(w + "_depois", protegido(depois))
    tcl.eval(_PROC % {"w": w, "depois": " ".join(COMANDOS_DEPOIS)})

    def desinstalar(_evento: Any = None) -> None:
        try:
            tcl.eval(f"catch {{rename {w} {{}}}}")
            for nome in (w + "_antes", w + "_depois"):
                tcl.deletecommand(nome)
        except Exception:      # noqa: BLE001 — o widget ja esta indo embora; nada aqui pode falhar alto
            pass

    texto.bind("<Destroy>", desinstalar, add="+")
    return original


__all__ = ["instalar", "COMANDOS_DEPOIS"]
