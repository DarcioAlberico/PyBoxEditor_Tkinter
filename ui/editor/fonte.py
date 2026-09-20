"""
`DialogoDeFonte`: a caixa "Fonte…" do modo texto (`Ctrl+D`) — família, corpo, negrito,
itálico, sublinhado, tachado, versalete, posição, cor e realce (ED-03; SPEC_EDITOR §8.2).

Construída sem `mostrar()` para o teste: as variáveis dos widgets são o contrato
(`variaveis`), `confirmar()` fecha com o `resultado` — só o que mudou em relação ao
`atual` — e `cancelar()` fecha com `None`. `mostrar()` é modal (`wait_window`) e
devolve o mesmo `resultado`. Botões reais, foco visível (§13.2).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, font as tkfont, ttk
from typing import Any, Sequence

CORPOS = (8, 9, 10, 10.5, 11, 12, 13, 14, 16, 18, 20, 22, 24, 28, 32, 36, 48)
POSICOES = (("normal", ""), ("sobrescrito", "sobre"), ("subscrito", "sub"))


class DialogoDeFonte:
    def __init__(self, master: tk.Misc, atual: dict[str, Any] | None = None, familias: Sequence[str] | None = None,
                 titulo: str = "Fonte"):
        self.master = master
        self.atual = dict(atual or {})
        self.familias = list(familias) if familias is not None else sorted(set(tkfont.families(master)))
        self.titulo = titulo
        self.resultado: dict[str, Any] | None = None
        self.top: tk.Toplevel | None = None
        self.variaveis: dict[str, tk.Variable] = {}

    # -- construção -------------------------------------------------------

    def _construir(self) -> tk.Toplevel:
        top = tk.Toplevel(self.master)
        top.title(self.titulo)
        top.transient(self.master.winfo_toplevel())
        top.resizable(False, False)
        self.top = top
        v = self.variaveis
        v["familia"] = tk.StringVar(value=self.atual.get("familia", ""))
        v["corpo_pt"] = tk.StringVar(value=_corpo_como_texto(self.atual.get("corpo_pt")))
        for chave in ("negrito", "italico", "sublinhado", "tachado", "versalete"):
            v[chave] = tk.BooleanVar(value=bool(self.atual.get(chave, False)))
        v["posicao"] = tk.StringVar(value=self.atual.get("posicao", "") or "")
        v["cor"] = tk.StringVar(value=self.atual.get("cor", "") or "")
        v["fundo"] = tk.StringVar(value=self.atual.get("fundo", "") or "")

        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        ttk.Label(corpo, text="Família:").grid(row=0, column=0, sticky="w")
        self.caixa_familia = ttk.Combobox(corpo, textvariable=v["familia"], values=[""] + self.familias, width=28)
        self.caixa_familia.grid(row=0, column=1, columnspan=3, sticky="ew", pady=2)
        ttk.Label(corpo, text="Corpo (pt):").grid(row=1, column=0, sticky="w")
        corpos = [""] + [_corpo_como_texto(c) for c in CORPOS]
        self.caixa_corpo = ttk.Combobox(corpo, textvariable=v["corpo_pt"], values=corpos, width=8)
        self.caixa_corpo.grid(row=1, column=1, sticky="w", pady=2)
        self.caixas: dict[str, ttk.Checkbutton] = {}
        opcoes = (("negrito", "Negrito"), ("italico", "Itálico"), ("sublinhado", "Sublinhado"),
                  ("tachado", "Tachado"), ("versalete", "Versalete"))
        for k, (chave, rotulo) in enumerate(opcoes):
            caixa = ttk.Checkbutton(corpo, text=rotulo, variable=v[chave])
            caixa.grid(row=2 + k // 3, column=1 + k % 3, sticky="w", pady=2)
            self.caixas[chave] = caixa
        ttk.Label(corpo, text="Posição:").grid(row=4, column=0, sticky="w")
        self.radios: dict[str, ttk.Radiobutton] = {}
        for k, (rotulo, valor) in enumerate(POSICOES):
            radio = ttk.Radiobutton(corpo, text=rotulo, value=valor, variable=v["posicao"])
            radio.grid(row=4, column=1 + k, sticky="w")
            self.radios[valor] = radio
        ttk.Label(corpo, text="Cor:").grid(row=5, column=0, sticky="w")
        ttk.Entry(corpo, textvariable=v["cor"], width=10).grid(row=5, column=1, sticky="w", pady=2)
        ttk.Button(corpo, text="Escolher…", command=lambda: self._escolher("cor")).grid(row=5, column=2, sticky="w")
        ttk.Label(corpo, text="Realce:").grid(row=6, column=0, sticky="w")
        ttk.Entry(corpo, textvariable=v["fundo"], width=10).grid(row=6, column=1, sticky="w", pady=2)
        ttk.Button(corpo, text="Escolher…", command=lambda: self._escolher("fundo")).grid(row=6, column=2, sticky="w")
        self.amostra = tk.Label(corpo, text="Amostra: 23…♖xe4 ±", anchor="w", relief="sunken", padx=8, pady=6,
                                highlightthickness=1)
        self.amostra.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 2))
        botoes = ttk.Frame(corpo)
        botoes.grid(row=8, column=0, columnspan=4, sticky="e", pady=(10, 0))
        self.botao_ok = ttk.Button(botoes, text="OK", command=self.confirmar, default="active")
        self.botao_ok.pack(side="right", padx=(6, 0))
        ttk.Button(botoes, text="Cancelar", command=self.cancelar).pack(side="right")
        for var in v.values():
            var.trace_add("write", lambda *a: self._atualizar_amostra())
        top.bind("<Return>", lambda e: self.confirmar())
        top.bind("<Escape>", lambda e: self.cancelar())
        top.protocol("WM_DELETE_WINDOW", self.cancelar)
        self._atualizar_amostra()
        return top

    def _escolher(self, chave: str) -> None:
        cor = colorchooser.askcolor(color=self.variaveis[chave].get() or None, parent=self.top)
        if cor and cor[1]:
            self.variaveis[chave].set(cor[1])

    def _atualizar_amostra(self) -> None:
        if self.top is None:
            return
        v = self.variaveis
        try:
            corpo = float(v["corpo_pt"].get() or 12)
        except ValueError:
            corpo = 12.0
        familia = v["familia"].get() or "Georgia"
        fonte = tkfont.Font(root=self.top, family=familia, size=max(4, int(round(corpo))),
                            weight="bold" if v["negrito"].get() else "normal",
                            slant="italic" if v["italico"].get() else "roman",
                            underline=bool(v["sublinhado"].get()), overstrike=bool(v["tachado"].get()))
        opcoes: dict[str, Any] = {"font": fonte}
        if v["cor"].get().startswith("#") and len(v["cor"].get()) in (4, 7):
            opcoes["foreground"] = v["cor"].get()
        if v["fundo"].get().startswith("#") and len(v["fundo"].get()) in (4, 7):
            opcoes["background"] = v["fundo"].get()
        try:
            self.amostra.configure(**opcoes)
        except tk.TclError:
            pass

    # -- resultado ----------------------------------------------------------

    def escolhas(self) -> dict[str, Any]:
        """O que está nas variáveis, no vocabulário de `TextoRico.aplicar`."""
        v = self.variaveis
        saida: dict[str, Any] = {"familia": v["familia"].get().strip(), "negrito": bool(v["negrito"].get()),
                                 "italico": bool(v["italico"].get()), "sublinhado": bool(v["sublinhado"].get()),
                                 "tachado": bool(v["tachado"].get()), "versalete": bool(v["versalete"].get()),
                                 "cor": v["cor"].get().strip(), "fundo": v["fundo"].get().strip()}
        posicao = v["posicao"].get()
        saida["sobrescrito"] = posicao == "sobre"
        saida["subscrito"] = posicao == "sub"
        corpo = v["corpo_pt"].get().strip().replace(",", ".")
        try:
            saida["corpo_pt"] = float(corpo) if corpo else None
        except ValueError:
            saida["corpo_pt"] = None
        return saida

    def diferencas(self) -> dict[str, Any]:
        """Só o que mudou em relação ao `atual` — é o que `TextoRico.aplicar` recebe."""
        escolhas = self.escolhas()
        atual = self.atual
        saida: dict[str, Any] = {}
        for chave, valor in escolhas.items():
            if chave in ("sobrescrito", "subscrito"):
                antes = atual.get("posicao", "") == ("sobre" if chave == "sobrescrito" else "sub")
                if valor != antes:
                    saida[chave] = valor
                continue
            antes = atual.get(chave, None if chave == "corpo_pt" else ("" if isinstance(valor, str) else False))
            if chave == "corpo_pt":
                antes = None if antes in (None, "") else float(antes)
            if valor != antes:
                saida[chave] = valor
        return saida

    def confirmar(self) -> dict[str, Any] | None:
        self.resultado = self.diferencas()
        self._fechar()
        return self.resultado

    def cancelar(self) -> None:
        self.resultado = None
        self._fechar()

    def _fechar(self) -> None:
        if self.top is not None:
            try:
                self.top.grab_release()
                self.top.destroy()
            except tk.TclError:
                pass
            self.top = None

    def mostrar(self) -> dict[str, Any] | None:
        top = self._construir()
        top.grab_set()
        self.caixa_familia.focus_set()
        top.wait_window()
        return self.resultado


def _corpo_como_texto(valor: Any) -> str:
    if valor in (None, ""):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return f"{numero:g}"
