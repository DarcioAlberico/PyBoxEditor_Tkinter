"""
Os objetos embutidos no modo texto: o registro que liga a janela embutida ao bloco
(ou ao trecho-ilha), o desenho de cada tipo de objeto e o `ObjetoGenerico` que
desenha qualquer bloco que ainda não tem desenho próprio (ED-03/ED-04; SPEC_EDITOR
DEC-03 "Objetos", §8.6–§8.10).

Um diagrama, uma figura, uma tabela ou uma ilha entram no `tk.Text` por
`window_create`, como um caractere. O `RegistroDeObjetos` guarda `nome da janela →
bloco`, e é de lá que o `dump` recupera o bloco **intacto** — a ilha byte a byte, o
diagrama com o FEN e a orientação, sem nada passar por tag. Um objeto **vivo** (a
grade de tabela, que se edita por dentro) registra também quem devolve o modelo
atual (`atualizar`), e o registro pergunta a ele a cada consulta.

## Os desenhos da ED-04

- `ObjetoDeFigura`: a imagem (PNG e GIF pelo `tk.PhotoImage`; JPEG pelo PIL quando há;
  SVG e o resto como caixa com o nome), na largura da figura, com a legenda embaixo.
- `ObjetoDeIlha`: a caixa cinza com o elemento e um trecho do XHTML; a ação principal
  abre o mini-editor modal (`EditorDeIlha`), que só aceita um fragmento legível.
- `ObjetoDeIlhaInline`: um glifo reservado (`⟨cite⟩`) com a dica; o fragmento fica no
  registro.
- `ObjetoDeQuebra` ("— quebra de página —"), `ObjetoDeMarcaDePagina` ("— página n —",
  que **não** quebra), `ObjetoDeSeparador` (a linha do `<hr/>`), `ObjetoDeFaixaDeNotas`
  (o marco "Notas" que abre a faixa de notas, §8.8).
- O diagrama continua `ObjetoGenerico` até a ED-05; a tabela é a `GradeDeTabela`
  (`ui/editor/tabela.py`), criada por quem chama (`ContextoDeObjetos.criar_tabela`).

Todo objeto é alcançável pelo teclado (`takefocus`), com foco visível (§13.2), e
`Enter`/duplo clique chamam `ao_ativar(objeto)` — a ação principal da §7.4.
"""

from __future__ import annotations

import base64
import posixpath
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable

from core.editor import modelo
from core.editor.modelo import (Bloco, Diagrama, Figura, IlhaBruta, MarcaDePagina, QuebraDePagina, Separador,
                                Tabela, Trecho)
from ui.editor.barra import Dica
from ui.editor.dialogos import _Dialogo
from ui.editor.dump import FaixaDeNotas

ROTULOS = {
    "Diagrama": "Diagrama", "Figura": "Figura", "Tabela": "Tabela", "IlhaBruta": "Fora do dialeto",
    "MarcaDePagina": "Página", "QuebraDePagina": "Quebra de página", "Separador": "Separador",
    "FaixaDeNotas": "Notas",
}
DICA_DA_ILHA = "conteúdo fora do dialeto — Enter edita o XHTML; F11 abre o modo código"
FUNDO = "#e6e6e6"
FUNDO_SELECIONADO = "#b8d4ff"
COR_DO_FOCO = "#0645ad"
LARGURA_MAXIMA_PX = 480
#: Pontos → pixels de tela a 96 dpi (o mesmo fator de `tags._px`).
PX_POR_PT = 1.333


def resumo_de(objeto: Any) -> str:
    """O que a caixa cinza escreve ao lado do tipo."""
    if isinstance(objeto, Diagrama):
        lado = {"w": "brancas", "b": "pretas"}.get(objeto.lado, "lado?")
        return f"{objeto.posicao}  ({lado}{', revisar' if objeto.estado == 'revisar' else ''})"
    if isinstance(objeto, Figura):
        return objeto.recurso + (f" — {objeto.alt}" if objeto.alt else "")
    if isinstance(objeto, Tabela):
        return f"{len(objeto.filas)}×{objeto.colunas}"
    if isinstance(objeto, IlhaBruta):
        return f"<{objeto.elemento}>"
    if isinstance(objeto, MarcaDePagina):
        return str(objeto.pagina)
    if isinstance(objeto, Trecho) and objeto.ilha:
        return f"<{nome_do_elemento(objeto.ilha)}>"
    if isinstance(objeto, (QuebraDePagina, Separador, FaixaDeNotas)):
        return ""
    return modelo.texto_de(objeto)[:40] if isinstance(objeto, Bloco) else ""


