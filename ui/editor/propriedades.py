"""
O painel Propriedades do modo texto (ED-04; SPEC_EDITOR §7.1, §8.3, §8.6–§8.9, AC-ED04-8).

O painel mostra o que está sob o cursor do `TextoRico` ativo — o parágrafo (estilo,
alinhamento, recuos, espaçamento, entrelinha, âncora, classe), a figura (alt, largura,
alinhamento, legenda, número), a tabela (legenda, número, largura, cabeçalho), a ilha
(o XHTML), a marca de página (a página), a referência de nota (o tipo) ou o link (o
destino e o título) — em campos que **só gravam em "Aplicar"**: mexer no campo não
toca o modelo; `Aplicar` chama `TextoRico.aplicar_propriedades(alvo, valores)`, que
faz a mudança com um ponto de desfazer. `Alt+Enter` traz o foco para cá.

O painel não sabe o que existe no livro: `verificar_destino(href)` é injetado pela
janela e diz se um link interno aponta para algo — quando não, o destino fica em
vermelho (AC-ED04-4). As ações que precisam da janela (seguir o link, ir à nota,
entrar na tabela, editar a ilha no mini-editor) saem por `ao_acao(nome, alvo)`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ui.editor.barra import AnelDeFoco

ESTILOS = ("corpo", "primeira", "titulo1", "titulo2", "titulo3", "titulo4", "titulo5", "titulo6", "notacao",
           "comentario", "legenda", "citacao", "nota", "destaque", "epigrafe", "assinatura", "cabecalho-diagrama")
ALINHAMENTOS = ("", "esquerda", "centro", "direita", "justificado")
ALINHAMENTOS_DE_FIGURA = ("esq", "centro", "dir")
TIPOS_DE_NOTA = ("rodape", "fim")
TITULOS = {"paragrafo": "Parágrafo", "figura": "Figura", "tabela": "Tabela", "ilha": "Ilha de XHTML",
           "ilha_inline": "Ilha inline", "marca": "Marca de página", "quebra": "Quebra de página",
           "separador": "Separador", "diagrama": "Diagrama", "nota": "Nota", "link": "Link", "lista": "Lista",
           "citacao": "Citação", "": "Propriedades"}
COR_DE_ERRO = "#b00020"


class PainelDePropriedades(ttk.Frame):
    def __init__(self, master: tk.Misc, texto: Any = None, ao_acao: Callable[[str, dict[str, Any]], Any] | None = None,
                 verificar_destino: Callable[[str], bool] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.texto_rico = texto
        self.ao_acao = ao_acao
        self.verificar_destino = verificar_destino
        self.alvo: dict[str, Any] = {"tipo": "", "id": "", "objeto": None, "campos": {}}
        self.variaveis: dict[str, tk.Variable] = {}
        self.entradas: dict[str, tk.Widget] = {}
        self.caixas_de_texto: dict[str, tk.Text] = {}
        self._chave = None
        self.titulo = ttk.Label(self, text="Propriedades", font=("Segoe UI", 9, "bold"))
        self.titulo.grid(row=0, column=0, sticky="w", padx=4, pady=(4, 2))
        self.corpo = ttk.Frame(self)
        self.corpo.grid(row=1, column=0, sticky="nsew", padx=4)
        self.corpo.columnconfigure(1, weight=1)
        self.rodape = ttk.Frame(self)
        self.rodape.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        self.anel_aplicar = AnelDeFoco(self.rodape, lambda pai: ttk.Button(pai, text="Aplicar", command=self.aplicar))
        self.anel_aplicar.pack(side="right")
        self.botao_aplicar: ttk.Button = self.anel_aplicar.widget
        self.botao_acao: ttk.Button | None = None
        self.aviso = ttk.Label(self, text="", foreground=COR_DE_ERRO, wraplength=220, justify="left")
        self.aviso.grid(row=3, column=0, sticky="w", padx=4)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Atualizar (o cursor moveu)
    # ------------------------------------------------------------------

    def atualizar(self, forcar: bool = False) -> dict[str, Any]:
        """Lê o alvo do editor ativo e remonta os campos se o alvo mudou (ou `forcar`)."""
        texto = self.texto_rico
        alvo = {"tipo": "", "id": "", "objeto": None, "campos": {}}
        if texto is not None:
            try:
                alvo = texto.ativo().alvo_das_propriedades() if hasattr(texto, "ativo") else \
                    texto.alvo_das_propriedades()
            except tk.TclError:
                alvo = {"tipo": "", "id": "", "objeto": None, "campos": {}}
        chave = (alvo["tipo"], alvo["id"], id(texto))
        if chave == self._chave and not forcar:
            return self.alvo
        self._chave = chave
        self.alvo = alvo
        self._montar()
        return alvo

    def _limpar(self) -> None:
        for filho in self.corpo.winfo_children():
            filho.destroy()
        self.variaveis.clear()
        self.entradas.clear()
        self.caixas_de_texto.clear()
        if self.botao_acao is not None:
            self.botao_acao.master.destroy()
            self.botao_acao = None
        self.aviso.configure(text="")

    def _montar(self) -> None:
        self._limpar()
        tipo, campos = self.alvo["tipo"], dict(self.alvo["campos"])
        self.titulo.configure(text=TITULOS.get(tipo, tipo.capitalize() or "Propriedades"))
        linha = 0
        if tipo == "paragrafo":
            linha = self._combo("estilo", "Estilo:", campos.get("estilo", "corpo"), ESTILOS, linha)
            linha = self._combo("alinhamento", "Alinhamento:", campos.get("alinhamento") or "", ALINHAMENTOS, linha)
            for chave, rotulo in (("recuo_primeira_em", "Recuo 1ª linha (em):"),
                                  ("recuo_esquerda_em", "Recuo esq. (em):"), ("recuo_direita_em", "Recuo dir. (em):"),
                                  ("antes_em", "Antes (em):"), ("depois_em", "Depois (em):"),
                                  ("entrelinha", "Entrelinha:")):
                linha = self._entrada(chave, rotulo, _numero(campos.get(chave)), linha)
            linha = self._check("manter_com_proximo", "Manter com o próximo",
                                bool(campos.get("manter_com_proximo")), linha)
            linha = self._check("manter_linhas", "Manter linhas juntas", bool(campos.get("manter_linhas")), linha)
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
        elif tipo == "figura":
            linha = self._fixo("Arquivo:", campos.get("recurso", ""), linha)
            linha = self._entrada("alt", "Texto alternativo:", campos.get("alt", ""), linha)
            if not campos.get("alt"):
                self.aviso.configure(text="Sem alt: quem ouve o livro não sabe o que a figura mostra.")
            linha = self._entrada("largura_pt", "Largura (pt):", _numero(campos.get("largura_pt")), linha)
            linha = self._combo("alinhamento", "Alinhamento:", campos.get("alinhamento", "centro"),
                                ALINHAMENTOS_DE_FIGURA, linha)
            linha = self._entrada("legenda", "Legenda:", campos.get("legenda", ""), linha)
            linha = self._entrada("numero", "Número:", _numero(campos.get("numero")), linha)
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
        elif tipo == "tabela":
            linha = self._fixo("Tamanho:", f"{campos.get('filas', 0)} × {campos.get('colunas', 0)}", linha)
            linha = self._entrada("legenda", "Legenda:", campos.get("legenda", ""), linha)
            linha = self._entrada("numero", "Número:", _numero(campos.get("numero")), linha)
            linha = self._entrada("largura_pct", "Largura (%):", _numero(campos.get("largura_pct")), linha)
            linha = self._check("primeira_fila_cabecalho", "Primeira fila é cabeçalho",
                                bool(campos.get("primeira_fila_cabecalho")), linha)
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
            self._acao("Entrar na tabela", "entrar_na_tabela")
        elif tipo in ("ilha", "ilha_inline"):
            if tipo == "ilha":
                linha = self._fixo("Elemento:", f"<{campos.get('elemento', '?')}>", linha)
            linha = self._caixa("xhtml", "XHTML:", campos.get("xhtml", ""), linha)
            if tipo == "ilha":
                linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
            self._acao("Editar no mini-editor…", "editar_ilha")
        elif tipo == "marca":
            linha = self._entrada("pagina", "Página do impresso:", _numero(campos.get("pagina")), linha)
            linha = self._fixo("Âncora (id):", f"pg-{campos.get('pagina', '?')}", linha)
            self.aviso.configure(text="A marca não quebra a página: é o marcador da lista de páginas.")
        elif tipo in ("quebra", "separador"):
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
        elif tipo == "diagrama":
            linha = self._fixo("FEN:", campos.get("fen", ""), linha)
            linha = self._fixo("Lado:", {"w": "brancas", "b": "pretas"}.get(campos.get("lado", ""), "?"), linha)
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            self.aviso.configure(text="Posição, orientação, coordenadas, marcas e legenda: Editar posição… "
                                      "(Enter sobre o diagrama) e o menu Xadrez.")
            self._acao("Editar posição…", "editar_posicao")
        elif tipo == "nota":
            linha = self._fixo("Número:", str(campos.get("numero", "")), linha)
            linha = self._combo("tipo", "Tipo:", campos.get("tipo", "rodape"), TIPOS_DE_NOTA, linha)
            linha = self._fixo("Texto:", campos.get("texto", "")[:80], linha)
            self._acao("Ir à nota", "ir_para_nota")
        elif tipo == "link":
            linha = self._entrada("href", "Destino (href):", campos.get("href", ""), linha)
            linha = self._entrada("titulo", "Título (dica):", campos.get("titulo", ""), linha)
            linha = self._fixo("Texto:", campos.get("texto", "")[:60], linha)
            self._conferir_destino(campos.get("href", ""))
            self._acao("Seguir link", "seguir_link")
        elif tipo:
            linha = self._entrada("id", "Âncora (id):", campos.get("id", ""), linha)
            linha = self._entrada("classe", "Classe CSS:", campos.get("classe", ""), linha)
        else:
            ttk.Label(self.corpo, text="Nada sob o cursor.", foreground="#555555").grid(row=0, column=0, sticky="w")
        self.botao_aplicar.state(["!disabled"] if self.variaveis or self.caixas_de_texto else ["disabled"])

    # -- os campos ---------------------------------------------------------

    def _rotulo(self, rotulo: str, linha: int) -> None:
        ttk.Label(self.corpo, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 4), pady=1)

    def _entrada(self, chave: str, rotulo: str, valor: str, linha: int) -> int:
        self._rotulo(rotulo, linha)
        variavel = tk.StringVar(master=self, value=str(valor))
        entrada = ttk.Entry(self.corpo, textvariable=variavel, width=18)
        entrada.grid(row=linha, column=1, sticky="ew", pady=1)
        entrada.bind("<Return>", lambda e: self.aplicar())
        if chave == "href":
            variavel.trace_add("write", lambda *a: self._conferir_destino(variavel.get()))
        self.variaveis[chave] = variavel
        self.entradas[chave] = entrada
        return linha + 1

    def _combo(self, chave: str, rotulo: str, valor: str, opcoes: tuple[str, ...], linha: int) -> int:
        self._rotulo(rotulo, linha)
        variavel = tk.StringVar(master=self, value=str(valor))
        caixa = ttk.Combobox(self.corpo, textvariable=variavel, values=list(opcoes), state="readonly", width=16)
        caixa.grid(row=linha, column=1, sticky="ew", pady=1)
        self.variaveis[chave] = variavel
        self.entradas[chave] = caixa
        return linha + 1

    def _check(self, chave: str, rotulo: str, valor: bool, linha: int) -> int:
        variavel = tk.BooleanVar(master=self, value=bool(valor))
        caixa = ttk.Checkbutton(self.corpo, text=rotulo, variable=variavel)
        caixa.grid(row=linha, column=0, columnspan=2, sticky="w", pady=1)
        self.variaveis[chave] = variavel
        self.entradas[chave] = caixa
        return linha + 1

    def _fixo(self, rotulo: str, valor: str, linha: int) -> int:
        self._rotulo(rotulo, linha)
        ttk.Label(self.corpo, text=valor, wraplength=160, justify="left").grid(row=linha, column=1, sticky="w", pady=1)
        return linha + 1

    def _caixa(self, chave: str, rotulo: str, valor: str, linha: int) -> int:
        self._rotulo(rotulo, linha)
        caixa = tk.Text(self.corpo, width=24, height=6, wrap="none", font=("Consolas", 9), highlightthickness=2,
                        exportselection=False, undo=True)
        caixa.insert("1.0", valor)
        caixa.grid(row=linha, column=0, columnspan=2, sticky="nsew", pady=1)
        self.corpo.rowconfigure(linha, weight=1)
        self.caixas_de_texto[chave] = caixa
        self.entradas[chave] = caixa
        return linha + 1

    def _acao(self, rotulo: str, nome: str) -> None:
        anel = AnelDeFoco(self.rodape, lambda pai: ttk.Button(pai, text=rotulo, command=lambda: self.acao(nome)))
        anel.pack(side="left")
        self.botao_acao = anel.widget

    def _conferir_destino(self, href: str) -> bool:
        """O destino em vermelho quando não existe (só links internos; os externos não se conferem aqui)."""
        entrada = self.entradas.get("href")
        existe = True
        if self.verificar_destino is not None and href and "://" not in href and not href.startswith("mailto:"):
            try:
                existe = bool(self.verificar_destino(href))
            except Exception:      # noqa: BLE001 — a verificação é da janela; falhar não derruba o painel
                existe = True
        if isinstance(entrada, ttk.Entry):
            entrada.configure(foreground=COR_DE_ERRO if not existe else "")
        self.aviso.configure(text="" if existe else f"O destino {href!r} não existe no livro.")
        return existe

    # ------------------------------------------------------------------
    # Aplicar e ações
    # ------------------------------------------------------------------

    def valores(self) -> dict[str, Any]:
        saida: dict[str, Any] = {chave: var.get() for chave, var in self.variaveis.items()}
        for chave, caixa in self.caixas_de_texto.items():
            saida[chave] = caixa.get("1.0", "end-1c")
        return saida

    def definir(self, chave: str, valor: Any) -> None:
        """Um campo, como quem digita nele (o teste usa)."""
        if chave in self.caixas_de_texto:
            self.caixas_de_texto[chave].delete("1.0", "end")
            self.caixas_de_texto[chave].insert("1.0", str(valor))
            return
        if chave not in self.variaveis:
            raise KeyError(chave)
        self.variaveis[chave].set(valor)

    def aplicar(self) -> bool:
        """"Aplicar": grava no modelo o que está nos campos — é o único momento em que o painel grava."""
        texto = self.texto_rico
        if texto is None or not self.alvo.get("tipo"):
            return False
        editor = texto.ativo() if hasattr(texto, "ativo") else texto
        mudou = bool(editor.aplicar_propriedades(self.alvo, self.valores()))
        self.atualizar(forcar=True)
        return mudou

    def acao(self, nome: str) -> Any:
        if self.ao_acao is not None:
            return self.ao_acao(nome, dict(self.alvo))
        return None

    def foco(self) -> None:
        for widget in self.entradas.values():
            try:
                widget.focus_set()
                return
            except tk.TclError:
                continue
        self.botao_aplicar.focus_set()


def _numero(valor: Any) -> str:
    if valor in (None, ""):
        return ""
    try:
        return f"{float(valor):g}"
    except (TypeError, ValueError):
        return str(valor)


__all__ = ["PainelDePropriedades", "ESTILOS", "ALINHAMENTOS", "TITULOS"]
