"""
`TextoRico`: o `tk.Text` que desenha o modelo do capítulo e o devolve (ED-03;
SPEC_EDITOR DEC-03, DEC-04, DEC-11, §8.1–§8.5, §8.15).

## O contrato

`carregar(capitulo)` desenha os blocos; `sincronizar()` devolve o `Capitulo` que o
widget contém agora — e é igual (`modelo.igual`) ao carregado enquanto ninguém edita
(AC-ED03-1). Entre um e outro, **toda edição passa pela API** (`inserir`, `apagar`,
`apagar_selecao`, `enter`, `backspace`, `alternar`, `aplicar`, `paragrafo`,
`estilo`, `lista`, `nivel`…): é ela que respeita as faixas protegidas
(`_pode_editar`), mantém as tags de parágrafo cobrindo o bloco inteiro, recalcula a
fonte derivada, registra o ponto de desfazer e avisa `<<Mudou>>`. As teclas chamam a
mesma API; os testes também (§14).

## Como cada coisa mora no widget

Ver `ui/editor/dump.py` (o inverso) e `ui/editor/tags.py` (as tags). O bloco começa
na marca `bloco:<id>` (gravidade `left`, para o que se digita no começo do bloco ficar
dentro dele) e termina no `\\n` antes da marca seguinte. Desenhar um bloco no meio do
texto usa uma marca provisória de gravidade `right` (`fim_ins`): tudo o que se insere
nela fica antes dela, e no fim ela aponta o fim do que entrou — é aí que a marca do
bloco seguinte é reposta, porque com gravidade `left` ela teria ficado presa no
começo do texto novo. O objeto é uma janela embutida registrada no
`RegistroDeObjetos`. A referência de nota é `¹` protegido com `nota:<id>`; a quebra
suave é um `\\n` com `qs`; o marcador de lista é texto com `marcador`+`protegido`.

## O modelo por bloco, e o desfazer

O widget guarda o **último modelo de cada bloco** (`_modelo`). Depois de cada edição,
`_reconciliar` reaplica as tags de parágrafo, refaz a fonte derivada, relê só os
blocos tocados pelo `dump` e registra no `Historico` um ponto `(ids, antes, depois)`
— a digitação contínua coalesce (DEC-04). Desfazer aplica o `antes` ao modelo e
redesenha o capítulo; é por isso que nem `undo=True` nem cópias do documento existem
aqui. Quem diz **quais** blocos uma edição tocou é o proxy do comando Tcl (o mesmo
truque do modo código): cada `insert`/`delete` que passa por ele anota os blocos do
intervalo, e o `mark previous` do Tk acha o bloco de um índice em uma ou duas chamadas.
"""

from __future__ import annotations

import copy
import re
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from core.editor import css_minima, dialeto, modelo
from core.editor.historico import Historico, Ponto
from core.editor.modelo import (Bloco, Capitulo, Citacao, Diagrama, Figura, IlhaBruta, ItemDeLista, Lista,
                                MarcaDePagina, Nota, Paragrafo, QuebraDePagina, Separador, Tabela, Trecho)
from ui.editor import dump as dump_mod
from ui.editor import tags as T
from ui.editor.calha import Calha
from ui.editor.objetos import ObjetoGenerico, RegistroDeObjetos
from ui.editor.tags import EstiloDeTela, Estilos, Fontes

BINDTAG = "EditorAtalhosTexto"
MARCA_DE_INSERCAO = "fim_ins"
PASSO_DA_FONTE_PT = 2.0
SOBRESCRITOS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
SIMBOLO_DA_PAGINA = "⁞"
INVISIVEIS = {"paragrafo": "¶", "tab": "→", "quebra": "⏎", "nbsp": "°"}
TIPOS_DE_OBJETO = (Diagrama, Figura, Tabela, IlhaBruta, MarcaDePagina, QuebraDePagina, Separador)
ATRIBUTOS_ALTERNAVEIS = {"negrito": "b", "italico": "i", "sublinhado": "u", "tachado": "s", "versalete": "vers",
                         "sobrescrito": "sobre", "subscrito": "sub"}
PREFIXOS_DE_APLICAR = {"familia": "fam:", "corpo_pt": "corpo:", "cor": "cor:", "fundo": "fundo:", "classe": "cls:",
                       "lang": "lang:", "titulo": "tit:", "link": "link:", "ref": "ref:", "papel": "papel:",
                       "nag": "nag:", "chave": "chave:"}
PREFIXOS_DE_PARAGRAFO = {"alinhamento": "al:", "recuo_primeira_em": "rec1:", "recuo_esquerda_em": "recE:",
                         "recuo_direita_em": "recD:", "antes_em": "antes:", "depois_em": "depois:",
                         "entrelinha": "entre:"}
SIMPLES_DE_PARAGRAFO = {"manter_com_proximo": "manter", "manter_linhas": "manterl"}
_RE_PALAVRA_ANTES = re.compile(r"(\w+|\W+)$")
_RE_PALAVRA_DEPOIS = re.compile(r"\w+|\W+")


def _sobrescrito(n: int) -> str:
    return "".join(SOBRESCRITOS[int(d)] for d in str(n))


def _valor_de_tag(valor: Any) -> str:
    return f"{valor:g}" if isinstance(valor, float) else str(valor)