def nome_do_elemento(xhtml: str) -> str:
    """O nome do primeiro elemento de um fragmento (`<cite>Obra</cite>` → `cite`); `…` para texto."""
    cru = xhtml.lstrip()
    if not cru.startswith("<"):
        return "…"
    if cru.startswith("<!--"):
        return "!--"
    if cru.startswith("<?"):
        return "?" + cru[2:].split(None, 1)[0].rstrip("?>")
    return cru[1:].split(None, 1)[0].rstrip("/>") or "…"


@dataclass
class ContextoDeObjetos:
    """O que o desenho de um objeto precisa de fora: os bytes de um recurso, a largura da tela, a grade."""

    recursos: Callable[[str], bytes | None] | None = None
    largura_maxima_px: int = LARGURA_MAXIMA_PX
    zoom: float = 1.0
    criar_tabela: Callable[[tk.Misc, Tabela], tk.Misc] | None = None
    limite_de_celulas: int = 400

    def dados_de(self, href: str) -> bytes | None:
        if self.recursos is None:
            return None
        try:
            return self.recursos(href)
        except Exception:      # noqa: BLE001 — um recurso que não abre vira caixa com o nome
            return None


class RegistroDeObjetos:
    """`nome da janela → bloco ou trecho`, e o inverso — o que o `dump` e a seleção de objeto consultam."""

    def __init__(self) -> None:
        self._por_nome: dict[str, Any] = {}
        self._por_id: dict[str, str] = {}
        self._widgets: dict[str, Any] = {}
        self._atualizar: dict[str, Callable[[], Any]] = {}

    def registrar(self, nome: str, objeto: Any, widget: Any = None,
                  atualizar: Callable[[], Any] | None = None) -> None:
        """`atualizar` é quem devolve o modelo **atual** de um objeto vivo (a grade de tabela)."""
        self._por_nome[nome] = objeto
        if isinstance(objeto, Bloco):
            self._por_id[objeto.id] = nome
        if widget is not None:
            self._widgets[nome] = widget
        if atualizar is not None:
            self._atualizar[nome] = atualizar

    def objeto(self, nome: str) -> Any:
        atualizar = self._atualizar.get(nome)
        if atualizar is not None:
            novo = atualizar()
            if novo is not None:
                self._por_nome[nome] = novo
        return self._por_nome.get(nome)

    def objeto_registrado(self, nome: str) -> Any:
        """O objeto como foi registrado, sem perguntar ao widget vivo."""
        return self._por_nome.get(nome)

    def substituir(self, nome: str, objeto: Any) -> None:
        """Troca o objeto de uma janela que continua a mesma (a figura que mudou de largura)."""
        antigo = self._por_nome.get(nome)
        if isinstance(antigo, Bloco):
            self._por_id.pop(antigo.id, None)
        self._por_nome[nome] = objeto
        if isinstance(objeto, Bloco):
            self._por_id[objeto.id] = nome

    def widget_de(self, nome: str) -> Any:
        return self._widgets.get(nome)

    def nome_de(self, bloco_id: str) -> str | None:
        return self._por_id.get(bloco_id)

    def esquecer(self, nome: str) -> None:
        objeto = self._por_nome.pop(nome, None)
        if isinstance(objeto, Bloco):
            self._por_id.pop(objeto.id, None)
        self._widgets.pop(nome, None)
        self._atualizar.pop(nome, None)

    def limpar(self) -> None:
        self._por_nome.clear()
        self._por_id.clear()
        self._widgets.clear()
        self._atualizar.clear()

    def __contains__(self, nome: str) -> bool:
        return nome in self._por_nome

    def __len__(self) -> int:
        return len(self._por_nome)

    # O registro serve de `Mapping` ao `dump`: `get` e `[]` devolvem o objeto vivo atualizado.
    def get(self, nome: str, padrao: Any = None) -> Any:
        if nome not in self._por_nome:
            return padrao
        return self.objeto(nome)

    def __getitem__(self, nome: str) -> Any:
        if nome not in self._por_nome:
            raise KeyError(nome)
        return self.objeto(nome)

    def nomes(self) -> list[str]:
        return list(self._por_nome)

    def como_dicionario(self) -> dict[str, Any]:
        """Os objetos por nome, com os vivos atualizados — o que o `dump` recebe."""
        return {nome: self.objeto(nome) for nome in list(self._por_nome)}


