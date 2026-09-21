"""
O painel Navegador (ED-08; SPEC_EDITOR §7.1, §9 "Book Browser"): a árvore do livro na
disposição da espinha — Texto, Estilos, Imagens, Fontes, Outros —, com o menu de contexto
completo (uma entrada por ação, todas com item na barra: Livro ▸), arrastar para
reordenar os capítulos, `Delete` para excluir, `F2` para renomear, `Espaço` para marcar
o arquivo para a busca (ED-06).

O painel não faz nada sozinho: toda ação chega a `janela.executar(nome)`, e é a janela
(`ui/editor/operacoes.py`) que sabe fazer. O `Treeview` fica em `arvore` — é o
`janela.navegador` de sempre, para o que já o consultava (`focus()`, `item()`).
"""

from __future__ import annotations

import posixpath
import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

from core.editor import epub, livro_ops
from core.editor.modelo import Livro
from ui.editor import menus as menus_mod

#: O menu de contexto do navegador: nomes de comando (com item na barra) e "-" para separador.
CONTEXTO = ("abrir_do_navegador", "-", "renomear", "renomear_varios", "excluir", "-", "adicionar_arquivo",
            "adicionar_copia", "novo_capitulo", "nova_folha", "-", "capa", "semantica_do_capitulo", "marcos",
            "vincular_folhas", "-", "mover_para_cima", "mover_para_baixo", "juntar_com_anterior", "dividir_capitulo",
            "ordenar_por_nome", "-", "abrir_com", "marcar_arquivo")
GRUPOS = ("Texto", "Estilos", "Imagens", "Fontes", "Outros")