class TextoRico(ttk.Frame):
    def __init__(self, master: tk.Misc, estilo_de_tela: EstiloDeTela | None = None, folhas: Any = (),
                 historico: Historico | None = None, relogio: Callable[[], float] = time.monotonic,
                 arquivo: str = "capitulo", **kw: Any):
        super().__init__(master, **kw)
        self.tela = estilo_de_tela or EstiloDeTela()
        self.estilos = Estilos(self.tela, None)
        self.fontes = Fontes(self)
        self.historico = historico or Historico(relogio=relogio)
        self.relogio = relogio
        self.arquivo = arquivo
        self.registro = RegistroDeObjetos()

        self.texto = tk.Text(self, undo=False, wrap="word", highlightthickness=2, padx=12, pady=8, spacing3=4,
                             exportselection=False, insertwidth=2)
        self.calha = Calha(self, self.texto)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=self._rolagem)
        self.calha.grid(row=0, column=0, sticky="ns")
        self.texto.grid(row=0, column=1, sticky="nsew")
        self.barra.grid(row=0, column=2, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self._modelo: dict[str, Bloco] = {}
        self._ordem: list[str] = []
        self._posicoes_antigas: dict[str, int] = {}
        self._notas: list[Nota] = []
        self._capitulo: Capitulo | None = None
        self._ptags: dict[str, tuple[str, ...]] = {}
        self._tocados: set[str] = set()
        self._em_carga = False
        self._em_desfazer = False
        self._reconciliando = False
        self._sujo = False
        self._pendente: dict[str, Any] = {}
        self._pendente_em = ""
        self._pincel: tuple[str, ...] | None = None
        self._invisiveis = False
        self._simples = False
        self._configuradas: set[str] = set()
        self.definir_folhas(folhas)
        T.configurar(self.texto, self.estilos, self.fontes)
        self._instalar_proxy()
        self._instalar_ligacoes()
        self.comandos: dict[str, Callable[..., Any]] = {
            "desfazer": self.desfazer, "refazer": self.refazer,
            "negrito": lambda: self.alternar("negrito"), "italico": lambda: self.alternar("italico"),
            "sublinhado": lambda: self.alternar("sublinhado"), "tachado": lambda: self.alternar("tachado"),
            "versalete": lambda: self.alternar("versalete"), "sobrescrito": lambda: self.alternar("sobrescrito"),
            "subscrito": lambda: self.alternar("subscrito"), "aumentar_fonte": self.aumentar_fonte,
            "diminuir_fonte": self.diminuir_fonte, "limpar_caractere": self.limpar_caractere,
            "limpar_paragrafo": self.limpar_paragrafo, "estilo": self.estilo,
            "estilo_de_caractere": self.estilo_de_caractere, "lista": self.lista, "nivel": self.nivel,
            "mudar_caixa": self.mudar_caixa, "pincel_copiar": self.pincel_copiar,
            "pincel_aplicar": self.pincel_aplicar,
            "alinhar_esquerda": lambda: self.paragrafo(alinhamento="esquerda"),
            "alinhar_centro": lambda: self.paragrafo(alinhamento="centro"),
            "alinhar_direita": lambda: self.paragrafo(alinhamento="direita"),
            "justificar": lambda: self.paragrafo(alinhamento="justificado"),
            "apagar_palavra_anterior": lambda: self.apagar_palavra(-1),
            "apagar_palavra_seguinte": lambda: self.apagar_palavra(1),
            "selecionar_paragrafo": self.selecionar_paragrafo, "selecionar_bloco": self.selecionar_bloco,
            "selecionar_tudo": self.selecionar_tudo, "invisiveis": self.invisiveis, "zoom": self.zoom,
            "enter": self.enter, "backspace": self.backspace, "apagar_selecao": self.apagar_selecao,
        }

    # ------------------------------------------------------------------
    # Folhas, estilos, tags sob demanda
    # ------------------------------------------------------------------

    def definir_folhas(self, folhas: Any) -> None:
        """As folhas do capítulo (`{href: texto}` ou pares), em cascata, na ordem dos `<link>`."""
        pares = list(folhas.items()) if isinstance(folhas, dict) else [tuple(p) for p in folhas]
        lidas, nomes = [], []
        for href, texto in pares:
            try:
                lidas.append(css_minima.ler(texto))
                nomes.append(href)
            except Exception:      # noqa: BLE001 — folha ilegível não impede o capítulo de abrir
                continue
        self.estilos = Estilos(self.tela, css_minima.cascata(lidas, nomes) if lidas else None)
        self._configuradas.clear()

    def _garantir_tag(self, tag: str) -> None:
        if tag in self._configuradas:
            return
        if T.e_de_paragrafo(tag):
            T.configurar_paragrafo(self.texto, tag, self.estilos, self.fontes)
        elif T.e_de_caractere(tag) and ":" in tag:
            T.configurar_caractere(self.texto, tag, self.estilos, self.fontes)
        elif tag.startswith(("lista:", "marc:", "ini:", "sub:", "pid:", "pcls:", "pex:")):
            self.texto.tag_configure(tag)
        self._configuradas.add(tag)

    def _tag_de_fonte(self, estilo: str, tags: Iterable[str]) -> str:
        nome, atributos = T.fonte_derivada(self.estilos, estilo, tags)
        if nome not in self._configuradas:
            T.configurar_fonte(self.texto, nome, atributos, self.fontes, self.estilos)
            self._configuradas.add(nome)
        return nome

    # ------------------------------------------------------------------
    # Proxy do comando Tcl: saber o que a edição tocou
    # ------------------------------------------------------------------

    def _instalar_proxy(self) -> None:
        self._original = self.texto._w + "_orig"
        self.texto.tk.call("rename", self.texto._w, self._original)
        self.texto.tk.createcommand(self.texto._w, self._proxy)

    def _proxy(self, comando: str, *args: Any) -> Any:
        chamar = self.texto.tk.call
        tocados: list[str] = []
        if not self._em_carga and comando in ("insert", "delete") and args:
            ini = str(chamar(self._original, "index", args[0]))
            if comando == "delete":
                fim = str(chamar(self._original, "index", args[1])) if len(args) > 1 else \
                    str(chamar(self._original, "index", f"{ini}+1c"))
            else:
                fim = ini
            tocados = self._blocos_entre(ini, fim)
        resultado = chamar((self._original, comando) + args)
        if tocados:
            self._tocados.update(tocados)
        elif comando == "mark" and len(args) >= 3 and args[0] == "set" and args[1] == "insert":
            self._cursor_moveu()
        elif comando == "yview" and args:
            self._agendar_calha()
        return resultado

    def _agendar_calha(self) -> None:
        try:
            self.after_idle(self.calha.redesenhar)
        except tk.TclError:
            pass

    def _rolagem(self, *args: Any) -> None:
        self.barra.set(*args)
        self._agendar_calha()

    def _cursor_moveu(self) -> None:
        if self._pendente and self.texto.index("insert") != self._pendente_em:
            self._pendente = {}
        try:
            self.texto.event_generate("<<CursorMoveu>>")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Marcas e blocos
    # ------------------------------------------------------------------

    def _marca(self, bloco_id: str) -> str:
        return dump_mod.PREFIXO_DA_MARCA + bloco_id

    def _inicio_de(self, bloco_id: str) -> str:
        return self.texto.index(self._marca(bloco_id))

    def _fim_de(self, bloco_id: str) -> str:
        """O índice **depois** do `\\n` terminal do bloco (= o começo do seguinte, ou `end-1c`)."""
        i = self._ordem.index(bloco_id)
        if i + 1 < len(self._ordem):
            return self._inicio_de(self._ordem[i + 1])
        return self.texto.index("end-1c")

    def _bloco_em(self, indice: str) -> str | None:
        """O id do bloco que contém `indice` — pelo `mark previous` (uma ou duas chamadas)."""
        if not self._ordem:
            return None
        # `mark previous` começa **antes** do índice: o `+1c` inclui as marcas que estão nele.
        marca = self.texto.mark_previous(f"{indice}+1c")
        while marca:
            if marca.startswith(dump_mod.PREFIXO_DA_MARCA):
                bloco_id = marca[len(dump_mod.PREFIXO_DA_MARCA):]
                if bloco_id in self._modelo or bloco_id in self._ordem:
                    return bloco_id
            marca = self.texto.mark_previous(marca)
        return self._ordem[0]

    def _blocos_entre(self, ini: str, fim: str) -> list[str]:
        """Os blocos que o intervalo `[ini, fim]` toca, na ordem."""
        if not self._ordem:
            return []
        primeiro = self._bloco_em(ini)
        if primeiro is None:
            return []
        saida = [primeiro]
        fim = self.texto.index(fim)
        i = self._ordem.index(primeiro) + 1
        while i < len(self._ordem) and self.texto.compare(self._inicio_de(self._ordem[i]), "<", fim):
            saida.append(self._ordem[i])
            i += 1
        return saida

    def bloco_atual(self) -> str | None:
        return self._bloco_em("insert")

    def modelo_de(self, bloco_id: str) -> Bloco | None:
        return self._modelo.get(bloco_id)

    @property
    def ordem(self) -> list[str]:
        return list(self._ordem)

    def _seguinte(self, bloco_id: str) -> str | None:
        i = self._ordem.index(bloco_id)
        return self._ordem[i + 1] if i + 1 < len(self._ordem) else None

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def carregar(self, capitulo: Capitulo) -> None:
        """Desenha o capítulo (o modelo é o dono; `texto_cru` é convertido antes); zera o histórico."""
        cap = capitulo
        if cap.texto_cru is not None:
            from core.editor import xhtml
            cap = xhtml.ler(cap.texto_cru, cap.arquivo)
        self._capitulo = cap
        self.arquivo = cap.arquivo
        self._notas = list(cap.notas)
        self.carregar_blocos(cap.blocos)
        self.historico.limpar(self.arquivo)
        self._sujo = False

    def carregar_blocos(self, blocos: Sequence[Bloco]) -> None:
        self._em_carga = True
        try:
            self._limpar_widget()
            for bloco in blocos:
                self._desenhar_bloco(bloco, "end-1c")
            self.texto.mark_set("insert", "1.0")
        finally:
            self._em_carga = False
        self._tocados.clear()
        self.calha.redesenhar()

    def _limpar_widget(self) -> None:
        for bloco_id in list(self._ordem):
            try:
                self.texto.mark_unset(self._marca(bloco_id))
            except tk.TclError:
                pass
        for nome in self.texto.window_names():
            try:
                self.texto.nametowidget(nome).destroy()
            except (tk.TclError, KeyError):
                pass
        self.texto.delete("1.0", "end")
        self.registro.limpar()
        self._modelo.clear()
        self._ordem.clear()
        self._ptags.clear()
        self._posicoes_antigas.clear()

    def _ptags_de(self, bloco: Bloco) -> tuple[str, ...]:
        """As tags de parágrafo de um bloco do modelo."""
        if isinstance(bloco, Lista):
            tags = ["p:corpo", "lista:o" if bloco.ordenada else "lista:n"]
            if bloco.marcador:
                tags.append(T.nome("marc:", bloco.marcador))
            if bloco.inicio != 1:
                tags.append(T.nome("ini:", bloco.inicio))
            return tuple(tags)
        if isinstance(bloco, Citacao):
            return ("p:citacao", "cit")
        if isinstance(bloco, Paragrafo):
            tags = [T.nome("p:", bloco.estilo)]
            for campo, pref in PREFIXOS_DE_PARAGRAFO.items():
                valor = getattr(bloco, campo)
                if valor not in (None, ""):
                    tags.append(T.nome(pref, _valor_de_tag(valor)))
            for campo, tag in SIMPLES_DE_PARAGRAFO.items():
                if getattr(bloco, campo):
                    tags.append(tag)
            return tuple(tags)
        return ("p:corpo",)

    @staticmethod
    def _tags_do_trecho(t: Trecho) -> tuple[str, ...]:
        tags: list[str] = []
        for atributo, tag in ATRIBUTOS_ALTERNAVEIS.items():
            if atributo == "sobrescrito":
                if t.posicao == "sobre":
                    tags.append(tag)
            elif atributo == "subscrito":
                if t.posicao == "sub":
                    tags.append(tag)
            elif getattr(t, atributo):
                tags.append(tag)
        if t.codigo:
            tags.append("code")
        for campo, pref in PREFIXOS_DE_APLICAR.items():
            valor = getattr(t, campo)
            if valor not in (None, ""):
                tags.append(T.nome(pref, _valor_de_tag(valor)))
        return tuple(tags)

    def _inserir_segmento(self, texto: str, ptags: tuple[str, ...], ctags: tuple[str, ...], estilo: str,
                          extras: tuple[str, ...] = ()) -> None:
        """Insere na marca provisória, com as tags do bloco, as do trecho, as extras e a fonte derivada."""
        todas = tuple(ptags) + tuple(ctags) + tuple(extras)
        for tag in todas:
            self._garantir_tag(tag)
        fonte = self._tag_de_fonte(estilo, ctags)
        self.texto.insert(MARCA_DE_INSERCAO, texto, todas + (fonte,))

    def _inserir_paragrafo(self, p: Paragrafo, ptags: tuple[str, ...], interno: bool = False) -> None:
        estilo = p.estilo
        if interno:
            # Dentro de lista ou citação, o parágrafo leva a sua formatação direta (recuo,
            # espaçamento), o id persistente e a classe; o `p:` é o do bloco.
            ptags = ptags + tuple(t for t in self._ptags_de(p) if not t.startswith("p:"))
            if p.id_persistente:
                ptags += (T.nome("pid:", p.id),)
            if p.classe:
                ptags += (T.nome("pcls:", p.classe),)
            if p.extras or p.origem is not None:
                ptags += (T.nome("pex:", dump_mod.codificar_extras(p)),)
        for t in p.trechos:
            if t.quebra_antes:
                self._inserir_segmento("\n", ptags, (), estilo, ("qs", "quebra", "protegido"))
            if t.pagina is not None:
                self._inserir_segmento(SIMBOLO_DA_PAGINA, ptags, (), estilo,
                                       (T.nome("pagina:", t.pagina), "protegido", "marcador"))
            if t.ilha:
                self._inserir_objeto(t, ptags, inline=True)
                continue
            if t.nota:
                numero = next((i for i, n in enumerate(self._notas, start=1) if n.id == t.nota), 0)
                self._inserir_segmento(_sobrescrito(numero) if numero else "¹", ptags, (), estilo,
                                       (T.nome("nota:", t.nota), "protegido"))
                continue
            if t.texto:
                self._inserir_segmento(t.texto, ptags, self._tags_do_trecho(t), estilo)

    def _inserir_objeto(self, objeto: Any, ptags: tuple[str, ...], inline: bool = False) -> str:
        janela = ObjetoGenerico(self.texto, objeto, inline=inline, ao_ativar=self._ativar_objeto)
        self.texto.window_create(MARCA_DE_INSERCAO, window=janela, align="baseline" if inline else "bottom",
                                 padx=2 if inline else 0, pady=0 if inline else 2)
        nome = str(janela)
        self.registro.registrar(nome, objeto)
        inicio = self.texto.index(nome)
        for tag in ptags + ("objeto", "protegido"):
            self._garantir_tag(tag)
            self.texto.tag_add(tag, inicio, f"{inicio}+1c")
        return nome

    def _ativar_objeto(self, objeto: Any) -> None:
        try:
            self.texto.event_generate("<<AtivarObjeto>>")
        except tk.TclError:
            pass

    def _desenhar_bloco(self, bloco: Bloco, indice: str, antes_de: str | None = None) -> None:
        """
        Desenha `bloco` em `indice`. Com `antes_de`, o bloco seguinte é esse: a marca dele
        é reposta no fim do que entrou (ver o cabeçalho). Não registra ponto.
        """
        texto = self.texto
        inicio = texto.index(indice)
        texto.mark_set(MARCA_DE_INSERCAO, inicio)
        texto.mark_gravity(MARCA_DE_INSERCAO, "right")
        ptags = self._ptags_de(bloco)
        if isinstance(bloco, TIPOS_DE_OBJETO):
            self._inserir_objeto(bloco, ptags)
            self._inserir_segmento("\n", ptags, (), "corpo")
        elif isinstance(bloco, Lista):
            self._desenhar_lista(bloco, ptags)
        elif isinstance(bloco, Citacao):
            for k, p in enumerate(bloco.blocos):
                if k:
                    self._inserir_segmento("\n", ptags, (), "citacao", ("qp", "quebra", "protegido"))
                self._inserir_paragrafo(p, ptags, interno=True)
            self._inserir_segmento("\n", ptags, (), "citacao")
        elif isinstance(bloco, Paragrafo):
            self._inserir_paragrafo(bloco, ptags)
            self._inserir_segmento("\n", ptags, (), bloco.estilo)
        else:
            self._inserir_segmento(modelo.texto_de(bloco) + "\n", ptags, (), "corpo")
        fim = texto.index(MARCA_DE_INSERCAO)
        texto.mark_unset(MARCA_DE_INSERCAO)
        texto.mark_set(self._marca(bloco.id), inicio)
        texto.mark_gravity(self._marca(bloco.id), "left")
        if antes_de is not None and antes_de in self._ordem:
            texto.mark_set(self._marca(antes_de), fim)
            self._ordem.insert(self._ordem.index(antes_de), bloco.id)
        else:
            self._ordem.append(bloco.id)
        self._modelo[bloco.id] = bloco
        self._ptags[bloco.id] = ptags

    def _desenhar_lista(self, lista: Lista, ptags: tuple[str, ...]) -> None:
        contadores: dict[int, int] = {}
        for k, (nivel, item, dona) in enumerate(_achatar(lista, 1)):
            if k:
                self._inserir_segmento("\n", ptags, (), "corpo", (T.nome("qi:", nivel), "quebra", "protegido"))
            for n in [n for n in contadores if n > nivel]:
                del contadores[n]
            contadores[nivel] = contadores.get(nivel, dona.inicio - 1) + 1
            tags_do_item = ptags + (T.nome("li:", nivel),)
            if nivel > 1:
                # A lista aninhada tem tipo, marcador e início próprios: vão na tag do item.
                tags_do_item += (T.nome("sub:", f"{'o' if dona.ordenada else 'n'}|{dona.marcador}|{dona.inicio}"),)
            marcador = f"{contadores[nivel]}. " if dona.ordenada else ("• " if nivel % 2 else "◦ ")
            self._inserir_segmento(marcador, tags_do_item, (), "corpo", ("marcador", "protegido"))
            for j, p in enumerate(item.paragrafos):
                if j:
                    self._inserir_segmento("\n", tags_do_item, (), "corpo", ("qp", "quebra", "protegido"))
                self._inserir_paragrafo(p, tags_do_item, interno=True)
        self._inserir_segmento("\n", ptags, (), "corpo")

    # ------------------------------------------------------------------
    # Sincronizar (dump) e reconciliar
    # ------------------------------------------------------------------

    def _dump(self, ini: str = "1.0", fim: str = "end-1c") -> list[tuple]:
        """
        O `dump` do intervalo **com as tags já ativas em `ini`** na frente: o Tk só relata
        `tagon` onde a tag começa, e uma tag que vem do bloco anterior (dois títulos
        seguidos, o mesmo `p:titulo4`) não começa dentro do intervalo.
        """
        ini = self.texto.index(ini)
        ativas = [("tagon", tag, ini) for tag in self.texto.tag_names(ini)]
        return ativas + self.texto.dump(ini, fim, all=True)

    def sincronizar(self, reler: bool = False) -> Capitulo | list[Bloco]:
        """
        O capítulo (ou só os blocos, se `carregar_blocos` foi usado) que o widget contém
        agora. Só os blocos tocados desde a última reconciliação são relidos: os outros já
        estão em `_modelo`, que toda edição pela API (ou pelo proxy) mantém. Com `reler`,
        todos passam pelo `dump` — é o que o teste de ida e volta e a medição usam.
        """
        self._reconciliar()
        if reler:
            self._reconciliar(set(self._ordem), reaplicar=False, registrar=False)
        blocos = [self._modelo[i] for i in self._ordem if i in self._modelo]
        if self._capitulo is None:
            return blocos
        c = self._capitulo
        return Capitulo(arquivo=c.arquivo, titulo=c.titulo, blocos=blocos, notas=list(self._notas),
                        folhas=list(c.folhas), idioma=c.idioma, semantica=c.semantica, cabeca_extra=c.cabeca_extra,
                        avisos=list(c.avisos), namespaces=dict(c.namespaces), linear=c.linear)

    def _blocos_do_dump(self, ids: Iterable[str]) -> dict[str, Bloco]:
        """Relê pelo `dump` só os blocos `ids`, com os anteriores por base (um `dump` só quando são muitos)."""
        saida: dict[str, Bloco] = {}
        registro = self.registro.como_dicionario()
        ids = list(ids)
        if len(ids) > 8 and len(ids) * 2 > len(self._ordem):
            pedidos = set(ids)
            blocos, _notas = dump_mod.dump_para_blocos(self._dump("1.0", "end-1c"), registro, self._modelo)
            return {b.id: b for b in blocos if b.id in pedidos}
        for bloco_id in ids:
            if bloco_id not in self._ordem:
                continue
            ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
            marca = self._marca(bloco_id)
            itens = [("mark", marca, ini)] + [it for it in self._dump(ini, fim) if it[0] != "mark"]
            blocos, _notas = dump_mod.dump_para_blocos(itens, registro, self._modelo)
            if blocos:
                saida[bloco_id] = blocos[0]
        return saida

    def _reconciliar(self, ids: Iterable[str] | None = None, coalescer: bool | None = None,
                     rotulo: str = "", reaplicar: bool = True, registrar: bool = True) -> None:
        """Reaplica tags e fontes nos blocos tocados, relê o modelo deles e registra o ponto de desfazer."""
        if self._reconciliando:
            return
        tocados = set(self._tocados)
        ids = (set(ids) if ids is not None else set()) | tocados
        self._tocados.clear()
        if not ids:
            return
        self._reconciliando = True
        try:
            for bloco_id in [i for i in ids if i in self._ordem and self._vazio(i)]:
                self._remover_bloco(bloco_id)
            vivos = [i for i in self._ordem if i in ids]
            for bloco_id in vivos:
                if reaplicar or bloco_id in tocados:
                    self._reaplicar_tags(bloco_id)
            novos = self._blocos_do_dump(vivos)
        finally:
            self._reconciliando = False
        sumidos = [i for i in ids if i not in vivos]
        antes = [self._modelo[i] for i in sorted(ids, key=self._posicao_para_ordenar) if i in self._modelo]
        depois = [novos[i] for i in vivos if i in novos]
        indices = {i: self._posicoes_antigas.get(i, self._ordem.index(i) if i in self._ordem else 0) for i in ids}
        for bloco_id, bloco in novos.items():
            self._modelo[bloco_id] = bloco
        for bloco_id in sumidos:
            self._modelo.pop(bloco_id, None)
            self._ptags.pop(bloco_id, None)
        if registrar and not self._em_carga and not self._em_desfazer and not modelo.igual(antes, depois):
            coalescer = self._simples if coalescer is None else coalescer
            self.historico.ponto(self.arquivo, sorted(ids, key=self._posicao_para_ordenar), antes, depois,
                                 coalescer=coalescer, rotulo=rotulo, indices=indices)
            self._sujo = True
            try:
                self.texto.event_generate("<<Mudou>>")
            except tk.TclError:
                pass
        self._simples = False
        self.calha.redesenhar()

    def _posicao_para_ordenar(self, bloco_id: str) -> int:
        if bloco_id in self._ordem:
            return self._ordem.index(bloco_id)
        return self._posicoes_antigas.get(bloco_id, len(self._ordem))

    def _vazio(self, bloco_id: str) -> bool:
        return self.texto.compare(self._inicio_de(bloco_id), ">=", self._fim_de(bloco_id))

    def _remover_bloco(self, bloco_id: str) -> None:
        """Tira o bloco da ordem e do registro (o texto dele é apagado por quem chama)."""
        if bloco_id in self._ordem:
            self._posicoes_antigas[bloco_id] = self._ordem.index(bloco_id)
            self._ordem.remove(bloco_id)
        try:
            self.texto.mark_unset(self._marca(bloco_id))
        except tk.TclError:
            pass
        nome = self.registro.nome_de(bloco_id)
        if nome:
            self.registro.esquecer(nome)
            try:
                self.texto.nametowidget(nome).destroy()
            except (tk.TclError, KeyError):
                pass

    def _reaplicar_tags(self, bloco_id: str) -> None:
        """
        As tags de parágrafo cobrem o bloco inteiro; a fonte derivada segue os marcadores.
        Um `dump` só por bloco: dele saem as tags presentes (as únicas que vale a pena
        tirar — `tag_names()` do widget inteiro tem centenas) e as corridas de texto.
        """
        ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
        ptags = self._ptags.get(bloco_id, ("p:corpo",))
        texto = self.texto
        composto = isinstance(self._modelo.get(bloco_id), (Lista, Citacao))
        itens = self._dump(ini, fim)
        presentes = {valor for chave, valor, _i in itens if chave in ("tagon", "tagoff")}
        for tag in presentes:
            if tag.startswith("fonte:"):
                texto.tag_remove(tag, ini, fim)
            elif tag in ptags or tag.startswith(("li:", "sub:", "pid:", "pcls:", "pex:")):
                continue
            elif tag.startswith(("p:", "lista:", "marc:", "ini:")) or tag == "cit":
                texto.tag_remove(tag, ini, fim)
            elif T.e_de_paragrafo(tag) and not composto:
                texto.tag_remove(tag, ini, fim)
        for tag in ptags:
            self._garantir_tag(tag)
            texto.tag_add(tag, ini, fim)
        estilo = next((T.valor(t) for t in ptags if t.startswith("p:")), "corpo")
        for inicio, tags, final in self._runs(ini, fim, itens):
            ctags = tuple(t for t in tags if T.e_de_caractere(t))
            texto.tag_add(self._tag_de_fonte(estilo, ctags), inicio, final)

    def _runs(self, ini: str, fim: str, itens: list[tuple] | None = None) -> list[tuple[str, frozenset, str]]:
        """`(inicio, tags, fim)` das corridas de texto com o mesmo conjunto de tags em `[ini, fim)`."""
        ativas: set[str] = set()
        runs: list[tuple[str, frozenset, str]] = []
        for chave, valor, indice in (itens if itens is not None else self._dump(ini, fim)):
            if chave == "tagon":
                ativas.add(valor)
            elif chave == "tagoff":
                ativas.discard(valor)
            elif chave == "text":
                final = self.texto.index(f"{indice}+{len(valor)}c")
                chaves = frozenset(t for t in ativas if T.e_de_caractere(t))
                if runs and runs[-1][1] == chaves and runs[-1][2] == indice:
                    runs[-1] = (runs[-1][0], chaves, final)
                else:
                    runs.append((indice, chaves, final))
        return runs

    # ------------------------------------------------------------------
    # Guarda de edição
    # ------------------------------------------------------------------

    def _pode_editar(self, ini: str, fim: str | None = None) -> bool:
        """`False` se o intervalo (ou o ponto de inserção) toca uma faixa protegida."""
        texto = self.texto
        ini = texto.index(ini)
        bloco = self._modelo.get(self._bloco_em(ini) or "")
        if isinstance(bloco, TIPOS_DE_OBJETO):
            return False           # o bloco de um objeto é a janela e o `\n`: texto não entra nele
        if fim is None:
            depois, antes = texto.tag_names(ini), texto.tag_names(f"{ini}-1c") if texto.compare(ini, ">", "1.0") else ()
            dentro = ("protegido" in depois and "protegido" in antes and not any(T.e_quebra(t) for t in depois)
                      and not any(T.e_quebra(t) for t in antes) and "objeto" not in depois)
            return not dentro
        fim = texto.index(fim)
        i = ini
        while texto.compare(i, "<", fim):
            tags = texto.tag_names(i)
            if "protegido" in tags and not any(T.e_quebra(t) for t in tags) and "invisivel" not in tags:
                return False
            i = texto.index(f"{i}+1c")
        return True

    # ------------------------------------------------------------------
    # Estado, seleção, posição
    # ------------------------------------------------------------------

    @property
    def sujo(self) -> bool:
        return self._sujo

    def marcar_limpo(self) -> None:
        self._sujo = False

    def foco(self) -> None:
        self.texto.focus_set()

    def selecao(self) -> tuple[str, str] | None:
        try:
            return self.texto.index("sel.first"), self.texto.index("sel.last")
        except tk.TclError:
            return None

    def posicao(self) -> tuple[str | None, int]:
        """`(id do bloco, deslocamento no texto do modelo)` do cursor."""
        bloco_id = self.bloco_atual()
        if bloco_id is None:
            return None, 0
        return bloco_id, self._deslocamento("insert", bloco_id)

    def _deslocamento(self, indice: str, bloco_id: str) -> int:
        """Quantos caracteres do **modelo** há do começo do bloco até `indice`."""
        n = 0
        indice = self.texto.index(indice)
        for chave, valor, i in self._dump(self._inicio_de(bloco_id), indice):
            pass
        i = self._inicio_de(bloco_id)
        texto = self.texto
        while texto.compare(i, "<", indice):
            tags = texto.tag_names(i)
            if not ("invisivel" in tags or "marcador" in tags
                    or ("protegido" in tags and not any(T.e_quebra(t) for t in tags))):
                n += 1
            i = texto.index(f"{i}+1c")
        return n

    def indice_de(self, bloco_id: str, deslocamento: int) -> str | None:
        ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
        itens = [("mark", self._marca(bloco_id), ini)] + [it for it in self._dump(ini, fim) if it[0] != "mark"]
        return dump_mod.indice_de(itens, bloco_id, deslocamento)

    def selecionar(self, ini: int, fim: int, bloco_id: str | None = None) -> None:
        """Seleciona `[ini, fim)` do **texto do modelo** do bloco (o atual por omissão)."""
        bloco_id = bloco_id or self.bloco_atual()
        if bloco_id is None:
            return
        a, b = self.indice_de(bloco_id, ini), self.indice_de(bloco_id, fim)
        if a is not None and b is not None:
            self.selecionar_indices(a, b)

    def selecionar_indices(self, ini: str, fim: str) -> None:
        self.texto.tag_remove("sel", "1.0", "end")
        self.texto.tag_add("sel", ini, fim)
        self.texto.mark_set("insert", fim)

    def selecionar_paragrafo(self) -> None:
        bloco_id = self.bloco_atual()
        if bloco_id:
            self.selecionar_indices(self._inicio_de(bloco_id), f"{self._fim_de(bloco_id)}-1c")

    def selecionar_bloco(self) -> None:
        bloco_id = self.bloco_atual()
        if bloco_id:
            self.selecionar_indices(self._inicio_de(bloco_id), self._fim_de(bloco_id))

    def selecionar_tudo(self) -> None:
        self.selecionar_indices("1.0", "end-1c")

    def ir_para(self, bloco_id: str, deslocamento: int = 0) -> None:
        """Põe o cursor no `deslocamento`-ésimo caractere do modelo do bloco; desfaz a seleção."""
        indice = self.indice_de(bloco_id, deslocamento)
        if indice is not None:
            self.texto.tag_remove("sel", "1.0", "end")
            self.texto.mark_set("insert", indice)
            self.texto.see("insert")

    # ------------------------------------------------------------------
    # Edição de texto
    # ------------------------------------------------------------------

    def _tags_para_inserir(self, indice: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        """`(ptags, ctags, estilo)` do que se digita em `indice`: as do bloco e as do caractere anterior."""
        bloco_id = self._bloco_em(indice)
        ptags = self._ptags.get(bloco_id, ("p:corpo",)) if bloco_id else ("p:corpo",)
        estilo = next((T.valor(t) for t in ptags if t.startswith("p:")), "corpo")
        anterior: tuple[str, ...] = ()
        if bloco_id and self.texto.compare(indice, ">", self._inicio_de(bloco_id)):
            anterior = tuple(self.texto.tag_names(f"{indice}-1c"))
        seguinte = tuple(self.texto.tag_names(indice))
        ctags = []
        for tag in anterior:
            if not T.e_de_caractere(tag) or tag.startswith(("nota:", "pagina:")):
                continue
            if tag.startswith(("link:", "ref:")) and tag not in seguinte:
                continue           # o link não se estende ao que se digita depois dele
            ctags.append(tag)
        li = next((t for t in anterior if t.startswith("li:")), None) or \
            next((t for t in seguinte if t.startswith("li:")), None)
        if li and li not in ptags:
            ptags = ptags + (li,)
        return ptags, tuple(ctags), estilo

    def _aplicar_pendente(self, ctags: tuple[str, ...]) -> tuple[str, ...]:
        tags = list(ctags)
        for chave, valor in self._pendente.items():
            if chave in ATRIBUTOS_ALTERNAVEIS:
                tag = ATRIBUTOS_ALTERNAVEIS[chave]
                if tag in ("sobre", "sub"):
                    tags = [t for t in tags if t not in ("sobre", "sub")]
                if valor and tag not in tags:
                    tags.append(tag)
                elif not valor and tag in tags:
                    tags.remove(tag)
            elif chave == "codigo":
                tags = [t for t in tags if t != "code"] + (["code"] if valor else [])
            elif chave in PREFIXOS_DE_APLICAR:
                pref = PREFIXOS_DE_APLICAR[chave]
                tags = [t for t in tags if not t.startswith(pref)]
                if valor not in (None, ""):
                    tags.append(T.nome(pref, _valor_de_tag(valor)))
        return tuple(tags)

    def inserir(self, texto: str, indice: str | None = None) -> bool:
        """Insere no cursor (ou em `indice`), com o formato do que vem antes e o pendente; `\\n` é `enter()`."""
        if not self._ordem:
            self._desenhar_bloco(Paragrafo(trechos=[]), "end-1c")
            self._tocados.clear()
        indice = self.texto.index(indice or "insert")
        if not self._pode_editar(indice):
            return False
        while "marcador" in self.texto.tag_names(indice):
            indice = self.texto.index(f"{indice}+1c")
        ptags, ctags, estilo = self._tags_para_inserir(indice)
        if self._pendente and indice == self._pendente_em:
            ctags = self._aplicar_pendente(ctags)
        self._pendente = {}
        self._pendente_em = ""
        self.texto.mark_set("insert", indice)
        for k, parte in enumerate(texto.split("\n")):
            if k:
                self.enter()
                ptags, _c, estilo = self._tags_para_inserir("insert")
            if parte:
                self._simples = len(parte) == 1
                self.texto.mark_set(MARCA_DE_INSERCAO, "insert")
                self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
                self._inserir_segmento(parte, ptags, ctags, estilo)
                self.texto.mark_set("insert", MARCA_DE_INSERCAO)
                self.texto.mark_unset(MARCA_DE_INSERCAO)
                self._reconciliar()
        return True

    def inserir_objeto(self, objeto: Bloco | Trecho) -> str:
        """
        Um objeto novo: um bloco (diagrama, figura, tabela, ilha, marca…) entra como bloco
        **depois** do bloco do cursor; um `Trecho(ilha=…)` entra inline no cursor. Desenhado
        por `ObjetoGenerico` até a fase que lhe dá desenho próprio. Devolve o id do bloco.
        """
        if isinstance(objeto, Trecho):
            if not objeto.ilha:
                raise ValueError("só um trecho-ilha entra como objeto inline")
            if not self._ordem:
                self.inserir("")
            indice = self.texto.index("insert")
            if not self._pode_editar(indice):
                raise ValueError("o cursor está numa faixa protegida")
            bloco_id = self._bloco_em(indice)
            ptags, _c, _e = self._tags_para_inserir(indice)
            self.texto.mark_set(MARCA_DE_INSERCAO, indice)
            self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
            self._inserir_objeto(objeto, ptags, inline=True)
            self.texto.mark_set("insert", MARCA_DE_INSERCAO)
            self.texto.mark_unset(MARCA_DE_INSERCAO)
            self._simples = False
            self._reconciliar({bloco_id} if bloco_id else None)
            return bloco_id or ""
        if not isinstance(objeto, TIPOS_DE_OBJETO):
            raise ValueError(f"não é um objeto: {type(objeto).__name__}")
        atual = self.bloco_atual()
        if atual is None:
            self._desenhar_bloco(objeto, "end-1c")
        else:
            self._desenhar_bloco(objeto, self._fim_de(atual), self._seguinte(atual))
        self._tocados.discard(objeto.id)
        self._modelo.pop(objeto.id, None)          # "antes" vazio: o ponto de desfazer é a inserção
        self._simples = False
        self._reconciliar({objeto.id})
        self.texto.mark_set("insert", self._inicio_de(objeto.id))
        return objeto.id

    def apagar(self, ini: str, fim: str) -> bool:
        """Apaga `[ini, fim)`; recusa o que toca uma faixa protegida. Entre blocos, junta as pontas."""
        ini, fim = self.texto.index(ini), self.texto.index(fim)
        if self.texto.compare(ini, ">=", fim) or not self._pode_editar(ini, fim):
            return False
        blocos = self._blocos_entre(ini, fim)
        if len(blocos) > 1 or (blocos and self.texto.compare(fim, ">=", self._fim_de(blocos[0]))):
            return self._apagar_entre_blocos(ini, fim, blocos)
        self._simples = self.texto.compare(fim, "==", f"{ini}+1c")
        self.texto.delete(ini, fim)
        self.texto.mark_set("insert", ini)
        self._reconciliar()
        return True

    def _apagar_entre_blocos(self, ini: str, fim: str, blocos: list[str]) -> bool:
        """
        Uma seleção que cruza blocos: os do meio somem; a cauda junta-se à cabeça (a
        marca da cauda some); o `\\n` terminal do último fica, como terminal da cabeça.
        """
        texto = self.texto
        primeiro, ultimo = blocos[0], blocos[-1]
        inicio_primeiro, fim_ultimo = self._inicio_de(primeiro), self._fim_de(ultimo)
        inteiro = texto.compare(ini, "<=", inicio_primeiro) and texto.compare(fim, ">=", fim_ultimo)
        if not inteiro and texto.compare(fim, ">=", fim_ultimo):
            fim = texto.index(f"{fim_ultimo}-1c")
        tocados = set(blocos)
        for bloco_id in blocos[1:]:
            self._remover_bloco(bloco_id)
        if inteiro:
            self._remover_bloco(primeiro)
        self._simples = False
        texto.delete(ini, fim)
        texto.mark_set("insert", ini)
        self._garantir_um_bloco(tocados)
        self._reconciliar(tocados)
        return True

    def _garantir_um_bloco(self, tocados: set[str]) -> None:
        """Um capítulo nunca fica sem bloco: apagado tudo, sobra um parágrafo vazio (e nada de texto órfão)."""
        if self._ordem:
            return
        self._em_carga = True
        try:
            self.texto.delete("1.0", "end")
            novo = Paragrafo(trechos=[])
            self._desenhar_bloco(novo, "end-1c")
        finally:
            self._em_carga = False
        self.texto.mark_set("insert", "1.0")
        tocados.add(novo.id)

    def apagar_selecao(self) -> bool:
        """Apaga a seleção: um objeto selecionado inteiro sai com desfazer; texto, pela guarda."""
        selecao = self.selecao()
        if not selecao:
            return False
        ini, fim = selecao
        self.texto.tag_remove("sel", "1.0", "end")
        blocos = self._blocos_entre(ini, fim)
        if self.texto.compare(self._inicio_de(blocos[-1]), ">=", fim) and len(blocos) > 1:
            blocos = blocos[:-1]          # a seleção termina exatamente onde o último começa
        inteiros = [b for b in blocos if self.texto.compare(self._inicio_de(b), ">=", ini)
                    and self.texto.compare(self._fim_de(b), "<=", fim)]
        if inteiros and len(inteiros) == len(blocos):
            texto = self.texto
            for bloco_id in blocos:
                self._remover_bloco(bloco_id)
            self._simples = False
            texto.delete(ini, fim)
            texto.mark_set("insert", ini)
            tocados = set(blocos)
            self._garantir_um_bloco(tocados)
            self._reconciliar(tocados)
            return True
        if not self._pode_editar_selecao(ini, fim, inteiros):
            return False
        for bloco_id in inteiros:
            pass
        if len(blocos) > 1:
            return self._apagar_entre_blocos(ini, fim, blocos)
        return self.apagar(ini, fim)

    def _pode_editar_selecao(self, ini: str, fim: str, inteiros: list[str]) -> bool:
        """Numa seleção, o protegido só é aceitável dentro de blocos inteiramente selecionados."""
        texto = self.texto
        i, fim = texto.index(ini), texto.index(fim)
        while texto.compare(i, "<", fim):
            tags = texto.tag_names(i)
            if "protegido" in tags and not any(T.e_quebra(t) for t in tags) and "invisivel" not in tags:
                if self._bloco_em(i) not in inteiros:
                    return False
            i = texto.index(f"{i}+1c")
        return True

    def enter(self) -> bool:
        """Novo bloco no cursor (fora de lista e citação); item ou parágrafo interno dentro."""
        if self.selecao():
            self.apagar_selecao()
        if not self._ordem:
            return self.inserir("")
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        bloco = self._modelo.get(bloco_id)
        if isinstance(bloco, TIPOS_DE_OBJETO):
            novo = Paragrafo(trechos=[])
            self._desenhar_bloco(novo, self._fim_de(bloco_id), self._seguinte(bloco_id))
            self.texto.mark_set("insert", self._inicio_de(novo.id))
            self._reconciliar({novo.id})
            return True
        if not self._pode_editar(indice):
            return False
        if isinstance(bloco, Lista):
            return self._enter_na_lista(bloco_id, indice)
        ptags = self._ptags[bloco_id]
        if isinstance(bloco, Citacao):
            self.texto.mark_set(MARCA_DE_INSERCAO, indice)
            self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
            self._inserir_segmento("\n", ptags, (), "citacao", ("qp", "quebra", "protegido"))
            self.texto.mark_set("insert", MARCA_DE_INSERCAO)
            self.texto.mark_unset(MARCA_DE_INSERCAO)
            self._simples = False
            self._reconciliar({bloco_id})
            return True
        estilo = next((T.valor(t) for t in ptags if t.startswith("p:")), "corpo")
        novo_estilo = "corpo" if estilo.startswith("titulo") else estilo
        novas_ptags = (T.nome("p:", novo_estilo),) if novo_estilo != estilo else ptags
        novo_id = modelo.id_novo()
        self._simples = False
        self.texto.insert(indice, "\n", ptags)
        depois = self.texto.index(f"{indice}+1c")
        self.texto.mark_set(self._marca(novo_id), depois)
        self.texto.mark_gravity(self._marca(novo_id), "left")
        self._ordem.insert(self._ordem.index(bloco_id) + 1, novo_id)
        self._ptags[novo_id] = novas_ptags
        self.texto.mark_set("insert", depois)
        self._reconciliar({bloco_id, novo_id})
        return True

    def _enter_na_lista(self, bloco_id: str, indice: str) -> bool:
        lista = self._modelo[bloco_id]
        assert isinstance(lista, Lista)
        item_i, par_i, desloc = self._posicao_na_lista(bloco_id, indice)
        itens = list(_achatar(lista, 1))
        nivel, item, dona = itens[item_i]
        paragrafo = item.paragrafos[par_i]
        if not modelo.texto_de(paragrafo).strip() and len(item.paragrafos) == 1:
            return self._sair_da_lista(bloco_id, item_i)
        antes, depois = modelo.dividir_paragrafo(paragrafo, desloc)
        novos = list(itens)
        novos[item_i] = (nivel, ItemDeLista(paragrafos=item.paragrafos[:par_i] + [antes]), dona)
        novos.insert(item_i + 1, (nivel, ItemDeLista(paragrafos=[depois] + item.paragrafos[par_i + 1:]), dona))
        nova = _montar_lista(lista, novos)
        self._reescrever_bloco(bloco_id, nova)
        self.ir_para(bloco_id, self._deslocamento_do_item(nova, item_i + 1))
        return True

    def _sair_da_lista(self, bloco_id: str, item_i: int) -> bool:
        """O item vira parágrafo(s) depois da lista (que se parte, se ele estava no meio); vazio vira vazio."""
        lista = self._modelo[bloco_id]
        assert isinstance(lista, Lista)
        itens = list(_achatar(lista, 1))
        antes_itens, depois_itens = itens[:item_i], itens[item_i + 1:]
        item = itens[item_i][1]
        novos = [Paragrafo(trechos=list(p.trechos)) for p in item.paragrafos if p.trechos] or [Paragrafo(trechos=[])]
        seguinte = self._seguinte(bloco_id)
        tocados = {bloco_id} | {n.id for n in novos}

        def desenhar_novos(depois_de: str | None) -> None:
            anterior = depois_de
            for novo in novos:
                if anterior is None:
                    self._desenhar_bloco(novo, self._inicio_de(bloco_id), bloco_id)
                else:
                    self._desenhar_bloco(novo, self._fim_de(anterior), seguinte)
                anterior = novo.id

        if antes_itens:
            self._reescrever_bloco(bloco_id, _montar_lista(lista, antes_itens), reconciliar=False)
            desenhar_novos(bloco_id)
            if depois_itens:
                segunda = _montar_lista(lista, depois_itens)
                segunda.id = modelo.id_novo()
                self._desenhar_bloco(segunda, self._fim_de(novos[-1].id), seguinte)
                tocados.add(segunda.id)
        elif depois_itens:
            desenhar_novos(None)
            self._reescrever_bloco(bloco_id, _montar_lista(lista, depois_itens), reconciliar=False)
        else:
            desenhar_novos(None)
            self._apagar_bloco_sem_ponto(bloco_id)
        self.texto.mark_set("insert", self._inicio_de(novos[0].id))
        self._simples = False
        self._reconciliar(tocados)
        return True

    def _apagar_bloco_sem_ponto(self, bloco_id: str) -> None:
        ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
        self._remover_bloco(bloco_id)
        self.texto.delete(ini, fim)

    def backspace(self) -> bool:
        """Apaga para trás pela guarda; no começo do bloco, junta ao anterior; no item, desce de nível."""
        if self.selecao():
            return self.apagar_selecao()
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None:
            return False
        bloco = self._modelo.get(bloco_id)
        inicio = self._inicio_de(bloco_id)
        if isinstance(bloco, Lista):
            item_i, par_i, desloc = self._posicao_na_lista(bloco_id, indice)
            if desloc == 0 and par_i == 0:
                nivel = list(_achatar(bloco, 1))[item_i][0]
                return self.nivel(-1) if nivel > 1 else self._sair_da_lista(bloco_id, item_i)
        if self.texto.compare(indice, "==", inicio):
            return self._juntar_ao_anterior(bloco_id)
        anterior = self.texto.tag_names(f"{indice}-1c")
        if "protegido" in anterior:
            if "qs" in anterior:
                self._simples = False
                self.texto.delete(f"{indice}-1c", indice)
                self._reconciliar()
                return True
            return False
        return self.apagar(f"{indice}-1c", indice)

    def _juntar_ao_anterior(self, bloco_id: str) -> bool:
        i = self._ordem.index(bloco_id)
        if i == 0:
            return False
        anterior = self._ordem[i - 1]
        bloco_anterior, bloco = self._modelo.get(anterior), self._modelo.get(bloco_id)
        if isinstance(bloco_anterior, TIPOS_DE_OBJETO):
            self.selecionar_indices(self._inicio_de(anterior), self._fim_de(anterior))
            return False
        if not isinstance(bloco, Paragrafo) or not isinstance(bloco_anterior, Paragrafo) \
                or isinstance(bloco, TIPOS_DE_OBJETO):
            return False
        terminal = self.texto.index(f"{self._fim_de(anterior)}-1c")
        self._remover_bloco(bloco_id)
        self._simples = False
        self.texto.delete(terminal, f"{terminal}+1c")
        self.texto.mark_set("insert", terminal)
        self._reconciliar({anterior, bloco_id})
        return True

    def apagar_palavra(self, direcao: int) -> bool:
        if self.selecao():
            return self.apagar_selecao()
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None:
            return False
        if direcao < 0:
            m = _RE_PALAVRA_ANTES.search(self.texto.get(self._inicio_de(bloco_id), indice))
            if not m:
                return self.backspace()
            return self.apagar(f"{indice}-{len(m.group(0))}c", indice)
        m = _RE_PALAVRA_DEPOIS.match(self.texto.get(indice, f"{self._fim_de(bloco_id)}-1c"))
        if not m:
            return False
        return self.apagar(indice, f"{indice}+{len(m.group(0))}c")

    # ------------------------------------------------------------------
    # Formatação de caractere
    # ------------------------------------------------------------------

    def _todos_tem(self, tag: str, ini: str, fim: str) -> bool:
        texto = self.texto
        i, algum = texto.index(ini), False
        while texto.compare(i, "<", fim):
            tags = texto.tag_names(i)
            if "protegido" not in tags and texto.get(i) != "\n":
                algum = True
                if tag not in tags:
                    return False
            i = texto.index(f"{i}+1c")
        return algum

    def _trocar_tag(self, ini: str, fim: str, tirar: Sequence[str] = (), por: str | None = None,
                    prefixo: str | None = None) -> None:
        texto = self.texto
        if prefixo:
            for tag in texto.tag_names():
                if tag.startswith(prefixo):
                    texto.tag_remove(tag, ini, fim)
        for tag in tirar:
            texto.tag_remove(tag, ini, fim)
        if por:
            self._garantir_tag(por)
            i = texto.index(ini)
            while texto.compare(i, "<", fim):
                tags = texto.tag_names(i)
                if "protegido" not in tags and texto.get(i) != "\n":
                    texto.tag_add(por, i, f"{i}+1c")
                i = texto.index(f"{i}+1c")

    def _tags_no_cursor(self) -> tuple[str, ...]:
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        if bloco_id and self.texto.compare(indice, ">", self._inicio_de(bloco_id)):
            return tuple(t for t in self.texto.tag_names(f"{indice}-1c") if T.e_de_caractere(t))
        return tuple(t for t in self.texto.tag_names(indice) if T.e_de_caractere(t))

    def alternar(self, atributo: str) -> bool:
        """
        Negrito, itálico, sublinhado, tachado, versalete, sobrescrito, subscrito: com
        seleção, tira se **todo** o intervalo tem o marcador, senão põe — sobre o marcador
        próprio, sem XOR com o estilo do parágrafo; sem seleção, fica pendente para o que
        se digitar a seguir. Devolve o estado novo.
        """
        if atributo not in ATRIBUTOS_ALTERNAVEIS:
            raise ValueError(f"atributo desconhecido: {atributo!r}")
        tag = ATRIBUTOS_ALTERNAVEIS[atributo]
        selecao = self.selecao()
        if not selecao:
            atual = self._pendente.get(atributo, tag in self._tags_no_cursor())
            self._pendente[atributo] = not atual
            self._pendente_em = self.texto.index("insert")
            return not atual
        ini, fim = selecao
        ligado = not self._todos_tem(tag, ini, fim)
        if ligado:
            self._trocar_tag(ini, fim, tirar=("sobre", "sub") if tag in ("sobre", "sub") else (), por=tag)
        else:
            self._trocar_tag(ini, fim, tirar=(tag,))
        self._reconciliar(self._blocos_entre(ini, fim), coalescer=False, rotulo=atributo)
        self.texto.tag_add("sel", ini, fim)
        return ligado

    def aplicar(self, **atributos: Any) -> None:
        """
        `negrito`…`subscrito` (booleanos), `codigo`, `familia`, `corpo_pt`, `cor`, `fundo`,
        `classe`, `lang`, `titulo`, `link`, `ref`, `papel`, `nag`, `chave` na seleção;
        sem seleção, pendente. `None`/`""` tira.
        """
        for chave in atributos:
            if chave not in ATRIBUTOS_ALTERNAVEIS and chave != "codigo" and chave not in PREFIXOS_DE_APLICAR:
                raise ValueError(f"atributo desconhecido: {chave!r}")
        selecao = self.selecao()
        if not selecao:
            self._pendente.update(atributos)
            self._pendente_em = self.texto.index("insert")
            return
        ini, fim = selecao
        for chave, valor in atributos.items():
            if chave in ATRIBUTOS_ALTERNAVEIS:
                tag = ATRIBUTOS_ALTERNAVEIS[chave]
                if valor:
                    self._trocar_tag(ini, fim, tirar=("sobre", "sub") if tag in ("sobre", "sub") else (), por=tag)
                else:
                    self._trocar_tag(ini, fim, tirar=(tag,))
            elif chave == "codigo":
                self._trocar_tag(ini, fim, tirar=() if valor else ("code",), por="code" if valor else None)
            else:
                pref = PREFIXOS_DE_APLICAR[chave]
                por = None if valor in (None, "") else T.nome(pref, _valor_de_tag(valor))
                self._trocar_tag(ini, fim, prefixo=pref, por=por)
        self._reconciliar(self._blocos_entre(ini, fim), coalescer=False, rotulo="formato")
        self.texto.tag_add("sel", ini, fim)

    def limpar_caractere(self) -> None:
        """Zera a formatação de caractere da seleção — menos `link`, `nota` e `ref` (§8.2)."""
        selecao = self.selecao()
        if not selecao:
            self._pendente = {}
            return
        ini, fim = selecao
        for tag in self.texto.tag_names():
            if T.e_de_caractere(tag) and not tag.startswith(("link:", "nota:", "ref:")):
                self.texto.tag_remove(tag, ini, fim)
        self._reconciliar(self._blocos_entre(ini, fim), coalescer=False, rotulo="limpar")
        self.texto.tag_add("sel", ini, fim)

    def estilo_de_caractere(self, nome: str) -> None:
        """Os estilos de caractere da §6.3 (`Lance`, `NAG`, `Figurina`, `Simbolo`, `Versalete`, `Jogador`…)."""
        if nome not in dialeto.ESTILOS_DE_CARACTERE:
            raise ValueError(f"estilo de caractere desconhecido: {nome!r}")
        classe, _docx = dialeto.ESTILOS_DE_CARACTERE[nome]
        if classe == "versalete":
            self.aplicar(versalete=True)
        elif classe == "sim":
            self.aplicar(familia="simbolos")
        else:
            self.aplicar(papel=dialeto.PAPEL_DA_CLASSE.get(classe, ""))

    def _corpo_no_cursor(self) -> float:
        bloco_id = self.bloco_atual()
        estilo = next((T.valor(t) for t in self._ptags.get(bloco_id or "", ()) if t.startswith("p:")), "corpo")
        for tag in self._tags_no_cursor():
            if tag.startswith("corpo:"):
                try:
                    return float(T.valor(tag))
                except ValueError:
                    pass
        return float(self.estilos.de_paragrafo(estilo).get("corpo_pt", self.tela.corpo_pt))

    def aumentar_fonte(self) -> float:
        novo = self._corpo_no_cursor() + PASSO_DA_FONTE_PT
        self.aplicar(corpo_pt=novo)
        return novo

    def diminuir_fonte(self) -> float:
        novo = max(4.0, self._corpo_no_cursor() - PASSO_DA_FONTE_PT)
        self.aplicar(corpo_pt=novo)
        return novo

    def pincel_copiar(self) -> tuple[str, ...]:
        self._pincel = tuple(t for t in self._tags_no_cursor() if not t.startswith(("link:", "nota:", "ref:")))
        return self._pincel

    def pincel_aplicar(self) -> bool:
        selecao = self.selecao()
        if self._pincel is None or not selecao:
            return False
        ini, fim = selecao
        for tag in self.texto.tag_names():
            if T.e_de_caractere(tag) and not tag.startswith(("link:", "nota:", "ref:")):
                self.texto.tag_remove(tag, ini, fim)
        for tag in self._pincel:
            self._trocar_tag(ini, fim, por=tag)
        self._reconciliar(self._blocos_entre(ini, fim), coalescer=False, rotulo="pincel")
        self.texto.tag_add("sel", ini, fim)
        return True

    def mudar_caixa(self, modo: str) -> bool:
        """`maiusculas`, `minusculas`, `capitalizar`, `alternar` na seleção (ou na palavra sob o cursor)."""
        selecao = self.selecao()
        bloco_id = self.bloco_atual()
        paragrafo = self._modelo.get(bloco_id) if bloco_id else None
        if not isinstance(paragrafo, Paragrafo) or isinstance(paragrafo, TIPOS_DE_OBJETO):
            return False
        if selecao:
            ini_i, fim_i = self._deslocamento(selecao[0], bloco_id), self._deslocamento(selecao[1], bloco_id)
        else:
            texto = modelo.texto_de(paragrafo)
            pos = self._deslocamento("insert", bloco_id)
            ini_i = fim_i = pos
            while ini_i > 0 and texto[ini_i - 1].isalnum():
                ini_i -= 1
            while fim_i < len(texto) and texto[fim_i].isalnum():
                fim_i += 1
        novo = modelo.mudar_caixa(copy.deepcopy(paragrafo), ini_i, fim_i, modo)   # muda no lugar: o antigo fica
        self._reescrever_bloco(bloco_id, novo)
        a, b = self.indice_de(bloco_id, ini_i), self.indice_de(bloco_id, fim_i)
        if selecao and a and b:
            self.selecionar_indices(a, b)
        elif b:
            self.texto.mark_set("insert", b)
        return True

    def estilo_no_cursor(self) -> dict[str, Any]:
        """O estilo do parágrafo e os atributos de caractere no cursor — para a barra."""
        bloco_id = self.bloco_atual()
        ptags = self._ptags.get(bloco_id or "", ("p:corpo",))
        tags = self._tags_no_cursor()
        saida: dict[str, Any] = {"estilo": next((T.valor(t) for t in ptags if t.startswith("p:")), "corpo"),
                                 "bloco": bloco_id,
                                 "tipo": type(self._modelo.get(bloco_id)).__name__ if bloco_id else ""}
        for atributo, tag in ATRIBUTOS_ALTERNAVEIS.items():
            saida[atributo] = bool(self._pendente.get(atributo, tag in tags))
        saida["codigo"] = "code" in tags
        for tag in tags:
            if ":" in tag:
                saida[T.prefixo(tag)[:-1]] = T.valor(tag)
        saida["corpo_pt"] = self._corpo_no_cursor()
        return saida

    # ------------------------------------------------------------------
    # Formatação de parágrafo, estilos, listas
    # ------------------------------------------------------------------

    def _blocos_da_selecao(self) -> list[str]:
        selecao = self.selecao()
        if selecao:
            blocos = self._blocos_entre(*selecao)
            if len(blocos) > 1 and self.texto.compare(self._inicio_de(blocos[-1]), ">=", selecao[1]):
                blocos = blocos[:-1]
            return blocos
        atual = self.bloco_atual()
        return [atual] if atual else []

    def _e_paragrafo_editavel(self, bloco_id: str) -> bool:
        bloco = self._modelo.get(bloco_id)
        return isinstance(bloco, Paragrafo) and not isinstance(bloco, TIPOS_DE_OBJETO)

    def paragrafo(self, **props: Any) -> list[str]:
        """
        `alinhamento`, `recuo_primeira_em`, `recuo_esquerda_em`, `recuo_direita_em`,
        `antes_em`, `depois_em`, `entrelinha`, `manter_com_proximo`, `manter_linhas` nos
        blocos da seleção (ou no atual). `None`/`""` tira. Devolve os ids tocados.
        """
        for chave in props:
            if chave not in PREFIXOS_DE_PARAGRAFO and chave not in SIMPLES_DE_PARAGRAFO:
                raise ValueError(f"propriedade de parágrafo desconhecida: {chave!r}")
        ids = [i for i in self._blocos_da_selecao() if self._e_paragrafo_editavel(i)]
        for bloco_id in ids:
            ptags = list(self._ptags.get(bloco_id, ("p:corpo",)))
            for chave, valor in props.items():
                if chave in PREFIXOS_DE_PARAGRAFO:
                    pref = PREFIXOS_DE_PARAGRAFO[chave]
                    ptags = [t for t in ptags if not t.startswith(pref)]
                    if valor not in (None, ""):
                        ptags.append(T.nome(pref, _valor_de_tag(valor)))
                else:
                    tag = SIMPLES_DE_PARAGRAFO[chave]
                    ptags = [t for t in ptags if t != tag] + ([tag] if valor else [])
            self._ptags[bloco_id] = tuple(ptags)
        self._reconciliar(ids, coalescer=False, rotulo="paragrafo")
        return ids

    def estilo(self, nome: str) -> list[str]:
        """O estilo nomeado (§6.3) nos blocos da seleção; `tituloN` vira `Titulo` no modelo."""
        if nome not in dialeto.ESTILOS_DE_PARAGRAFO:
            raise ValueError(f"estilo desconhecido: {nome!r}")
        ids = [i for i in self._blocos_da_selecao() if self._e_paragrafo_editavel(i)]
        for bloco_id in ids:
            self._ptags[bloco_id] = tuple(t for t in self._ptags.get(bloco_id, ()) if not t.startswith("p:")) \
                + (T.nome("p:", nome),)
        self._reconciliar(ids, coalescer=False, rotulo="estilo")
        return ids

    def limpar_paragrafo(self) -> list[str]:
        ids = [i for i in self._blocos_da_selecao() if self._e_paragrafo_editavel(i)]
        for bloco_id in ids:
            self._ptags[bloco_id] = tuple(t for t in self._ptags.get(bloco_id, ()) if t.startswith("p:"))
        self._reconciliar(ids, coalescer=False, rotulo="limpar parágrafo")
        return ids

    def _reescrever_bloco(self, bloco_id: str, novo: Bloco, reconciliar: bool = True) -> None:
        """Troca o desenho de um bloco pelo de `novo` (mesmo id); o ponto sai na reconciliação."""
        novo.id = bloco_id
        ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
        seguinte = self._seguinte(bloco_id)
        antigo = self._modelo.get(bloco_id)
        self._remover_bloco(bloco_id)
        self._em_carga = True
        try:
            self.texto.delete(ini, fim)
            self._desenhar_bloco(novo, ini, seguinte)
        finally:
            self._em_carga = False
        if antigo is not None:
            self._modelo[bloco_id] = antigo      # o "antes" do ponto; o "depois" vem do dump
        self._tocados.add(bloco_id)
        self._simples = False
        if reconciliar:
            self._reconciliar({bloco_id}, coalescer=False)

    def lista(self, ordenada: bool = False) -> list[str]:
        """Os parágrafos da seleção viram uma lista (um item cada); uma lista do mesmo tipo volta a parágrafos."""
        ids = self._blocos_da_selecao()
        if not ids:
            return []
        primeiro = self._modelo.get(ids[0])
        if isinstance(primeiro, Lista) and len(ids) == 1:
            if primeiro.ordenada == ordenada:
                return self._desfazer_lista(ids[0])
            nova = _montar_lista(Lista(ordenada=ordenada, itens=[], id=primeiro.id), list(_achatar(primeiro, 1)))
            self._reescrever_bloco(ids[0], nova)
            return [ids[0]]
        paragrafos = [self._modelo[i] for i in ids if self._e_paragrafo_editavel(i)]
        if not paragrafos:
            return []
        itens = [ItemDeLista(paragrafos=[Paragrafo(trechos=list(p.trechos))]) for p in paragrafos]
        nova = Lista(ordenada=ordenada, itens=itens)
        alvo = paragrafos[0].id
        for outro in [p.id for p in paragrafos[1:]]:
            self._apagar_bloco_sem_ponto(outro)
            self._tocados.add(outro)
        self._reescrever_bloco(alvo, nova)
        self.ir_para(alvo, 0)
        return [alvo]

    def _desfazer_lista(self, bloco_id: str) -> list[str]:
        lista = self._modelo[bloco_id]
        assert isinstance(lista, Lista)
        novos = [Paragrafo(trechos=list(p.trechos)) for _n, item, _o in _achatar(lista, 1) for p in item.paragrafos]
        seguinte = self._seguinte(bloco_id)
        self._reescrever_bloco(bloco_id, novos[0], reconciliar=False)
        anterior = bloco_id
        for novo in novos[1:]:
            self._desenhar_bloco(novo, self._fim_de(anterior), seguinte)
            anterior = novo.id
        self._reconciliar({bloco_id} | {n.id for n in novos[1:]}, coalescer=False)
        self.ir_para(bloco_id, 0)
        return [bloco_id] + [n.id for n in novos[1:]]

    def _posicao_na_lista(self, bloco_id: str, indice: str) -> tuple[int, int, int]:
        """`(item, parágrafo do item, deslocamento no parágrafo)` do índice dentro da lista."""
        lista = self._modelo[bloco_id]
        assert isinstance(lista, Lista)
        desloc = self._deslocamento(indice, bloco_id)
        andados = 0
        itens = list(_achatar(lista, 1))
        for k, (_nivel, item, _o) in enumerate(itens):
            for j, p in enumerate(item.paragrafos):
                comprimento = len(modelo.texto_de(p))
                if desloc <= andados + comprimento:
                    return k, j, desloc - andados
                andados += comprimento + 1
        return len(itens) - 1, len(itens[-1][1].paragrafos) - 1, 0

    @staticmethod
    def _deslocamento_do_item(lista: Lista, item_i: int) -> int:
        andados = 0
        for k, (_n, item, _o) in enumerate(_achatar(lista, 1)):
            if k == item_i:
                return andados
            andados += sum(len(modelo.texto_de(p)) + 1 for p in item.paragrafos)
        return andados

    def nivel(self, delta: int) -> bool:
        """Sobe (+1) ou desce (−1) o nível do item sob o cursor (`Tab`/`Shift+Tab` no item)."""
        bloco_id = self.bloco_atual()
        lista = self._modelo.get(bloco_id) if bloco_id else None
        if not isinstance(lista, Lista):
            return False
        item_i, _p, desloc = self._posicao_na_lista(bloco_id, "insert")
        itens = list(_achatar(lista, 1))
        nivel, item, dona = itens[item_i]
        novo_nivel = nivel + delta
        if novo_nivel < 1 or (delta > 0 and (item_i == 0 or novo_nivel > itens[item_i - 1][0] + 1)):
            return False
        dona_nova = itens[item_i - 1][2] if delta > 0 and itens[item_i - 1][0] == novo_nivel else dona
        itens[item_i] = (novo_nivel, item, dona_nova)
        nova = _montar_lista(lista, itens)
        self._reescrever_bloco(bloco_id, nova)
        self.ir_para(bloco_id, self._deslocamento_do_item(nova, item_i) + desloc)
        return True

    # ------------------------------------------------------------------
    # Tela: zoom, invisíveis, largura
    # ------------------------------------------------------------------

    def zoom(self, fator: float) -> float:
        """Só a tela: redesenha com o corpo multiplicado; o modelo não muda."""
        self.tela.zoom = max(0.5, min(4.0, float(fator)))
        self._configuradas.clear()
        T.configurar(self.texto, self.estilos, self.fontes)
        self._redesenhar_tudo()
        return self.tela.zoom

    def _redesenhar_tudo(self) -> None:
        posicao = self.posicao()
        blocos = [self._modelo[i] for i in self._ordem if i in self._modelo]
        notas, capitulo, sujo = self._notas, self._capitulo, self._sujo
        invisiveis = self._invisiveis
        self._invisiveis = False
        self.carregar_blocos(blocos)
        self._notas, self._capitulo, self._sujo = notas, capitulo, sujo
        if invisiveis:
            self.invisiveis(True)
        if posicao[0] and posicao[0] in self._ordem:
            self.ir_para(posicao[0], posicao[1])

    def invisiveis(self, mostrar: bool) -> bool:
        """`¶` no fim do bloco, `⏎` na quebra suave, `°` no espaço inseparável — protegidos, fora do `dump`."""
        if mostrar == self._invisiveis:
            return mostrar
        self._invisiveis = mostrar
        texto = self.texto
        self._em_carga = True
        try:
            if not mostrar:
                faixas = texto.tag_ranges("invisivel")
                for a, b in reversed(list(zip(faixas[::2], faixas[1::2]))):
                    texto.delete(a, b)
                return False
            for bloco_id in list(self._ordem):
                if isinstance(self._modelo.get(bloco_id), TIPOS_DE_OBJETO):
                    continue
                ptags = self._ptags.get(bloco_id, ("p:corpo",))
                extras = ptags + ("invisivel", "protegido")
                for tag in extras:
                    self._garantir_tag(tag)
                i = self._inicio_de(bloco_id)
                while texto.compare(i, "<", self._fim_de(bloco_id)):
                    ch, tags = texto.get(i), texto.tag_names(i)
                    if "invisivel" in tags:
                        i = texto.index(f"{i}+1c")
                        continue
                    simbolo = None
                    if ch == "\n":
                        simbolo = INVISIVEIS["quebra"] if "qs" in tags else (
                            INVISIVEIS["paragrafo"] if not any(T.e_quebra(t) for t in tags) else None)
                    elif ch == " ":
                        simbolo = INVISIVEIS["nbsp"]
                    elif ch == "\t":
                        simbolo = INVISIVEIS["tab"]
                    if simbolo:
                        texto.insert(i, simbolo, extras)
                        i = texto.index(f"{i}+1c")
                    i = texto.index(f"{i}+1c")
        finally:
            self._em_carga = False
            self._tocados.clear()
        return mostrar

    def largura_de_leitura(self, colunas: int) -> int:
        """~`colunas` caracteres de largura (0 = toda a janela), com margens cinza fora (§8.15)."""
        self.tela.largura_de_leitura = max(0, int(colunas))
        if self.tela.largura_de_leitura:
            fonte = self.fontes.fonte(self.tela.familia, self.tela.corpo_na_tela())
            largura = fonte.measure("n") * self.tela.largura_de_leitura
            disponivel = self.texto.winfo_width()
            margem = max(12, (disponivel - largura) // 2) if disponivel > largura else 12
            self.texto.configure(padx=margem)
        else:
            self.texto.configure(padx=12)
        return self.tela.largura_de_leitura

    # ------------------------------------------------------------------
    # Desfazer
    # ------------------------------------------------------------------

    def ponto(self, ids: Iterable[str] | None = None, rotulo: str = "") -> None:
        """Fecha um ponto de desfazer para os blocos dados (ou os tocados)."""
        self._reconciliar(ids, coalescer=False, rotulo=rotulo)

    def desfazer(self) -> bool:
        ponto = self.historico.desfazer(self.arquivo)
        if ponto is None:
            return False
        self._aplicar_ponto(ponto, "antes")
        return True

    def refazer(self) -> bool:
        ponto = self.historico.refazer(self.arquivo)
        if ponto is None:
            return False
        self._aplicar_ponto(ponto, "depois")
        return True

    def _aplicar_ponto(self, ponto: Ponto, sentido: str) -> None:
        from core.editor import historico as historico_mod

        self._reconciliar()
        capitulo = Capitulo(arquivo=self.arquivo, blocos=[self._modelo[i] for i in self._ordem if i in self._modelo],
                            notas=list(self._notas))
        historico_mod.aplicar(capitulo, ponto, sentido)
        self._em_desfazer = True
        try:
            invisiveis = self._invisiveis
            self._invisiveis = False
            self.carregar_blocos(capitulo.blocos)
            self._notas = list(capitulo.notas)
            if invisiveis:
                self.invisiveis(True)
        finally:
            self._em_desfazer = False
        self._sujo = True
        alvo = next((i for i in ponto.ids if i in self._ordem), None)
        if alvo:
            self.ir_para(alvo, 0)
        try:
            self.texto.event_generate("<<Mudou>>")
        except tk.TclError:
            pass

    @property
    def pode_desfazer(self) -> bool:
        return self.historico.pode_desfazer(self.arquivo)

    @property
    def pode_refazer(self) -> bool:
        return self.historico.pode_refazer(self.arquivo)

    # ------------------------------------------------------------------
    # Ligações de teclado (a API por trás de cada tecla)
    # ------------------------------------------------------------------

    def _instalar_ligacoes(self) -> None:
        texto = self.texto
        tags = list(texto.bindtags())
        tags.insert(1, BINDTAG)
        texto.bindtags(tuple(tags))
        q = self._quebra
        ligacoes = {
            "<Return>": lambda e: q(self.enter()), "<KP_Enter>": lambda e: q(self.enter()),
            "<BackSpace>": lambda e: q(self.backspace()), "<Delete>": lambda e: q(self._delete()),
            "<Key>": self._tecla,
            "<Tab>": lambda e: q(self.nivel(1) or self.inserir("\t")), "<Shift-Tab>": lambda e: q(self.nivel(-1)),
            "<Control-b>": lambda e: q(self.alternar("negrito")), "<Control-i>": lambda e: q(self.alternar("italico")),
            "<Control-u>": lambda e: q(self.alternar("sublinhado")),
            "<Control-Shift-K>": lambda e: q(self.alternar("versalete")),
            "<Control-equal>": lambda e: q(self.alternar("subscrito")),
            "<Control-plus>": lambda e: q(self.alternar("sobrescrito")),
            "<Control-Shift-greater>": lambda e: q(self.aumentar_fonte()),
            "<Control-Shift-less>": lambda e: q(self.diminuir_fonte()),
            "<Control-l>": lambda e: q(self.paragrafo(alinhamento="esquerda")),
            "<Control-e>": lambda e: q(self.paragrafo(alinhamento="centro")),
            "<Control-r>": lambda e: q(self.paragrafo(alinhamento="direita")),
            "<Control-j>": lambda e: q(self.paragrafo(alinhamento="justificado")),
            "<Control-space>": lambda e: q(self.limpar_caractere()),
            "<Control-q>": lambda e: q(self.limpar_paragrafo()),
            "<Control-BackSpace>": lambda e: q(self.apagar_palavra(-1)),
            "<Control-Delete>": lambda e: q(self.apagar_palavra(1)),
            "<Control-Shift-L>": lambda e: q(self.lista(False)), "<Control-Shift-O>": lambda e: q(self.lista(True)),
            "<<Undo>>": lambda e: q(self.desfazer()), "<<Redo>>": lambda e: q(self.refazer()),
            "<<SelectAll>>": lambda e: q(self.selecionar_tudo()),
            "<<Paste>>": self._colar, "<<Cut>>": self._recortar,
            "<Key-Insert>": lambda e: "break", "<<PasteSelection>>": lambda e: "break",
            "<Control-d>": lambda e: "break", "<Control-o>": lambda e: "break", "<Control-t>": lambda e: "break",
            "<Control-h>": lambda e: "break", "<Control-k>": lambda e: "break",
        }
        for sequencia, handler in ligacoes.items():
            texto.bind_class(BINDTAG, sequencia, handler)
        self.ligacoes = ligacoes

    @staticmethod
    def _quebra(_resultado: Any = None) -> str:
        return "break"

    def _tecla(self, evento: Any) -> str | None:
        char = getattr(evento, "char", "")
        estado = getattr(evento, "state", 0) or 0
        if not char or ord(char[0]) < 32 or char[0] == "\x7f":
            return None
        if estado & 0x4 and not estado & 0x20000:          # Control sem AltGr: não é texto
            return None
        if self.selecao():
            self.apagar_selecao()
        self.inserir(char)
        return "break"

    def _delete(self) -> bool:
        if self.selecao():
            return self.apagar_selecao()
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None:
            return False
        if self.texto.compare(indice, ">=", f"{self._fim_de(bloco_id)}-1c"):
            seguinte = self._seguinte(bloco_id)
            if seguinte is None:
                return False
            self.texto.mark_set("insert", self._inicio_de(seguinte))
            return self._juntar_ao_anterior(seguinte)
        return self.apagar(indice, f"{indice}+1c")

    def _colar(self, evento: Any) -> str:
        try:
            conteudo = self.texto.clipboard_get()
        except tk.TclError:
            return "break"
        if self.selecao():
            self.apagar_selecao()
        self.inserir(conteudo.replace("\r\n", "\n"))
        return "break"

    def _recortar(self, evento: Any) -> str:
        selecao = self.selecao()
        if selecao:
            try:
                self.texto.clipboard_clear()
                self.texto.clipboard_append(self.texto.get(*selecao))
            except tk.TclError:
                pass
            self.apagar_selecao()
        return "break"


# ----------------------------------------------------------------------
# Listas: achatar e montar de volta
# ----------------------------------------------------------------------

def _achatar(lista: Lista, nivel: int):
    """`(nível, item, lista dona)` de cada item, com os filhos logo depois do pai."""
    for item in lista.itens:
        yield nivel, item, lista
        if item.filhos is not None:
            yield from _achatar(item.filhos, nivel + 1)


def _montar_lista(base: Lista, itens: Sequence[tuple[int, ItemDeLista, Lista]]) -> Lista:
    """A lista de volta dos itens achatados; os filhos saem do nível, com os atributos da lista dona."""
    def montar(indice: int, nivel: int) -> tuple[list[ItemDeLista], int]:
        saida: list[ItemDeLista] = []
        while indice < len(itens):
            n, item, dona = itens[indice]
            if n < nivel:
                break
            if n > nivel:
                filhos, indice = montar(indice, n)
                sublista = Lista(ordenada=dona.ordenada, itens=filhos, inicio=dona.inicio, marcador=dona.marcador)
                if saida:
                    saida[-1].filhos = sublista
                else:
                    saida.append(ItemDeLista(paragrafos=[Paragrafo(trechos=[])], filhos=sublista))
                continue
            saida.append(ItemDeLista(paragrafos=list(item.paragrafos)))
            indice += 1
        return saida, indice

    raiz, _ = montar(0, 1)
    return Lista(ordenada=base.ordenada, itens=raiz, inicio=base.inicio, marcador=base.marcador, id=base.id,
                 id_persistente=base.id_persistente, classe=base.classe, extras=dict(base.extras),
                 origem=base.origem)