# ----------------------------------------------------------------------
# A base dos desenhos
# ----------------------------------------------------------------------

class ObjetoBase(ttk.Frame):
    """
    Um frame com um rótulo focável por dentro: `selecionar(sim)`, a dica, e
    `Enter`/duplo clique → `ao_ativar(objeto)`. As subclasses montam o miolo em
    `_montar()` e podem trocar o rótulo focável (`self.rotulo`).
    """

    inline = False

    def __init__(self, master: tk.Misc, objeto: Any, inline: bool = False, ao_ativar: Any = None,
                 contexto: ContextoDeObjetos | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.objeto = objeto
        self.inline = inline
        self.ao_ativar = ao_ativar
        self.contexto = contexto or ContextoDeObjetos()
        self.rotulo: tk.Widget = self._montar()
        self._instalar()

    def _montar(self) -> tk.Widget:      # pragma: no cover — cada objeto faz o seu
        raise NotImplementedError

    def _rotulo(self, texto: str, **kw: Any) -> tk.Label:
        opcoes: dict[str, Any] = {"text": texto, "relief": "groove", "borderwidth": 1,
                                  "padx": 3 if self.inline else 6, "pady": 0 if self.inline else 3,
                                  "background": FUNDO, "foreground": "#333333", "takefocus": 1,
                                  "cursor": "arrow", "highlightthickness": 2, "highlightbackground": FUNDO,
                                  "highlightcolor": COR_DO_FOCO}
        opcoes.update(kw)
        return tk.Label(self, **opcoes)

    def _instalar(self) -> None:
        dica = self.dica()
        if dica:
            Dica(self.rotulo, dica)
        self.rotulo.bind("<Double-Button-1>", self._ativar)
        self.rotulo.bind("<Return>", self._ativar)

    def _ativar(self, _evento: Any = None) -> str:
        if self.ao_ativar is not None:
            self.ao_ativar(self.objeto)
        return "break"

    def dica(self) -> str:
        return ""

    @property
    def texto(self) -> str:
        try:
            return str(self.rotulo.cget("text"))
        except tk.TclError:
            return ""

    def selecionar(self, sim: bool) -> None:
        try:
            self.rotulo.configure(background=FUNDO_SELECIONADO if sim else FUNDO)
        except tk.TclError:
            pass

    def atualizar(self, objeto: Any) -> None:
        """O objeto mudou (propriedades aplicadas): redesenha o miolo."""
        self.objeto = objeto
        for filho in self.winfo_children():
            filho.destroy()
        self.rotulo = self._montar()
        self._instalar()


class ObjetoGenerico(ObjetoBase):
    """
    A caixa cinza: o tipo do bloco, um resumo, e uma dica para a ilha. É um botão de
    verdade por dentro (`tk.Label` com `takefocus`), para o teclado alcançar (§13.2).
    """

    def _montar(self) -> tk.Widget:
        objeto = self.objeto
        tipo = type(objeto).__name__
        if isinstance(objeto, Trecho):
            texto = resumo_de(objeto)
        else:
            resumo = resumo_de(objeto)
            rotulo = ROTULOS.get(tipo, tipo)
            texto = f"{rotulo}: {resumo}" if resumo else rotulo
        rotulo = self._rotulo(texto)
        rotulo.pack(fill="x")
        return rotulo

    def dica(self) -> str:
        return DICA_DA_ILHA if isinstance(self.objeto, (IlhaBruta, Trecho)) else ""


# ----------------------------------------------------------------------
# Figura
# ----------------------------------------------------------------------

def imagem_de(dados: bytes, largura_px: int | None = None, largura_maxima_px: int = LARGURA_MAXIMA_PX,
              master: tk.Misc | None = None) -> tk.PhotoImage | None:
    """
    Um `PhotoImage` dos bytes, na largura pedida (ou no máximo da tela). PNG e GIF pelo
    Tk; o resto pelo PIL, importado só aqui (DEC-07); `None` quando ninguém lê.
    """
    alvo = int(largura_px) if largura_px else None
    imagem: tk.PhotoImage | None = None
    try:
        imagem = tk.PhotoImage(master=master, data=base64.b64encode(dados))
    except tk.TclError:
        imagem = None
    if imagem is not None:
        largura = imagem.width()
        limite = alvo or min(largura, largura_maxima_px)
        if largura > limite > 0:
            fator = -(-largura // limite)           # teto: a imagem nunca passa da largura
            try:
                return imagem.subsample(fator, fator)
            except tk.TclError:
                return imagem
        return imagem
    try:
        import io

        from PIL import Image, ImageTk
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(dados)) as im:
            im.load()
            largura, altura = im.size
            limite = alvo or min(largura, largura_maxima_px)
            if largura != limite and limite > 0:
                im = im.resize((limite, max(1, int(round(altura * limite / largura)))))
            return ImageTk.PhotoImage(im, master=master)
    except Exception:      # noqa: BLE001 — imagem ilegível vira caixa com o nome
        return None


class ObjetoDeFigura(ObjetoBase):
    """A figura na largura dela, com a legenda embaixo; sem imagem legível, uma caixa com o nome."""

    def _montar(self) -> tk.Widget:
        figura: Figura = self.objeto
        self.imagem = None
        dados = self.contexto.dados_de(figura.recurso)
        largura_px = None
        if figura.largura_pt is not None:
            largura_px = max(8, int(round(figura.largura_pt * PX_POR_PT * self.contexto.zoom)))
        if dados:
            self.imagem = imagem_de(dados, largura_px, self.contexto.largura_maxima_px, master=self)
        if self.imagem is not None:
            rotulo = self._rotulo("", image=self.imagem, relief="flat", padx=0, pady=0, background="#ffffff",
                                  highlightbackground="#ffffff")
        else:
            nome = posixpath.basename(figura.recurso)
            rotulo = self._rotulo(f"Figura: {nome}" + (f" — {figura.alt}" if figura.alt else ""),
                                  width=max(12, min(48, (largura_px or 240) // 8)))
        rotulo.pack()
        legenda = "".join(t.texto for t in figura.legenda)
        if legenda or figura.numero is not None:
            prefixo = f"Figura {figura.numero}. " if figura.numero is not None else ""
            tk.Label(self, text=prefixo + legenda, foreground="#444444", background="#ffffff",
                     wraplength=max(120, largura_px or self.contexto.largura_maxima_px), justify="center").pack()
        return rotulo

    def dica(self) -> str:
        figura: Figura = self.objeto
        alt = figura.alt or "(sem alt — a leitura em voz alta não sabe o que é)"
        return f"{figura.recurso}\nalt: {alt}\nEnter ou Alt+Enter: propriedades"

    def selecionar(self, sim: bool) -> None:
        cor = FUNDO_SELECIONADO if sim else ("#ffffff" if self.imagem is not None else FUNDO)
        try:
            self.rotulo.configure(background=cor, highlightbackground=cor)
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# Ilhas
# ----------------------------------------------------------------------

def _previa(xhtml: str, largura: int = 60) -> str:
    plano = " ".join(xhtml.split())
    return plano if len(plano) <= largura else plano[: largura - 1] + "…"


class ObjetoDeIlha(ObjetoBase):
    """A ilha de bloco: `<svg>` e um trecho do XHTML; a ação principal é o mini-editor."""

    def _montar(self) -> tk.Widget:
        ilha: IlhaBruta = self.objeto
        rotulo = self._rotulo(f"<{ilha.elemento}>  {_previa(ilha.xhtml)}", anchor="w", justify="left")
        rotulo.pack(fill="x")
        return rotulo

    def dica(self) -> str:
        return DICA_DA_ILHA + "\n" + _previa(self.objeto.xhtml, 200)


class ObjetoDeIlhaInline(ObjetoBase):
    """A ilha inline: um glifo reservado com o nome do elemento; o fragmento mora no registro."""

    def _montar(self) -> tk.Widget:
        trecho: Trecho = self.objeto
        rotulo = self._rotulo(f"⟨{nome_do_elemento(trecho.ilha)}⟩", padx=2, pady=0, foreground="#5a3e8a")
        rotulo.pack()
        return rotulo

    def dica(self) -> str:
        return DICA_DA_ILHA + "\n" + _previa(self.objeto.ilha, 200)


class EditorDeIlha(_Dialogo):
    """
    O mini-editor modal de uma ilha: o XHTML numa caixa monoespaçada, aceito só quando
    `xhtml.ler_fragmento` o lê (bem-formado, prefixos declarados). Constrói-se sem
    mostrar (`construir()`), para o teste escrever na caixa e chamar `confirmar()`.
    """

    def __init__(self, master: tk.Misc, xhtml: str, titulo: str = "Ilha de XHTML"):
        super().__init__(master, titulo)
        self.xhtml = xhtml
        self.caixa: tk.Text | None = None
        self.erro = ""

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=8)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        ttk.Label(corpo, text="O fragmento XHTML da ilha (bem-formado, com todo prefixo declarado):").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.caixa = tk.Text(corpo, width=80, height=16, wrap="none", font=("Consolas", 10), undo=True,
                             highlightthickness=2, exportselection=False)
        self.caixa.insert("1.0", self.xhtml)
        barra_v = ttk.Scrollbar(corpo, orient="vertical", command=self.caixa.yview)
        self.caixa.configure(yscrollcommand=barra_v.set)
        self.caixa.grid(row=1, column=0, sticky="nsew")
        barra_v.grid(row=1, column=1, sticky="ns")
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.rotulo_de_erro = ttk.Label(corpo, text="", foreground="#b00020", wraplength=560, justify="left")
        self.rotulo_de_erro.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        botoes = self._botoes(corpo)
        botoes.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        top.unbind("<Return>")                       # Enter é quebra de linha na caixa
        return top

    def texto(self) -> str:
        if self.caixa is None:
            return self.xhtml
        return self.caixa.get("1.0", "end-1c")

    def definir_texto(self, texto: str) -> None:
        self.construir()
        assert self.caixa is not None
        self.caixa.delete("1.0", "end")
        self.caixa.insert("1.0", texto)

    def validar(self) -> str:
        """Vazio quando o fragmento é legível; senão a mensagem de erro (fica no diálogo)."""
        from core.editor import xhtml

        texto = self.texto().strip()
        if not texto:
            return "a ilha não pode ficar vazia — para apagá-la, apague o objeto no texto"
        try:
            xhtml.ler_fragmento(texto)
        except ValueError as erro:
            return str(erro)
        return ""

    def confirmar(self) -> Any:
        self.erro = self.validar()
        if self.erro:
            if self.top is not None:
                self.rotulo_de_erro.configure(text=self.erro)
            self.resultado = None
            return None
        return super().confirmar()

    def _ler(self) -> str:
        return self.texto().strip()

    def _foco_inicial(self) -> None:
        if self.caixa is not None:
            self.caixa.focus_set()


# ----------------------------------------------------------------------
# Quebras, marca de página, separador, faixa de notas
# ----------------------------------------------------------------------

class ObjetoDeQuebra(ObjetoBase):
    def _montar(self) -> tk.Widget:
        rotulo = self._rotulo("— quebra de página —", relief="flat", foreground="#666666", background="#ffffff",
                              highlightbackground="#ffffff")
        rotulo.pack()
        return rotulo

    def dica(self) -> str:
        return "Quebra de página pedida: quebra no DOCX e no PDF"

    def selecionar(self, sim: bool) -> None:
        self.rotulo.configure(background=FUNDO_SELECIONADO if sim else "#ffffff")


class ObjetoDeMarcaDePagina(ObjetoBase):
    def _montar(self) -> tk.Widget:
        marca: MarcaDePagina = self.objeto
        rotulo = self._rotulo(f"— página {marca.pagina} —", relief="flat", foreground="#8a8a8a",
                              background="#ffffff", highlightbackground="#ffffff")
        rotulo.pack()
        return rotulo

    def dica(self) -> str:
        return f"Página {self.objeto.pagina} do impresso: marcador para a lista de páginas; não quebra"

    def selecionar(self, sim: bool) -> None:
        self.rotulo.configure(background=FUNDO_SELECIONADO if sim else "#ffffff")


class ObjetoDeSeparador(ObjetoBase):
    LARGURA = 240

    def _montar(self) -> tk.Widget:
        rotulo = tk.Frame(self, height=2, width=self.LARGURA, background="#999999", takefocus=1,
                          highlightthickness=2, highlightbackground="#ffffff", highlightcolor=COR_DO_FOCO,
                          cursor="arrow")
        rotulo.pack(pady=4)
        return rotulo

    @property
    def texto(self) -> str:
        return "—" * 3

    def dica(self) -> str:
        return "Separador (<hr/>)"

    def selecionar(self, sim: bool) -> None:
        self.rotulo.configure(background=FUNDO_SELECIONADO if sim else "#999999")


class ObjetoDeFaixaDeNotas(ObjetoBase):
    """O marco da faixa de notas: uma linha com "Notas" — o que vem depois são as notas do capítulo."""

    def _montar(self) -> tk.Widget:
        rotulo = self._rotulo("Notas", relief="ridge", foreground="#7a3e00", background="#f6efe6",
                              highlightbackground="#f6efe6", padx=10, pady=1, font=("Segoe UI", 8, "bold"))
        rotulo.pack()
        return rotulo

    def dica(self) -> str:
        return "As notas de rodapé e de fim do capítulo; Esc volta à referência"


# ----------------------------------------------------------------------
# A fábrica
# ----------------------------------------------------------------------

def criar_objeto(master: tk.Misc, objeto: Any, inline: bool = False, ao_ativar: Any = None,
                 contexto: ContextoDeObjetos | None = None) -> tk.Misc:
    """O widget que desenha `objeto` — o específico da ED-04, ou o `ObjetoGenerico`."""
    contexto = contexto or ContextoDeObjetos()
    if isinstance(objeto, Trecho):
        return ObjetoDeIlhaInline(master, objeto, True, ao_ativar, contexto)
    if isinstance(objeto, Figura):
        return ObjetoDeFigura(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, IlhaBruta):
        return ObjetoDeIlha(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, QuebraDePagina):
        return ObjetoDeQuebra(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, MarcaDePagina):
        return ObjetoDeMarcaDePagina(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, Separador):
        return ObjetoDeSeparador(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, FaixaDeNotas):
        return ObjetoDeFaixaDeNotas(master, objeto, inline, ao_ativar, contexto)
    if isinstance(objeto, Tabela) and contexto.criar_tabela is not None \
            and len(objeto.filas) * objeto.colunas <= contexto.limite_de_celulas:
        return contexto.criar_tabela(master, objeto)
    return ObjetoGenerico(master, objeto, inline, ao_ativar, contexto)


__all__ = ["RegistroDeObjetos", "ContextoDeObjetos", "ObjetoBase", "ObjetoGenerico", "ObjetoDeFigura",
           "ObjetoDeIlha", "ObjetoDeIlhaInline", "EditorDeIlha", "ObjetoDeQuebra", "ObjetoDeMarcaDePagina",
           "ObjetoDeSeparador", "ObjetoDeFaixaDeNotas", "criar_objeto", "imagem_de", "resumo_de",
           "nome_do_elemento", "ROTULOS", "DICA_DA_ILHA", "LARGURA_MAXIMA_PX", "PX_POR_PT"]