class Navegador(ttk.Frame):
    def __init__(self, master: tk.Misc, janela: Any, **kw: Any):
        super().__init__(master, **kw)
        self.janela = janela
        self.arvore = ttk.Treeview(self, show="tree", selectmode="browse", height=10)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._arrastando: str | None = None
        self._menu: tk.Menu | None = None
        a = self.arvore
        a.bind("<Double-Button-1>", lambda e: self._abrir())
        a.bind("<Return>", lambda e: self._abrir())
        a.bind("<Button-3>", self._botao_direito, add="+")
        a.bind("<Delete>", lambda e: self._executar("excluir"))
        a.bind("<F2>", lambda e: self._executar("renomear"))
        a.bind("<space>", lambda e: self._executar("marcar_arquivo"))
        a.bind("<ButtonPress-1>", self._comeca_arrasto, add="+")
        a.bind("<B1-Motion>", self._arrasta, add="+")
        a.bind("<ButtonRelease-1>", self._solta, add="+")

    # -- conteúdo ------------------------------------------------------------------

    def atualizar(self, livro: Livro | None, marcados: Sequence[str] = ()) -> None:
        arvore = self.arvore
        aberto = {iid for iid in arvore.get_children() if arvore.item(iid, "open")}
        selecionado = arvore.focus()
        arvore.delete(*arvore.get_children())
        if livro is None:
            return
        grupos: dict[str, list[tuple[str, str]]] = {g: [] for g in GRUPOS}
        for cap in livro.capitulos:
            rotulo = cap.titulo_efetivo
            extra = rotulo if rotulo and rotulo != posixpath.basename(cap.arquivo) else ""
            if cap.semantica:
                extra = (extra + " " if extra else "") + f"[{cap.semantica}]"
            grupos["Texto"].append((cap.arquivo, extra))
        for caminho, recurso in livro.recursos.items():
            if recurso.tipo_mime == epub.MIME_CSS:
                grupos["Estilos"].append((caminho, "(padrão)" if livro.folhas[:1] == [caminho] else ""))
            elif recurso.tipo_mime.startswith("image/"):
                grupos["Imagens"].append((caminho, "(capa)" if caminho == livro.metadados.capa else ""))
            elif "font" in recurso.tipo_mime:
                grupos["Fontes"].append((caminho, ""))
            elif caminho not in (livro.nav, livro.ncx):
                grupos["Outros"].append((caminho, ""))
        grupos["Outros"].append((livro.nav, "(regenerado)"))
        if livro.ncx:
            grupos["Outros"].append((livro.ncx, "(regenerado)"))
        grupos["Outros"].append((livro.opf, "(regenerado ao salvar)"))
        marcados = set(marcados)
        for nome, itens in grupos.items():
            iid_grupo = f"grupo:{nome}"
            no = arvore.insert("", "end", iid=iid_grupo, text=f"{nome} ({len(itens)})",
                               open=(nome == "Texto") if not aberto else (iid_grupo in aberto))
            for caminho, extra in itens:
                marca = "✓ " if caminho in marcados else ""
                rotulo = marca + posixpath.basename(caminho) + (f" — {extra}" if extra else "")
                arvore.insert(no, "end", iid=caminho, text=rotulo)
        if selecionado and arvore.exists(selecionado):
            arvore.focus(selecionado)
            arvore.selection_set(selecionado)

    def selecionado(self) -> str | None:
        """O href focado (ou selecionado); `None` num grupo ou sem nada."""
        iid = self.arvore.focus() or (self.arvore.selection() or ("",))[0]
        if not iid or iid.startswith("grupo:"):
            return None
        return iid

    def selecionar(self, href: str) -> bool:
        if not self.arvore.exists(href):
            return False
        pai = self.arvore.parent(href)
        if pai:
            self.arvore.item(pai, open=True)
        self.arvore.focus(href)
        self.arvore.selection_set(href)
        self.arvore.see(href)
        return True

    def capitulos_visiveis(self) -> list[str]:
        return list(self.arvore.get_children("grupo:Texto")) if self.arvore.exists("grupo:Texto") else []

    # -- ações -------------------------------------------------------------------

    def _executar(self, nome: str) -> str:
        self.janela.executar(nome)
        return "break"

    def _abrir(self) -> str:
        href = self.selecionado()
        if href:
            self.janela.executar("abrir_do_navegador", href)
        return "break"

    def _botao_direito(self, evento: Any) -> str:
        iid = self.arvore.identify_row(evento.y)
        if iid:
            self.arvore.focus(iid)
            self.arvore.selection_set(iid)
        self.arvore.focus_set()
        self.menu_de_contexto(evento.x_root, evento.y_root)
        return "break"

    def menu_de_contexto(self, x: int | None = None, y: int | None = None) -> tk.Menu:
        """O menu do navegador, montado dos itens da barra (toda ação de contexto tem item)."""
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        janela = self.janela
        menu = tk.Menu(self, tearoff=0)
        href = self.selecionado()
        for nome in CONTEXTO:
            if nome == "-":
                menu.add_separator()
                continue
            item = menus_mod.item_de(nome)
            rotulo = item.rotulo if item is not None else nome
            if nome == "abrir_do_navegador":
                rotulo = "Abrir"
            if nome == "semantica_do_capitulo":
                sub = tk.Menu(menu, tearoff=0)
                for tipo, rotulo_s in livro_ops.SEMANTICAS:
                    sub.add_command(label=rotulo_s, command=lambda t=tipo: janela.executar("semantica", t))
                menu.add_cascade(label="Semântica do capítulo", menu=sub,
                                 state="normal" if href and janela.disponivel("semantica") else "disabled")
                continue
            disponivel = janela.disponivel(nome) or nome == "abrir_do_navegador"
            if nome in ("abrir_do_navegador", "renomear", "excluir", "adicionar_copia", "abrir_com",
                        "marcar_arquivo", "mover_para_cima", "mover_para_baixo", "juntar_com_anterior") and not href:
                disponivel = False
            menu.add_command(label=rotulo, command=lambda n=nome: janela.executar(n),
                             state="normal" if disponivel else "disabled")
        self._menu = menu
        if x is not None and y is not None and self.winfo_viewable():
            try:
                menu.tk_popup(int(x), int(y))
            finally:
                try:
                    menu.grab_release()
                except tk.TclError:
                    pass
        return menu

    # -- arrastar para reordenar ------------------------------------------------------

    def _comeca_arrasto(self, evento: Any) -> None:
        iid = self.arvore.identify_row(evento.y)
        self._arrastando = iid if iid and self.arvore.parent(iid) == "grupo:Texto" else None

    def _arrasta(self, evento: Any) -> None:
        if self._arrastando is None:
            return
        alvo = self.arvore.identify_row(evento.y)
        if alvo and alvo != self._arrastando and self.arvore.parent(alvo) == "grupo:Texto":
            self.arvore.move(self._arrastando, "grupo:Texto", self.arvore.index(alvo))

    def _solta(self, _evento: Any) -> None:
        if self._arrastando is None:
            return
        href = self._arrastando
        self._arrastando = None
        ordem = self.capitulos_visiveis()
        livro = getattr(getattr(self.janela, "projeto", None), "livro", None)
        if livro is None or [c.arquivo for c in livro.capitulos] == ordem:
            return
        self.janela.executar("reordenar_capitulos", ordem)
        self.selecionar(href)


__all__ = ["Navegador", "CONTEXTO", "GRUPOS"]
