"""
`JanelaDoEditor`: a janela de edição de livros — painéis, abas, menus, atalhos,
barras, barra de status, Mensagens, Resultados, Validação, a guarda ao fechar, o
rascunho automático e as três portas de entrada (ED-02; SPEC_EDITOR §7, §13, DEC-09).

## O que a janela é, e o que não é

A janela segura um `Projeto` (ED-01) e desenha cada arquivo aberto numa aba com o
`TextoRico` (ED-03) ou o `EditorDeCodigo` (ED-07). Ela não sabe formatar, realçar
nem gravar: **despacha**. Todo caminho — item de menu, botão de barra, acorde de
teclado, menu de contexto — chega a `executar(nome)`, que procura `comandos[nome]`
na hora e trata o erro em duas camadas (§13.3): `ValueError` é erro de entrada e
vira uma caixa simples com o que fazer; qualquer outra exceção é defeito do
programa e vira a caixa de falha com o traceback dobrado e "Copiar" — e a janela
continua viva (AC-ED02-8). É por isso que o teste troca `comandos[nome]` por um
espião e prova os três caminhos de uma vez (§14).

## Quem é o dono do capítulo

O modo é da aba (§7.1). Em texto, o `TextoRico` é o dono e `sincronizar()` devolve
o capítulo; em código, o texto do widget é o `Capitulo.texto_cru` (DEC-01, INV-09).
`alternar_modo` faz a passagem pelas funções puras `xhtml.escrever` e `xhtml.ler`:
texto → código sempre; código → texto **só** com o XHTML bem-formado e todo
prefixo declarado — senão fica em código, com linha e coluna na barra, em
Mensagens e em Validação, e o cursor na linha (AC-ED02-5). Salvar sincroniza toda
aba aberta de volta ao modelo antes de `Projeto.salvar`; o rascunho de 60 s faz o
mesmo, por `after` de um segundo, com o relógio injetável do `Rascunho`.

## As fases seguintes

Cada fase liga o que entrega por `registrar_comandos({nome: função}, modos=…)` — o
item de menu já existe (§7.3, `ui/editor/menus.py`) e acorda sozinho; até lá, ele
diz a fase na barra de status ao ser percorrido. `modos_do_comando` restringe um
comando registrado a um modo.

## A ED-04 na janela

Os objetos do modo texto (§8.6–§8.11) chegam por `_registrar_comandos_da_ed04`: a
área de transferência (`core/editor/area_de_transferencia.py`, com o acesso ao sistema
injetado daqui — `clipboard_get`/`clipboard_append` e o `ImageGrab` do PIL, lazy), o
painel Propriedades (`ui/editor/propriedades.py`, que só grava em "Aplicar"), a ação
principal de um objeto (`acao_principal`: tabela → primeira célula; nota → a nota; ilha
→ o mini-editor; diagrama → a ED-05; o resto → o painel), "Seguir link" (que troca de
aba e leva ao bloco; destino inexistente fica vermelho no painel e vai a Resultados),
imagem de arquivo → recurso do livro, tabela, ilha, notas, quebras, e "Dividir capítulo
aqui"/"Juntar com o anterior" por `livro_ops`, com as abas e o sumário recarregados.

## A ED-06 na janela

`_registrar_comandos_da_ed06` liga o painel Busca (`ui/editor/busca.py`: o `Buscador`
traduz a ocorrência do modelo em seleção na aba, e procura no widget quando a aba está
aberta e no modelo quando não está), a ortografia (`ui/editor/ortografia.py: Corretor`,
com os léxicos por idioma em `lexicos()` e o dicionário do livro ao lado do EPUB), "Ir
para…" nos dois modos, a caixa de símbolos, o `Ctrl+Shift+X` e as estatísticas.

## A ED-08 na janela

O navegador e o sumário viraram painéis próprios (`ui/editor/navegador.py`,
`ui/editor/sumario.py`) que chamam a janela por comando; o menu Livro inteiro, os
relatórios, a validação, as limpezas, a prévia (`F12`) e os metadados completos moram
em `ui/editor/operacoes.py: OperacoesDoLivro`, registrado por
`_registrar_comandos_da_ed08`. O OPF abre só para leitura (`epub.texto_do_opf`), e os
clipes passam a valer no modo texto (o fragmento vira modelo).

## A ED-11 na janela

A ponte com o documento editorial mora em `Projeto` (`documento_editorial`, `diario`,
`ponte`) e em `core/editor/importar_ir.py`; aqui ficam "Importar ▸ JSON editorial…" e
`abrir_documento_editorial` (`ui/editor/conversoes.py`), "Abrir…" com `.json`, o
`descrever_suspeita` que o painel Propriedades usa para mostrar motivos e leituras do
bloco suspeito, a ação "Marcar como revisto" e as linhas da ponte no log ao salvar.

## A ED-05 na janela

`ui/editor/xadrez.py: Xadrez` é dono do menu Xadrez (`_registrar_comandos_da_ed05`): o
diagrama entra e se edita pela `DialogoDeDiagrama` (`ui/editor/diagrama.py`), o painel
Xadrez e a barra de xadrez são a paleta (`ui/editor/paleta.py`), a validação vai a
Resultados com a tag `notacao-ilegal` e o `✗` na calha, e o gancho `ao_fechar_token` do
`TextoRico` faz as figurinas ao digitar. `Enter` sobre um diagrama abre o editor de posição.

## A ED-10 na janela

`ui/editor/conversoes.py: Conversoes` é dona de "Exportar…" (EPUB, HTML único, HTML em
pasta, TXT), de "Importar ▸" (HTML/XHTML e TXT viram capítulos do livro aberto, ou o
livro, sem livro aberto; EPUB é anexado) e de "Juntar/Dividir em capítulos por título" e
"Dividir nos marcadores"; `abrir` aceita `.html`/`.xhtml`/`.txt` e os abre como livro.
"""

from __future__ import annotations

import os
import posixpath
import re
import time
import tkinter as tk
import traceback
import webbrowser
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable, Iterable

from core.editor import area_de_transferencia as area_mod
from core.editor import epub, estatisticas, livro_ops, modelo, sumario, xhtml
from core.editor.clipes import Clipes
from core.editor.modelo import (Capitulo, Celula, Diagrama, Figura, IlhaBruta, Paragrafo, Pessoa, Recurso, Tabela,
                                Trecho)
from core.editor.projeto import Projeto, Rascunho, Recentes
from core.editor.xhtml import ErroDeXhtml
from ui.editor import atalhos as atalhos_mod
from ui.editor import barra as barra_mod
from ui.editor import menus as menus_mod
from ui.editor.abas import Aba, Abas
from ui.editor.busca import Buscador, PainelDeBusca
from ui.editor.buscas_salvas import BuscasSalvas
from ui.editor.codigo import EditorDeCodigo
from ui.editor.conversoes import (EXTENSOES_DE_DOCX, EXTENSOES_DE_HTML, EXTENSOES_DE_JSON, EXTENSOES_DE_TXT, FORMATOS,
                                  Conversoes)
from ui.editor.dialogos import Caixas
from ui.editor.estilos import PainelDeEstilos
from ui.editor.mensagens import PainelDeMensagens, logger
from ui.editor.navegador import Navegador
from ui.editor.operacoes import OperacoesDoLivro
from ui.editor.ortografia import Corretor
from ui.editor.propriedades import PainelDePropriedades
from ui.editor.resultados import PainelDeResultados, Resultado
from ui.editor.sumario import PainelDeSumario
from ui.editor.tabela import GradeDeTabela
from ui.editor.tags import EstiloDeTela
from ui.editor.tipografia import Tipografo
from ui.editor.texto_rico import TextoRico
from ui.editor.xadrez import Xadrez

TITULO = "Editor de livro"
CHAVE_DAS_PREFERENCIAS = "editor"
INTERVALO_DO_RASCUNHO_S = 60.0
#: A ordem lógica de tabulação da §7.1 — fixa, independente do encaixe.
ORDEM_DOS_PAINEIS = ("navegador", "sumario", "estilos", "editor", "propriedades", "xadrez", "busca", "resultados",
                     "mensagens", "validacao")
#: (formato, rótulo, fase) — a tabela inteira mora em `ui/editor/conversoes.py` desde a ED-10.
FORMATOS_DE_EXPORTACAO = tuple((f, r, fase) for f, r, fase, _e, _t in FORMATOS)
IDIOMAS = ("pt", "en", "es", "fr", "de", "it", "ru")
_RE_TAG = re.compile(r"<[^>]*>")
_RE_ID = re.compile(r'\bid\s*=\s*"([^"]*)"')


@dataclass
class Painel:
    nome: str
    grupo: str                      # "esquerda" | "centro" | "direita" | "inferior"
    widget: tk.Misc                 # o contêiner que se mostra e esconde
    foco: Callable[[], Any]         # o que recebe o foco
    visivel: bool = True


class _Despacho:
    """O que `atalhos.ligar` consulta: só o comando que existe **e** vale no modo atual."""

    def __init__(self, janela: "JanelaDoEditor"):
        self.janela = janela

    def get(self, nome: str) -> Callable[[], Any] | None:
        if not self.janela.disponivel(nome):
            return None
        return lambda n=nome: self.janela.executar(n)

    def __contains__(self, nome: str) -> bool:
        return self.janela.disponivel(nome)


class JanelaDoEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, projeto: Projeto | None = None, task_controller: Any = None,
                 documento_editorial: Any = None, *, settings: Any = None,
                 relogio: Callable[[], float] = time.monotonic, ao_fechar: Callable[[], Any] | None = None,
                 tema_codigo: str | None = None):
        super().__init__(parent)
        self.parent = parent
        self.title(TITULO)
        self.relogio = relogio
        self.ao_fechar = ao_fechar
        self.documento_editorial = documento_editorial
        self.settings = settings if settings is not None else _settings_padrao()
        self.caixas = Caixas(self)
        self.log = logger()
        self.projeto: Projeto | None = None
        self.rascunho: Rascunho | None = None
        self.recentes = Recentes(self.settings)
        self.clipes = Clipes.carregar(self.settings)
        self.comandos: dict[str, Callable[..., Any]] = {}
        self.modos_do_comando: dict[str, tuple[str, ...]] = {}
        self.variaveis: dict[str, tk.BooleanVar] = {}
        self.itens_dinamicos: dict[str, Callable[[], list[tuple[str, Callable[[], Any] | None]]]] = {
            "recentes": self._itens_recentes, "clipes": self._itens_de_clipes,
            "semantica": lambda: self.operacoes.itens_de_semantica()}
        self.paineis: dict[str, Painel] = {}
        self.ultimo_erro: tuple[str, str] | None = None
        self._tique_id: str | None = None
        self._contagem_id: str | None = None
        self._pincel_carregado = False
        self._salvo_em = ""
        self._tela_cheia = False
        self._protocolo_anterior: str | None = None
        self._despacho = _Despacho(self)
        self._tema_codigo = tema_codigo or self._preferencia("tema_codigo", "claro")
        #: A área de transferência (§8.11): o acesso ao sistema é injetado daqui (o teste troca).
        self.area = area_mod.AreaDeTransferencia(self._ler_clipboard, self._gravar_clipboard, _imagem_do_clipboard)
        self.abrir_url: Callable[[str], Any] = webbrowser.open
        #: Os arquivos marcados no navegador para o escopo "arquivos marcados" da busca (ED-06).
        self.arquivos_marcados: set[str] = set()
        self._lexicos_cache: tuple[str | None, Any] | None = None

        self.task = task_controller if task_controller is not None else _task_controller(self)
        self._construir()
        self._registrar_comandos_da_ed02()
        self._registrar_comandos_da_ed04()
        self._registrar_comandos_da_ed06()
        self._registrar_comandos_da_ed06b()
        self._registrar_comandos_da_ed08()
        self._registrar_comandos_da_ed10()
        self._registrar_comandos_da_ed05()
        self.menus = menus_mod.Menus(self)
        self.configure(menu=self.menus.barra)
        atalhos_mod.ligar(self, atalhos_mod.TABELA, self._despacho, self.modo_atual, escopos=("janela", "fundo"),
                          frente=False)
        self.mensagens.instalar(self.log)
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self._instalar_guarda_no_parent()
        self._restaurar_layout()
        if projeto is not None:
            self._instalar_projeto(projeto)
        self.atualizar()
        self._agendar_tique()

    # ==================================================================
    # Construção
    # ==================================================================

    def _construir(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.barras = ttk.Frame(self)
        self.barras.grid(row=0, column=0, sticky="ew")
        self.barra_de_arquivo = barra_mod.Barra(self.barras, self, barra_mod.BOTOES_DE_ARQUIVO, "arquivo")
        self.barra_de_arquivo.pack(side="top", fill="x")
        self.barra_de_formatacao = barra_mod.Barra(self.barras, self, barra_mod.BOTOES_DE_FORMATACAO, "formatacao")
        self.barra_de_codigo = barra_mod.Barra(self.barras, self, barra_mod.BOTOES_DE_CODIGO, "codigo")
        self.barra_de_formatacao.pack(side="top", fill="x")
        self.barra_de_xadrez = barra_mod.BarraDeXadrez(self.barras, self)
        self.barra_de_xadrez.pack(side="top", fill="x")
        self.barra_de_clipes: Any = None

        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.grid(row=1, column=0, sticky="nsew")
        self.esquerda = ttk.PanedWindow(self.paned, orient="vertical")
        self.centro = ttk.PanedWindow(self.paned, orient="vertical")
        self.direita = ttk.PanedWindow(self.paned, orient="vertical")
        self.paned.add(self.esquerda, weight=1)
        self.paned.add(self.centro, weight=4)
        self.paned.add(self.direita, weight=1)

        # Esquerda: Navegador, Sumário, Estilos
        self.quadro_navegador = ttk.LabelFrame(self.esquerda, text="Navegador")
        self.painel_navegador = Navegador(self.quadro_navegador, self)
        self.painel_navegador.pack(fill="both", expand=True)
        self.navegador = self.painel_navegador.arvore
        self.quadro_sumario = ttk.LabelFrame(self.esquerda, text="Sumário")
        self.painel_sumario = PainelDeSumario(self.quadro_sumario, self)
        self.painel_sumario.pack(fill="both", expand=True)
        self.arvore_do_sumario = self.painel_sumario.arvore
        self.quadro_estilos = ttk.LabelFrame(self.esquerda, text="Estilos")
        self._texto_de_reserva = TextoRico(self.quadro_estilos)          # o alvo do painel sem aba aberta
        self.painel_de_estilos = PainelDeEstilos(self.quadro_estilos, self._texto_de_reserva, "",
                                                 ao_gravar=self._gravar_folha_padrao)
        self.painel_de_estilos.pack(fill="both", expand=True)
        for quadro in (self.quadro_navegador, self.quadro_sumario, self.quadro_estilos):
            self.esquerda.add(quadro, weight=1)

        # Centro: abas e o caderno de baixo
        self.abas = Abas(self.centro, ao_trocar=self._trocou_de_aba)
        self.inferior = ttk.Notebook(self.centro)
        self.busca = PainelDeBusca(self.inferior, ao_executar=self.executar,
                                   historico=self._preferencia("buscas", []) or [],
                                   ao_gravar_historico=lambda itens: self._gravar_preferencia("buscas", itens))
        self.resultados = PainelDeResultados(self.inferior, ao_ativar=self._ativar_resultado)
        self.mensagens = PainelDeMensagens(self.inferior)
        self.validacao = PainelDeResultados(self.inferior, ao_ativar=self._ativar_resultado)
        self.inferior.add(self.busca, text="Busca")
        self.inferior.add(self.resultados, text="Resultados")
        self.inferior.add(self.mensagens, text="Mensagens")
        self.inferior.add(self.validacao, text="Validação")
        self.inferior.enable_traversal()
        self.centro.add(self.abas, weight=4)
        self.centro.add(self.inferior, weight=1)

        # Direita: Propriedades, Xadrez
        self.quadro_propriedades = ttk.LabelFrame(self.direita, text="Propriedades")
        self.painel_de_propriedades = PainelDePropriedades(self.quadro_propriedades, None,
                                                           ao_acao=self._acao_das_propriedades,
                                                           verificar_destino=self.destino_existe,
                                                           descrever_suspeita=self.descrever_suspeita)
        self.painel_de_propriedades.pack(fill="both", expand=True)
        self.propriedades = self.painel_de_propriedades
        self.quadro_xadrez = ttk.LabelFrame(self.direita, text="Xadrez")
        self.xadrez = tk.Label(self.quadro_xadrez, text="Paleta de xadrez (ED-05)", anchor="nw",
                               takefocus=1, highlightthickness=2, padx=6, pady=4, wraplength=200, justify="left")
        self.xadrez.pack(fill="both", expand=True)
        self.direita.add(self.quadro_propriedades, weight=1)
        self.direita.add(self.quadro_xadrez, weight=1)

        # Status
        self.status_bar = ttk.Frame(self, relief="sunken")
        self.status_bar.grid(row=2, column=0, sticky="ew")
        self.campos: dict[str, ttk.Label] = {}
        for nome in ("capitulo", "posicao", "palavras", "idioma", "modo", "estado"):
            rotulo = ttk.Label(self.status_bar, text="", padding=(6, 2))
            rotulo.pack(side="left")
            ttk.Separator(self.status_bar, orient="vertical").pack(side="left", fill="y", pady=2)
            self.campos[nome] = rotulo
        self.campos["aviso"] = ttk.Label(self.status_bar, text="", padding=(6, 2), anchor="w")
        self.campos["aviso"].pack(side="left", fill="x", expand=True)

        self.paineis = {
            "navegador": Painel("navegador", "esquerda", self.quadro_navegador, self._focar_navegador),
            "sumario": Painel("sumario", "esquerda", self.quadro_sumario, self._focar_sumario),
            "estilos": Painel("estilos", "esquerda", self.quadro_estilos, self.painel_de_estilos.lista.focus_set),
            "editor": Painel("editor", "centro", self.abas, self.foco_no_editor),
            "propriedades": Painel("propriedades", "direita", self.quadro_propriedades,
                                   self.painel_de_propriedades.foco),
            "xadrez": Painel("xadrez", "direita", self.quadro_xadrez, self.xadrez.focus_set),
            "busca": Painel("busca", "inferior", self.busca, lambda: self._focar_inferior(self.busca, self.busca.foco)),
            "resultados": Painel("resultados", "inferior", self.resultados,
                                 lambda: self._focar_inferior(self.resultados, self.resultados.foco)),
            "mensagens": Painel("mensagens", "inferior", self.mensagens,
                                lambda: self._focar_inferior(self.mensagens, self.mensagens.foco)),
            "validacao": Painel("validacao", "inferior", self.validacao,
                                lambda: self._focar_inferior(self.validacao, self.validacao.foco)),
        }
        for nome in ("navegador", "sumario", "estilos", "propriedades", "xadrez", "busca", "barra_de_formatacao",
                     "barra_de_xadrez", "invisiveis", "quebra_automatica", "tela_cheia", "numeros_de_linha",
                     "realce_da_linha", "figurinas_ao_digitar"):
            self.variaveis[nome] = tk.BooleanVar(master=self, value=nome not in ("invisiveis", "tela_cheia"))

    def _focar_inferior(self, painel: tk.Misc, foco: Callable[[], Any] | None = None) -> None:
        try:
            self.inferior.select(painel)
        except tk.TclError:
            pass
        (foco or painel.focus_set)()

    def _focar_navegador(self) -> None:
        self.navegador.focus_set()
        if not self.navegador.focus() and self.navegador.get_children():
            primeiro = self.navegador.get_children()[0]
            self.navegador.focus(primeiro)
            self.navegador.selection_set(primeiro)

    def _focar_sumario(self) -> None:
        self.arvore_do_sumario.focus_set()
        filhos = self.arvore_do_sumario.get_children()
        if not self.arvore_do_sumario.focus() and filhos:
            self.arvore_do_sumario.focus(filhos[0])
            self.arvore_do_sumario.selection_set(filhos[0])

    # ==================================================================
    # Comandos: registro e despacho
    # ==================================================================

    def registrar_comandos(self, fonte: Any, modos: tuple[str, ...] | None = None) -> None:
        """`fonte` é um dict `nome → função` ou um objeto/módulo com `.comandos`; `modos` restringe todos."""
        comandos = fonte if isinstance(fonte, dict) else getattr(fonte, "comandos")
        for nome, funcao in comandos.items():
            self.comandos[nome] = funcao
            if modos is not None:
                self.modos_do_comando[nome] = tuple(modos)
            else:
                self.modos_do_comando.pop(nome, None)

    def disponivel(self, nome: str, modo: str | None = None) -> bool:
        if nome not in self.comandos:
            return False
        modos = self.modos_do_comando.get(nome)
        return modos is None or (modo or self.modo_atual()) in modos

    def executar(self, nome: str, *args: Any, **kw: Any) -> Any:
        """O único caminho de menu, barra, atalho e contexto até um comando (§13.3)."""
        comando = self.comandos.get(nome)
        if comando is None:
            item = menus_mod.item_de(nome)
            self.status(f"{item.rotulo if item else nome}: chega na {item.fase if item else 'fase seguinte'}")
            return None
        try:
            return comando(*args, **kw)
        except ValueError as erro:
            self.ultimo_erro = ("entrada", str(erro))
            self.log.warning("%s: %s", nome, erro)
            self.status(str(erro))
            self.caixas.entrada(str(erro))
            return None
        except Exception as erro:      # noqa: BLE001 — a segunda camada: defeito do programa, janela viva
            detalhe = traceback.format_exc()
            self.ultimo_erro = ("falha", detalhe)
            self.log.error("%s: %s: %s", nome, type(erro).__name__, erro)
            self.status(f"Defeito do programa em {nome}: {type(erro).__name__}: {erro}")
            self.caixas.falha(f"{nome}: {type(erro).__name__}: {erro}", detalhe)
            return None

    def _registrar_comandos_da_ed02(self) -> None:
        j = self
        arquivo = {
            "novo": j.novo, "novo_de_modelo": j.novo_de_modelo, "abrir": j.abrir, "salvar": j.salvar,
            "salvar_como": j.salvar_como, "reverter": j.reverter, "checkpoint_criar": j.checkpoint_criar,
            "checkpoint_comparar": j.checkpoint_comparar, "checkpoint_restaurar": j.checkpoint_restaurar,
            "fechar_aba": j.fechar_aba, "fechar_livro": j.fechar_livro, "exportar": j.exportar, "sair": j.fechar,
        }
        editar = {
            "desfazer": lambda: j._no_editor("desfazer"), "refazer": lambda: j._no_editor("refazer"),
            "apagar_palavra_anterior": lambda: j._no_editor("apagar_palavra_anterior"),
            "apagar_palavra_seguinte": lambda: j._no_editor("apagar_palavra_seguinte"),
            "recortar": j.recortar, "copiar": j.copiar, "colar": j.colar, "colar_sem_formatacao": j.colar,
            "selecionar_tudo": lambda: j._no_editor("selecionar_tudo"),
            "selecionar_paragrafo": lambda: j._no_texto("selecionar_paragrafo"),
            "selecionar_bloco": lambda: j._no_texto("selecionar_bloco"),
            "maiusculas": lambda: j._texto().mudar_caixa("maiusculas"),
            "minusculas": lambda: j._texto().mudar_caixa("minusculas"),
            "capitalizar": lambda: j._texto().mudar_caixa("capitalizar"),
            "pincel": j.pincel, "escape": j.escape, "menu_de_contexto": j.menu_de_contexto,
        }
        exibir = {
            "modo_texto": lambda: j.alternar_modo(para="texto"), "modo_codigo": lambda: j.alternar_modo(para="codigo"),
            "alternar_modo": j.alternar_modo, "capitulo_seguinte": lambda: j.capitulo_vizinho(1),
            "capitulo_anterior": lambda: j.capitulo_vizinho(-1), "painel_seguinte": lambda: j.painel_vizinho(1),
            "painel_anterior": lambda: j.painel_vizinho(-1), "foco_no_editor": j.foco_no_editor,
            "painel_navegador": lambda: j._painel_pela_variavel("navegador"),
            "painel_sumario": lambda: j._painel_pela_variavel("sumario"),
            "painel_estilos": lambda: j._painel_pela_variavel("estilos"),
            "painel_propriedades": lambda: j._painel_pela_variavel("propriedades"),
            "painel_xadrez": lambda: j._painel_pela_variavel("xadrez"),
            "painel_busca": lambda: j._painel_pela_variavel("busca"),
            "barra_de_formatacao": lambda: j.mostrar_barra("formatacao", j.variaveis["barra_de_formatacao"].get()),
            "barra_de_xadrez": lambda: j.mostrar_barra("xadrez", j.variaveis["barra_de_xadrez"].get()),
            "invisiveis": lambda: j._texto().invisiveis(j.variaveis["invisiveis"].get()),
            "quebra_automatica": lambda: j.quebra_automatica(j.variaveis["quebra_automatica"].get()),
            "largura_toda": lambda: j._texto().largura_de_leitura(0),
            "largura_60": lambda: j._texto().largura_de_leitura(60),
            "largura_80": lambda: j._texto().largura_de_leitura(80),
            "largura_100": lambda: j._texto().largura_de_leitura(100),
            "zoom_mais": lambda: j.zoom(1), "zoom_menos": lambda: j.zoom(-1), "zoom_zero": lambda: j.zoom(0),
            "tela_cheia": lambda: j.tela_cheia(j.variaveis["tela_cheia"].get()),
            "numeros_de_linha": lambda: j._codigo().numeros_de_linha(j.variaveis["numeros_de_linha"].get()),
            "realce_da_linha": lambda: j._codigo().realce_da_linha(j.variaveis["realce_da_linha"].get()),
        }
        inserir = {
            "inserir_link": j.inserir_link, "inserir_ancora": j.inserir_ancora, "inserir_imagem": j.inserir_imagem,
            "espaco_inseparavel": lambda: j.inserir_texto(" "),
            "hifen_inseparavel": lambda: j.inserir_texto("‑"),
            "hifen_opcional": lambda: j.inserir_texto("­"),
            "dividir_capitulo": j.dividir_capitulo, "aplicar_clipe": j.aplicar_clipe,
        }
        formatar = {
            "fonte": j.fonte, "negrito": lambda: j._no_editor("negrito"), "italico": lambda: j._no_editor("italico"),
            "sublinhado": lambda: j._no_editor("sublinhado"), "tachado": lambda: j._no_texto("tachado"),
            "versalete": lambda: j._no_texto("versalete"), "sobrescrito": lambda: j._no_texto("sobrescrito"),
            "subscrito": lambda: j._no_texto("subscrito"), "aumentar_fonte": lambda: j._no_texto("aumentar_fonte"),
            "diminuir_fonte": lambda: j._no_texto("diminuir_fonte"), "cor": j.cor,
            "realce_nenhum": lambda: j._texto().aplicar(fundo=""), "paragrafo": j.paragrafo,
            "alinhar_esquerda": lambda: j._no_texto("alinhar_esquerda"),
            "alinhar_centro": lambda: j._no_texto("alinhar_centro"),
            "alinhar_direita": lambda: j._no_texto("alinhar_direita"), "justificar": lambda: j._no_texto("justificar"),
            "recuar": lambda: j.recuar(1), "diminuir_recuo": lambda: j.recuar(-1),
            "entrelinha_1": lambda: j._texto().paragrafo(entrelinha=1.0),
            "entrelinha_15": lambda: j._texto().paragrafo(entrelinha=1.5),
            "entrelinha_2": lambda: j._texto().paragrafo(entrelinha=2.0),
            "marcadores": lambda: j._texto().lista(False), "numeracao": lambda: j._texto().lista(True),
            "novo_estilo": j.novo_estilo, "modificar_estilo": j.modificar_estilo,
            "selecionar_com_estilo": lambda: j.painel_de_estilos.selecionar_tudo_com(),
            "limpar_caractere": lambda: j._no_texto("limpar_caractere"),
            "limpar_paragrafo": lambda: j._no_texto("limpar_paragrafo"),
        }
        for rotulo, cor in menus_mod.REALCES:
            formatar[f"realce_{rotulo.lower()}"] = (lambda c=cor: j._texto().aplicar(fundo=c))
        for nome in menus_mod.ESTILOS:
            formatar[f"estilo_{nome}"] = (lambda n=nome: j._texto().estilo(n))
        for nome in menus_mod.ESTILOS_DE_CARACTERE:
            formatar[f"caractere_{nome.lower()}"] = (lambda n=nome: j._texto().estilo_de_caractere(n))
        ferramentas = {
            "contagem": j.contagem, "bem_formado": j.bem_formado, "consertar": j.consertar, "reformatar": j.reformatar,
            "reformatar_css": j.reformatar, "clipes": j.clipes_comando, "autocompletar": lambda: j._codigo().sugerir(),
            "comentar": lambda: j._codigo().comentar(), "ir_para": j.ir_para,
            "ir_ao_alvo": lambda: j._codigo().ir_ao_alvo(), "voltar": lambda: j._codigo().voltar(),
        }
        livro = {"metadados": j.metadados}
        ajuda = {"atalhos": j.atalhos, "dialeto": j.dialeto, "sobre": j.sobre}
        for grupo in (arquivo, editar, exibir, inserir, formatar, ferramentas, livro, ajuda):
            self.registrar_comandos(grupo)
        so_no_codigo = ("bem_formado", "consertar", "reformatar", "reformatar_css", "autocompletar", "comentar",
                        "ir_ao_alvo", "voltar", "numeros_de_linha", "realce_da_linha")
        for nome in so_no_codigo:
            self.modos_do_comando[nome] = ("codigo",)

    def _registrar_comandos_da_ed04(self) -> None:
        """Os objetos do modo texto (§8.6–§8.11): cada comando acorda o item que a tabela de menus já tem."""
        j = self
        texto = {
            "colar_como_xhtml": j.colar_como_xhtml, "seguir_link": j.seguir_link,
            "inserir_tabela": j.inserir_tabela, "nota_de_rodape": lambda: j._texto_ativo().inserir_nota("rodape"),
            "nota_de_fim": lambda: j._texto_ativo().inserir_nota("fim"),
            "quebra_de_linha": lambda: j._texto_ativo().inserir_quebra_suave(),
            "quebra_de_pagina": lambda: j._texto().inserir_quebra_de_pagina(),
            "inserir_separador": lambda: j._texto().inserir_separador(), "inserir_ilha": j.inserir_ilha,
            "propriedades_do_objeto": j.propriedades_do_objeto, "editar_ilha": j.editar_ilha,
            "apagar_nota": j.apagar_nota,
            "tabela_fila_acima": lambda: j._grade().inserir_fila(depois=False),
            "tabela_fila_abaixo": lambda: j._grade().inserir_fila(depois=True),
            "tabela_coluna_esquerda": lambda: j._grade().inserir_coluna(depois=False),
            "tabela_coluna_direita": lambda: j._grade().inserir_coluna(depois=True),
            "tabela_excluir_fila": lambda: j._grade().excluir_fila(),
            "tabela_excluir_coluna": lambda: j._grade().excluir_coluna(),
            "tabela_cabecalho": lambda: j._grade().alternar_cabecalho(), "tabela_excluir": j.tabela_excluir,
        }
        self.registrar_comandos(texto, modos=("texto",))
        ambos = {"inserir_link": j.inserir_link, "inserir_ancora": j.inserir_ancora, "inserir_imagem": j.inserir_imagem,
                 "dividir_capitulo": j.dividir_capitulo, "juntar_com_anterior": j.juntar_com_anterior,
                 "colar": j.colar, "colar_sem_formatacao": j.colar_sem_formatacao, "copiar": j.copiar,
                 "recortar": j.recortar}
        self.registrar_comandos(ambos)

    def _registrar_comandos_da_ed06(self) -> None:
        """Busca, ortografia, ir para, símbolos, código Unicode e estatísticas (§8.12–§8.15)."""
        j = self
        self.buscador = Buscador(self, self.busca)
        self.corretor = Corretor(self)
        self.registrar_comandos(self.buscador.comandos)
        self.registrar_comandos(self.corretor.comandos)
        self.registrar_comandos({"ir_para": j.ir_para, "inserir_simbolo": j.inserir_simbolo,
                                 "estatisticas": j.estatisticas})
        self.registrar_comandos({"codigo_unicode": j.codigo_unicode}, modos=("texto",))

    def _registrar_comandos_da_ed08(self) -> None:
        """O livro no modo código (§9): o menu Livro, relatórios, validação, prévia, metadados completos."""
        self.operacoes = OperacoesDoLivro(self)
        self.registrar_comandos(self.operacoes.comandos)
        self.registrar_comandos({"ir_para_destino": self.ir_para_destino, "clipes": self.clipes_comando,
                                 "aplicar_clipe": self.aplicar_clipe})

    def _registrar_comandos_da_ed05(self) -> None:
        """Xadrez no editor (ED-05, §11): o menu Xadrez, Inserir → Referência/Figurina/NAG, a paleta e a barra."""
        self.xadrez_controlador = Xadrez(self)
        self.registrar_comandos(self.xadrez_controlador.comandos)
        for nome in self.xadrez_controlador.so_no_texto:
            self.modos_do_comando[nome] = ("texto",)
        self.registrar_comandos({"validar_notacao_selecao": lambda: self.xadrez_controlador.validar_notacao("selecao"),
                                 "validar_notacao_livro": lambda: self.xadrez_controlador.validar_notacao("livro")})
        self.modos_do_comando["validar_notacao_selecao"] = ("texto",)

    def _registrar_comandos_da_ed10(self) -> None:
        """Exportar (EPUB/HTML/TXT), importar (HTML/TXT/EPUB), juntar e dividir por título (ED-10)."""
        self.conversoes = Conversoes(self)
        self.registrar_comandos(self.conversoes.comandos)

    def _registrar_comandos_da_ed06b(self) -> None:
        """Tipografia, juntar hifenizadas e buscas salvas (ED-06b, §8.12 e §8.14)."""
        self.tipografo = Tipografo(self)
        self.buscas_salvas = BuscasSalvas(self, self.busca)
        self.registrar_comandos(self.tipografo.comandos)
        self.registrar_comandos(self.buscas_salvas.comandos)

    # ==================================================================
    # Estado: modo, aba, editores
    # ==================================================================

    def aba_ativa(self) -> Aba | None:
        return self.abas.ativa()

    def modo_atual(self) -> str:
        aba = self.aba_ativa()
        return aba.modo if aba is not None else "texto"

    def editor_ativo(self) -> Any:
        aba = self.aba_ativa()
        return aba.widget if aba is not None else None

    def _texto(self) -> TextoRico:
        aba = self.aba_ativa()
        if aba is None or aba.modo != "texto" or not isinstance(aba.widget, TextoRico):
            raise ValueError("Este comando é do modo texto: abra um capítulo e pressione F11 para o modo texto.")
        return aba.widget

    def _codigo(self) -> EditorDeCodigo:
        aba = self.aba_ativa()
        if aba is None or aba.modo != "codigo" or not isinstance(aba.widget, EditorDeCodigo):
            raise ValueError("Este comando é do modo código: pressione F11 para o modo código.")
        if aba.somente_leitura:
            raise ValueError(f"{aba.nome} é regenerado ao salvar e abre só para leitura (DEC-01).")
        return aba.widget

    def _no_editor(self, nome: str) -> Any:
        editor = self.editor_ativo()
        if editor is None:
            raise ValueError("Nenhuma aba aberta: abra um livro (Ctrl+O) ou crie um novo (Ctrl+N).")
        aba = self.aba_ativa()
        if aba is not None and aba.somente_leitura and nome not in ("selecionar_tudo",):
            raise ValueError(f"{aba.nome} é regenerado ao salvar e abre só para leitura (DEC-01).")
        comando = editor.comandos.get(nome)
        if comando is None:
            raise ValueError(f"{nome} não existe no modo {self.modo_atual()}.")
        return comando()

    def _texto_ativo(self) -> TextoRico:
        """O `TextoRico` que recebe formatação e texto: a célula de tabela com o foco, ou o capítulo."""
        return self._texto().ativo()

    def _no_texto(self, nome: str) -> Any:
        return self._texto_ativo().comandos[nome]()

    def _grade(self) -> GradeDeTabela:
        """A grade da tabela sob o cursor (ou com uma célula focada) — o alvo de Formatar → Tabela ▸."""
        texto = self._texto()
        celula = texto.ativo()
        if celula is not texto:
            grade = celula.master
            while grade is not None and not isinstance(grade, GradeDeTabela):
                grade = getattr(grade, "master", None)
            if isinstance(grade, GradeDeTabela):
                return grade
        objeto = texto.objeto_no_cursor()
        if isinstance(objeto, Tabela):
            grade = texto.widget_do_objeto(objeto.id)
            if isinstance(grade, GradeDeTabela):
                return grade
            raise ValueError("esta tabela passa de 400 células e se edita no modo código (F11)")
        raise ValueError("o cursor precisa estar numa tabela (ou numa célula dela)")

    def _exigir_projeto(self) -> Projeto:
        if self.projeto is None:
            raise ValueError("Nenhum livro aberto: abra um livro (Ctrl+O) ou crie um novo (Ctrl+N).")
        return self.projeto

    def _capitulo_da_aba(self, aba: Aba) -> Capitulo:
        projeto = self._exigir_projeto()
        cap = projeto.livro.capitulo(aba.arquivo)
        if cap is None:
            raise ValueError(f"o capítulo {aba.arquivo} já não está no livro")
        return cap

    # ==================================================================
    # Projeto: abrir, novo, instalar, fechar
    # ==================================================================

    def novo(self) -> Projeto | None:
        if not self._confirmar_descarte():
            return self.projeto
        projeto = Projeto.novo(relogio=self.relogio)
        self._instalar_projeto(projeto)
        self._gravar_preferencia("idioma_ortografia", projeto.livro.metadados.idioma)
        self.log.info("Livro novo.")
        return projeto

    def novo_de_modelo(self, titulo: str | None = None, autor: str | None = None,
                       idioma: str | None = None) -> Projeto | None:
        """Título, autor e idioma → `Metadados`; sem argumentos, pergunta (AC-ED02-11)."""
        if titulo is None:
            resposta = self.caixas.formulario("Novo livro a partir de modelo", [
                ("titulo", "Título:", "Livro novo"), ("autor", "Autor:", ""),
                ("idioma", "Idioma (código):", self._preferencia("idioma_ortografia", "pt"))], {"idioma": IDIOMAS})
            if resposta is None:
                return self.projeto
            titulo, autor, idioma = resposta["titulo"], resposta["autor"], resposta["idioma"]
        titulo = (titulo or "").strip() or "Livro novo"
        idioma = (idioma or "pt").strip() or "pt"
        if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]+)*", idioma):
            raise ValueError(f"idioma inválido: {idioma!r} — use um código como pt, en ou pt-BR")
        if not self._confirmar_descarte():
            return self.projeto
        projeto = Projeto.novo(titulo, (autor or "").strip(), idioma, relogio=self.relogio)
        self._instalar_projeto(projeto)
        self._gravar_preferencia("idioma_ortografia", idioma)
        self.log.info("Livro novo a partir de modelo: %s (%s).", titulo, idioma)
        return projeto

    def abrir(self, caminho: str | None = None) -> Projeto | None:
        """Abre um EPUB; sem `caminho`, pergunta. Oferece o rascunho pendente, se houver (§7.6)."""
        if caminho is None:
            caminho = self.caixas.abrir(diretorio=self._preferencia("diretorios", {}).get("abrir", ""))
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if not os.path.isfile(caminho):
            self.recentes.remover(caminho)
            raise ValueError(f"o arquivo não existe: {caminho}")
        if caminho.lower().endswith(EXTENSOES_DE_HTML + EXTENSOES_DE_TXT):
            return self.conversoes.abrir_como_livro(caminho)          # ED-10: §10.6 "Abrir / importar"
        if caminho.lower().endswith(EXTENSOES_DE_JSON):
            return self.conversoes.importar_json(caminho)             # ED-11: o documento editorial
        if caminho.lower().endswith(EXTENSOES_DE_DOCX):
            return self.conversoes.abrir_como_livro(caminho)          # ED-12: DOCX como livro
        if not self._confirmar_descarte():
            return None
        pendentes = Rascunho.pendentes(caminho)
        projeto: Projeto | None = None
        if pendentes:
            dados = Rascunho.ler(pendentes[0])
            resposta = self.caixas.pergunta(
                f"Há um rascunho de {dados.get('quando', '?')} para este livro, gravado sem salvar.\n"
                "Restaurar o rascunho? (Não abre o arquivo como está no disco.)", cancelar=False)
            if resposta:
                projeto = Rascunho.restaurar(pendentes[0], relogio=self.relogio)
        if projeto is None:
            self.status(f"Abrindo {os.path.basename(caminho)}…")
            self.configure(cursor="watch")
            try:
                projeto = Projeto.abrir(caminho, relogio=self.relogio)
            finally:
                self.configure(cursor="")
        self._instalar_projeto(projeto)
        pasta = os.path.dirname(caminho)
        self._gravar_preferencia("diretorios", {**self._preferencia("diretorios", {}), "abrir": pasta})
        self.log.info("Aberto: %s (%d capítulos).", caminho, len(projeto.livro.capitulos))
        self.status(f"Aberto: {os.path.basename(caminho)}")
        return projeto

    def _instalar_projeto(self, projeto: Projeto) -> None:
        self._fechar_projeto(descartar=True)
        self.projeto = projeto
        self.rascunho = Rascunho(projeto, relogio=self.relogio,
                                 intervalo_s=float(self._preferencia("intervalo_rascunho", INTERVALO_DO_RASCUNHO_S)))
        if self._preferencia("idioma_ortografia", "") == "":
            self._gravar_preferencia("idioma_ortografia", projeto.livro.metadados.idioma)
        if projeto.caminho:
            self.recentes.adicionar(projeto.caminho)
        self.validacao.limpar()
        self.resultados.limpar()
        self.atualizar_navegador()
        self.atualizar_sumario()
        self._atualizar_painel_de_estilos()
        if projeto.livro.capitulos:
            primeiro = projeto.livro.capitulos[0]
            self.abrir_capitulo(primeiro.arquivo)
        if projeto.relatorio is not None and projeto.relatorio.avisos:
            for aviso in projeto.relatorio.avisos[:50]:
                self.log.warning("%s", aviso)
        self.atualizar()

    def _fechar_projeto(self, descartar: bool = True) -> None:
        if self.projeto is not None and descartar:
            self.projeto.fechar()
        self.abas.fechar_todas()
        self.projeto = None
        self.rascunho = None
        self.navegador.delete(*self.navegador.get_children())
        self.arvore_do_sumario.delete(*self.arvore_do_sumario.get_children())
        self.painel_de_estilos.texto_rico = self._texto_de_reserva
        self.painel_de_estilos.folha_padrao = ""
        self.arquivos_marcados.clear()
        self._lexicos_cache = None
        if hasattr(self, "operacoes"):
            self.operacoes.vigiados.clear()
        if hasattr(self, "buscador"):
            self.buscador.marcas.clear()
            self.buscador.atual = None

    def fechar_livro(self) -> bool:
        if self.projeto is None:
            return True
        if not self._confirmar_descarte():
            return False
        nome = self.projeto.nome
        self._fechar_projeto(descartar=True)
        self.log.info("Fechado: %s.", nome)
        self.atualizar()
        return True

    def _confirmar_descarte(self) -> bool:
        """A guarda: `True` quando se pode seguir (salvo, ou descartado de propósito)."""
        projeto = self.projeto
        if projeto is None or not self._sujo():
            return True
        resposta = self.caixas.pergunta(f"O livro “{projeto.nome}” tem alterações não salvas.\nSalvar antes?")
        if resposta is None:
            return False
        if resposta:
            return self.salvar() is not None
        return True

    def _sujo(self) -> bool:
        if self.projeto is None:
            return False
        return self.projeto.sujo or any(a.sujo for a in self.abas.abas)

    # ==================================================================
    # Salvar, reverter, pontos de verificação, exportar
    # ==================================================================

    def _sincronizar_aba(self, aba: Aba) -> None:
        """O que está no widget volta ao modelo (texto) ou ao `texto_cru` (código)."""
        if self.projeto is None or aba.widget is None or aba.somente_leitura:
            return
        livro = self.projeto.livro
        if aba.tipo == "capitulo":
            cap = livro.capitulo(aba.arquivo)
            if cap is None:
                return
            if aba.modo == "texto":
                novo = aba.widget.sincronizar()
                cap.blocos, cap.notas = list(novo.blocos), list(novo.notas)
                cap.texto_cru = None
            else:
                cap.texto_cru = aba.widget.texto_todo()
        elif aba.tipo == "recurso":
            recurso = livro.recurso(aba.arquivo)
            if recurso is not None:
                recurso.texto_cru = aba.widget.texto_todo()

    def _sincronizar_tudo(self) -> None:
        for aba in self.abas.abas:
            self._sincronizar_aba(aba)

    def _validar_abas_de_codigo(self) -> None:
        """Um XHTML mal-formado numa aba de código é recusado antes de tocar o disco (AC-004)."""
        self.validacao.limpar()
        for aba in self.abas.abas:
            if aba.tipo != "capitulo" or aba.modo != "codigo" or aba.somente_leitura:
                continue
            erro = xhtml.bem_formado(aba.widget.texto_todo())
            if erro is not None:
                self._relatar_erro_de_xhtml(aba, erro)
                raise ValueError(f"{aba.nome}: {erro} — o livro não foi salvo.")

    def salvar(self, **opcoes: Any) -> Any:
        projeto = self._exigir_projeto()
        if not projeto.caminho:
            return self.salvar_como(**opcoes)
        self._validar_abas_de_codigo()
        self._sincronizar_tudo()
        opcoes.setdefault("ncx", self._preferencia("ncx", None))
        self.status(f"Salvando {projeto.nome}…")
        self.configure(cursor="watch")
        try:
            relatorio = projeto.salvar(**opcoes)
        finally:
            self.configure(cursor="")
        self._depois_de_salvar(relatorio)
        return relatorio

    def salvar_como(self, caminho: str | None = None, **opcoes: Any) -> Any:
        projeto = self._exigir_projeto()
        if caminho is None:
            sugestao = projeto.caminho or (_nome_seguro(projeto.livro.metadados.titulo) + ".epub")
            caminho = self.caixas.salvar_como(sugestao, diretorio=self._preferencia("diretorios", {}).get("salvar", ""))
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if not caminho.lower().endswith(".epub"):
            caminho += ".epub"
        self._validar_abas_de_codigo()
        self._sincronizar_tudo()
        opcoes.setdefault("ncx", self._preferencia("ncx", None))
        self.configure(cursor="watch")
        try:
            relatorio = projeto.salvar_como(caminho, **opcoes)
        finally:
            self.configure(cursor="")
        self.recentes.adicionar(caminho)
        self._gravar_preferencia("diretorios", {**self._preferencia("diretorios", {}),
                                               "salvar": os.path.dirname(caminho)})
        self._depois_de_salvar(relatorio)
        return relatorio

    def _depois_de_salvar(self, relatorio: Any) -> None:
        assert self.projeto is not None
        for aba in self.abas.abas:
            if aba.widget is not None and hasattr(aba.widget, "marcar_limpo"):
                aba.widget.marcar_limpo()
        self._salvo_em = time.strftime("%H:%M")
        for aviso in getattr(relatorio, "avisos", [])[:50]:
            self.log.warning("%s", aviso)
        self.log.info("Salvo: %s (%d capítulos, %.1f s).", self.projeto.caminho, getattr(relatorio, "capitulos", 0),
                      getattr(relatorio, "tempo_s", 0.0))
        ponte = getattr(self.projeto, "ponte", None)
        if ponte is not None:
            self.status(f"Salvo: {self.projeto.nome} — ponte: {ponte.eventos} evento(s) no diário")
        self.atualizar()

    def reverter(self) -> Any:
        projeto = self._exigir_projeto()
        if not projeto.caminho:
            raise ValueError("o livro ainda não foi salvo: não há a que reverter")
        if self._sujo() and not self.caixas.pergunta("Descartar as alterações e voltar ao que está no disco?",
                                                      cancelar=False):
            return None
        relatorio = projeto.reverter()
        self._reabrir_abas()
        self.log.info("Revertido ao salvo: %s.", projeto.caminho)
        self.atualizar()
        return relatorio

    def _reabrir_abas(self) -> None:
        """Depois de reverter ou restaurar: as mesmas abas, recarregadas do modelo novo."""
        assert self.projeto is not None
        abertas = [(a.arquivo, a.tipo) for a in self.abas.abas]
        ativa = self.aba_ativa()
        arquivo_ativo = ativa.arquivo if ativa else None
        self.abas.fechar_todas()
        self.atualizar_navegador()
        self.atualizar_sumario()
        self._atualizar_painel_de_estilos()
        livro = self.projeto.livro
        for arquivo, tipo in abertas:
            if tipo == "capitulo" and livro.capitulo(arquivo) is not None:
                self.abrir_capitulo(arquivo)
            elif tipo == "recurso" and livro.recurso(arquivo) is not None:
                self.abrir_recurso(arquivo)
        if arquivo_ativo:
            aba = self.abas.por_arquivo(arquivo_ativo)
            if aba is not None:
                self.abas.selecionar(aba)
        if not self.abas.abas and livro.capitulos:
            self.abrir_capitulo(livro.capitulos[0].arquivo)

    def checkpoint_criar(self, rotulo: str | None = None) -> Any:
        projeto = self._exigir_projeto()
        if rotulo is None:
            rotulo = self.caixas.pedir_texto("Ponto de verificação", "Rótulo (opcional):", "")
            if rotulo is None:
                return None
        self._sincronizar_tudo()
        ponto = projeto.checkpoint(rotulo)
        self.log.info("Ponto de verificação: %s.", ponto.caminho)
        self.status(f"Ponto de verificação criado: {ponto.nome}")
        return ponto

    def _escolher_checkpoint(self, titulo: str, ok: str) -> Any:
        projeto = self._exigir_projeto()
        pontos = projeto.checkpoints()
        if not pontos:
            raise ValueError("não há pontos de verificação deste livro (Arquivo → Ponto de verificação → Criar…)")
        rotulos = [f"{p.quando}  {p.rotulo}".rstrip() for p in pontos]
        indice = self.caixas.escolher(titulo, "Ponto de verificação:", rotulos, ok)
        return pontos[indice] if indice is not None else None

    def checkpoint_comparar(self, ponto: Any = None) -> list | None:
        projeto = self._exigir_projeto()
        if ponto is None:
            ponto = self._escolher_checkpoint("Comparar com um ponto de verificação", "Comparar")
            if ponto is None:
                return None
        self._sincronizar_tudo()
        diferencas = projeto.diferenca(ponto)
        self.resultados.definir([Resultado(d.arquivo, d.estado, (d.diff.splitlines() or ["(binário)"])[0][:120],
                                           {"diff": d.diff}) for d in diferencas],
                                f"Diferenças em relação a {ponto.nome}: {len(diferencas)}")
        self._focar_inferior(self.resultados)
        texto = "\n\n".join(f"== {d}\n{d.diff}" if d.diff else f"== {d}" for d in diferencas) or "Nenhuma diferença."
        self.caixas.texto(f"Comparação com {ponto.nome}", texto)
        self.log.info("Comparado com %s: %d diferença(s).", ponto.nome, len(diferencas))
        return diferencas

    def checkpoint_restaurar(self, ponto: Any = None) -> Any:
        projeto = self._exigir_projeto()
        if ponto is None:
            ponto = self._escolher_checkpoint("Restaurar um ponto de verificação", "Restaurar")
            if ponto is None:
                return None
            if not self.caixas.pergunta(f"Substituir o livro atual pelo ponto {ponto.nome}?\n"
                                        "(Nada é gravado até você salvar.)", cancelar=False):
                return None
        relatorio = projeto.restaurar(ponto)
        self._reabrir_abas()
        self.log.info("Restaurado o ponto %s.", ponto.nome)
        self.atualizar()
        return relatorio

    def exportar(self, formato: str | None = None, caminho: str | None = None) -> str | None:
        """A caixa de formato (§7.3) — desde a ED-10 mora em `ui/editor/conversoes.py`."""
        return self.conversoes.exportar(formato, caminho)

    # ==================================================================
    # Abas: abrir capítulo, recurso, leitura; trocar de modo; fechar
    # ==================================================================

    def _folhas_de(self, cap: Capitulo) -> list[tuple[str, str]]:
        assert self.projeto is not None
        livro = self.projeto.livro
        saida = []
        for href in cap.folhas:
            recurso = livro.recurso(href)
            if recurso is None:
                continue
            try:
                texto = recurso.texto_cru if recurso.texto_cru is not None else \
                    epub.dados_de(livro, recurso).decode("utf-8", errors="replace")
            except FileNotFoundError:
                continue
            saida.append((href, texto))
        return saida

    def _criar_texto(self, frame: ttk.Frame, aba: Aba, cap: Capitulo) -> TextoRico:
        assert self.projeto is not None
        widget = TextoRico(frame, estilo_de_tela=self._estilo_de_tela(), folhas=self._folhas_de(cap),
                           historico=self.projeto.historico, relogio=self.relogio, arquivo=cap.arquivo,
                           recursos=self._dados_do_recurso, ao_ativar=self.acao_principal)
        if hasattr(self, "xadrez_controlador"):
            widget.ao_fechar_token = self.xadrez_controlador.ao_fechar_token       # figurinas ao digitar (ED-05)
        widget.carregar(cap)
        self._ligar_editor(widget, aba)
        return widget

    def _dados_do_recurso(self, href: str) -> bytes | None:
        """Os bytes de uma imagem do livro para o desenho da figura; `None` quando não há."""
        if self.projeto is None:
            return None
        recurso = self.projeto.livro.recurso(href)
        if recurso is None:
            return None
        try:
            return epub.dados_de(self.projeto.livro, recurso)
        except FileNotFoundError:
            return None

    def _criar_codigo(self, frame: ttk.Frame, aba: Aba, texto: str, linguagem: str = "xhtml",
                      folhas: Iterable[tuple[str, str]] = ()) -> EditorDeCodigo:
        widget = EditorDeCodigo(frame, linguagem, folhas=list(folhas),
                                abrir_alvo=lambda a, alvo: self._abrir_alvo(aba, a, alvo), tema=self._tema_codigo,
                                tabulacao=int(self._preferencia("tabulacao", 2)), relogio=self.relogio)
        widget.carregar(texto)
        self._ligar_editor(widget, aba)
        t = widget.texto
        t.bind("<<IrParaLinha>>", lambda e: self.executar("ir_para"), add="+")
        t.bind("<<InserirLink>>", lambda e: self.executar("inserir_link"), add="+")
        t.bind("<<DividirNoCursor>>", lambda e: self.executar("dividir_capitulo"), add="+")
        t.bind("<<Clipes>>", lambda e: self.executar("clipes"), add="+")
        if aba.somente_leitura:
            t.configure(state="disabled")
        return widget

    def _ligar_editor(self, widget: Any, aba: Aba) -> None:
        widget.texto.bind("<<Mudou>>", lambda e, a=aba: self._mudou(a), add="+")
        widget.texto.bind("<<CursorMoveu>>", lambda e, a=aba: self._cursor_moveu(a), add="+")
        widget.texto.bind("<Button-3>", self._botao_direito, add="+")
        atalhos_mod.ligar(widget.texto, atalhos_mod.TABELA, self._despacho, self.modo_atual)

    def _estilo_de_tela(self) -> EstiloDeTela:
        tela = EstiloDeTela()
        prefs = self._preferencia("estilo_de_tela", {})
        if isinstance(prefs, dict):
            for chave, valor in prefs.items():
                if hasattr(tela, chave):
                    setattr(tela, chave, valor)
        tela.zoom = float(self._preferencia("zoom", 1.0) or 1.0)
        tela.largura_de_leitura = int(self._preferencia("largura_de_leitura", 0) or 0)
        return tela

    def abrir_capitulo(self, arquivo: str, modo: str | None = None) -> Aba:
        """A aba do capítulo: em texto (o padrão), ou em código quando `texto_cru` manda (INV-09)."""
        projeto = self._exigir_projeto()
        cap = projeto.livro.capitulo(arquivo)
        if cap is None:
            raise ValueError(f"não há capítulo {arquivo!r} no livro")
        existente = self.abas.por_arquivo(arquivo)
        if existente is not None:
            self.abas.selecionar(existente)
            if modo is not None and existente.modo != modo:
                self.alternar_modo(existente, para=modo)
            else:
                self._trocou_de_aba(existente)      # sem esperar o <<NotebookTabChanged>> do laco de eventos
            return existente
        if modo is None:
            modo = "codigo" if cap.texto_cru is not None else "texto"
        if modo == "texto" and cap.texto_cru is not None:
            erro = xhtml.bem_formado(cap.texto_cru)
            if erro is not None:
                modo = "codigo"
                self.log.warning("%s abre em código: %s", cap.arquivo, erro)

        def criar(frame: ttk.Frame, aba: Aba) -> Any:
            if aba.modo == "texto":
                return self._criar_texto(frame, aba, cap)
            texto = cap.texto_cru if cap.texto_cru is not None else \
                xhtml.escrever(cap, pasta_de_imagens=epub.pasta_de_imagens(projeto.livro))
            return self._criar_codigo(frame, aba, texto, "xhtml", self._folhas_de(cap))

        aba = self.abas.abrir(arquivo, "capitulo", modo, criar)
        self.atualizar()
        return aba

    def abrir_recurso(self, caminho: str) -> Aba:
        """Uma folha de estilo em código; outro recurso de texto também; binário, não."""
        projeto = self._exigir_projeto()
        recurso = projeto.livro.recurso(caminho)
        if recurso is None:
            raise ValueError(f"não há recurso {caminho!r} no livro")
        if recurso.texto_cru is None and not _e_texto(recurso.tipo_mime):
            raise ValueError(f"{caminho} é {recurso.tipo_mime}: não se edita como texto")
        existente = self.abas.por_arquivo(caminho)
        if existente is not None:
            self.abas.selecionar(existente)
            return existente
        texto = recurso.texto_cru if recurso.texto_cru is not None else \
            epub.dados_de(projeto.livro, recurso).decode("utf-8", errors="replace")
        linguagem = "css" if recurso.tipo_mime == epub.MIME_CSS else "xhtml"
        aba = self.abas.abrir(caminho, "recurso", "codigo",
                             lambda frame, aba: self._criar_codigo(frame, aba, texto, linguagem))
        self.atualizar()
        return aba

    def abrir_leitura(self, arquivo: str) -> Aba:
        """O `nav.xhtml`, o NCX ou o OPF regenerados do modelo, só para ler (DEC-01)."""
        projeto = self._exigir_projeto()
        livro = projeto.livro
        if arquivo == livro.nav:
            texto = sumario.escrever_nav(livro)
        elif livro.ncx and arquivo == livro.ncx:
            texto = sumario.escrever_ncx(livro)
        elif arquivo == livro.opf:
            texto = epub.texto_do_opf(livro)
        else:
            raise ValueError(f"{arquivo} não é o nav, o NCX nem o OPF do livro")
        existente = self.abas.por_arquivo(arquivo)
        if existente is not None:
            self.abas.selecionar(existente)
            return existente
        aba = self.abas.abrir(arquivo, "leitura", "codigo",
                             lambda frame, aba: self._criar_codigo(frame, aba, texto, "xhtml"), somente_leitura=True)
        self.atualizar()
        return aba

    def alternar_modo(self, aba: Aba | None = None, para: str | None = None) -> str:
        """
        F11. Texto → código pelo `xhtml.escrever`; código → texto pelo `xhtml.ler`, **só** se
        bem-formado — senão fica em código com o erro na barra, em Mensagens e em Validação,
        e o cursor na linha (AC-ED02-5). Devolve o modo em que a aba ficou.
        """
        aba = aba or self.aba_ativa()
        if aba is None:
            raise ValueError("Nenhuma aba aberta.")
        if aba.tipo != "capitulo":
            raise ValueError(f"{aba.nome} só abre em código.")
        if para is not None and para == aba.modo:
            return aba.modo
        projeto = self._exigir_projeto()
        cap = self._capitulo_da_aba(aba)
        if aba.modo == "texto":
            self._sincronizar_aba(aba)
            texto = xhtml.escrever(cap, pasta_de_imagens=epub.pasta_de_imagens(projeto.livro))
            cap.texto_cru = texto
            self.abas.trocar_widget(aba, "codigo", lambda frame, a: self._criar_codigo(frame, a, texto, "xhtml",
                                                                                         self._folhas_de(cap)))
            self.log.info("Modo código: %s.", aba.nome)
        else:
            texto = aba.widget.texto_todo()
            erro = xhtml.bem_formado(texto)
            if erro is None:
                try:
                    novo = xhtml.ler(texto, cap.arquivo)
                except ErroDeXhtml as e:
                    erro = e
            if erro is not None:
                self._relatar_erro_de_xhtml(aba, erro)
                aba.widget.ir_para(erro.linha, erro.coluna)
                aba.widget.foco()
                self.atualizar()
                return "codigo"
            _copiar_capitulo(novo, cap)
            cap.texto_cru = None
            self.abas.trocar_widget(aba, "texto", lambda frame, a: self._criar_texto(frame, a, cap))
            self.validacao.limpar()
            self.log.info("Modo texto: %s.", aba.nome)
        aba.widget.foco()
        self.atualizar()
        return aba.modo

    def _relatar_erro_de_xhtml(self, aba: Aba, erro: ErroDeXhtml) -> None:
        onde = f"linha {erro.linha}, col {erro.coluna}"
        self.validacao.definir([Resultado(aba.arquivo, onde, erro.mensagem,
                                          {"linha": erro.linha, "coluna": erro.coluna})], "XHTML mal-formado")
        try:
            self.inferior.select(self.validacao)
        except tk.TclError:
            pass
        self.log.error("%s: %s", aba.nome, erro)
        self.status(f"{aba.nome}: {erro}")

    def fechar_aba(self, aba: Aba | None = None) -> bool:
        aba = aba or self.aba_ativa()
        if aba is None:
            raise ValueError("Nenhuma aba aberta.")
        self._sincronizar_aba(aba)
        if aba.sujo and self.projeto is not None:
            self.projeto.marcar_sujo()
        self.abas.fechar(aba)
        self.atualizar()
        return True

    def capitulo_vizinho(self, passo: int) -> Aba | None:
        projeto = self._exigir_projeto()
        capitulos = [c.arquivo for c in projeto.livro.capitulos]
        if not capitulos:
            raise ValueError("o livro não tem capítulos")
        aba = self.aba_ativa()
        if aba is not None and aba.arquivo in capitulos:
            atual = capitulos.index(aba.arquivo)
        else:
            atual = -1 if passo > 0 else len(capitulos)
        alvo = atual + passo
        if not 0 <= alvo < len(capitulos):
            self.status("Já é o " + ("último" if passo > 0 else "primeiro") + " capítulo.")
            return None
        return self.abrir_capitulo(capitulos[alvo])

    # ==================================================================
    # Eventos dos editores
    # ==================================================================

    def _mudou(self, aba: Aba) -> None:
        if self.projeto is not None:
            self.projeto.marcar_sujo()
        self.abas.rotular(aba)
        self._atualizar_titulo()
        self._atualizar_estado()
        self._agendar_contagem()
        if aba is self.aba_ativa() and isinstance(aba.widget, TextoRico) and not self._foco_no_painel_de_propriedades():
            self.painel_de_propriedades.atualizar(forcar=True)

    def _cursor_moveu(self, aba: Aba) -> None:
        if aba is self.aba_ativa():
            self._atualizar_posicao(aba)
            if isinstance(aba.widget, TextoRico) and not self._foco_no_painel_de_propriedades():
                self.painel_de_propriedades.atualizar()

    def _foco_no_painel_de_propriedades(self) -> bool:
        try:
            foco = self.focus_get()
        except (tk.TclError, KeyError):
            return False
        while foco is not None:
            if foco is self.painel_de_propriedades:
                return True
            foco = getattr(foco, "master", None)
        return False

    def _trocou_de_aba(self, aba: Aba | None) -> None:
        if aba is not None and isinstance(aba.widget, TextoRico):
            self.painel_de_estilos.texto_rico = aba.widget
            self.painel_de_propriedades.texto_rico = aba.widget
        else:
            self.painel_de_propriedades.texto_rico = None
        self.painel_de_propriedades.atualizar()
        self.atualizar()

    def _botao_direito(self, evento: Any) -> str:
        try:
            evento.widget.focus_set()
        except tk.TclError:
            pass
        self.menu_de_contexto(evento.x_root, evento.y_root)
        return "break"

    def _abrir_alvo(self, de_aba: Aba, arquivo: str, alvo: str) -> None:
        """`ir_ao_alvo` do modo código: abre o arquivo apontado e vai à âncora ou à regra."""
        projeto = self._exigir_projeto()
        base = posixpath.dirname(de_aba.arquivo)
        caminho = posixpath.normpath(posixpath.join(base, arquivo)) if arquivo else de_aba.arquivo
        if projeto.livro.capitulo(caminho) is not None:
            aba = self.abrir_capitulo(caminho, modo="codigo")
        elif projeto.livro.recurso(caminho) is not None:
            aba = self.abrir_recurso(caminho)
        else:
            raise ValueError(f"o alvo {arquivo!r} não está no livro")
        if alvo and isinstance(aba.widget, EditorDeCodigo):
            padrao = f'id="{alvo}"' if not alvo.startswith(".") else alvo
            indice = aba.widget.texto.search(padrao, "1.0")
            if indice:
                linha, coluna = indice.split(".")
                aba.widget.ir_para(int(linha), int(coluna) + 1)

    def _ativar_resultado(self, item: Resultado) -> None:
        """Um resultado ativado: abre o arquivo e vai à linha (código) ou ao bloco (texto)."""
        if self.projeto is None:
            return
        dados = item.dados
        livro = self.projeto.livro
        comprimento = int(dados.get("comprimento", 0) or 0)
        if livro.capitulo(item.arquivo) is not None:
            if "linha" in dados:
                aba = self.abrir_capitulo(item.arquivo, modo="codigo")
                aba.widget.ir_para(int(dados["linha"]), int(dados.get("coluna", 1)))
                if comprimento:
                    t = aba.widget.texto
                    t.tag_remove("sel", "1.0", "end")
                    t.tag_add("sel", "insert", f"insert+{comprimento}c")
            else:
                aba = self.abrir_capitulo(item.arquivo)
                bloco = dados.get("bloco")
                if bloco and isinstance(aba.widget, TextoRico):
                    if "deslocamento" in dados and bloco in aba.widget.ordem:
                        desloc = int(dados.get("deslocamento", 0))
                        if comprimento:
                            aba.widget.selecionar(desloc, desloc + comprimento, bloco)
                            aba.widget.texto.see("insert")
                        else:
                            aba.widget.ir_para(bloco, desloc)
                    elif bloco in aba.widget.ordem:
                        aba.widget.selecionar_objeto(bloco)
            aba.widget.foco()
        elif livro.recurso(item.arquivo) is not None:
            aba = self.abrir_recurso(item.arquivo)
            if "linha" in dados:
                aba.widget.ir_para(int(dados["linha"]), int(dados.get("coluna", 1)))
            elif "inicio" in dados:
                linha = aba.widget.texto_todo()[:int(dados["inicio"])].count("\n") + 1
                aba.widget.ir_para(linha)
            aba.widget.foco()

    # ==================================================================
    # Comandos de edição que a janela intermedeia
    # ==================================================================

    def _ler_clipboard(self) -> str:
        try:
            return self.clipboard_get()
        except tk.TclError:
            return ""

    def _gravar_clipboard(self, texto: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(texto)
        except tk.TclError:
            pass

    def _editor_de_edicao(self) -> Any:
        """O editor que recebe copiar/colar: a célula com o foco, o capítulo ou o código."""
        editor = self.editor_ativo()
        aba = self.aba_ativa()
        if editor is None or aba is None:
            raise ValueError("Nenhuma aba aberta.")
        if isinstance(editor, TextoRico):
            return editor.ativo()
        return editor

    def copiar(self) -> str:
        """Copiar (§8.11): o modelo fica no processo; o sistema recebe só o texto plano."""
        editor = self._editor_de_edicao()
        if isinstance(editor, TextoRico):
            fragmento = editor.fragmento_da_selecao()
            return self.area.copiar(fragmento)
        selecao = editor.selecao()
        texto = editor.texto.get(*selecao) if selecao else ""
        if texto:
            self.area.copiar(area_mod.Fragmento(blocos=[], inline=True, texto=texto))
        return texto

    def recortar(self) -> str:
        texto = self.copiar()
        if not texto:
            return ""
        editor = self._editor_de_edicao()
        aba = self.aba_ativa()
        if aba is not None and aba.somente_leitura:
            raise ValueError(f"{aba.nome} abre só para leitura.")
        if isinstance(editor, TextoRico):
            editor.apagar_selecao()
        else:
            selecao = editor.selecao()
            if selecao:
                editor.texto.delete(*selecao)
        return texto

    def colar(self, forcar_texto: bool = False) -> str:
        """
        Colar (§8.11): interno (com formato, figura, ilha e notas) quando o texto do sistema
        é o do último copiar; texto de fora vira parágrafos; imagem vira recurso e figura.
        """
        editor = self._editor_de_edicao()
        aba = self.aba_ativa()
        if aba is not None and aba.somente_leitura:
            raise ValueError(f"{aba.nome} abre só para leitura.")
        colagem = self.area.colar(forcar_texto=forcar_texto)
        if colagem is None:
            self.status("Nada para colar.")
            return ""
        if not isinstance(editor, TextoRico):
            if colagem.tipo == "imagem":
                raise ValueError("uma imagem cola só no modo texto (F11)")
            editor.inserir(colagem.texto)
            return colagem.texto
        if colagem.tipo == "interno" and colagem.fragmento is not None:
            editor.colar_fragmento(colagem.fragmento)
            return colagem.texto
        if colagem.tipo == "imagem" and colagem.imagem:
            self._colar_imagem(colagem.imagem)
            return "(imagem)"
        blocos = area_mod.blocos_do_texto(colagem.texto)
        if len(blocos) <= 1:
            texto = blocos[0].trechos[0].texto if blocos else colagem.texto.strip()
            if editor.selecao():
                editor.apagar_selecao()
            editor.inserir(texto)
        else:
            editor.inserir_blocos(blocos)
        return colagem.texto

    def colar_sem_formatacao(self) -> str:
        """`Ctrl+Shift+V`: sempre o texto plano do sistema."""
        return self.colar(forcar_texto=True)

    def colar_como_xhtml(self, texto: str | None = None) -> list[str]:
        """"Colar como XHTML": o texto do sistema é consertado e lido como fragmento do dialeto."""
        editor = self._texto_ativo()
        if texto is None:
            try:
                texto = self.area.ler_sistema() or ""
            except Exception:      # noqa: BLE001 — sem texto no sistema
                texto = ""
        if not texto.strip():
            raise ValueError("não há XHTML na área de transferência")
        blocos, avisos = area_mod.blocos_do_xhtml(texto, self.aba_ativa().arquivo if self.aba_ativa() else "")
        for aviso in avisos:
            self.log.info("colar como XHTML: %s", aviso)
        if not blocos:
            raise ValueError("o XHTML colado não tem nenhum bloco")
        if len(blocos) == 1 and isinstance(blocos[0], Paragrafo) and not isinstance(blocos[0], modelo.Titulo) \
                and editor.objeto_no_cursor() is None:
            editor.inserir_trechos(blocos[0].trechos)
            return [editor.bloco_atual() or ""]
        return editor.inserir_blocos(blocos)

    def _colar_imagem(self, png: bytes, alt: str = "") -> str:
        """A imagem do sistema vira `Images/colada-<n>.png` no livro e uma figura no cursor (§8.7)."""
        projeto = self._exigir_projeto()
        pasta = epub.pasta_de_imagens(projeto.livro)
        n = 1
        while livro_ops.nome_livre(projeto.livro, f"{pasta}/colada-{n}.png") != f"{pasta}/colada-{n}.png":
            n += 1
        href = f"{pasta}/colada-{n}.png"
        projeto.livro.recursos[href] = Recurso(caminho=href, tipo_mime=epub.MIME_PNG, dados=bytes(png))
        projeto.marcar_sujo()
        self.atualizar_navegador()
        self._texto().inserir_objeto(Figura(recurso=href, alt=alt))
        self.log.info("Imagem colada: %s (%d bytes).", href, len(png))
        if not alt:
            self._avisar_alt_vazio(href)
        return href

    def inserir_texto(self, texto: str) -> None:
        editor = self._editor_de_edicao()
        aba = self.aba_ativa()
        if aba is not None and aba.somente_leitura:
            raise ValueError(f"{aba.nome} abre só para leitura.")
        if isinstance(editor, TextoRico):
            if editor.selecao():
                editor.apagar_selecao()
            editor.inserir(texto)
        else:
            editor.inserir(texto)

    def pincel(self) -> bool:
        texto = self._texto_ativo()
        if not self._pincel_carregado:
            texto.pincel_copiar()
            self._pincel_carregado = True
            self.status("Pincel carregado: selecione o texto que recebe a formatação e chame o pincel de novo.")
            return False
        self._pincel_carregado = False
        if not texto.pincel_aplicar():
            self.status("Pincel: nada selecionado.")
            return False
        return True

    def fonte(self) -> dict[str, Any] | None:
        texto = self._texto_ativo()
        e = texto.estilo_no_cursor()
        atual = {"familia": e.get("fam", ""), "corpo_pt": e.get("corpo_pt"), "cor": e.get("cor", ""),
                 "fundo": e.get("fundo", ""),
                 "posicao": "sobre" if e.get("sobrescrito") else ("sub" if e.get("subscrito") else "")}
        for chave in ("negrito", "italico", "sublinhado", "tachado", "versalete"):
            atual[chave] = bool(e.get(chave))
        escolha = self.caixas.fonte(atual)
        if escolha:
            texto.aplicar(**escolha)
        return escolha

    def cor(self) -> str:
        texto = self._texto_ativo()
        atual = texto.estilo_no_cursor().get("cor", "")
        escolhida = self.caixas.cor(atual)
        if escolhida:
            texto.aplicar(cor=escolhida)
        return escolhida

    def paragrafo(self) -> dict[str, Any] | None:
        texto = self._texto_ativo()
        bloco = texto.modelo_de(texto.bloco_atual() or "")
        atual: dict[str, Any] = {}
        if isinstance(bloco, Paragrafo):
            for chave in ("alinhamento", "recuo_primeira_em", "recuo_esquerda_em", "recuo_direita_em", "antes_em",
                          "depois_em", "entrelinha"):
                atual[chave] = getattr(bloco, chave)
        escolha = self.caixas.paragrafo(atual)
        if escolha:
            texto.paragrafo(**escolha)
        return escolha

    def recuar(self, sentido: int) -> Any:
        texto = self._texto_ativo()
        if texto.nivel(sentido):
            return True
        bloco = texto.modelo_de(texto.bloco_atual() or "")
        atual = float(getattr(bloco, "recuo_esquerda_em", None) or 0.0)
        novo = max(0.0, atual + 2.0 * sentido)
        return texto.paragrafo(recuo_esquerda_em=novo or None)

    def zoom(self, sentido: int) -> float:
        editor = self.editor_ativo()
        if editor is None:
            raise ValueError("Nenhuma aba aberta.")
        if isinstance(editor, TextoRico):
            fator = 1.0 if sentido == 0 else editor.tela.zoom * (1.1 if sentido > 0 else 1 / 1.1)
            valor = editor.zoom(round(fator, 3))
            self._gravar_preferencia("zoom", valor)
            return valor
        return float(editor.zoom_zero() if sentido == 0 else editor.zoom(sentido))

    def quebra_automatica(self, ligar: bool) -> bool:
        editor = self.editor_ativo()
        if editor is None:
            raise ValueError("Nenhuma aba aberta.")
        if isinstance(editor, TextoRico):
            editor.texto.configure(wrap="word" if ligar else "none")
        else:
            editor.quebra_automatica(ligar)
        self.variaveis["quebra_automatica"].set(bool(ligar))
        return bool(ligar)

    def novo_estilo(self, nome: str | None = None) -> str | None:
        self._texto()
        if nome is None:
            nome = self.caixas.pedir_texto("Novo estilo a partir da seleção", "Nome do estilo (classe CSS):", "")
            if nome is None:
                return None
        return self.painel_de_estilos.novo_estilo_da_selecao(nome)

    def modificar_estilo(self) -> Aba | None:
        """Abre a folha padrão em código na regra do estilo escolhido no painel (a regra em texto, ED-03)."""
        projeto = self._exigir_projeto()
        nome = self.painel_de_estilos.escolhido()
        if not nome:
            raise ValueError("escolha um estilo no painel Estilos")
        if not projeto.livro.folhas:
            raise ValueError("o livro não tem folha de estilo padrão")
        aba = self.abrir_recurso(projeto.livro.folhas[0])
        regra = self.painel_de_estilos.regra_de(nome).split("{")[0].strip()
        indice = aba.widget.texto.search(regra, "1.0") if regra else ""
        if indice:
            linha, coluna = indice.split(".")
            aba.widget.ir_para(int(linha), int(coluna) + 1)
        aba.widget.foco()
        return aba

    def _gravar_folha_padrao(self, texto: str) -> None:
        projeto = self._exigir_projeto()
        if not projeto.livro.folhas:
            raise ValueError("o livro não tem folha de estilo padrão")
        href = projeto.livro.folhas[0]
        recurso = projeto.livro.recurso(href)
        if recurso is None:
            raise ValueError(f"a folha {href} não está nos recursos")
        recurso.texto_cru = texto
        aba = self.abas.por_arquivo(href)
        if aba is not None and isinstance(aba.widget, EditorDeCodigo):
            aba.widget.carregar(texto)
        projeto.marcar_sujo()
        self.painel_de_estilos.folha_padrao = texto
        self.painel_de_estilos.atualizar()
        self._atualizar_titulo()

    def _texto_do_recurso(self, recurso: Recurso) -> str:
        """O texto de um recurso: o editado (`texto_cru`), senão o que está no zip; "" se sumiu."""
        if recurso.texto_cru is not None:
            return recurso.texto_cru
        if self.projeto is None:
            return ""
        try:
            return epub.dados_de(self.projeto.livro, recurso).decode("utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _atualizar_painel_de_estilos(self) -> None:
        texto = ""
        if self.projeto is not None and self.projeto.livro.folhas:
            recurso = self.projeto.livro.recurso(self.projeto.livro.folhas[0])
            if recurso is not None:
                texto = self._texto_do_recurso(recurso)
        self.painel_de_estilos.folha_padrao = texto
        self.painel_de_estilos.atualizar()

    # -- modo código ------------------------------------------------------

    def inserir_link(self, href: str | None = None, rotulo: str | None = None) -> None:
        """Link… (`Ctrl+K`): no texto, na seleção ou como texto novo (§8.9); no código, `<a href>`."""
        if self.modo_atual() == "texto":
            editor: Any = self._texto_ativo()
            selecao = editor.selecao()
            inicial = editor.texto.get(*selecao) if selecao else ""
            atual = editor.link_no_cursor() or ""
        else:
            editor = self._codigo()
            selecao = editor.selecao()
            inicial = editor.texto.get(*selecao) if selecao else ""
            atual = ""
        if href is None:
            resposta = self.caixas.formulario("Inserir link", [("href", "Destino (href):", atual),
                                                               ("rotulo", "Texto do link:", inicial)])
            if resposta is None:
                return None
            href, rotulo = resposta["href"].strip(), resposta["rotulo"]
            if not href:
                raise ValueError("o link precisa de um destino (href)")
            rotulo = rotulo or None
        if isinstance(editor, TextoRico):
            editor.inserir_link(href, rotulo if not selecao else None)
        else:
            editor.inserir_link(href, rotulo)

    def inserir_ancora(self, id_: str | None = None) -> str | None:
        """Âncora (id)…: no texto, o `id` persistente do bloco do cursor (§8.9); no código, um `id="…"`."""
        if id_ is None:
            atual = ""
            if self.modo_atual() == "texto":
                bloco = self._texto_ativo().modelo_de(self._texto_ativo().bloco_atual() or "")
                atual = bloco.id if bloco is not None and bloco.id_persistente else ""
            id_ = self.caixas.pedir_texto("Inserir âncora", "id:", atual)
            if id_ is None:
                return None
        id_ = id_.strip()
        if not re.fullmatch(r"[^\W\d][\w.:-]*", id_):
            raise ValueError(f"id inválido: {id_!r} — comece por letra, sem espaços")
        if self.modo_atual() == "texto":
            texto = self._texto_ativo()
            bloco_id = texto.bloco_atual()
            if bloco_id is None:
                raise ValueError("o cursor precisa estar num bloco")
            texto.definir_id(bloco_id, id_)
            self.painel_de_propriedades.atualizar(forcar=True)
            return id_
        self._codigo().inserir_id(id_)
        return id_

    def inserir_imagem(self, caminho: str | None = None, alt: str | None = None) -> str | None:
        """
        Imagem…: no texto, um arquivo de imagem vira recurso do livro (em `Images/`) e uma
        `Figura` no cursor (§8.7); um recurso que já está no livro entra direto. No código,
        um `<img>` de um recurso do livro. Devolve o href do recurso.
        """
        projeto = self._exigir_projeto()
        aba = self.aba_ativa()
        assert aba is not None
        imagens = [c for c, r in projeto.livro.recursos.items() if r.tipo_mime.startswith("image/")]
        if self.modo_atual() == "codigo":
            editor = self._codigo()
            if caminho is None:
                if not imagens:
                    raise ValueError("o livro não tem imagens (Livro → Adicionar arquivo… chega na ED-08)")
                indice = self.caixas.escolher("Inserir imagem", "Imagem do livro:", imagens, "Inserir")
                if indice is None:
                    return None
                caminho = imagens[indice]
                alt = self.caixas.pedir_texto("Inserir imagem", "Texto alternativo (alt):", "") or ""
            relativo = posixpath.relpath(caminho, posixpath.dirname(aba.arquivo) or ".")
            editor.inserir_imagem(relativo, alt or "")
            return caminho
        texto = self._texto()
        if caminho is None:
            caminho = self.caixas.abrir_imagem(self._preferencia("diretorios", {}).get("imagens", ""))
            if not caminho:
                return None
            alt = self.caixas.pedir_texto("Inserir imagem", "Texto alternativo (alt):", "")
            if alt is None:
                return None
        if caminho in imagens:
            href = caminho
        else:
            caminho = os.path.abspath(os.fspath(caminho))
            if not os.path.isfile(caminho):
                raise ValueError(f"o arquivo não existe: {caminho}")
            tipo = epub.tipo_mime_de(caminho)
            if not tipo.startswith("image/"):
                raise ValueError(f"{os.path.basename(caminho)} não é uma imagem (PNG, JPEG, GIF ou SVG)")
            with open(caminho, "rb") as f:
                dados = f.read()
            pasta = epub.pasta_de_imagens(projeto.livro)
            href = livro_ops.nome_livre(projeto.livro, f"{pasta}/{os.path.basename(caminho)}")
            projeto.livro.recursos[href] = Recurso(caminho=href, tipo_mime=tipo, dados=dados)
            projeto.marcar_sujo()
            self.atualizar_navegador()
            self._gravar_preferencia("diretorios", {**self._preferencia("diretorios", {}),
                                                   "imagens": os.path.dirname(caminho)})
            self.log.info("Imagem adicionada ao livro: %s (%d bytes).", href, len(dados))
        texto.inserir_objeto(Figura(recurso=href, alt=(alt or "").strip()))
        if not (alt or "").strip():
            self._avisar_alt_vazio(href)
        self.painel_de_propriedades.atualizar(forcar=True)
        return href

    def _avisar_alt_vazio(self, href: str) -> None:
        self.log.warning("%s: figura sem texto alternativo (alt) — preencha em Propriedades.", href)
        self.status(f"{posixpath.basename(href)}: sem alt — preencha o texto alternativo em Propriedades.")

    def dividir_capitulo(self) -> str | None:
        """
        Dividir capítulo aqui. No texto (`Ctrl+Shift+Enter`), por `livro_ops.dividir` antes
        do bloco do cursor (um parágrafo é partido nele); no código (`Ctrl+Enter`), o texto
        depois do cursor vira o capítulo novo (§9.5). As abas e o sumário são recarregados.
        """
        projeto = self._exigir_projeto()
        aba = self.aba_ativa()
        assert aba is not None
        if aba.modo == "texto":
            return self._dividir_no_texto(aba)
        editor = self._codigo()
        partes = editor.dividir_no_cursor()
        if partes is None:
            raise ValueError("não dá para dividir aqui: o cursor precisa estar no corpo, entre blocos")
        antes, depois = partes
        cap = self._capitulo_da_aba(aba)
        cap.texto_cru = antes
        novo_nome = livro_ops.nome_livre(projeto.livro, cap.arquivo)
        novo = Capitulo(arquivo=novo_nome, texto_cru=depois, folhas=list(cap.folhas), idioma=cap.idioma,
                        namespaces=dict(cap.namespaces), linear=cap.linear)
        projeto.livro.capitulos.insert(projeto.livro.capitulos.index(cap) + 1, novo)
        editor.carregar(antes)
        projeto.marcar_sujo()
        self.atualizar_navegador()
        self.log.info("Dividido: %s → %s.", cap.arquivo, novo_nome)
        self.abrir_capitulo(novo_nome, modo="codigo")
        return novo_nome

    def _dividir_no_texto(self, aba: Aba) -> str:
        projeto = self._exigir_projeto()
        texto = self._texto()
        if texto.em_nota():
            raise ValueError("o cursor está na faixa de notas: dividir se faz no corpo do capítulo (Esc)")
        bloco_id, desloc = texto.posicao()
        if bloco_id is None:
            raise ValueError("o cursor precisa estar num bloco")
        bloco = texto.modelo_de(bloco_id)
        if isinstance(bloco, Paragrafo) and 0 < desloc < len(modelo.texto_de(bloco)):
            texto.enter()
            bloco_id = texto.bloco_atual()
        ordem = texto.ordem_do_capitulo
        i = ordem.index(bloco_id) if bloco_id in ordem else 0
        if i == 0:
            raise ValueError("o cursor está no primeiro bloco: não há o que deixar no capítulo de cima")
        self._sincronizar_aba(aba)
        novo_nome = livro_ops.dividir(projeto.livro, aba.arquivo, i)
        projeto.marcar_sujo()
        self._recarregar_aba(aba)
        self.atualizar_navegador()
        self.atualizar_sumario()
        self.log.info("Dividido: %s → %s (antes do bloco %d).", aba.arquivo, novo_nome, i + 1)
        self.abrir_capitulo(novo_nome)
        return novo_nome

    def juntar_com_anterior(self) -> str:
        """Livro → Juntar com o anterior (`livro_ops.juntar`): a aba do que entrou fecha; a do alvo recarrega."""
        projeto = self._exigir_projeto()
        aba = self.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("abra o capítulo que vai se juntar ao anterior")
        self._sincronizar_tudo()
        alvo = livro_ops.juntar(projeto.livro, aba.arquivo)
        projeto.marcar_sujo()
        self.abas.fechar(aba)
        aba_do_alvo = self.abas.por_arquivo(alvo)
        if aba_do_alvo is not None:
            self._recarregar_aba(aba_do_alvo)
        self.atualizar_navegador()
        self.atualizar_sumario()
        self.log.info("Juntado: %s → %s.", aba.arquivo, alvo)
        self.abrir_capitulo(alvo)
        return alvo

    def _recarregar_aba(self, aba: Aba) -> None:
        """O widget da aba redesenhado do modelo (depois de `livro_ops` mexer no capítulo)."""
        if self.projeto is None or aba.widget is None:
            return
        cap = self.projeto.livro.capitulo(aba.arquivo)
        if cap is None:
            return
        if isinstance(aba.widget, TextoRico):
            if cap.texto_cru is not None:
                cap.blocos, cap.notas = list(xhtml.ler(cap.texto_cru, cap.arquivo).blocos), []
            aba.widget.carregar(cap)
            aba.widget._sujo = True
        elif isinstance(aba.widget, EditorDeCodigo):
            texto = cap.texto_cru if cap.texto_cru is not None else \
                xhtml.escrever(cap, pasta_de_imagens=epub.pasta_de_imagens(self.projeto.livro))
            aba.widget.carregar(texto)
        self.abas.rotular(aba)

    # -- objetos, notas, propriedades, links (ED-04) -----------------------------

    def inserir_tabela(self, filas: int | None = None, colunas: int | None = None,
                       cabecalho: bool = False) -> str | None:
        """Inserir → Tabela…: uma tabela vazia no cursor, e o foco na primeira célula (§8.6)."""
        texto = self._texto()
        if filas is None or colunas is None:
            resposta = self.caixas.tabela()
            if resposta is None:
                return None
            filas, colunas, cabecalho = resposta
        filas, colunas = int(filas), int(colunas)
        if filas < 1 or colunas < 1:
            raise ValueError("a tabela precisa de pelo menos uma fila e uma coluna")
        tabela = Tabela(filas=[[Celula(blocos=[], cabecalho=bool(cabecalho and f == 0)) for _ in range(colunas)]
                               for f in range(filas)], primeira_fila_cabecalho=bool(cabecalho))
        texto.inserir_bloco_no_cursor(tabela)
        grade = texto.widget_do_objeto(tabela.id)
        if isinstance(grade, GradeDeTabela):
            grade.entrar(0, 0)
        self.painel_de_propriedades.atualizar(forcar=True)
        return tabela.id

    def tabela_excluir(self) -> bool:
        texto = self._texto()
        grade = self._grade()
        texto.selecionar_objeto(grade.tabela.id)
        texto.foco()
        return texto.apagar_selecao()

    def inserir_ilha(self, xhtml_texto: str | None = None) -> list[str]:
        """Inserir → Ilha de XHTML…: o fragmento do mini-editor entra como ilha (ou como dialeto, se couber)."""
        editor = self._texto_ativo()
        if xhtml_texto is None:
            xhtml_texto = self.caixas.ilha("", "Inserir ilha de XHTML")
            if xhtml_texto is None:
                return []
        blocos, avisos = area_mod.blocos_do_xhtml(xhtml_texto, self.aba_ativa().arquivo if self.aba_ativa() else "")
        for aviso in avisos:
            self.log.info("ilha: %s", aviso)
        if not blocos:
            raise ValueError("o fragmento não tem nenhum bloco")
        if len(blocos) == 1 and isinstance(blocos[0], Paragrafo) and not isinstance(blocos[0], modelo.Titulo) \
                and editor.objeto_no_cursor() is None:
            editor.inserir_trechos(blocos[0].trechos)
            return [editor.bloco_atual() or ""]
        return editor.inserir_blocos(blocos)

    def editar_ilha(self, xhtml_texto: str | None = None) -> bool:
        """A ação principal da ilha (bloco ou inline): o mini-editor; o resultado volta ao texto."""
        editor = self._texto_ativo()
        alvo = editor.alvo_das_propriedades()
        if alvo["tipo"] not in ("ilha", "ilha_inline"):
            raise ValueError("o cursor precisa estar sobre uma ilha de XHTML")
        if xhtml_texto is None:
            xhtml_texto = self.caixas.ilha(alvo["campos"]["xhtml"], "Editar ilha de XHTML")
            if xhtml_texto is None:
                return False
        editor.aplicar_propriedades(alvo, {"xhtml": xhtml_texto})
        self.painel_de_propriedades.atualizar(forcar=True)
        return True

    def apagar_nota(self, nota_id: str | None = None) -> bool:
        texto = self._texto_ativo()
        nota_id = nota_id or texto.nota_no_cursor() or texto.em_nota()
        if not nota_id:
            raise ValueError("o cursor precisa estar numa referência de nota ou na nota")
        return texto.apagar_nota(nota_id)

    def propriedades_do_objeto(self) -> dict[str, Any]:
        """`Alt+Enter`: o painel Propriedades (visível) com o objeto ou parágrafo do cursor, e o foco nele."""
        self._texto()
        if not self.paineis["propriedades"].visivel:
            self.mostrar_painel("propriedades", True)
        alvo = self.painel_de_propriedades.atualizar(forcar=True)
        self.painel_de_propriedades.foco()
        return alvo

    def acao_principal(self, objeto: Any) -> str:
        """
        `Enter` sobre um objeto (§7.4): tabela → primeira célula; ilha → mini-editor;
        diagrama → editor de posição (ED-05); os demais → propriedades.
        """
        texto = self._texto()
        if isinstance(objeto, Tabela):
            grade = texto.widget_do_objeto(objeto.id)
            if isinstance(grade, GradeDeTabela):
                grade.entrar(0, 0)
                return "tabela"
        if isinstance(objeto, (IlhaBruta, Trecho)):
            self.editar_ilha()
            return "ilha"
        if isinstance(objeto, Diagrama):
            texto.selecionar_objeto(objeto.id)
            self.executar("editar_posicao")
            return "diagrama"
        self.propriedades_do_objeto()
        return "propriedades"

    def _acao_das_propriedades(self, nome: str, alvo: dict[str, Any]) -> Any:
        """Os botões de ação do painel Propriedades."""
        if nome == "seguir_link":
            return self.executar("seguir_link")
        if nome == "ir_para_nota":
            texto = self._texto()
            texto.ir_para_nota(alvo["id"])
            return alvo["id"]
        if nome == "entrar_na_tabela":
            grade = self._texto().widget_do_objeto(alvo["id"])
            if isinstance(grade, GradeDeTabela):
                grade.entrar(0, 0)
            return alvo["id"]
        if nome == "editar_ilha":
            return self.executar("editar_ilha")
        if nome == "editar_posicao":
            self._texto().selecionar_objeto(alvo["id"])
            return self.executar("editar_posicao")
        if nome == "limpar_suspeita":
            feito = self._texto().limpar_suspeita(alvo["id"])
            self.painel_de_propriedades.atualizar(forcar=True)
            self.status("Bloco marcado como revisto" if feito else "O bloco não estava marcado como suspeito")
            return feito
        return None

    def descrever_suspeita(self, bloco: Any) -> tuple[list[str], list[str]]:
        """
        `(motivos, leituras)` de um bloco suspeito (ED-11, §10.6.5): as frases e as linhas com as
        duas leituras vêm do documento editorial do projeto; sem ele, os códigos do `data-suspeito`.
        """
        codigos = str(getattr(bloco, "extras", {}).get("data-suspeito", "")).split()
        motivos, leituras = list(codigos), []
        documento = self.projeto.documento_editorial if self.projeto is not None else None
        origem = getattr(bloco, "origem", None)
        if documento is None or origem is None:
            return motivos, leituras
        for page in documento.pages:
            if page.page_id != origem.page_id:
                continue
            block = next((b for b in page.blocks if b.id == origem.bloco_id), None)
            if block is None:
                break
            frases = [str(f) for f in block.metadata.get("motivos") or []]
            motivos = frases or motivos
            evidencias = {e.id: e for e in page.evidence}
            for linha in block.metadata.get("linhas") or []:
                leituras.append(str(linha.get("texto", "")))
                evidencia = evidencias.get(str(linha.get("evidence_id", "")))
                for alternativa in (evidencia.alternatives if evidencia is not None else []):
                    papel = alternativa.metadata.get("papel") or alternativa.source
                    leituras.append(f"  {papel}: {alternativa.text}")
                if evidencia is not None and evidencia.diagnostics:
                    leituras.append("  motivos: " + "; ".join(evidencia.diagnostics))
            break
        return motivos, leituras

    def _resolver_destino(self, href: str, de_arquivo: str) -> tuple[str, str]:
        """`(arquivo, âncora)` de um href interno relativo ao OPF, ou `#id` do próprio capítulo."""
        arquivo, _, ancora = href.partition("#")
        if not arquivo:
            arquivo = de_arquivo
        return posixpath.normpath(arquivo), ancora

    def destino_existe(self, href: str, de_arquivo: str | None = None) -> bool:
        """Um link interno aponta para um capítulo (e um `id`) que existe? (INV-02; AC-ED04-4)"""
        if self.projeto is None or not href:
            return True
        if "://" in href or href.startswith(("mailto:", "data:")):
            return True
        aba = self.aba_ativa()
        arquivo, ancora = self._resolver_destino(href, de_arquivo or (aba.arquivo if aba else ""))
        livro = self.projeto.livro
        cap = livro.capitulo(arquivo)
        if cap is None:
            return livro.recurso(arquivo) is not None and not ancora
        if not ancora:
            return True
        aba_do_cap = self.abas.por_arquivo(arquivo)
        if aba_do_cap is not None and isinstance(aba_do_cap.widget, TextoRico):
            widget = aba_do_cap.widget
            if widget.modelo_de(ancora) is not None or ancora in widget.ids_das_notas():
                return True
            return any(b.id == ancora for b in modelo.blocos_do_capitulo(widget.sincronizar()))
        if cap.texto_cru is not None:
            return ancora in _RE_ID.findall(cap.texto_cru)
        return any(b.id == ancora for b in modelo.blocos_do_capitulo(cap)) or cap.nota(ancora) is not None

    def seguir_link(self) -> str | None:
        """
        Editar → Seguir link: um link externo abre no navegador; `arquivo#id` troca de aba e
        vai ao bloco (§8.9). Destino inexistente: em vermelho no painel, em Resultados, e erro.
        """
        aba = self.aba_ativa()
        if aba is None:
            raise ValueError("Nenhuma aba aberta.")
        if aba.modo == "codigo":
            self._codigo().ir_ao_alvo()
            return None
        texto = self._texto_ativo()
        href = texto.link_no_cursor()
        if not href:
            raise ValueError("o cursor não está sobre um link")
        if "://" in href or href.startswith("mailto:"):
            self.abrir_url(href)
            self.log.info("Link externo: %s", href)
            return href
        if href.startswith("data:"):
            raise ValueError("um link data: não se segue")
        arquivo, ancora = self._resolver_destino(href, aba.arquivo)
        if not self.destino_existe(href, aba.arquivo):
            self.painel_de_propriedades.atualizar(forcar=True)
            bloco_id, desloc = texto.posicao()
            self.resultados.definir([Resultado(aba.arquivo, "link", f"destino inexistente: {href}",
                                               {"bloco": bloco_id or "", "deslocamento": desloc})],
                                    "Links quebrados")
            self.log.warning("%s: link para destino inexistente: %s", aba.arquivo, href)
            raise ValueError(f"o destino {href!r} não existe no livro")
        self.ir_para_destino(f"{arquivo}#{ancora}" if ancora else arquivo)
        return href

    def bem_formado(self) -> Any:
        editor = self._codigo()
        aba = self.aba_ativa()
        assert aba is not None
        if editor.linguagem != "xhtml":
            raise ValueError("bem-formado é para XHTML; para CSS use Reformatar CSS")
        erro = editor.verificar_bem_formado()
        if erro is None:
            self.validacao.definir([], "Bem-formado")
            self.status(f"{aba.nome}: bem-formado.")
            self.log.info("%s: bem-formado.", aba.nome)
        else:
            self._relatar_erro_de_xhtml(aba, erro)
            editor.ir_para(erro.linha, erro.coluna)
        return erro

    def consertar(self) -> list[str]:
        editor = self._codigo()
        aba = self.aba_ativa()
        assert aba is not None
        avisos = editor.consertar()
        for aviso in avisos:
            self.log.info("%s: consertar: %s", aba.nome, aviso)
        self.status(f"{aba.nome}: {len(avisos)} conserto(s).")
        return avisos

    def reformatar(self) -> Any:
        editor = self._codigo()
        aba = self.aba_ativa()
        assert aba is not None
        erro = editor.reformatar()
        if erro is not None:
            self._relatar_erro_de_xhtml(aba, erro)
            editor.ir_para(erro.linha, erro.coluna)
        else:
            self.status(f"{aba.nome}: reformatado.")
        return erro

    def clipes_comando(self) -> Any:
        """`Ctrl+Shift+J`: mostra a barra de clipes (a ED-07 a desenha) e leva o foco ao primeiro."""
        if self.editor_ativo() is None:
            raise ValueError("Nenhuma aba aberta.")
        if self.barra_de_clipes is None:
            from ui.editor.clipes import BarraDeClipes

            self.barra_de_clipes = BarraDeClipes(self.barras, self.clipes, self.aplicar_clipe)
        if not self.barra_de_clipes.winfo_ismapped():
            self.barra_de_clipes.pack(side="top", fill="x")
        botoes = self.barra_de_clipes.botoes
        if botoes:
            botoes[0].focus_set()
        return self.barra_de_clipes

    def aplicar_clipe(self, clipe: Any) -> str:
        """No código, o texto do clipe; no texto, o fragmento vira modelo (`blocos_do_xhtml`) — AC-ED08-9."""
        if self.modo_atual() == "codigo":
            return self._codigo().aplicar_clipe(clipe)
        editor = self._texto_ativo()
        selecao = editor.selecao()
        conteudo = editor.texto.get(*selecao) if selecao else ""
        texto, _cursor = clipe.aplicar(conteudo)
        blocos, avisos = area_mod.blocos_do_xhtml(texto, self.aba_ativa().arquivo if self.aba_ativa() else "")
        for aviso in avisos:
            self.log.info("clipe: %s", aviso)
        if not blocos:
            raise ValueError("o clipe não produziu nenhum bloco")
        if selecao:
            editor.apagar_selecao()
        if len(blocos) == 1 and isinstance(blocos[0], Paragrafo) and not isinstance(blocos[0], modelo.Titulo) \
                and editor.objeto_no_cursor() is None:
            editor.inserir_trechos(blocos[0].trechos)
        else:
            editor.inserir_blocos(blocos)
        return texto

    def _itens_de_clipes(self) -> list[tuple[str, Callable[[], Any] | None]]:
        return [(f"{c.grupo}: {c.nome}", (lambda c=c: self.executar("aplicar_clipe", c))) for c in self.clipes]

    def _itens_recentes(self) -> list[tuple[str, Callable[[], Any] | None]]:
        return [(c, (lambda c=c: self.executar("abrir", c))) for c in self.recentes.lista()]

    # -- livro, ferramentas, ajuda -------------------------------------------

    def metadados(self, titulo: str | None = None, autor: str | None = None, idioma: str | None = None) -> Any:
        projeto = self._exigir_projeto()
        md = projeto.livro.metadados
        if titulo is None:
            resposta = self.caixas.formulario("Metadados", [
                ("titulo", "Título:", md.titulo), ("autor", "Autor:", md.autores[0].nome if md.autores else ""),
                ("idioma", "Idioma:", md.idioma)], {"idioma": IDIOMAS},
                "Capa, editora, coleção e o resto do OPF chegam na ED-08.")
            if resposta is None:
                return None
            titulo, autor, idioma = resposta["titulo"], resposta["autor"], resposta["idioma"]
        titulo = (titulo or "").strip()
        if not titulo:
            raise ValueError("o livro precisa de um título")
        md.titulo = titulo
        if idioma:
            md.idioma = idioma.strip()
        autor = (autor or "").strip()
        if autor:
            if md.autores:
                md.autores[0].nome = autor
            else:
                md.autores.append(Pessoa(nome=autor))
        elif md.autores:
            md.autores.pop(0)
        projeto.marcar_sujo()
        self.log.info("Metadados: %s — %s (%s).", md.titulo, autor or "sem autor", md.idioma)
        self.atualizar()
        return md

    def contagem(self) -> dict[str, int]:
        projeto = self._exigir_projeto()
        aba = self.aba_ativa()
        capitulo = self._palavras_da_aba(aba) if aba is not None else 0
        self._sincronizar_tudo()
        livro = sum(_palavras_do_capitulo(c) for c in projeto.livro.capitulos)
        saida = {"capitulo": capitulo, "livro": livro, "capitulos": len(projeto.livro.capitulos)}
        self.status(f"{capitulo:,} palavras neste capítulo; {livro:,} no livro.".replace(",", "."))
        self.caixas.informar(f"Capítulo atual: {capitulo:,} palavras\nLivro: {livro:,} palavras em "
                             f"{len(projeto.livro.capitulos)} capítulos".replace(",", "."), "Contagem de palavras")
        return saida

    def atalhos(self) -> str:
        texto = atalhos_mod.texto_de_ajuda()
        self.caixas.texto("Atalhos de teclado", texto)
        return texto

    def dialeto(self) -> str:
        from core.editor import dialeto as dialeto_mod

        linhas = ["O dialeto do livro (SPEC_EDITOR §6)", "",
                  "O modo texto edita só este vocabulário; o resto vira ilha (editável no modo código, F11).", "",
                  "Estilos de parágrafo:"]
        for nome, (elemento, classe, docx) in dialeto_mod.ESTILOS_DE_PARAGRAFO.items():
            seletor = elemento + (f".{classe}" if classe else "")
            linhas.append(f"  {nome:20s} {seletor:24s} (DOCX: {docx})")
        linhas += ["", "Estilos de caractere:"]
        for nome, (classe, docx) in dialeto_mod.ESTILOS_DE_CARACTERE.items():
            linhas.append(f"  {nome:20s} span.{classe:18s} (DOCX: {docx})")
        linhas += ["", "Blocos: parágrafo, título 1–6, lista, tabela, figura, diagrama (div.diagrama com o FEN em",
                   "data-fen), citação, separador, quebra de página, marca de página, nota de rodapé e de fim.",
                   "Trechos: negrito, itálico, sublinhado, tachado, versalete, sobrescrito, subscrito, código,",
                   "link, referência, nota, lance, NAG, figurina, jogador, abertura."]
        texto = "\n".join(linhas)
        self.caixas.texto("O dialeto do livro", texto)
        return texto

    def sobre(self) -> str:
        texto = ("Editor de livro do PyBoxEditor\n\nModo texto (à maneira do WordPad e do Word) e modo código "
                 "(à maneira do Sigil), sobre o mesmo livro; salva EPUB 3.\n\n"
                 "Fases prontas: ED-00, ED-01, ED-02, ED-03, ED-04, ED-05, ED-05b, ED-06, ED-06b, ED-07, ED-08, ED-09, "
                 "ED-09b, ED-10, ED-11, ED-12.")
        self.caixas.informar(texto, "Sobre o editor de livro")
        return texto

    # -- ED-06: ir para, símbolos, código Unicode, estatísticas, léxicos ----------------

    def lexicos(self) -> Any:
        """Os léxicos da ortografia deste livro (um por idioma, com o dicionário ao lado do EPUB)."""
        from core.editor.ortografia import Lexicos

        projeto = self._exigir_projeto()
        caminho = projeto.caminho or None
        if self._lexicos_cache is None or self._lexicos_cache[0] != caminho:
            self._lexicos_cache = (caminho, Lexicos(caminho))
        return self._lexicos_cache[1]

    def ir_para(self, tipo: str | None = None, n: int | None = None) -> Any:
        """
        Ir para… (`Ctrl+G`): linha (código), bloco (texto), diagrama, figura, tabela, página
        do impresso ou capítulo (AC-ED06-4). Sem argumentos, pergunta.
        """
        from core.editor import busca as busca_mod

        projeto = self._exigir_projeto()
        aba = self.aba_ativa()
        if aba is None:
            raise ValueError("Nenhuma aba aberta.")
        modo = self.modo_atual()
        tipos = ([("linha", "Linha")] if modo == "codigo" else [("bloco", "Bloco")]) + [
            ("diagrama", "Diagrama"), ("figura", "Figura"), ("tabela", "Tabela"), ("pagina", "Página do impresso"),
            ("capitulo", "Capítulo")]
        if tipo is None:
            resposta = self.caixas.ir_para(tipos, tipos[0][0], 1)
            if resposta is None:
                return None
            tipo, n = resposta
        n = int(n if n is not None else 1)
        if tipo == "linha":
            editor = self._codigo()
            total = int(editor.texto.index("end-1c").split(".")[0])
            if not 1 <= n <= total:
                raise ValueError(f"a linha precisa estar entre 1 e {total}")
            editor.ir_para(n)
            editor.foco()
            return n
        destino = busca_mod.destino(projeto.livro, tipo, n, aba.arquivo if aba.tipo == "capitulo" else "")
        if destino is None:
            rotulo = dict(tipos).get(tipo, tipo)
            raise ValueError(f"não há {rotulo.lower()} {n} no livro")
        alvo = self.abrir_capitulo(destino.arquivo)
        if destino.bloco_id and alvo.widget is not None:
            if isinstance(alvo.widget, TextoRico):
                if destino.bloco_id in alvo.widget.ordem:
                    bloco = alvo.widget.modelo_de(destino.bloco_id)
                    if isinstance(bloco, Paragrafo):
                        alvo.widget.ir_para(destino.bloco_id, destino.deslocamento)
                    else:
                        alvo.widget.selecionar_objeto(destino.bloco_id)
                        alvo.widget.texto.see("insert")
            else:
                indice = alvo.widget.texto.search(f'id="{destino.bloco_id}"', "1.0")
                if indice:
                    alvo.widget.ir_para(int(indice.split(".")[0]))
        alvo.widget.foco()
        self.status(f"Ir para: {destino.endereco}")
        return destino

    def inserir_simbolo(self, caractere: str | None = None) -> str | None:
        """Inserir → Símbolo…: a caixa de símbolos; o escolhido entra no editor ativo."""
        if self.editor_ativo() is None:
            raise ValueError("Nenhuma aba aberta.")
        if caractere is None:
            caractere = self.caixas.simbolo()
            if not caractere:
                return None
        self.inserir_texto(caractere)
        return caractere

    def codigo_unicode(self) -> str | None:
        """`Ctrl+Shift+X`: o hexadecimal antes do cursor vira o caractere, e o caractere vira o código."""
        from core.editor import simbolos as simbolos_mod

        texto = self._texto_ativo()
        bloco_id, desloc = texto.posicao()
        if bloco_id is None:
            raise ValueError("o cursor precisa estar num bloco de texto")
        bloco = texto.modelo_de(bloco_id)
        if not isinstance(bloco, Paragrafo) and bloco_id not in texto.ordem:
            raise ValueError("o cursor precisa estar num parágrafo")
        antes = modelo.texto_de(bloco)[:desloc] if bloco is not None else ""
        if texto.selecao():
            antes = texto.texto.get(*texto.selecao())
            desloc = texto.posicao_de(texto.selecao()[1])[1]
        resultado = simbolos_mod.alternar(antes)
        if resultado is None:
            raise ValueError("não há nada antes do cursor para converter")
        quantos, novo = resultado
        texto.selecionar(desloc - quantos, desloc, bloco_id)
        texto.apagar_selecao()
        texto.inserir(novo)
        self.status(f"{antes[-quantos:]!r} → {novo!r}")
        return novo

    def estatisticas(self) -> Any:
        """Ferramentas → Estatísticas do livro…: a contagem do modelo, por capítulo e no total."""
        from core.editor import estatisticas as estatisticas_mod

        projeto = self._exigir_projeto()
        self._sincronizar_tudo()
        total = estatisticas_mod.contar_livro(projeto.livro)
        linhas = [f"{projeto.nome}", ""] + total.linhas() + ["", "Por capítulo:"]
        for cap in projeto.livro.capitulos:
            c = estatisticas_mod.contar_capitulo(cap)
            linhas.append(f"  {cap.arquivo}: {c.palavras} palavras, {c.caracteres} caracteres, {c.blocos} blocos")
        if total.avisos:
            linhas += ["", "Avisos:"] + [f"  {a}" for a in total.avisos]
        self.caixas.texto("Estatísticas do livro", "\n".join(linhas), monoespaco=False)
        self.status(f"{total.palavras:,} palavras no livro".replace(",", "."))
        return total

    # ==================================================================
    # Painéis, barras, foco, tela
    # ==================================================================

    def mostrar_painel(self, nome: str, visivel: bool) -> bool:
        painel = self.paineis[nome]
        if painel.visivel == bool(visivel):
            return painel.visivel
        tinha_foco = self._painel_com_foco() == nome
        grupo = {"esquerda": self.esquerda, "centro": self.centro, "direita": self.direita}.get(painel.grupo)
        if painel.grupo == "inferior":
            if visivel:
                self.centro.add(self.inferior, weight=1)
            else:
                self.centro.forget(self.inferior)
            for outro in self.paineis.values():
                if outro.grupo == "inferior":
                    outro.visivel = bool(visivel)
        else:
            assert grupo is not None
            if visivel:
                antes = [p for p in self.paineis.values() if p.grupo == painel.grupo and p.visivel
                         and ORDEM_DOS_PAINEIS.index(p.nome) < ORDEM_DOS_PAINEIS.index(nome)]
                _por_em(grupo, len(antes), painel.widget)
            else:
                grupo.forget(painel.widget)
            painel.visivel = bool(visivel)
            self._ajustar_laterais()
        if nome in self.variaveis:
            self.variaveis[nome].set(bool(visivel))
        if not visivel and tinha_foco:
            self.foco_no_editor()
        self._gravar_layout()
        return painel.visivel

    def _ajustar_laterais(self) -> None:
        """Uma lateral sem painel visível some da janela; volta quando um deles reaparece."""
        for grupo, paned, posicao in (("esquerda", self.esquerda, 0), ("direita", self.direita, 2)):
            algum = any(p.visivel for p in self.paineis.values() if p.grupo == grupo)
            presente = str(paned) in self.paned.panes()
            if algum and not presente:
                _por_em(self.paned, posicao, paned)
            elif not algum and presente:
                self.paned.forget(paned)

    def _painel_pela_variavel(self, nome: str) -> bool:
        return self.mostrar_painel(nome, self.variaveis[nome].get())

    def mostrar_barra(self, nome: str, visivel: bool) -> bool:
        barra = {"formatacao": self.barra_de_formatacao, "codigo": self.barra_de_codigo,
                 "xadrez": self.barra_de_xadrez}[nome]
        chave = "barra_de_formatacao" if nome in ("formatacao", "codigo") else "barra_de_xadrez"
        self.variaveis[chave].set(bool(visivel))
        if visivel:
            self._empilhar_barras()
        else:
            barra.pack_forget()
        self._gravar_layout()
        return bool(visivel)

    def _empilhar_barras(self) -> None:
        """A ordem das barras: arquivo, a do modo (formatação ou código), xadrez, clipes."""
        for barra in (self.barra_de_arquivo, self.barra_de_formatacao, self.barra_de_codigo, self.barra_de_xadrez):
            barra.pack_forget()
        self.barra_de_arquivo.pack(side="top", fill="x")
        if self.variaveis["barra_de_formatacao"].get():
            do_modo = self.barra_de_codigo if self.modo_atual() == "codigo" else self.barra_de_formatacao
            do_modo.pack(side="top", fill="x")
        if self.variaveis["barra_de_xadrez"].get():
            self.barra_de_xadrez.pack(side="top", fill="x")
        if self.barra_de_clipes is not None and self.barra_de_clipes.winfo_ismapped():
            self.barra_de_clipes.pack_forget()
            self.barra_de_clipes.pack(side="top", fill="x")

    def _painel_com_foco(self) -> str | None:
        try:
            foco = self.focus_get()
        except (tk.TclError, KeyError):
            return None
        while foco is not None:
            for painel in self.paineis.values():
                if foco is painel.widget:
                    if painel.grupo == "inferior":
                        return painel.nome
                    return painel.nome
            try:
                foco = foco.master
            except AttributeError:
                return None
        return None

    def painel_vizinho(self, passo: int) -> str:
        """F6 / Shift+F6: o próximo painel visível na ordem lógica da §7.1."""
        visiveis = [n for n in ORDEM_DOS_PAINEIS if self.paineis[n].visivel]
        if not visiveis:
            return ""
        atual = self._painel_com_foco()
        if atual in visiveis:
            alvo = visiveis[(visiveis.index(atual) + passo) % len(visiveis)]
        else:
            alvo = visiveis[0] if passo > 0 else visiveis[-1]
        self.paineis[alvo].foco()
        return alvo

    def foco_no_editor(self) -> None:
        editor = self.editor_ativo()
        if editor is not None:
            editor.foco()
        else:
            self.abas.focus_set()

    def escape(self) -> None:
        """`Esc`: fecha as sugestões do código; sai da célula de tabela; volta da nota; senão, foco no editor."""
        editor = self.editor_ativo()
        if isinstance(editor, EditorDeCodigo) and getattr(editor, "_popup", None) is not None:
            editor.fechar_sugestoes()
            return
        if isinstance(editor, TextoRico):
            celula = editor.ativo()
            if celula is not editor and celula.ao_escape is not None:
                celula.ao_escape()
                return
            if editor.em_nota() and editor.voltar_da_nota():
                return
        self.foco_no_editor()

    def menu_de_contexto(self, x: int | None = None, y: int | None = None) -> tk.Menu:
        """`Shift+F10` e a tecla de menu: o menu do editor ativo, no cursor."""
        menu = self.menus.contexto(self.modo_atual())
        editor = self.editor_ativo()
        if not self.winfo_viewable():
            return menu                    # janela escondida (teste): o menu existe, mas não se posta
        if x is None or y is None:
            x, y = self.winfo_rootx() + 40, self.winfo_rooty() + 80
            if editor is not None:
                try:
                    caixa = editor.texto.bbox("insert")
                    if caixa:
                        x = editor.texto.winfo_rootx() + caixa[0]
                        y = editor.texto.winfo_rooty() + caixa[1] + caixa[3]
                except tk.TclError:
                    pass
        try:
            menu.tk_popup(int(x), int(y))
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return menu

    def tela_cheia(self, ligar: bool) -> bool:
        self._tela_cheia = bool(ligar)
        try:
            self.attributes("-fullscreen", self._tela_cheia)
        except tk.TclError:
            pass
        self.variaveis["tela_cheia"].set(self._tela_cheia)
        return self._tela_cheia

    # ==================================================================
    # Navegador e sumário
    # ==================================================================

    def atualizar_navegador(self) -> None:
        self.painel_navegador.atualizar(self.projeto.livro if self.projeto is not None else None,
                                        self.arquivos_marcados)

    def _abrir_do_navegador(self) -> Aba | None:
        href = self.painel_navegador.selecionado()
        if href is None or self.projeto is None:
            return None
        return self.operacoes.abrir_do_navegador(href)

    def abrir_arquivo(self, caminho: str) -> Aba | None:
        """Qualquer entrada do navegador: capítulo, folha, nav/NCX; imagem e OPF avisam."""
        projeto = self._exigir_projeto()
        livro = projeto.livro
        if livro.capitulo(caminho) is not None:
            return self.abrir_capitulo(caminho)
        if caminho in (livro.nav, livro.ncx):
            return self.abrir_leitura(caminho)
        if caminho == livro.opf:
            return self.abrir_leitura(caminho)
        recurso = livro.recurso(caminho)
        if recurso is None:
            raise ValueError(f"{caminho} não está no livro")
        if recurso.tipo_mime.startswith("image/"):
            raise ValueError(f"{caminho}: uma imagem se insere por Inserir → Imagem… (ou vira capa por Livro → Capa…)")
        return self.abrir_recurso(caminho)

    def atualizar_sumario(self) -> None:
        self.painel_sumario.atualizar(self.projeto.livro.sumario if self.projeto is not None else [])

    @property
    def _destinos(self) -> dict[str, str]:
        return self.painel_sumario.destinos

    def _ir_pelo_sumario(self) -> Aba | None:
        destino = self.painel_sumario.destino_selecionado()
        if not destino:
            return None
        return self.ir_para_destino(destino)

    def ir_para_destino(self, destino: str) -> Aba | None:
        """`arquivo#id` → a aba do arquivo, no bloco (texto) ou na linha do `id` (código)."""
        arquivo, _, ancora = destino.partition("#")
        projeto = self._exigir_projeto()
        if projeto.livro.capitulo(arquivo) is None:
            raise ValueError(f"o destino {destino!r} aponta para um capítulo que não existe")
        aba = self.abrir_capitulo(arquivo)
        if ancora and aba.widget is not None:
            if isinstance(aba.widget, TextoRico):
                if aba.widget.modelo_de(ancora) is not None:
                    aba.widget.ir_para(ancora)
                elif ancora in aba.widget.ids_das_notas():
                    aba.widget.ir_para_nota(ancora)
            else:
                indice = aba.widget.texto.search(f'id="{ancora}"', "1.0")
                if indice:
                    aba.widget.ir_para(int(indice.split(".")[0]))
        aba.widget.foco()
        return aba

    # ==================================================================
    # Status, título, atualização
    # ==================================================================

    def status(self, texto: str) -> None:
        self.campos["aviso"].configure(text=texto)

    def _atualizar_titulo(self) -> None:
        if self.projeto is None:
            self.title(TITULO)
            return
        self.title(f"{'• ' if self._sujo() else ''}{self.projeto.nome} — {TITULO}")

    def _atualizar_estado(self) -> None:
        if self.projeto is None:
            self.campos["estado"].configure(text="")
            return
        if self._sujo():
            estado = "• alterado"
        elif self._salvo_em:
            estado = "salvo " + self._salvo_em
        else:
            estado = "sem alterações"
        self.campos["estado"].configure(text=estado)

    def _atualizar_posicao(self, aba: Aba | None) -> None:
        if aba is None or aba.widget is None:
            self.campos["posicao"].configure(text="")
            return
        if isinstance(aba.widget, TextoRico):
            bloco_id, deslocamento = aba.widget.posicao()
            ordem = aba.widget.ordem
            n = ordem.index(bloco_id) + 1 if bloco_id in ordem else 0
            self.campos["posicao"].configure(text=f"bloco {n}/{len(ordem)}, car {deslocamento + 1}")
        else:
            linha, coluna = aba.widget.posicao
            self.campos["posicao"].configure(text=f"linha {linha}, col {coluna}")

    def _agendar_contagem(self) -> None:
        if self._contagem_id is not None:
            try:
                self.after_cancel(self._contagem_id)
            except tk.TclError:
                pass
        try:
            self._contagem_id = self.after(500, self._atualizar_contagem)
        except tk.TclError:
            self._contagem_id = None

    def _atualizar_contagem(self) -> None:
        self._contagem_id = None
        aba = self.aba_ativa()
        if aba is None:
            self.campos["palavras"].configure(text="")
            return
        self.campos["palavras"].configure(text=f"{self._palavras_da_aba(aba):,} palavras".replace(",", "."))

    def _palavras_da_aba(self, aba: Aba) -> int:
        if aba.widget is None:
            return 0
        if isinstance(aba.widget, TextoRico):
            return estatisticas.contar_capitulo(aba.widget.sincronizar()).palavras
        return estatisticas.palavras_de(_RE_TAG.sub(" ", aba.widget.texto_todo()))

    def atualizar(self) -> None:
        """Depois de qualquer mudança de projeto, aba ou modo: menus, barras, status, título, rótulos."""
        if not self.winfo_exists():
            return
        modo = self.modo_atual()
        aba = self.aba_ativa()
        if hasattr(self, "menus"):
            self.menus.atualizar(modo)
        for barra in (self.barra_de_arquivo, self.barra_de_formatacao, self.barra_de_codigo):
            barra.atualizar(self.comandos, modo, self.modos_do_comando)
        self._empilhar_barras()
        self._atualizar_titulo()
        self.abas.rotular()
        if self.projeto is not None:
            capitulos = [c.arquivo for c in self.projeto.livro.capitulos]
            n = capitulos.index(aba.arquivo) + 1 if aba is not None and aba.arquivo in capitulos else 0
            self.campos["capitulo"].configure(text=f"cap {n}/{len(capitulos)}" if n else f"{len(capitulos)} capítulos")
            self.campos["idioma"].configure(text=self.projeto.livro.metadados.idioma)
            self._atualizar_estado()
        else:
            for nome in ("capitulo", "idioma", "estado"):
                self.campos[nome].configure(text="")
        self.campos["modo"].configure(text="MODO CÓDIGO" if modo == "codigo" else "MODO TEXTO")
        self._atualizar_posicao(aba)
        self._atualizar_contagem()
        if aba is not None and isinstance(aba.widget, EditorDeCodigo):
            self.variaveis["numeros_de_linha"].set(aba.widget._numeros_de_linha)
            self.variaveis["realce_da_linha"].set(aba.widget._realce_da_linha)
        if aba is not None and isinstance(aba.widget, TextoRico):
            self.variaveis["invisiveis"].set(aba.widget._invisiveis)
            self.painel_de_propriedades.texto_rico = aba.widget
        else:
            self.painel_de_propriedades.texto_rico = None
        if not self._foco_no_painel_de_propriedades():
            self.painel_de_propriedades.atualizar()

    # ==================================================================
    # Preferências e layout
    # ==================================================================

    def _preferencias(self) -> dict:
        editor = self.settings.get(CHAVE_DAS_PREFERENCIAS, {})
        return dict(editor) if isinstance(editor, dict) else {}

    def _preferencia(self, chave: str, padrao: Any = None) -> Any:
        return self._preferencias().get(chave, padrao)

    def _gravar_preferencia(self, chave: str, valor: Any) -> None:
        editor = self._preferencias()
        editor[chave] = valor
        self.settings.set(CHAVE_DAS_PREFERENCIAS, editor)
        try:
            self.settings.save()
        except OSError as erro:
            self.log.warning("preferências não gravadas: %s", erro)

    def layout(self) -> dict[str, Any]:
        return {"geometria": self.geometry() if self.winfo_exists() else "",
                "paineis": {n: p.visivel for n, p in self.paineis.items() if n != "editor"},
                "barras": {"formatacao": self.variaveis["barra_de_formatacao"].get(),
                           "xadrez": self.variaveis["barra_de_xadrez"].get()}}

    def _gravar_layout(self) -> None:
        if not self.winfo_exists():
            return
        self._gravar_preferencia("layout", self.layout())

    def _restaurar_layout(self) -> None:
        layout = self._preferencia("layout", {})
        if not isinstance(layout, dict):
            return
        geometria = layout.get("geometria")
        if geometria and re.fullmatch(r"\d+x\d+[+-]\d+[+-]\d+", str(geometria)):
            try:
                self.geometry(str(geometria))
            except tk.TclError:
                pass
        paineis = layout.get("paineis", {})
        if isinstance(paineis, dict):
            for nome, visivel in paineis.items():
                if nome in self.paineis and nome != "editor" and not visivel:
                    self.mostrar_painel(nome, False)
        barras = layout.get("barras", {})
        if isinstance(barras, dict):
            for nome, visivel in barras.items():
                if nome in ("formatacao", "xadrez") and not visivel:
                    self.mostrar_barra(nome, False)

    # ==================================================================
    # Rascunho, guarda e fechamento
    # ==================================================================

    def _agendar_tique(self) -> None:
        try:
            self._tique_id = self.after(1000, self._tique_agendado)
        except tk.TclError:
            self._tique_id = None

    def _tique_agendado(self) -> None:
        self._tique_id = None
        if not self.winfo_exists():
            return
        try:
            self._tique()
        finally:
            self._agendar_tique()

    def _tique(self) -> bool:
        """Um segundo do rascunho: sincroniza o que está sujo e deixa o `Rascunho` decidir se grava."""
        if self.projeto is None or self.rascunho is None:
            return False
        if self._sujo():
            if any(a.sujo for a in self.abas.abas) and not self.projeto.sujo:
                self.projeto.marcar_sujo()
            self._sincronizar_tudo()
        gravou = self.rascunho.tique()
        if gravou:
            self.log.info("Rascunho gravado: %s", self.rascunho.ultimo_caminho)
            self.status("Rascunho gravado " + time.strftime("%H:%M"))
        return gravou

    def _instalar_guarda_no_parent(self) -> None:
        """Fechar a janela principal passa pela guarda do editor (AC-ED02-6)."""
        try:
            self._protocolo_anterior = str(self.parent.protocol("WM_DELETE_WINDOW") or "")
            self.parent.protocol("WM_DELETE_WINDOW", self._fechar_pelo_parent)
        except tk.TclError:
            self._protocolo_anterior = None

    def _desinstalar_guarda_no_parent(self) -> None:
        if self._protocolo_anterior is None:
            return
        try:
            self.parent.protocol("WM_DELETE_WINDOW", self._protocolo_anterior)
        except tk.TclError:
            pass
        self._protocolo_anterior = None

    def _fechar_pelo_parent(self) -> None:
        anterior = self._protocolo_anterior
        if self.winfo_exists():
            if self._sujo() and self.rascunho is not None:
                self._sincronizar_tudo()
                self.rascunho.gravar()
            if not self.fechar():
                return
        if anterior:
            self.parent.tk.eval(anterior)
        else:
            self.parent.destroy()

    def fechar(self) -> bool:
        """A guarda (resposta injetável em `caixas.pergunta`); `True` quando fechou."""
        if not self.winfo_exists():
            return True
        if not self._confirmar_descarte():
            return False
        self._gravar_layout()
        if self._tique_id is not None:
            try:
                self.after_cancel(self._tique_id)
            except tk.TclError:
                pass
            self._tique_id = None
        if self._contagem_id is not None:
            try:
                self.after_cancel(self._contagem_id)
            except tk.TclError:
                pass
        if self.projeto is not None:
            self.projeto.fechar()
        self._desinstalar_guarda_no_parent()
        if hasattr(self, "operacoes"):
            self.operacoes.fechar()
        self.mensagens.desinstalar(self.log)
        try:
            self.task.shutdown()
        except Exception:      # noqa: BLE001 — um controlador emprestado pode já estar fechado
            pass
        self.destroy()
        if self.ao_fechar is not None:
            self.ao_fechar()
        return True


# ----------------------------------------------------------------------
# Auxiliares
# ----------------------------------------------------------------------

def _por_em(paned: ttk.PanedWindow, posicao: int, widget: tk.Misc) -> None:
    """`insert` numa posição do `PanedWindow` — ou `add`, porque `insert` no fim (ou no vazio) é erro no Tk."""
    if posicao >= len(paned.panes()):
        paned.add(widget, weight=1)
    else:
        paned.insert(posicao, widget, weight=1)


def _copiar_capitulo(de: Capitulo, para: Capitulo) -> None:
    """O que `xhtml.ler` devolveu entra no capítulo do livro (mesmo objeto, mesma posição na espinha)."""
    for campo in ("titulo", "blocos", "notas", "folhas", "idioma", "semantica", "cabeca_extra", "avisos", "namespaces"):
        setattr(para, campo, getattr(de, campo))


def _palavras_do_capitulo(cap: Capitulo) -> int:
    """A mesma contagem de `core/editor/estatisticas.py` (ED-06): notas e legendas entram (AC-ED06-5)."""
    return estatisticas.contar_capitulo(cap).palavras


def _e_texto(tipo_mime: str) -> bool:
    return tipo_mime.startswith("text/") or tipo_mime in (epub.MIME_XHTML, epub.MIME_NCX, "application/xml",
                                                          "image/svg+xml", "application/javascript")


def _nome_seguro(titulo: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in (titulo or "livro").strip())[:60].strip() or "livro"


def _settings_padrao() -> Any:
    from config.settings import Settings

    return Settings()


def _imagem_do_clipboard() -> bytes | None:
    """A imagem da área de transferência como PNG, pelo `ImageGrab` do PIL (importado só aqui, DEC-07)."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return None
    try:
        imagem = ImageGrab.grabclipboard()
    except Exception:      # noqa: BLE001 — sem imagem, ou plataforma sem ImageGrab
        return None
    if imagem is None or isinstance(imagem, list):
        return None
    import io

    buffer = io.BytesIO()
    imagem.save(buffer, "PNG")
    return buffer.getvalue()


def _task_controller(widget: tk.Misc) -> Any:
    from core.services.task_controller import TaskController

    return TaskController(widget)


def abrir_editor(parent: tk.Misc, caminho: str | None = None, **kw: Any) -> JanelaDoEditor:
    """A porta de entrada da janela principal e da caixa de conclusão: a janela, com o livro aberto."""
    janela = JanelaDoEditor(parent, **kw)
    if caminho:
        janela.executar("abrir", caminho)
    return janela


__all__ = ["JanelaDoEditor", "abrir_editor", "Painel", "ORDEM_DOS_PAINEIS", "FORMATOS_DE_EXPORTACAO", "TITULO"]
