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

## A faixa de notas (ED-04, §8.8)

Depois do último bloco do capítulo vem o marco `FaixaDeNotas` (um objeto, "Notas") e,
para cada nota, os parágrafos dela — blocos comuns na `_ordem`, com a tag de
parágrafo `dn:<id>|<tipo>` e, no primeiro, o número como marcador protegido. Editam-se
como qualquer parágrafo; `sincronizar()` os devolve agrupados em `Capitulo.notas`, e o
ponto de desfazer de uma edição numa nota é sobre a **nota inteira** (`Nota`), não sobre
o parágrafo. `inserir_nota` põe a referência no cursor e o cursor na nota; `Esc`
(`voltar_da_nota`) volta à referência; apagar a última referência apaga a nota.

## Objetos vivos, células e o texto de fora

A tabela é uma `GradeDeTabela` (`ui/editor/tabela.py`) de células que são `TextoRico`
em modo célula (`celula=True`: sem calha, sem barra, altura pelas linhas exibidas, com o
`dono` apontando o texto de fora). O registro pergunta à grade o modelo atual quando o
`dump` chega a ela, e uma edição numa célula vira um ponto de desfazer sobre a tabela
inteira no texto de fora. As ligações de teclado moram numa bindtag de **classe**
(`EditorAtalhosTexto`), ligada uma vez por interpretador, cujo handler despacha para o
`TextoRico` dono do widget que recebeu a tecla (`_INSTANCIAS`) — uma bindtag de classe
com closures sobre `self` serviria só o último widget criado.

## O modelo por bloco, e o desfazer

O widget guarda o **último modelo de cada bloco** (`_modelo`). Depois de cada edição,
`_reconciliar` reaplica as tags de parágrafo, refaz a fonte derivada, relê só os
blocos tocados pelo `dump` e registra no `Historico` um ponto `(ids, antes, depois)`
— a digitação contínua coalesce (DEC-04). Desfazer aplica o `antes` ao modelo e
redesenha o capítulo; é por isso que nem `undo=True` nem cópias do documento existem
aqui. Quem diz **quais** blocos uma edição tocou é o proxy do comando Tcl (o mesmo
truque do modo código): cada `insert`/`delete` que passa por ele anota os blocos do
intervalo, e o `mark previous` do Tk acha o bloco de um índice em uma ou duas chamadas. O proxy é um
`proc` Tcl (`ui/editor/proxy.py`), não um comando Python: um erro Tcl dentro de um comando
Python derruba o `mainloop` mesmo quando o Python o captura (ED-04).
"""

from __future__ import annotations

import copy
import re
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from core.editor import css_minima, dialeto, modelo
from core.editor.area_de_transferencia import Fragmento
from core.editor.historico import Historico, Ponto
from core.editor.modelo import (Bloco, Capitulo, Citacao, Diagrama, Figura, IlhaBruta, ItemDeLista, Lista,
                                MarcaDePagina, Nota, Paragrafo, QuebraDePagina, Separador, Tabela, Titulo, Trecho)
from ui.editor import dump as dump_mod
from ui.editor import proxy as proxy_mod
from ui.editor import tags as T
from ui.editor.calha import Calha
from ui.editor.dump import ID_DA_FAIXA, FaixaDeNotas
from ui.editor.objetos import ContextoDeObjetos, RegistroDeObjetos, criar_objeto
from ui.editor.tabela import LIMITE as LIMITE_DE_CELULAS
from ui.editor.tabela import GradeDeTabela
from ui.editor.tags import EstiloDeTela, Estilos, Fontes

BINDTAG = "EditorAtalhosTexto"
MARCA_DE_INSERCAO = "fim_ins"
PASSO_DA_FONTE_PT = 2.0
SOBRESCRITOS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
SIMBOLO_DA_PAGINA = "⁞"
INVISIVEIS = {"paragrafo": "¶", "tab": "→", "quebra": "⏎", "nbsp": "°"}
TIPOS_DE_OBJETO = (Diagrama, Figura, Tabela, IlhaBruta, MarcaDePagina, QuebraDePagina, Separador, FaixaDeNotas)
#: O alinhamento com que cada objeto de bloco é desenhado na linha.
ALINHAMENTO_DO_OBJETO = {"esq": "esquerda", "centro": "centro", "dir": "direita"}
TIPOS_DE_NOTA = ("rodape", "fim")
#: Quanto uma edição numa célula espera antes de a tabela ser relida (a digitação contínua junta-se).
ATRASO_DA_CELULA_MS = 250
#: `TextoRico` por caminho do `tk.Text` — o despacho da bindtag de classe (ver o cabeçalho).
_INSTANCIAS: dict[str, "TextoRico"] = {}
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
#: Tags de caractere que **não** se estendem ao que se digita depois delas: o link e a
#: referência (ED-04), e os átomos de xadrez (ED-05) — o NAG com código, a figurina, a
#: chave de índice e a fonte de símbolos valem para o símbolo, não para o " Nc6" que vem.
NAO_SE_ESTENDEM = ("link:", "ref:", "nag:", "chave:", "papel:nag", "papel:figurina", "papel:jogador",
                   "papel:abertura", "fam:simbolos")
#: O que fecha um token de notação ao digitar (ED-05): espaço e a pontuação que segue um lance.
SEPARADORES_DE_TOKEN = frozenset(" \t,;:.)]!?")
_RE_PALAVRA_DEPOIS = re.compile(r"\w+|\W+")


def _sobrescrito(n: int) -> str:
    return "".join(SOBRESCRITOS[int(d)] for d in str(n))


def _contagem(resultado: Any) -> int:
    """O inteiro de `Text.count`: o tkinter devolve `None` para zero, uma tupla ou um inteiro conforme a versão."""
    if resultado is None:
        return 0
    if isinstance(resultado, (tuple, list)):
        return int(resultado[0]) if resultado else 0
    return int(resultado)


def _numero_ou_nenhum(valor: Any, nome: str) -> float | None:
    """Um campo numérico do painel: vazio é `None`; texto que não é número é erro de entrada."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        return float(str(valor).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"{nome}: {valor!r} não é um número") from None


def _valor_de_tag(valor: Any) -> str:
    return f"{valor:g}" if isinstance(valor, float) else str(valor)


class TextoRico(ttk.Frame):
    def __init__(self, master: tk.Misc, estilo_de_tela: EstiloDeTela | None = None, folhas: Any = (),
                 historico: Historico | None = None, relogio: Callable[[], float] = time.monotonic,
                 arquivo: str = "capitulo", *, celula: bool = False, dono: "TextoRico | None" = None,
                 estilos: Estilos | None = None, fontes: Fontes | None = None,
                 recursos: Callable[[str], bytes | None] | None = None,
                 ao_ativar: Callable[[Any], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.celula = bool(celula)
        self.dono = dono
        self.tela = estilo_de_tela or (dono.tela if dono is not None else EstiloDeTela())
        self.estilos = estilos or Estilos(self.tela, None)
        self.fontes = fontes or Fontes(self)
        self.historico = historico or Historico(relogio=relogio)
        self.relogio = relogio
        self.arquivo = arquivo
        self.recursos = recursos
        self.ao_ativar = ao_ativar
        self.registro = RegistroDeObjetos()
        #: Os ganchos que a grade de tabela põe numa célula (ED-04, §8.6).
        self.ao_tab: Callable[[int], Any] | None = None
        #: O gancho das figurinas ao digitar (ED-05, §11.5): `(id do bloco, deslocamento antes do
        #: separador) -> bool` — chamado depois de um espaço ou pontuação entrar num parágrafo.
        self.ao_fechar_token: Callable[[str, int], bool] | None = None
        self.ao_escape: Callable[[], Any] | None = None
        self.ao_sair_vertical: Callable[[int], Any] | None = None
        self.ao_sair_horizontal: Callable[[int], Any] | None = None

        if self.celula:
            self.texto = tk.Text(self, undo=False, wrap="word", highlightthickness=1, padx=4, pady=2, spacing3=0,
                                 exportselection=False, insertwidth=2, height=1, width=12,
                                 highlightbackground="#c8c8c8", highlightcolor="#0645ad")
            self.calha = _SemCalha()               # uma célula não tem margem de ícones
            self.barra = None
            self.texto.pack(fill="both", expand=True)
        else:
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
        self._composto = 0
        self._ids_compostos: set[str] = set()
        self._modelo_antes: dict[str, Bloco] = {}
        self._notas_antes: list[Nota] = []
        self._rotulo_composto = ""
        self._objeto_selecionado: str | None = None
        self._reconciliacao_agendada: str | None = None
        self._antes_forcado: dict[str, Bloco] = {}
        self._configuradas: set[str] = set()
        if estilos is None:
            self.definir_folhas(folhas)
        T.configurar(self.texto, self.estilos, self.fontes, preguicoso=self.celula)
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
            "quebra_de_linha": self.inserir_quebra_suave, "quebra_de_pagina": self.inserir_quebra_de_pagina,
            "inserir_separador": self.inserir_separador,
            "nota_de_rodape": lambda: self.inserir_nota("rodape"), "nota_de_fim": lambda: self.inserir_nota("fim"),
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
        elif tag.startswith(("lista:", "marc:", "ini:", "sub:", "pid:", "pcls:", "pex:", "ncab:")):
            self.texto.tag_configure(tag)
        elif self.celula and T.e_fixa(tag):
            T.configurar_fixa(self.texto, tag, self.estilos, self.fontes)
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
        """O `proc` Tcl de `ui/editor/proxy.py`: `_antes` anota os blocos que um `insert`/`delete` toca."""
        self._original = proxy_mod.instalar(self.texto, self._antes_do_comando, self._depois_do_comando)

    def _antes_do_comando(self, comando: str, args: tuple[str, ...]) -> None:
        if self._em_carga or not args:
            return
        ini = self.texto.index(args[0])
        if comando == "delete":
            fim = self.texto.index(args[1]) if len(args) > 1 else self.texto.index(f"{ini}+1c")
        else:
            fim = ini
        self._tocados.update(self._blocos_entre(ini, fim))

    def _depois_do_comando(self, comando: str, args: tuple[str, ...]) -> None:
        if comando == "mark" and len(args) >= 3 and args[0] == "set" and args[1] == "insert":
            self._cursor_moveu()
        elif comando == "yview" and args:
            self._agendar_calha()

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
        self.carregar_blocos(cap.blocos, cap.notas)
        self.historico.limpar(self.arquivo)
        self._sujo = False

    def carregar_blocos(self, blocos: Sequence[Bloco], notas: Sequence[Nota] | None = None) -> None:
        """Desenha os blocos e, com `notas`, a faixa de notas depois deles (§8.8)."""
        self._em_carga = True
        try:
            self._limpar_widget()
            self._notas = [copy.deepcopy(n) for n in (notas or [])]
            for bloco in blocos:
                self._desenhar_bloco(bloco, "end-1c")
            if self._notas:
                self._desenhar_faixa()
                for nota in self._notas:
                    self._desenhar_nota(nota)
            self.texto.mark_set("insert", "1.0")
        finally:
            self._em_carga = False
        self._tocados.clear()
        self.calha.redesenhar()
        if self.celula:
            self.ajustar_altura()

    # -- a faixa de notas ---------------------------------------------------

    def _raiz(self) -> "TextoRico":
        """O texto de fora de uma célula (o dono das notas); o próprio widget quando não é célula."""
        raiz = self
        while raiz.dono is not None:
            raiz = raiz.dono
        return raiz

    def _tem_faixa(self) -> bool:
        return ID_DA_FAIXA in self._ordem

    def _desenhar_faixa(self) -> None:
        if not self._tem_faixa():
            self._desenhar_bloco(FaixaDeNotas(), "end-1c")

    def _nota_do_paragrafo(self, bloco_id: str) -> str | None:
        nota = dump_mod.nota_da_tag(self._ptags.get(bloco_id, ()))
        return nota[0] if nota else None

    def _paragrafos_da_nota(self, nota_id: str) -> list[str]:
        return [i for i in self._ordem if self._nota_do_paragrafo(i) == nota_id]

    def ids_das_notas(self) -> list[str]:
        return [n.id for n in self._raiz()._notas]

    def _numero_da_nota(self, nota_id: str) -> int:
        return next((i for i, n in enumerate(self._raiz()._notas, start=1) if n.id == nota_id), 0)

    def _glifo_da_nota(self, nota_id: str) -> str:
        numero = self._numero_da_nota(nota_id)
        return _sobrescrito(numero) if numero else "¹"

    def _desenhar_nota(self, nota: Nota, antes_de: str | None = None) -> None:
        """Os parágrafos da nota, com `dn:<id>|<tipo>` e o número como marcador no primeiro."""
        extras = (T.nome("dn:", f"{nota.id}|{nota.tipo}"),)
        paragrafos = list(nota.blocos) or [Paragrafo(trechos=[], estilo="nota")]
        for k, paragrafo in enumerate(paragrafos):
            if not isinstance(paragrafo, Paragrafo):
                continue
            onde = self._inicio_de(antes_de) if antes_de is not None else "end-1c"
            self._desenhar_bloco(paragrafo, onde, antes_de, extras=extras,
                                 marcador=f"{self._glifo_da_nota(nota.id)} " if k == 0 else "",
                                 tag_do_marcador=T.nome("ncab:", nota.id))

    def _montar_nota(self, nota_id: str) -> Nota | None:
        """A nota como está no widget agora (`None` se não tem mais parágrafo)."""
        ids = self._paragrafos_da_nota(nota_id)
        blocos = [self._modelo[i] for i in ids if i in self._modelo and isinstance(self._modelo[i], Paragrafo)]
        if not blocos:
            return None
        tipo = (dump_mod.nota_da_tag(self._ptags.get(ids[0], ())) or (nota_id, "rodape"))[1]
        return Nota(id=nota_id, tipo=tipo, blocos=blocos)

    def _nota_cache(self, nota_id: str) -> Nota | None:
        return next((n for n in self._notas if n.id == nota_id), None)

    def notas_atuais(self) -> list[Nota]:
        """As notas do capítulo como estão na faixa, na ordem da faixa."""
        saida: list[Nota] = []
        vistos: set[str] = set()
        for bloco_id in self._ordem:
            nota_id = self._nota_do_paragrafo(bloco_id)
            if nota_id and nota_id not in vistos:
                vistos.add(nota_id)
                nota = self._montar_nota(nota_id)
                if nota is not None:
                    saida.append(nota)
        return saida

    def _ids_do_capitulo(self) -> list[str]:
        """Os blocos do capítulo propriamente: o que vem antes da faixa de notas."""
        saida = []
        for bloco_id in self._ordem:
            if bloco_id == ID_DA_FAIXA:
                break
            saida.append(bloco_id)
        return saida

    @property
    def ordem_do_capitulo(self) -> list[str]:
        return self._ids_do_capitulo()

    def em_nota(self, indice: str = "insert") -> str | None:
        """O id da nota em que o índice está (`None` fora da faixa)."""
        bloco_id = self._bloco_em(indice)
        return self._nota_do_paragrafo(bloco_id) if bloco_id else None

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
        if isinstance(bloco, Figura):
            return ("p:corpo", T.nome("al:", ALINHAMENTO_DO_OBJETO.get(bloco.alinhamento, "centro")))
        if isinstance(bloco, (Diagrama, QuebraDePagina, MarcaDePagina, Separador, FaixaDeNotas)):
            return ("p:corpo", "al:centro")
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
                self._inserir_segmento(self._glifo_da_nota(t.nota), ptags, (), estilo,
                                       (T.nome("nota:", t.nota), "protegido"))
                continue
            if t.texto:
                self._inserir_segmento(t.texto, ptags, self._tags_do_trecho(t), estilo)

    def _contexto_de_objetos(self) -> ContextoDeObjetos:
        try:
            largura = int(self.texto.winfo_width())
        except tk.TclError:
            largura = 0
        if largura < 100:
            largura = 640
        return ContextoDeObjetos(recursos=self._raiz().recursos, largura_maxima_px=max(120, largura - 60),
                                 zoom=self.tela.zoom, criar_tabela=self._criar_grade if not self.celula else None,
                                 limite_de_celulas=LIMITE_DE_CELULAS)

    def _criar_grade(self, master: tk.Misc, tabela: Tabela) -> GradeDeTabela:
        contexto = self._contexto_de_objetos()
        return GradeDeTabela(master, tabela, self._criar_celula,
                             ao_mudar=lambda estrutural=False, t=tabela: self._mudou_objeto(t.id, estrutural),
                             ao_sair=lambda direcao, t=tabela: self._sair_da_tabela(t.id, direcao),
                             ao_ativar=self._ativar_objeto, largura_px=contexto.largura_maxima_px)

    def _criar_celula(self, master: tk.Misc, blocos: Sequence[Paragrafo]) -> "TextoRico":
        celula = TextoRico(master, celula=True, dono=self, estilos=self.estilos, fontes=self.fontes,
                           historico=Historico(relogio=self.relogio), relogio=self.relogio, arquivo=self.arquivo,
                           ao_ativar=self.ao_ativar)
        celula.carregar_blocos(blocos)
        return celula

    def _mudou_objeto(self, bloco_id: str, estrutural: bool = False) -> None:
        """
        Uma célula da tabela mudou: o bloco da tabela é relido pelo registro e o ponto é
        sobre ela inteira — a digitação coalesce e é reconciliada com atraso (uma tabela de
        400 células custa dezenas de ms por releitura; o `sincronizar` de quem precisar
        antes disso a inclui, porque o id já está em `_tocados`); uma fila ou coluna a mais
        é ponto próprio, na hora.
        """
        if self._em_carga or bloco_id not in self._ordem:
            return
        self._tocados.add(bloco_id)
        if estrutural or self._composto:
            self._reconciliar(coalescer=False, rotulo="tabela")
            return
        if self._reconciliacao_agendada is None:
            try:
                self._reconciliacao_agendada = self.after(ATRASO_DA_CELULA_MS, self._reconciliar_agendada)
            except tk.TclError:
                self._reconciliar(coalescer=True, rotulo="tabela")

    def _reconciliar_agendada(self) -> None:
        self._reconciliacao_agendada = None
        if self._tocados:
            self._reconciliar(coalescer=True, rotulo="tabela")

    def _sair_da_tabela(self, bloco_id: str, direcao: int) -> None:
        """`Esc` e as setas nas bordas: o cursor sai para o texto de fora (§8.6)."""
        if bloco_id not in self._ordem:
            return
        if direcao < 0:
            i = self._ordem.index(bloco_id)
            if i > 0:
                self.texto.mark_set("insert", f"{self._fim_de(self._ordem[i - 1])}-1c")
            else:
                self.texto.mark_set("insert", self._inicio_de(bloco_id))
        elif direcao > 0:
            seguinte = self._seguinte(bloco_id)
            if seguinte is None or seguinte == ID_DA_FAIXA:
                novo = Paragrafo(trechos=[])
                self._desenhar_bloco(novo, self._fim_de(bloco_id), seguinte)
                self.texto.mark_set("insert", self._inicio_de(novo.id))
                self._reconciliar({novo.id})
            else:
                self.texto.mark_set("insert", self._inicio_de(seguinte))
        else:
            self.texto.mark_set("insert", self._inicio_de(bloco_id))
        self.texto.tag_remove("sel", "1.0", "end")
        self.foco()
        self.texto.see("insert")

    def _inserir_objeto(self, objeto: Any, ptags: tuple[str, ...], inline: bool = False) -> str:
        contexto = self._contexto_de_objetos()
        janela = criar_objeto(self.texto, objeto, inline=inline, ao_ativar=self._ativar_objeto, contexto=contexto)
        e_grade = isinstance(janela, GradeDeTabela)
        self.texto.window_create(MARCA_DE_INSERCAO, window=janela, align="baseline" if inline else "bottom",
                                 padx=2 if inline else 0, pady=0 if inline else 2)
        nome = str(janela)
        self.registro.registrar(nome, objeto, widget=janela, atualizar=janela.modelo if e_grade else None)
        inicio = self.texto.index(nome)
        for tag in ptags + ("objeto", "protegido"):
            self._garantir_tag(tag)
            self.texto.tag_add(tag, inicio, f"{inicio}+1c")
        return nome

    def _ativar_objeto(self, objeto: Any) -> None:
        """A ação principal de um objeto (§7.4): quem sabe o que fazer é a janela (`ao_ativar`)."""
        raiz = self._raiz()
        if raiz.ao_ativar is not None:
            raiz.ao_ativar(objeto)
        try:
            self.texto.event_generate("<<AtivarObjeto>>")
        except tk.TclError:
            pass

    def widget_do_objeto(self, bloco_id: str) -> Any:
        nome = self.registro.nome_de(bloco_id)
        return self.registro.widget_de(nome) if nome else None

    def _desenhar_bloco(self, bloco: Bloco, indice: str, antes_de: str | None = None, *,
                        extras: tuple[str, ...] = (), marcador: str = "", tag_do_marcador: str = "") -> None:
        """
        Desenha `bloco` em `indice`. Com `antes_de`, o bloco seguinte é esse: a marca dele
        é reposta no fim do que entrou (ver o cabeçalho). `extras` são tags de parágrafo a
        mais (o `dn:` da nota); `marcador` é um prefixo protegido (o número da nota). Não
        registra ponto.
        """
        texto = self.texto
        inicio = texto.index(indice)
        texto.mark_set(MARCA_DE_INSERCAO, inicio)
        texto.mark_gravity(MARCA_DE_INSERCAO, "right")
        ptags = self._ptags_de(bloco) + tuple(extras)
        if marcador:
            estilo_do_marcador = bloco.estilo if isinstance(bloco, Paragrafo) else "corpo"
            self._inserir_segmento(marcador, ptags, (), estilo_do_marcador,
                                   ("marcador", "protegido") + ((tag_do_marcador,) if tag_do_marcador else ()))
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
        blocos = [self._modelo[i] for i in self._ids_do_capitulo() if i in self._modelo]
        if self._capitulo is None:
            return blocos
        c = self._capitulo
        return Capitulo(arquivo=c.arquivo, titulo=c.titulo, blocos=blocos, notas=self.notas_atuais(),
                        folhas=list(c.folhas), idioma=c.idioma, semantica=c.semantica, cabeca_extra=c.cabeca_extra,
                        avisos=list(c.avisos), namespaces=dict(c.namespaces), linear=c.linear)

    def _blocos_do_dump(self, ids: Iterable[str]) -> dict[str, Bloco]:
        """Relê pelo `dump` só os blocos `ids`, com os anteriores por base (um `dump` só quando são muitos)."""
        saida: dict[str, Bloco] = {}
        registro = self.registro
        ids = list(ids)
        if len(ids) > 8 and len(ids) * 2 > len(self._ordem):
            pedidos = set(ids)
            itens = self._dump("1.0", "end-1c")
            blocos, notas = dump_mod.dump_para_blocos(itens, registro, self._modelo)
            saida = {b.id: b for b in blocos if b.id in pedidos}
            for nota in notas:
                for paragrafo in nota.blocos:
                    if paragrafo.id in pedidos:
                        saida[paragrafo.id] = paragrafo
            return saida
        for bloco_id in ids:
            if bloco_id not in self._ordem:
                continue
            ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
            marca = self._marca(bloco_id)
            itens = [("mark", marca, ini)] + [it for it in self._dump(ini, fim) if it[0] != "mark"]
            blocos, notas = dump_mod.dump_para_blocos(itens, registro, self._modelo)
            if blocos:
                saida[bloco_id] = blocos[0]
            elif notas and notas[0].blocos:
                saida[bloco_id] = notas[0].blocos[0]
        return saida

    def _reconciliar(self, ids: Iterable[str] | None = None, coalescer: bool | None = None,
                     rotulo: str = "", reaplicar: bool = True, registrar: bool = True) -> None:
        """
        Reaplica tags e fontes nos blocos tocados, relê o modelo deles e registra o ponto
        de desfazer. Um parágrafo da faixa de notas entra no ponto como a **nota** inteira.
        Dentro de um ponto composto (`_abrir_composto`), só acumula os ids.
        """
        if self._reconciliando:
            return
        if self._reconciliacao_agendada is not None:
            try:
                self.after_cancel(self._reconciliacao_agendada)
            except tk.TclError:
                pass
            self._reconciliacao_agendada = None
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
        de_nota = {i: self._nota_do_paragrafo(i) for i in ids}
        ids_do_capitulo = [i for i in ids if not de_nota[i] and i != ID_DA_FAIXA]
        notas_tocadas = list(dict.fromkeys(n for i in sorted(ids, key=self._posicao_para_ordenar)
                                           if (n := de_nota[i])))
        antes = [self._antes_forcado.pop(i, None) or self._modelo[i]
                 for i in sorted(ids_do_capitulo, key=self._posicao_para_ordenar) if i in self._modelo]
        for i in ids:
            self._antes_forcado.pop(i, None)
        antes += [copy.deepcopy(n) for n in (self._nota_cache(nid) for nid in notas_tocadas) if n is not None]
        indices = {i: self._posicoes_antigas.get(i, self._ordem.index(i) if i in self._ordem else 0)
                   for i in ids_do_capitulo}
        indices.update({nid: k for k, n in enumerate(self._notas) for nid in notas_tocadas if n.id == nid})
        for bloco_id, bloco in novos.items():
            self._modelo[bloco_id] = bloco
        for bloco_id in sumidos:
            self._modelo.pop(bloco_id, None)
            self._ptags.pop(bloco_id, None)
        depois = [novos[i] for i in vivos if i in novos and not de_nota[i]]
        for nid in notas_tocadas:
            montada = self._montar_nota(nid)
            cache = self._nota_cache(nid)
            if montada is not None:
                depois.append(montada)
                if cache is None:
                    self._notas.append(montada)
                else:
                    self._notas[self._notas.index(cache)] = montada
            elif cache is not None:
                self._notas.remove(cache)
        ids_do_ponto = sorted(ids_do_capitulo, key=self._posicao_para_ordenar) + notas_tocadas
        if self._composto:
            self._ids_compostos.update(ids_do_ponto)
        elif registrar and not self._em_carga and not self._em_desfazer:
            coalescer = self._simples if coalescer is None else coalescer
            self._registrar_ponto(ids_do_ponto, antes, depois, indices, coalescer, rotulo)
        self._simples = False
        self.calha.redesenhar()
        if self.celula:
            self.ajustar_altura()

    def _registrar_ponto(self, ids: Sequence[str], antes: list[Any], depois: list[Any], indices: dict[str, int],
                         coalescer: bool = False, rotulo: str = "") -> bool:
        """Um ponto no histórico, se algo mudou; avisa `<<Mudou>>`. Devolve se registrou."""
        if antes == depois or modelo.igual(antes, depois):      # `==` é o atalho barato para o "nada mudou"
            return False
        self.historico.ponto(self.arquivo, list(ids), antes, depois, coalescer=coalescer, rotulo=rotulo,
                             indices=indices)
        self._sujo = True
        try:
            self.texto.event_generate("<<Mudou>>")
        except tk.TclError:
            pass
        return True

    # -- pontos compostos: várias edições, um desfazer --------------------------

    def _abrir_composto(self, rotulo: str = "") -> None:
        """Até `_fechar_composto`, as reconciliações só acumulam ids; o ponto sai no fim, inteiro."""
        if self._composto == 0:
            self._reconciliar()
            self._ids_compostos = set()
            self._modelo_antes = dict(self._modelo)
            self._notas_antes = [copy.deepcopy(n) for n in self._notas]
            self._posicoes_do_composto = {i: k for k, i in enumerate(self._ordem)}
            self._rotulo_composto = rotulo
        self._composto += 1

    def _fechar_composto(self) -> None:
        self._composto -= 1
        if self._composto > 0:
            return
        self._reconciliar()
        ids = set(self._ids_compostos)
        self._ids_compostos = set()
        if not ids or self._em_carga or self._em_desfazer:
            return
        notas_antes = {n.id: n for n in self._notas_antes}
        notas_depois = {n.id: n for n in self._notas}
        ids_de_nota = [i for i in ids if i in notas_antes or i in notas_depois]
        ids_de_bloco = sorted((i for i in ids if i not in ids_de_nota),
                              key=lambda i: self._posicoes_do_composto.get(i, self._posicao_para_ordenar(i)))
        antes = [self._modelo_antes[i] for i in ids_de_bloco if i in self._modelo_antes]
        antes += [notas_antes[i] for i in ids_de_nota if i in notas_antes]
        depois = [self._modelo[i] for i in ids_de_bloco if i in self._modelo and i in self._ordem]
        depois += [notas_depois[i] for i in ids_de_nota if i in notas_depois]
        indices = {i: self._posicoes_do_composto.get(i, self._posicao_para_ordenar(i)) for i in ids_de_bloco}
        indices.update({i: k for k, n in enumerate(self._notas_antes) for i in ids_de_nota if n.id == i})
        self._registrar_ponto(ids_de_bloco + ids_de_nota, antes, depois, indices, False, self._rotulo_composto)
        self._modelo_antes = {}
        self._notas_antes = []

    def _posicao_para_ordenar(self, bloco_id: str) -> int:
        if bloco_id in self._ordem:
            return self._ordem.index(bloco_id)
        return self._posicoes_antigas.get(bloco_id, len(self._ordem))

    def _vazio(self, bloco_id: str) -> bool:
        return self.texto.compare(self._inicio_de(bloco_id), ">=", self._fim_de(bloco_id))

    def _remover_bloco(self, bloco_id: str) -> None:
        """Tira o bloco da ordem e do registro (o texto dele é apagado por quem chama)."""
        if bloco_id in self._ordem:
            self._posicoes_antigas[bloco_id] = len(self._ids_do_capitulo()) if self._nota_do_paragrafo(bloco_id) \
                else self._ordem.index(bloco_id)
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

    def _e_referencia_de_nota(self, indice: str) -> str:
        """O id da nota se o caractere em `indice` é uma referência de nota; senão ""."""
        return next((T.valor(t) for t in self.texto.tag_names(indice) if t.startswith("nota:")), "")

    def _sobre_objeto(self, indice: str = "insert") -> str | None:
        """O id do bloco-objeto quando o cursor está **sobre** a janela dele (antes dela), senão `None`."""
        indice = self.texto.index(indice)
        if "objeto" not in self.texto.tag_names(indice):
            return None
        bloco_id = self._bloco_em(indice)
        bloco = self._modelo.get(bloco_id) if bloco_id else None
        return bloco_id if isinstance(bloco, TIPOS_DE_OBJETO) else None

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
        return self.posicao_de("insert")

    def posicao_de(self, indice: str) -> tuple[str | None, int]:
        """`(id do bloco, deslocamento no texto do modelo)` de qualquer índice do widget (a busca, ED-06)."""
        bloco_id = self._bloco_em(indice)
        if bloco_id is None:
            return None, 0
        return bloco_id, self._deslocamento(indice, bloco_id)

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
        self._deselecionar_objetos()
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
        """Todo o capítulo — sem a faixa de notas, como o Ctrl+A do Word não pega as notas."""
        fim = self._inicio_de(ID_DA_FAIXA) if self._tem_faixa() else "end-1c"
        self.selecionar_indices("1.0", fim)

    def selecionar_objeto(self, bloco_id: str) -> None:
        """Seleciona o bloco-objeto inteiro e o realça no desenho dele (`sel-objeto`)."""
        self.selecionar_indices(self._inicio_de(bloco_id), self._fim_de(bloco_id))
        self.texto.mark_set("insert", self._inicio_de(bloco_id))
        widget = self.widget_do_objeto(bloco_id)
        if widget is not None and hasattr(widget, "selecionar"):
            widget.selecionar(True)
            self._objeto_selecionado = bloco_id

    def _deselecionar_objetos(self) -> None:
        if self._objeto_selecionado is not None:
            widget = self.widget_do_objeto(self._objeto_selecionado)
            if widget is not None and hasattr(widget, "selecionar"):
                try:
                    widget.selecionar(False)
                except tk.TclError:
                    pass
            self._objeto_selecionado = None

    def _objeto_da_selecao(self) -> str | None:
        """O id do objeto quando a seleção é exatamente o bloco dele."""
        selecao = self.selecao()
        if not selecao:
            return None
        ini, fim = selecao
        bloco_id = self._bloco_em(ini)
        if bloco_id and isinstance(self._modelo.get(bloco_id), TIPOS_DE_OBJETO) \
                and self.texto.compare(ini, "==", self._inicio_de(bloco_id)) \
                and self.texto.compare(fim, "<=", self._fim_de(bloco_id)) \
                and self.texto.compare(fim, ">", ini):
            return bloco_id
        return None

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

    def _dentro_do_texto(self, indice: str) -> str:
        """Um índice depois do `\n` terminal do último bloco volta para antes dele (nada fica fora de bloco)."""
        if self._ordem and self.texto.compare(indice, ">=", "end-1c"):
            return self.texto.index("end-2c")
        return indice

    def ir_para_o_fim(self) -> None:
        """O cursor no fim do último bloco (antes do `\n` terminal); num widget vazio, em `1.0`."""
        if self._ordem:
            self.texto.mark_set("insert", f"{self._fim_de(self._ordem[-1])}-1c")
        else:
            self.texto.mark_set("insert", "1.0")

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
            if tag.startswith(NAO_SE_ESTENDEM) and tag not in seguinte:
                continue           # o link, o NAG, a figurina… não se estendem ao que se digita depois deles
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
        indice = self._dentro_do_texto(self.texto.index(indice or "insert"))
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
                if self.ao_fechar_token is not None and len(parte) == 1 and parte in SEPARADORES_DE_TOKEN:
                    self._fechou_token()
        return True

    def _fechou_token(self) -> None:
        """Um separador acabou de entrar: o gancho (figurinas ao digitar) vê o token que ficou antes dele."""
        bloco_id, desloc = self.posicao()
        if bloco_id is None or desloc <= 1 or self.ao_fechar_token is None:
            return
        try:
            self.ao_fechar_token(bloco_id, desloc - 1)
        except Exception:      # noqa: BLE001 — um gancho que falha não pode travar a digitação
            pass

    def inserir_formatado(self, texto: str, **atributos: Any) -> bool:
        """Insere `texto` já com os atributos de trecho (`papel`, `nag`, `familia`, `ref`, `link`…)."""
        if self.selecao():
            self.apagar_selecao()
        self._pendente = dict(atributos)
        self._pendente_em = self.texto.index("insert")
        try:
            return self.inserir(texto)
        finally:
            self._pendente = {}

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
        if not isinstance(objeto, TIPOS_DE_OBJETO) or isinstance(objeto, FaixaDeNotas):
            raise ValueError(f"não é um objeto: {type(objeto).__name__}")
        if self.celula:
            raise ValueError("uma célula de tabela não recebe figura, tabela nem ilha de bloco (sem aninhar, §8.6)")
        if isinstance(objeto, Tabela) and len(objeto.filas) * objeto.colunas > LIMITE_DE_CELULAS:
            raise ValueError(f"a tabela teria {len(objeto.filas) * objeto.colunas} células; o máximo é "
                             f"{LIMITE_DE_CELULAS} (§8.6)")
        if objeto.id in self._ordem:
            objeto.id = modelo.id_novo()
        atual = self.bloco_atual()
        if self.em_nota():
            raise ValueError("uma nota não recebe objeto de bloco: o cursor está na faixa de notas (Esc sai)")
        if atual is None or (atual == ID_DA_FAIXA and not self._ids_do_capitulo()):
            self._desenhar_bloco(objeto, "1.0" if self._tem_faixa() else "end-1c",
                                 ID_DA_FAIXA if self._tem_faixa() else None)
        elif atual == ID_DA_FAIXA:
            anterior = self._ids_do_capitulo()[-1]
            self._desenhar_bloco(objeto, self._fim_de(anterior), ID_DA_FAIXA)
        else:
            self._desenhar_bloco(objeto, self._fim_de(atual), self._seguinte(atual))
        self._tocados.discard(objeto.id)
        self._modelo.pop(objeto.id, None)          # "antes" vazio: o ponto de desfazer é a inserção
        self._simples = False
        self._reconciliar({objeto.id})
        self.texto.mark_set("insert", self._inicio_de(objeto.id))
        return objeto.id

    def inserir_bloco_no_cursor(self, bloco: Bloco) -> str:
        """
        Um bloco **no cursor**: no meio de um parágrafo, o parágrafo é partido e o bloco
        entra entre as metades (a quebra de página do `Ctrl+Enter`); no começo, entra
        antes; no fim ou num objeto, depois. Devolve o id do bloco; um desfazer só.
        """
        atual = self.bloco_atual()
        modelo_atual = self._modelo.get(atual) if atual else None
        if atual is None or not isinstance(modelo_atual, Paragrafo) or isinstance(modelo_atual, TIPOS_DE_OBJETO) \
                or self.em_nota():
            return self.inserir_objeto(bloco)
        desloc = self._deslocamento("insert", atual)
        comprimento = len(modelo.texto_de(modelo_atual))
        self._abrir_composto("inserir")
        try:
            if desloc == 0 and comprimento > 0:
                if bloco.id in self._ordem:
                    bloco.id = modelo.id_novo()
                self._desenhar_bloco(bloco, self._inicio_de(atual), atual)
                self._modelo.pop(bloco.id, None)
                self._reconciliar({bloco.id})
            else:
                if 0 < desloc < comprimento:
                    self.enter()
                    self.texto.mark_set("insert", f"{self._fim_de(atual)}-1c")
                self.inserir_objeto(bloco)
        finally:
            self._fechar_composto()
        self.texto.mark_set("insert", self._inicio_de(bloco.id))
        return bloco.id

    # ------------------------------------------------------------------
    # Quebras, separador, marca de página (§8.10)
    # ------------------------------------------------------------------

    def inserir_quebra_suave(self) -> bool:
        """`Shift+Enter`: um `\\n` com `qs` — `quebra_antes` no trecho seguinte."""
        if self.selecao():
            self.apagar_selecao()
        if not self._ids_do_capitulo():
            self.inserir("")
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        bloco = self._modelo.get(bloco_id) if bloco_id else None
        if bloco_id is None or isinstance(bloco, TIPOS_DE_OBJETO) or not self._pode_editar(indice):
            return False
        while "marcador" in self.texto.tag_names(indice):
            indice = self.texto.index(f"{indice}+1c")
        ptags, _c, estilo = self._tags_para_inserir(indice)
        self.texto.mark_set(MARCA_DE_INSERCAO, indice)
        self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
        self._inserir_segmento("\n", ptags, (), estilo, ("qs", "quebra", "protegido"))
        self.texto.mark_set("insert", MARCA_DE_INSERCAO)
        self.texto.mark_unset(MARCA_DE_INSERCAO)
        self._simples = False
        self._reconciliar({bloco_id})
        return True

    def inserir_quebra_de_pagina(self) -> str:
        """`Ctrl+Enter`: uma `QuebraDePagina` no cursor (parte o parágrafo); desenhada "— quebra de página —"."""
        if self.celula:
            raise ValueError("uma célula de tabela não recebe quebra de página")
        return self.inserir_bloco_no_cursor(QuebraDePagina())

    def inserir_separador(self) -> str:
        return self.inserir_bloco_no_cursor(Separador())

    def inserir_marca_de_pagina(self, pagina: int) -> str:
        return self.inserir_bloco_no_cursor(MarcaDePagina(pagina=int(pagina)))

    # ------------------------------------------------------------------
    # Notas (§8.8)
    # ------------------------------------------------------------------

    def inserir_nota(self, tipo: str = "rodape") -> str:
        """
        Uma nota nova: a referência protegida no cursor, a nota (um parágrafo vazio) na
        faixa, o cursor na nota (`Esc` volta). Devolve o id da nota. Numa célula, a nota
        vai para o capítulo de fora.
        """
        if tipo not in TIPOS_DE_NOTA:
            raise ValueError(f"tipo de nota desconhecido: {tipo!r} (rodape ou fim)")
        if self.selecao():
            self.apagar_selecao()
        if not self._ids_do_capitulo():
            self.inserir("")
        indice = self.texto.index("insert")
        if self.em_nota():
            raise ValueError("uma nota não recebe outra nota: saia da faixa de notas (Esc)")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None or isinstance(self._modelo.get(bloco_id), TIPOS_DE_OBJETO) \
                or not self._pode_editar(indice):
            raise ValueError("o cursor precisa estar num parágrafo para receber a referência da nota")
        while "marcador" in self.texto.tag_names(indice):
            indice = self.texto.index(f"{indice}+1c")
        raiz = self._raiz()
        nota = Nota(tipo=tipo, blocos=[Paragrafo(trechos=[], estilo="nota")])
        raiz._abrir_composto("nota")
        if raiz is not self:
            self._abrir_composto("nota")
        try:
            raiz._criar_nota(nota)
            ptags, _c, estilo = self._tags_para_inserir(indice)
            self.texto.mark_set(MARCA_DE_INSERCAO, indice)
            self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
            self._inserir_segmento(self._glifo_da_nota(nota.id), ptags, (), estilo,
                                   (T.nome("nota:", nota.id), "protegido"))
            self.texto.mark_set("insert", MARCA_DE_INSERCAO)
            self.texto.mark_unset(MARCA_DE_INSERCAO)
            self._simples = False
            self._reconciliar({bloco_id})
            raiz._renumerar()
        finally:
            if raiz is not self:
                self._fechar_composto()
            raiz._fechar_composto()
        raiz.ir_para_nota(nota.id)
        return nota.id

    def _criar_nota(self, nota: Nota) -> None:
        """Põe a nota na faixa (rodapé depois do último rodapé; fim no fim) e na lista de notas."""
        assert not self.celula and self._composto > 0      # o ponto é o composto de quem chamou
        if nota.tipo == "rodape":
            posicao = max((k for k, n in enumerate(self._notas) if n.tipo == "rodape"), default=-1) + 1
        else:
            posicao = len(self._notas)
        self._desenhar_faixa()
        seguinte = self._notas[posicao].id if posicao < len(self._notas) else None
        antes_de = self._paragrafos_da_nota(seguinte)[0] if seguinte and self._paragrafos_da_nota(seguinte) else None
        self._desenhar_nota(nota, antes_de)
        self._notas.insert(posicao, copy.deepcopy(nota))
        self._tocados.update(self._paragrafos_da_nota(nota.id))
        self._reconciliar()
        self._renumerar_na_tela()

    def _renumerar(self) -> None:
        """
        A ordem das notas pela primeira referência (rodapé antes de fim), como
        `modelo.renumerar_notas`; se a ordem mudou, a faixa é redesenhada; os números
        na tela são refeitos sempre.
        """
        if self.celula:
            self._raiz()._renumerar()
            return
        self._reconciliar()
        if not self._notas:
            return
        cap = Capitulo(arquivo=self.arquivo, blocos=[self._modelo[i] for i in self._ids_do_capitulo()
                                                    if i in self._modelo], notas=list(self._notas))
        modelo.renumerar_notas(cap)
        nova_ordem = [n.id for n in cap.notas]
        if nova_ordem != [n.id for n in self._notas]:
            self._notas = [self._nota_cache(i) for i in nova_ordem if self._nota_cache(i) is not None]
            self._redesenhar_faixa()
        self._renumerar_na_tela()

    def _redesenhar_faixa(self) -> None:
        """A faixa de notas de novo, na ordem de `_notas`, sem ponto (o modelo não muda)."""
        if not self._tem_faixa():
            return
        posicao = self.posicao()
        notas = [self._montar_nota(n.id) or n for n in self._notas]
        self._em_carga = True
        try:
            inicio = self._inicio_de(ID_DA_FAIXA)
            for bloco_id in [i for i in self._ordem if i == ID_DA_FAIXA or self._nota_do_paragrafo(i)]:
                self._remover_bloco(bloco_id)
                self._modelo.pop(bloco_id, None)
                self._ptags.pop(bloco_id, None)
            # Até `end-1c`, não `end`: apagar da cabeça de uma linha até `end` leva junto a quebra
            # de linha da linha anterior (é como o Tk evita uma última linha vazia).
            self.texto.delete(inicio, "end-1c")
            self._desenhar_faixa()
            for nota in notas:
                self._desenhar_nota(nota)
        finally:
            self._em_carga = False
        self._tocados.clear()
        if posicao[0] and posicao[0] in self._ordem:
            self.ir_para(posicao[0], posicao[1])

    def _renumerar_na_tela(self) -> None:
        """Os glifos das referências e os números dos marcadores da faixa, sem tocar o modelo."""
        raiz = self._raiz()
        alvos: list[TextoRico] = [self]
        for nome in self.registro.nomes():
            widget = self.registro.widget_de(nome)
            if isinstance(widget, GradeDeTabela):
                alvos.extend(c for fila in widget.celulas for c in fila)
        for alvo in alvos:
            texto = alvo.texto
            alvo._em_carga = True
            try:
                for tag in texto.tag_names():
                    if tag.startswith("nota:"):
                        glifo = raiz._glifo_da_nota(T.valor(tag))
                        faixas = texto.tag_ranges(tag)
                        for a, b in zip(faixas[::2], faixas[1::2]):
                            if texto.get(a, b) != glifo:
                                tags = texto.tag_names(a)
                                texto.delete(a, b)
                                texto.insert(a, glifo, tags)
                    elif tag.startswith("ncab:"):
                        numero = f"{raiz._glifo_da_nota(T.valor(tag))} "
                        faixas = texto.tag_ranges(tag)
                        for a, b in zip(faixas[::2], faixas[1::2]):
                            if texto.get(a, b) != numero:
                                tags = texto.tag_names(a)
                                texto.delete(a, b)
                                texto.insert(a, numero, tags)
            finally:
                alvo._em_carga = False

    def ir_para_nota(self, nota_id: str) -> bool:
        """O cursor no começo do texto da nota (e a origem guardada para `voltar_da_nota`)."""
        raiz = self._raiz()
        ids = raiz._paragrafos_da_nota(nota_id)
        if not ids:
            return False
        raiz.ir_para(ids[0], 0)
        raiz.foco()
        return True

    def voltar_da_nota(self) -> bool:
        """`Esc` na faixa: o cursor volta para depois da referência da nota em que está."""
        nota_id = self.em_nota()
        if nota_id is None:
            return False
        referencias = self._referencias_de(nota_id)
        if referencias:
            widget, indice = referencias[0]
            widget.texto.tag_remove("sel", "1.0", "end")
            widget.texto.mark_set("insert", f"{indice}+1c")
            widget.texto.see("insert")
            widget.foco()
            return True
        primeiro = self._ids_do_capitulo()
        if primeiro:
            self.ir_para(primeiro[0], 0)
        return bool(primeiro)

    def nota_no_cursor(self) -> str | None:
        """O id da nota cuja referência está sob o cursor (antes ou depois dele)."""
        indice = self.texto.index("insert")
        nota = self._e_referencia_de_nota(indice)
        if not nota and self.texto.compare(indice, ">", "1.0"):
            nota = self._e_referencia_de_nota(f"{indice}-1c")
        return nota or None

    def apagar_nota(self, nota_id: str) -> bool:
        """Apaga a nota e toda referência a ela (um desfazer só); renumera."""
        raiz = self._raiz()
        if raiz is not self:
            return raiz.apagar_nota(nota_id)
        if self._nota_cache(nota_id) is None and not self._referencias_de(nota_id):
            return False
        tag = T.nome("nota:", nota_id)
        self._abrir_composto("apagar nota")
        try:
            faixas = self.texto.tag_ranges(tag)
            for a, b in reversed(list(zip(faixas[::2], faixas[1::2]))):
                self.texto.delete(a, b)
            for nome in self.registro.nomes():
                widget = self.registro.widget_de(nome)
                if isinstance(widget, GradeDeTabela):
                    for fila in widget.celulas:
                        for celula in fila:
                            f = celula.texto.tag_ranges(tag)
                            for a, b in reversed(list(zip(f[::2], f[1::2]))):
                                celula.texto.delete(a, b)
                            celula._reconciliar()
            self._reconciliar()
            self._apagar_paragrafos_da_nota(nota_id)
            self._reconciliar()
            self._renumerar()
        finally:
            self._fechar_composto()
        return True

    def mudar_tipo_da_nota(self, nota_id: str, tipo: str) -> bool:
        """Rodapé ↔ fim: a tag `dn:` dos parágrafos muda, a faixa é reordenada e renumerada."""
        if tipo not in TIPOS_DE_NOTA:
            raise ValueError(f"tipo de nota desconhecido: {tipo!r}")
        raiz = self._raiz()
        if raiz is not self:
            return raiz.mudar_tipo_da_nota(nota_id, tipo)
        ids = self._paragrafos_da_nota(nota_id)
        cache = self._nota_cache(nota_id)
        if not ids or cache is None or cache.tipo == tipo:
            return False
        nova = T.nome("dn:", f"{nota_id}|{tipo}")
        self._abrir_composto("tipo da nota")
        try:
            for pid in ids:
                self._ptags[pid] = tuple(t for t in self._ptags[pid] if not t.startswith("dn:")) + (nova,)
                self._tocados.add(pid)
            self._reconciliar(ids, coalescer=False)
            self._renumerar()
        finally:
            self._fechar_composto()
        return True

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

    def apagar_bloco(self, bloco_id: str) -> bool:
        """Apaga um bloco inteiro pela API (respeita `protegido`); é o que "Cabeçalho em legenda" usa (ED-05)."""
        if bloco_id not in self._ordem:
            return False
        return self.apagar(self._inicio_de(bloco_id), self._fim_de(bloco_id))

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
        if self._ids_do_capitulo():
            return
        self._em_carga = True
        try:
            novo = Paragrafo(trechos=[])
            if self._tem_faixa():
                self.texto.delete("1.0", self._inicio_de(ID_DA_FAIXA))
                self._desenhar_bloco(novo, "1.0", ID_DA_FAIXA)
            else:
                self.texto.delete("1.0", "end")
                self._desenhar_bloco(novo, "end-1c")
        finally:
            self._em_carga = False
        self.texto.mark_set("insert", self._inicio_de(novo.id))
        tocados.add(novo.id)

    def _garantir_notas(self, tocados: set[str]) -> None:
        """Uma nota cujos parágrafos foram todos apagados na faixa fica com um parágrafo vazio."""
        for nota in list(self._notas):
            if self._paragrafos_da_nota(nota.id):
                continue
            seguinte = next((i for i in self._ordem[self._ordem.index(ID_DA_FAIXA) + 1:]
                             if self._numero_da_nota(self._nota_do_paragrafo(i) or "") > self._numero_da_nota(nota.id)),
                            None) if self._tem_faixa() else None
            vazia = Nota(id=nota.id, tipo=nota.tipo, blocos=[Paragrafo(trechos=[], estilo="nota")])
            self._em_carga = True
            try:
                if not self._tem_faixa():
                    self._desenhar_faixa()
                self._desenhar_nota(vazia, seguinte)
            finally:
                self._em_carga = False
            tocados.update(self._paragrafos_da_nota(nota.id))

    def apagar_selecao(self) -> bool:
        """
        Apaga a seleção: um objeto selecionado inteiro sai com desfazer; texto, pela
        guarda; uma referência de nota selecionada sai — e leva a nota, se era a última
        referência dela (§8.8). A faixa de notas nunca sai: a seleção pára antes dela.
        """
        selecao = self.selecao()
        if not selecao:
            return False
        ini, fim = selecao
        self._deselecionar_objetos()
        self.texto.tag_remove("sel", "1.0", "end")
        if self._tem_faixa() and self.texto.compare(ini, "<", self._inicio_de(ID_DA_FAIXA)) \
                and self.texto.compare(fim, ">", self._inicio_de(ID_DA_FAIXA)):
            fim = self._inicio_de(ID_DA_FAIXA)
            if self.texto.compare(ini, ">=", fim):
                return False
        blocos = self._blocos_entre(ini, fim)
        if self.texto.compare(self._inicio_de(blocos[-1]), ">=", fim) and len(blocos) > 1:
            blocos = blocos[:-1]          # a seleção termina exatamente onde o último começa
        if ID_DA_FAIXA in blocos:
            return False
        referencias = self._referencias_entre(ini, fim)
        raiz = self._raiz()
        if raiz is not self:
            raiz._abrir_composto("apagar")
        self._abrir_composto("apagar")
        try:
            apagou = self._apagar_intervalo(ini, fim, blocos)
            if apagou and referencias:
                for nota_id in referencias:
                    if not raiz._referencias_de(nota_id):
                        raiz._apagar_paragrafos_da_nota(nota_id)
                raiz._renumerar()
        finally:
            self._fechar_composto()
            if raiz is not self:
                raiz._fechar_composto()
        return apagou

    def _apagar_intervalo(self, ini: str, fim: str, blocos: list[str]) -> bool:
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
            self._garantir_notas(tocados)
            self._reconciliar(tocados)
            return True
        if not self._pode_editar_selecao(ini, fim, inteiros):
            return False
        if len(blocos) > 1:
            return self._apagar_entre_blocos(ini, fim, blocos)
        return self._apagar_com_referencias(ini, fim)

    def _apagar_com_referencias(self, ini: str, fim: str) -> bool:
        """`apagar` dentro de um bloco, aceitando referências de nota no intervalo."""
        ini, fim = self.texto.index(ini), self.texto.index(fim)
        if self.texto.compare(ini, ">=", fim) or not self._pode_editar_selecao(ini, fim, []):
            return False
        self._simples = False
        self.texto.delete(ini, fim)
        self.texto.mark_set("insert", ini)
        self._reconciliar()
        return True

    def _pode_editar_selecao(self, ini: str, fim: str, inteiros: list[str]) -> bool:
        """
        Numa seleção, o protegido só é aceitável dentro de blocos inteiros — ou quando é
        uma referência de nota ou uma ilha inline (um caractere-objeto, que se apaga).
        """
        texto = self.texto
        i, fim = texto.index(ini), texto.index(fim)
        while texto.compare(i, "<", fim):
            tags = texto.tag_names(i)
            if "protegido" in tags and not any(T.e_quebra(t) for t in tags) and "invisivel" not in tags \
                    and not any(t.startswith("nota:") for t in tags) and not self._e_ilha_inline(i):
                if self._bloco_em(i) not in inteiros:
                    return False
            i = texto.index(f"{i}+1c")
        return True

    def _e_ilha_inline(self, indice: str) -> bool:
        if "objeto" not in self.texto.tag_names(indice):
            return False
        bloco_id = self._bloco_em(indice)
        return bloco_id is not None and not isinstance(self._modelo.get(bloco_id), TIPOS_DE_OBJETO)

    def _referencias_entre(self, ini: str, fim: str) -> list[str]:
        """Os ids das notas referenciadas em `[ini, fim)`, na ordem, sem repetir."""
        texto = self.texto
        saida: list[str] = []
        i, fim = texto.index(ini), texto.index(fim)
        while texto.compare(i, "<", fim):
            nota = self._e_referencia_de_nota(i)
            if nota and nota not in saida:
                saida.append(nota)
            i = texto.index(f"{i}+1c")
        return saida

    def _referencias_de(self, nota_id: str) -> list[tuple["TextoRico", str]]:
        """`(widget, índice)` de cada referência à nota, no texto de fora e nas células."""
        tag = T.nome("nota:", nota_id)
        saida = [(self, str(a)) for a in self.texto.tag_ranges(tag)[::2]]
        for nome in self.registro.nomes():
            widget = self.registro.widget_de(nome)
            if isinstance(widget, GradeDeTabela):
                for fila in widget.celulas:
                    for celula in fila:
                        saida.extend((celula, str(a)) for a in celula.texto.tag_ranges(tag)[::2])
        return saida

    def _apagar_paragrafos_da_nota(self, nota_id: str) -> None:
        for pid in self._paragrafos_da_nota(nota_id):
            self._apagar_bloco_sem_ponto(pid)
            self._tocados.add(pid)
        if self._tem_faixa() and not any(self._nota_do_paragrafo(i) for i in self._ordem):
            self._apagar_bloco_sem_ponto(ID_DA_FAIXA)

    def enter(self) -> bool:
        """
        Novo bloco no cursor (fora de lista e citação); item ou parágrafo interno dentro.
        Sobre um objeto, a ação principal (§7.4); sobre uma referência de nota, vai à
        nota; depois de um objeto (no `\\n` dele), abre um parágrafo a seguir.
        """
        if self.selecao():
            objeto = self._objeto_da_selecao()
            if objeto is not None:
                self._ativar_objeto(self._modelo[objeto])
                return True
            self.apagar_selecao()
        if not self._ids_do_capitulo():
            return self.inserir("")
        indice = self.texto.index("insert")
        nota = self._e_referencia_de_nota(indice) or (
            self._e_referencia_de_nota(f"{indice}-1c") if self.texto.compare(indice, ">", "1.0") else "")
        if nota and nota in self.ids_das_notas():
            self.ir_para_nota(nota)
            return True
        bloco_id = self._bloco_em(indice)
        bloco = self._modelo.get(bloco_id)
        if isinstance(bloco, TIPOS_DE_OBJETO):
            if self._sobre_objeto(indice) and not isinstance(bloco, FaixaDeNotas):
                self._ativar_objeto(bloco)
                return True
            seguinte = self._seguinte(bloco_id)
            if isinstance(bloco, FaixaDeNotas) and seguinte is not None:
                self.texto.mark_set("insert", self.indice_de(seguinte, 0) or self._inicio_de(seguinte))
                return True
            novo = Paragrafo(trechos=[])
            self._desenhar_bloco(novo, self._fim_de(bloco_id), seguinte)
            self.texto.mark_set("insert", self._inicio_de(novo.id))
            self._reconciliar({novo.id})
            return True
        while "marcador" in self.texto.tag_names(indice) and self.texto.compare(indice, "<", self._fim_de(bloco_id)):
            indice = self.texto.index(f"{indice}+1c")
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
        """
        Apaga para trás pela guarda; no começo do bloco, junta ao anterior; no item, desce
        de nível. Antes de um objeto ou de uma referência de nota, **seleciona** (o segundo
        `BackSpace` apaga, com desfazer) — é o que o Word faz.
        """
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
            if "objeto" in anterior or any(t.startswith("nota:") for t in anterior):
                self.selecionar_indices(f"{indice}-1c", indice)
                return False
            return False
        return self.apagar(f"{indice}-1c", indice)

    def _juntar_ao_anterior(self, bloco_id: str) -> bool:
        """
        `BackSpace` no começo do bloco. Antes de um objeto, seleciona-o; antes de uma marca
        de página, junta os parágrafos **através** dela (a página vira `Trecho.pagina`,
        INV-10); na faixa, só dentro da mesma nota.
        """
        i = self._ordem.index(bloco_id)
        if i == 0:
            return False
        anterior = self._ordem[i - 1]
        bloco_anterior, bloco = self._modelo.get(anterior), self._modelo.get(bloco_id)
        if self._nota_do_paragrafo(bloco_id) != self._nota_do_paragrafo(anterior):
            return False
        if isinstance(bloco_anterior, MarcaDePagina) and i >= 2 and isinstance(bloco, Paragrafo) \
                and isinstance(self._modelo.get(self._ordem[i - 2]), Paragrafo) \
                and not isinstance(self._modelo.get(self._ordem[i - 2]), TIPOS_DE_OBJETO):
            return self._juntar_atraves_da_marca(self._ordem[i - 2], anterior, bloco_id)
        if isinstance(bloco_anterior, TIPOS_DE_OBJETO):
            if not isinstance(bloco_anterior, FaixaDeNotas):
                self.selecionar_objeto(anterior)
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

    def _juntar_atraves_da_marca(self, a_id: str, marca_id: str, b_id: str) -> bool:
        """`juntar_paragrafos(a, b, marca)`: um parágrafo só, com a página do impresso no trecho (§8.10)."""
        a, b = self._modelo[a_id], self._modelo[b_id]
        marca = self._modelo[marca_id]
        assert isinstance(a, Paragrafo) and isinstance(b, Paragrafo) and isinstance(marca, MarcaDePagina)
        juntado = modelo.juntar_paragrafos(copy.deepcopy(a), b, marca)
        posicao = len(modelo.texto_de(a))
        self._abrir_composto("juntar")
        try:
            self._apagar_bloco_sem_ponto(b_id)
            self._tocados.add(b_id)
            self._apagar_bloco_sem_ponto(marca_id)
            self._tocados.add(marca_id)
            self._reescrever_bloco(a_id, juntado)
        finally:
            self._fechar_composto()
        self.ir_para(a_id, posicao)
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
    # Links, âncoras, ids (§8.9)
    # ------------------------------------------------------------------

    def _tag_no_cursor(self, prefixo: str) -> tuple[str, str] | None:
        """`(tag, índice)` da tag com este prefixo sob o cursor — no caractere seguinte, senão no anterior."""
        indice = self.texto.index("insert")
        for i in (indice, f"{indice}-1c"):
            if i != indice and not self.texto.compare(indice, ">", "1.0"):
                break
            tag = next((t for t in self.texto.tag_names(i) if t.startswith(prefixo)), None)
            if tag:
                return tag, self.texto.index(i)
        return None

    def _faixa_da_tag(self, tag: str, indice: str) -> tuple[str, str] | None:
        """O intervalo contínuo da tag que contém `indice`."""
        faixas = self.texto.tag_ranges(tag)
        for a, b in zip(faixas[::2], faixas[1::2]):
            if self.texto.compare(a, "<=", indice) and self.texto.compare(indice, "<", b):
                return str(a), str(b)
        return None

    def link_no_cursor(self) -> str | None:
        """O `href` do link sob o cursor, ou `None`."""
        achado = self._tag_no_cursor("link:")
        return T.valor(achado[0]) if achado else None

    def inserir_link(self, href: str, rotulo: str | None = None) -> bool:
        """
        Com seleção, o link vai nela; sem seleção, `rotulo` (ou o href) é inserido já com o
        link. Um link sob o cursor sem seleção é trocado inteiro.
        """
        href = (href or "").strip()
        if not href:
            raise ValueError("o link precisa de um destino (href)")
        if self.selecao():
            self.aplicar(link=href)
            return True
        achado = self._tag_no_cursor("link:")
        if achado is not None and rotulo is None:
            faixa = self._faixa_da_tag(achado[0], achado[1])
            if faixa:
                self.selecionar_indices(*faixa)
                self.aplicar(link=href)
                self.texto.tag_remove("sel", "1.0", "end")
                return True
        texto = rotulo if rotulo else href
        self._pendente = {"link": href}
        self._pendente_em = self.texto.index("insert")
        ok = self.inserir(texto)
        self._pendente = {}
        return ok

    def tirar_link(self) -> bool:
        achado = self._tag_no_cursor("link:")
        if achado is None:
            return False
        faixa = self._faixa_da_tag(achado[0], achado[1])
        if not faixa:
            return False
        self.selecionar_indices(*faixa)
        self.aplicar(link="")
        self.texto.tag_remove("sel", "1.0", "end")
        return True

    def _renomear_bloco(self, bloco_id: str, novo_id: str, novo: Bloco) -> None:
        """Troca o id de um bloco vivo (a marca, a ordem, as tags, o registro) e registra o ponto."""
        if novo_id in self._ordem or novo_id in self.ids_das_notas():
            raise ValueError(f"já há um bloco com o id {novo_id!r} neste capítulo (INV-01)")
        self._reconciliar()
        texto = self.texto
        inicio = self._inicio_de(bloco_id)
        i = self._ordem.index(bloco_id)
        antigo = self._modelo[bloco_id]
        texto.mark_unset(self._marca(bloco_id))
        texto.mark_set(self._marca(novo_id), inicio)
        texto.mark_gravity(self._marca(novo_id), "left")
        self._ordem[i] = novo_id
        self._ptags[novo_id] = self._ptags.pop(bloco_id, ("p:corpo",))
        nome = self.registro.nome_de(bloco_id)
        if nome:
            self.registro.substituir(nome, novo)
            widget = self.registro.widget_de(nome)
            if widget is not None and hasattr(widget, "atualizar"):
                widget.atualizar(novo)
        self._modelo.pop(bloco_id, None)
        self._modelo[novo_id] = novo
        self._reconciliando = True
        try:
            self._reaplicar_tags(novo_id)
            depois = self._blocos_do_dump([novo_id]).get(novo_id, novo)
        finally:
            self._reconciliando = False
        self._modelo[novo_id] = depois
        self._registrar_ponto([bloco_id, novo_id], [antigo], [depois], {bloco_id: i, novo_id: i}, False, "id")
        self.calha.redesenhar()

    def definir_id(self, bloco_id: str, novo_id: str) -> str:
        """A âncora: o bloco passa a ter este `id`, persistente (§8.9). Devolve o id."""
        novo_id = (novo_id or "").strip()
        if not re.fullmatch(r"[^\W\d][\w.:-]*", novo_id):
            raise ValueError(f"id inválido: {novo_id!r} — comece por letra, sem espaços")
        bloco = self._modelo.get(bloco_id)
        if bloco is None or isinstance(bloco, FaixaDeNotas):
            raise ValueError("o cursor precisa estar num bloco do capítulo")
        novo = copy.deepcopy(bloco)
        novo.id = novo_id
        novo.id_persistente = True
        if novo_id == bloco_id:
            if not bloco.id_persistente:
                self._reescrever_bloco(bloco_id, novo)
            return novo_id
        self._renomear_bloco(bloco_id, novo_id, novo)
        self.texto.mark_set("insert", self._inicio_de(novo_id))
        return novo_id

    def definir_classe(self, bloco_id: str, classe: str) -> None:
        bloco = self._modelo.get(bloco_id)
        if bloco is None or isinstance(bloco, FaixaDeNotas):
            raise ValueError("o cursor precisa estar num bloco do capítulo")
        novo = copy.deepcopy(bloco)
        novo.classe = " ".join((classe or "").split())
        if isinstance(bloco, TIPOS_DE_OBJETO):
            self.substituir_objeto(bloco_id, novo)
        else:
            self._reescrever_bloco(bloco_id, novo)

    # ------------------------------------------------------------------
    # Objetos: substituir, ilhas, o objeto sob o cursor
    # ------------------------------------------------------------------

    def objeto_no_cursor(self) -> Bloco | None:
        """O bloco-objeto sob o cursor (antes ou depois dele) ou selecionado; `None` senão."""
        bloco_id = self._objeto_da_selecao() or self._sobre_objeto("insert")
        if bloco_id is None:
            indice = self.texto.index("insert")
            if self.texto.compare(indice, ">", "1.0") and "objeto" in self.texto.tag_names(f"{indice}-1c"):
                candidato = self._bloco_em(f"{indice}-1c")
                if candidato and isinstance(self._modelo.get(candidato), TIPOS_DE_OBJETO):
                    bloco_id = candidato
        if bloco_id is None:
            return None
        bloco = self._modelo.get(bloco_id)
        return None if isinstance(bloco, FaixaDeNotas) else bloco

    def ilha_inline_no_cursor(self) -> str | None:
        """O nome da janela da ilha inline sob o cursor (antes ou depois dele)."""
        indice = self.texto.index("insert")
        for i in (indice, f"{indice}-1c"):
            if i != indice and not self.texto.compare(indice, ">", "1.0"):
                break
            if "objeto" not in self.texto.tag_names(i):
                continue
            for nome in self.texto.window_names():
                if self.texto.compare(self.texto.index(nome), "==", i) \
                        and isinstance(self.registro.objeto_registrado(nome), Trecho):
                    return nome
        return None

    def substituir_objeto(self, bloco_id: str, novo: Bloco) -> str:
        """
        O objeto com propriedades novas (a figura com outra largura, a tabela com legenda):
        o desenho é refeito, o registro aponta o novo modelo, e o ponto de desfazer é
        registrado. Um id novo (a marca de página que mudou de página) é renomeado.
        """
        atual = self._modelo.get(bloco_id)
        if not isinstance(atual, TIPOS_DE_OBJETO) or isinstance(atual, FaixaDeNotas):
            raise ValueError("não há objeto com esse id")
        if type(novo) is not type(atual):
            self._reescrever_bloco(bloco_id, novo)
            return novo.id
        if novo.id != bloco_id:
            self._renomear_bloco(bloco_id, novo.id, novo)
            return novo.id
        nome = self.registro.nome_de(bloco_id)
        widget = self.registro.widget_de(nome) if nome else None
        if nome:
            self.registro.substituir(nome, novo)
        if widget is not None and hasattr(widget, "atualizar"):
            widget.atualizar(novo)
        else:
            self._reescrever_bloco(bloco_id, novo)
            return bloco_id
        self._tocados.add(bloco_id)
        self._reconciliar({bloco_id}, coalescer=False, rotulo="propriedades")
        return bloco_id

    def substituir_ilha(self, bloco_id: str, xhtml: str) -> list[str]:
        """
        O XHTML editado de uma ilha de bloco: lido como fragmento, vira o(s) bloco(s) que
        for(em) — de volta ao dialeto, se agora couber nele. Devolve os ids novos.
        """
        from core.editor import xhtml as xhtml_mod

        blocos = xhtml_mod.ler_fragmento(xhtml.strip(), self.arquivo)
        if not blocos:
            raise ValueError("o fragmento não tem nenhum bloco")
        atual = self._modelo.get(bloco_id)
        if not isinstance(atual, IlhaBruta):
            raise ValueError("o cursor não está sobre uma ilha")
        ids = []
        self._abrir_composto("ilha")
        try:
            primeiro = blocos[0]
            primeiro.id = bloco_id
            self._reescrever_bloco(bloco_id, primeiro)
            ids.append(bloco_id)
            anterior = bloco_id
            for bloco in blocos[1:]:
                if bloco.id in self._ordem:
                    bloco.id = modelo.id_novo()
                self._desenhar_bloco(bloco, self._fim_de(anterior), self._seguinte(anterior))
                self._modelo.pop(bloco.id, None)
                self._reconciliar({bloco.id})
                ids.append(bloco.id)
                anterior = bloco.id
        finally:
            self._fechar_composto()
        return ids

    def substituir_ilha_inline(self, nome: str, xhtml: str) -> bool:
        """O XHTML editado de uma ilha inline: o fragmento novo no lugar (ou o texto, se virou dialeto)."""
        from core.editor import xhtml as xhtml_mod

        trecho = self.registro.objeto_registrado(nome)
        if not isinstance(trecho, Trecho):
            raise ValueError("não há ilha inline com esse nome")
        blocos = xhtml_mod.ler_fragmento(xhtml.strip(), self.arquivo)
        if len(blocos) != 1 or not isinstance(blocos[0], Paragrafo):
            raise ValueError("uma ilha inline recebe só conteúdo inline (um elemento como <cite> ou <abbr>)")
        indice = self.texto.index(nome)
        bloco_id = self._bloco_em(indice)
        self._abrir_composto("ilha")
        try:
            self._em_carga = True
            try:
                self.registro.esquecer(nome)
                self.texto.nametowidget(nome).destroy()
                self.texto.delete(indice, f"{indice}+1c")
            finally:
                self._em_carga = False
            self.texto.mark_set("insert", indice)
            self._tocados.add(bloco_id)
            self.inserir_trechos(blocos[0].trechos)
        finally:
            self._fechar_composto()
        return True

    # ------------------------------------------------------------------
    # Fragmentos: copiar e colar com formato (§8.11)
    # ------------------------------------------------------------------

    def fragmento_da_selecao(self) -> Fragmento:
        """O modelo do que está selecionado: blocos (o primeiro e o último parciais) e as notas referenciadas."""
        selecao = self.selecao()
        if not selecao:
            return Fragmento()
        ini, fim = selecao
        if self._tem_faixa() and self.texto.compare(ini, "<", self._inicio_de(ID_DA_FAIXA)) \
                and self.texto.compare(fim, ">", self._inicio_de(ID_DA_FAIXA)):
            fim = self._inicio_de(ID_DA_FAIXA)
        blocos = self._blocos_entre(ini, fim)
        if len(blocos) > 1 and self.texto.compare(self._inicio_de(blocos[-1]), ">=", fim):
            blocos = blocos[:-1]
        if not blocos or ID_DA_FAIXA in blocos:
            return Fragmento()
        marca = self._marca(blocos[0])
        itens = [("mark", marca, self.texto.index(ini))]
        itens += [it for it in self._dump(ini, fim) if it[0] != "mark" or it[1] != marca]
        modelos, _notas = dump_mod.dump_para_blocos(itens, self.registro, self._modelo)
        modelos = copy.deepcopy(modelos)
        inline = len(blocos) == 1 and isinstance(self._modelo.get(blocos[0]), Paragrafo) \
            and not isinstance(self._modelo.get(blocos[0]), TIPOS_DE_OBJETO) and len(modelos) == 1
        notas: list[Nota] = []
        for bloco in modelos:
            for trecho in modelo._todos_os_trechos(bloco):
                nota = self._raiz()._nota_cache(trecho.nota) if trecho.nota else None
                if nota is not None and nota.id not in {n.id for n in notas}:
                    notas.append(copy.deepcopy(nota))
        texto = modelo.texto_de(modelos[0]) if inline else "\n".join(modelo.texto_de(b) for b in modelos)
        fragmento = Fragmento(blocos=modelos, inline=inline, texto=texto)
        fragmento.notas = notas
        return fragmento

    def inserir_trechos(self, trechos: Sequence[Trecho]) -> bool:
        """Trechos com o formato deles no cursor (ilhas inline, referências de nota e quebras inclusive)."""
        if self.selecao():
            self.apagar_selecao()
        if not self._ids_do_capitulo():
            self.inserir("")
        indice = self._dentro_do_texto(self.texto.index("insert"))
        if not self._pode_editar(indice):
            return False
        while "marcador" in self.texto.tag_names(indice):
            indice = self.texto.index(f"{indice}+1c")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None or isinstance(self._modelo.get(bloco_id), TIPOS_DE_OBJETO):
            return False
        ptags, _c, estilo = self._tags_para_inserir(indice)
        self._pendente = {}
        self.texto.mark_set(MARCA_DE_INSERCAO, indice)
        self.texto.mark_gravity(MARCA_DE_INSERCAO, "right")
        notas = self.ids_das_notas()
        for t in trechos:
            if t.quebra_antes:
                self._inserir_segmento("\n", ptags, (), estilo, ("qs", "quebra", "protegido"))
            if t.pagina is not None:
                self._inserir_segmento(SIMBOLO_DA_PAGINA, ptags, (), estilo,
                                       (T.nome("pagina:", t.pagina), "protegido", "marcador"))
            if t.ilha:
                self._inserir_objeto(copy.deepcopy(t), ptags, inline=True)
            elif t.nota:
                if t.nota in notas:
                    self._inserir_segmento(self._glifo_da_nota(t.nota), ptags, (), estilo,
                                           (T.nome("nota:", t.nota), "protegido"))
            elif t.texto:
                self._inserir_segmento(t.texto, ptags, self._tags_do_trecho(t), estilo)
        self.texto.mark_set("insert", MARCA_DE_INSERCAO)
        self.texto.mark_unset(MARCA_DE_INSERCAO)
        self._simples = False
        self._reconciliar({bloco_id})
        return True

    def inserir_blocos(self, blocos: Sequence[Bloco]) -> list[str]:
        """
        Blocos no cursor: o primeiro e o último parágrafos fundem-se com o parágrafo do
        cursor (partido nele), os do meio entram inteiros; num objeto ou lista, tudo entra
        inteiro depois. Ids que colidem ganham outro. Um desfazer só. Devolve os ids.
        """
        blocos = [copy.deepcopy(b) for b in blocos]
        if not blocos:
            return []
        if self.selecao():
            self.apagar_selecao()
        if not self._ids_do_capitulo():
            self.inserir("")
        usados = set(self._ordem) | set(self.ids_das_notas())
        for bloco in blocos:
            if bloco.id in usados or not bloco.id_persistente:
                bloco.id = modelo.id_novo()
            usados.add(bloco.id)
        atual = self.bloco_atual()
        atual_modelo = self._modelo.get(atual) if atual else None
        e_paragrafo = isinstance(atual_modelo, Paragrafo) and not isinstance(atual_modelo, TIPOS_DE_OBJETO) \
            and not self.em_nota()
        ids: list[str] = []
        self._abrir_composto("colar")
        try:
            if not e_paragrafo:
                anterior = atual if atual != ID_DA_FAIXA else (self._ids_do_capitulo() or [None])[-1]
                for bloco in blocos:
                    self._inserir_bloco_depois(bloco, anterior)
                    ids.append(bloco.id)
                    anterior = bloco.id
            else:
                primeiro, ultimo = blocos[0], blocos[-1]
                funde_primeiro = isinstance(primeiro, Paragrafo) and not isinstance(primeiro, Titulo) \
                    and not isinstance(primeiro, TIPOS_DE_OBJETO)
                funde_ultimo = len(blocos) > 1 and isinstance(ultimo, Paragrafo) and not isinstance(ultimo, Titulo) \
                    and not isinstance(ultimo, TIPOS_DE_OBJETO)
                meio = blocos[1:-1] if funde_ultimo else blocos[1:]
                if funde_primeiro and len(blocos) == 1:
                    self.inserir_trechos(primeiro.trechos)
                    return [atual]
                self.enter()
                cauda = self.bloco_atual()
                self.texto.mark_set("insert", f"{self._fim_de(atual)}-1c")
                if funde_primeiro:
                    self.inserir_trechos(primeiro.trechos)
                    ids.append(atual)
                else:
                    meio = [primeiro] + meio
                anterior = atual
                for bloco in meio:
                    self._inserir_bloco_depois(bloco, anterior)
                    ids.append(bloco.id)
                    anterior = bloco.id
                if funde_ultimo:
                    self.ir_para(cauda, 0)
                    self.inserir_trechos(ultimo.trechos)
                    ids.append(cauda)
                elif cauda and not modelo.texto_de(self._modelo.get(cauda, Paragrafo(trechos=[]))).strip() \
                        and not any(t.ilha or t.nota for t in getattr(self._modelo.get(cauda), "trechos", [])):
                    self._apagar_bloco_sem_ponto(cauda)
                    self._tocados.add(cauda)
                    self.texto.mark_set("insert", f"{self._fim_de(anterior)}-1c")
        finally:
            self._fechar_composto()
        return ids

    def _inserir_bloco_depois(self, bloco: Bloco, anterior: str | None) -> None:
        """Um bloco desenhado depois de `anterior` (ou no começo), como parte de um composto."""
        if anterior is None or anterior == ID_DA_FAIXA:
            self._desenhar_bloco(bloco, "1.0", self._ordem[0] if self._ordem else None)
        else:
            self._desenhar_bloco(bloco, self._fim_de(anterior), self._seguinte(anterior))
        self._modelo.pop(bloco.id, None)
        self._tocados.add(bloco.id)
        self._reconciliar({bloco.id})
        self.texto.mark_set("insert", f"{self._fim_de(bloco.id)}-1c")

    def colar_fragmento(self, fragmento: Fragmento) -> bool:
        """
        Colar interno (§8.11): o fragmento com formato, figura e ilha; as notas
        referenciadas nascem de novo neste capítulo (com id novo), como no Word.
        """
        if fragmento.vazio:
            return False
        raiz = self._raiz()
        trocas: dict[str, str] = {}
        raiz._abrir_composto("colar")
        if raiz is not self:
            self._abrir_composto("colar")
        try:
            for nota in getattr(fragmento, "notas", []) or []:
                nova = copy.deepcopy(nota)
                nova.id = modelo.id_novo()
                for paragrafo in nova.blocos:
                    paragrafo.id = modelo.id_novo()
                trocas[nota.id] = nova.id
                raiz._criar_nota(nova)
            blocos = copy.deepcopy(fragmento.blocos)
            if trocas:
                for bloco in blocos:
                    for trecho in modelo._todos_os_trechos(bloco):
                        if trecho.nota:
                            trecho.nota = trocas.get(trecho.nota, "")
            if fragmento.inline and blocos and isinstance(blocos[0], Paragrafo):
                ok = self.inserir_trechos(blocos[0].trechos)
            else:
                ok = bool(self.inserir_blocos(blocos))
            if trocas:
                raiz._renumerar()
        finally:
            if raiz is not self:
                self._fechar_composto()
            raiz._fechar_composto()
        return ok

    # ------------------------------------------------------------------
    # Propriedades (o painel; §8.3, §8.6–§8.9)
    # ------------------------------------------------------------------

    def alvo_das_propriedades(self) -> dict[str, Any]:
        """
        O que o painel Propriedades mostra para a posição do cursor: `tipo` (`figura`,
        `tabela`, `ilha`, `ilha_inline`, `marca`, `quebra`, `separador`, `diagrama`,
        `nota`, `link`, `paragrafo` ou `""`), `id`, `objeto` e os `campos` editáveis.
        """
        objeto = self.objeto_no_cursor()
        if objeto is not None:
            tipo = {Figura: "figura", Tabela: "tabela", IlhaBruta: "ilha", MarcaDePagina: "marca",
                    QuebraDePagina: "quebra", Separador: "separador", Diagrama: "diagrama"}.get(type(objeto), "")
            campos: dict[str, Any] = {"id": objeto.id if objeto.id_persistente else "", "classe": objeto.classe}
            if isinstance(objeto, Figura):
                campos.update({"recurso": objeto.recurso, "alt": objeto.alt, "largura_pt": objeto.largura_pt,
                               "alinhamento": objeto.alinhamento, "legenda": "".join(t.texto for t in objeto.legenda),
                               "numero": objeto.numero})
            elif isinstance(objeto, Tabela):
                campos.update({"legenda": "".join(t.texto for t in objeto.legenda), "numero": objeto.numero,
                               "largura_pct": objeto.largura_pct,
                               "primeira_fila_cabecalho": objeto.primeira_fila_cabecalho,
                               "filas": len(objeto.filas), "colunas": objeto.colunas})
            elif isinstance(objeto, IlhaBruta):
                campos.update({"elemento": objeto.elemento, "xhtml": objeto.xhtml})
            elif isinstance(objeto, MarcaDePagina):
                campos.update({"pagina": objeto.pagina})
            elif isinstance(objeto, Diagrama):
                campos.update({"fen": objeto.fen, "lado": objeto.lado, "orientacao": objeto.orientacao})
            return {"tipo": tipo, "id": objeto.id, "objeto": objeto, "campos": campos}
        nome = self.ilha_inline_no_cursor()
        if nome is not None:
            trecho = self.registro.objeto_registrado(nome)
            return {"tipo": "ilha_inline", "id": nome, "objeto": trecho, "campos": {"xhtml": trecho.ilha}}
        nota_id = self.nota_no_cursor()
        if nota_id:
            nota = self._raiz()._nota_cache(nota_id)
            return {"tipo": "nota", "id": nota_id, "objeto": nota,
                    "campos": {"tipo": nota.tipo if nota else "?", "numero": self._numero_da_nota(nota_id),
                               "texto": modelo.texto_de(nota)[:200] if nota else "(nota inexistente)"}}
        achado = self._tag_no_cursor("link:")
        if achado is not None:
            titulo = self._tag_no_cursor("tit:")
            faixa = self._faixa_da_tag(achado[0], achado[1])
            return {"tipo": "link", "id": achado[0], "objeto": None,
                    "campos": {"href": T.valor(achado[0]), "titulo": T.valor(titulo[0]) if titulo else "",
                               "texto": self.texto.get(*faixa) if faixa else ""}}
        bloco_id = self.bloco_atual()
        bloco = self._modelo.get(bloco_id) if bloco_id else None
        if isinstance(bloco, Paragrafo):
            campos = {"estilo": bloco.estilo if not isinstance(bloco, Titulo) else f"titulo{bloco.nivel}",
                      "id": bloco.id if bloco.id_persistente else "", "classe": bloco.classe}
            for chave in PREFIXOS_DE_PARAGRAFO:
                campos[chave] = getattr(bloco, chave)
            for chave in SIMPLES_DE_PARAGRAFO:
                campos[chave] = getattr(bloco, chave)
            return {"tipo": "paragrafo", "id": bloco_id, "objeto": bloco, "campos": campos}
        if bloco is not None:
            return {"tipo": type(bloco).__name__.lower(), "id": bloco_id, "objeto": bloco,
                    "campos": {"id": bloco.id if bloco.id_persistente else "", "classe": bloco.classe}}
        return {"tipo": "", "id": "", "objeto": None, "campos": {}}

    def aplicar_propriedades(self, alvo: dict[str, Any], valores: dict[str, Any]) -> bool:
        """
        Grava no modelo o que o painel devolveu em "Aplicar" — só o que veio em `valores`.
        Devolve se algo mudou. `ValueError` para valor inválido.
        """
        tipo, id_ = alvo.get("tipo", ""), alvo.get("id", "")
        valores = dict(valores)
        if tipo in ("figura", "tabela", "ilha", "marca", "quebra", "separador", "diagrama"):
            atual = self._modelo.get(id_)
            if atual is None:
                raise ValueError("o objeto já não está no capítulo")
            novo = copy.deepcopy(atual)
            id_novo = valores.pop("id", None)
            classe = valores.pop("classe", None)
            if classe is not None:
                novo.classe = " ".join(str(classe).split())
            if isinstance(novo, Figura):
                if "alt" in valores:
                    novo.alt = str(valores["alt"]).strip()
                if "largura_pt" in valores:
                    novo.largura_pt = _numero_ou_nenhum(valores["largura_pt"], "largura")
                if "alinhamento" in valores and valores["alinhamento"]:
                    novo.alinhamento = str(valores["alinhamento"])
                if "legenda" in valores:
                    novo.legenda = [Trecho(texto=str(valores["legenda"]))] if str(valores["legenda"]).strip() else []
                if "numero" in valores:
                    n = _numero_ou_nenhum(valores["numero"], "número")
                    novo.numero = int(n) if n is not None else None
            elif isinstance(novo, Tabela):
                if "legenda" in valores:
                    novo.legenda = [Trecho(texto=str(valores["legenda"]))] if str(valores["legenda"]).strip() else []
                if "numero" in valores:
                    n = _numero_ou_nenhum(valores["numero"], "número")
                    novo.numero = int(n) if n is not None else None
                if "largura_pct" in valores:
                    n = _numero_ou_nenhum(valores["largura_pct"], "largura")
                    novo.largura_pct = int(n) if n is not None else None
                if "primeira_fila_cabecalho" in valores:
                    ligar = bool(valores["primeira_fila_cabecalho"])
                    novo.primeira_fila_cabecalho = ligar
                    for celula in (novo.filas[0] if novo.filas else []):
                        celula.cabecalho = ligar
            elif isinstance(novo, IlhaBruta) and "xhtml" in valores:
                self.substituir_ilha(id_, str(valores["xhtml"]))
                return True
            elif isinstance(novo, MarcaDePagina) and "pagina" in valores:
                pagina = _numero_ou_nenhum(valores["pagina"], "página")
                if pagina is None or int(pagina) < 1:
                    raise ValueError("a página precisa ser um inteiro positivo")
                novo = MarcaDePagina(pagina=int(pagina), classe=novo.classe, extras=dict(novo.extras),
                                     origem=novo.origem)
            if id_novo is not None and str(id_novo).strip() and str(id_novo).strip() != novo.id:
                novo.id = str(id_novo).strip()
                if not re.fullmatch(r"[^\W\d][\w.:-]*", novo.id):
                    raise ValueError(f"id inválido: {novo.id!r}")
                novo.id_persistente = True
            elif id_novo is not None and str(id_novo).strip() == novo.id:
                novo.id_persistente = True
            if modelo.igual(novo, atual) and novo.id == atual.id and novo.id_persistente == atual.id_persistente:
                return False
            self.substituir_objeto(id_, novo)
            return True
        if tipo == "ilha_inline":
            if "xhtml" in valores:
                return self.substituir_ilha_inline(id_, str(valores["xhtml"]))
            return False
        if tipo == "nota":
            if "tipo" in valores:
                return self.mudar_tipo_da_nota(id_, str(valores["tipo"]))
            return False
        if tipo == "link":
            faixa = self._faixa_da_tag(id_, self._tag_no_cursor("link:")[1]) if self._tag_no_cursor("link:") else None
            if faixa is None:
                raise ValueError("o cursor já não está sobre o link")
            indice = self.texto.index("insert")
            self.selecionar_indices(*faixa)
            atributos: dict[str, Any] = {}
            if "href" in valores:
                href = str(valores["href"]).strip()
                if not href:
                    raise ValueError("o link precisa de um destino (href); para tirá-lo, use Limpar formatação")
                atributos["link"] = href
            if "titulo" in valores:
                atributos["titulo"] = str(valores["titulo"]).strip()
            self.aplicar(**atributos)
            self.texto.tag_remove("sel", "1.0", "end")
            self.texto.mark_set("insert", indice)
            return bool(atributos)
        if tipo == "paragrafo":
            bloco = self._modelo.get(id_)
            if not isinstance(bloco, Paragrafo):
                raise ValueError("o cursor já não está num parágrafo")
            mudou = False
            self._abrir_composto("propriedades")
            try:
                estilo = valores.pop("estilo", None)
                if estilo and estilo != (f"titulo{bloco.nivel}" if isinstance(bloco, Titulo) else bloco.estilo):
                    self.ir_para(id_, 0)
                    self.estilo(str(estilo))
                    mudou = True
                props = {k: v for k, v in valores.items() if k in PREFIXOS_DE_PARAGRAFO or k in SIMPLES_DE_PARAGRAFO}
                for chave in list(props):
                    if chave in PREFIXOS_DE_PARAGRAFO and chave != "alinhamento":
                        props[chave] = _numero_ou_nenhum(props[chave], chave)
                    elif chave in SIMPLES_DE_PARAGRAFO:
                        props[chave] = bool(props[chave])
                    elif chave == "alinhamento":
                        props[chave] = str(props[chave] or "")
                if props:
                    self.ir_para(id_, 0)
                    self.paragrafo(**props)
                    mudou = True
                classe = valores.get("classe")
                if classe is not None and " ".join(str(classe).split()) != bloco.classe:
                    self.definir_classe(id_, str(classe))
                    mudou = True
                id_novo = valores.get("id")
                if id_novo is not None and str(id_novo).strip() and (str(id_novo).strip() != bloco.id
                                                                    or not bloco.id_persistente):
                    self.definir_id(id_, str(id_novo))
                    mudou = True
            finally:
                self._fechar_composto()
            return mudou
        raise ValueError("não há o que aplicar aqui")

    # ------------------------------------------------------------------
    # Células e o editor ativo
    # ------------------------------------------------------------------

    def ativo(self) -> "TextoRico":
        """A célula de tabela com o foco, quando há; senão este widget."""
        try:
            foco = self.focus_get()
        except (tk.TclError, KeyError):
            return self
        while foco is not None and foco is not self:
            if isinstance(foco, TextoRico) and foco.celula:
                return foco
            foco = getattr(foco, "master", None)
        return self

    def ajustar_altura(self) -> int:
        """Numa célula, a altura em linhas exibidas (`count -displaylines`), no mínimo uma."""
        if not self.celula:
            return 0
        # Sem tela (widget ainda não mapeado) o Tk conta uma linha exibida por caractere: vale `-lines`.
        unidade = "displaylines" if self.texto.winfo_ismapped() else "lines"
        try:
            linhas = _contagem(self.texto.count("1.0", "end-1c", unidade))
        except tk.TclError:
            linhas = 1
        linhas = max(1, min(40, linhas))
        try:
            if int(self.texto.cget("height")) != linhas:
                self.texto.configure(height=linhas)
        except tk.TclError:
            pass
        return linhas

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
        """
        Troca o desenho de um bloco pelo de `novo` (mesmo id); o ponto sai na reconciliação,
        com o modelo antigo como "antes" (`_antes_forcado`) e `novo` como base do que o
        `dump` não lê das tags (classe, id persistente, extras). O cursor fica onde estava.
        """
        novo.id = bloco_id
        ini, fim = self._inicio_de(bloco_id), self._fim_de(bloco_id)
        seguinte = self._seguinte(bloco_id)
        antigo = self._modelo.get(bloco_id)
        no_bloco = self._bloco_em("insert") == bloco_id
        desloc = self._deslocamento("insert", bloco_id) if no_bloco else None
        ptags_de_nota = tuple(t for t in self._ptags.get(bloco_id, ()) if t.startswith("dn:"))
        self._remover_bloco(bloco_id)
        self._em_carga = True
        try:
            self.texto.delete(ini, fim)
            self._desenhar_bloco(novo, ini, seguinte, extras=ptags_de_nota)
        finally:
            self._em_carga = False
        if antigo is not None:
            self._antes_forcado[bloco_id] = antigo      # o "antes" do ponto; o "depois" vem do dump
        self._tocados.add(bloco_id)
        self._simples = False
        if reconciliar:
            self._reconciliar({bloco_id}, coalescer=False)
        if desloc is not None and bloco_id in self._ordem:
            self.ir_para(bloco_id, min(desloc, len(modelo.texto_de(self._modelo.get(bloco_id, novo)))))

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
        T.configurar(self.texto, self.estilos, self.fontes, preguicoso=self.celula)
        self._redesenhar_tudo()
        return self.tela.zoom

    def _redesenhar_tudo(self) -> None:
        self._reconciliar()
        posicao = self.posicao()
        blocos = [self._modelo[i] for i in self._ids_do_capitulo() if i in self._modelo]
        notas, capitulo, sujo = self.notas_atuais(), self._capitulo, self._sujo
        invisiveis = self._invisiveis
        self._invisiveis = False
        self.carregar_blocos(blocos, notas)
        self._capitulo, self._sujo = capitulo, sujo
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
        """Numa célula, o desfazer é o do texto de fora (o ponto é sobre a tabela inteira)."""
        if self.dono is not None:
            return self._raiz().desfazer()
        self._reconciliar()
        ponto = self.historico.desfazer(self.arquivo)
        if ponto is None:
            return False
        self._aplicar_ponto(ponto, "antes")
        return True

    def refazer(self) -> bool:
        if self.dono is not None:
            return self._raiz().refazer()
        self._reconciliar()
        ponto = self.historico.refazer(self.arquivo)
        if ponto is None:
            return False
        self._aplicar_ponto(ponto, "depois")
        return True

    def _aplicar_ponto(self, ponto: Ponto, sentido: str) -> None:
        from core.editor import historico as historico_mod

        capitulo = Capitulo(arquivo=self.arquivo,
                            blocos=[self._modelo[i] for i in self._ids_do_capitulo() if i in self._modelo],
                            notas=[copy.deepcopy(n) for n in self._notas])
        historico_mod.aplicar(capitulo, ponto, sentido)
        self._em_desfazer = True
        try:
            invisiveis = self._invisiveis
            self._invisiveis = False
            self.carregar_blocos(capitulo.blocos, capitulo.notas)
            if invisiveis:
                self.invisiveis(True)
        finally:
            self._em_desfazer = False
        self._sujo = True
        alvo = next((i for i in ponto.ids if i in self._ordem), None)
        if alvo is None:
            nota = next((i for i in ponto.ids if self._paragrafos_da_nota(i)), None)
            alvo = self._paragrafos_da_nota(nota)[0] if nota else None
        if alvo:
            self.ir_para(alvo, 0)
        try:
            self.texto.event_generate("<<Mudou>>")
        except tk.TclError:
            pass

    @property
    def pode_desfazer(self) -> bool:
        if self.dono is not None:
            return self._raiz().pode_desfazer
        self._reconciliar()
        return self.historico.pode_desfazer(self.arquivo)

    @property
    def pode_refazer(self) -> bool:
        if self.dono is not None:
            return self._raiz().pode_refazer
        return self.historico.pode_refazer(self.arquivo)

    # ------------------------------------------------------------------
    # Ligações de teclado (a API por trás de cada tecla)
    # ------------------------------------------------------------------

    def _instalar_ligacoes(self) -> None:
        """
        As teclas → a API. Os handlers ficam em `self.ligacoes` (o teste os chama com um
        evento); a bindtag de classe é ligada **uma vez** por interpretador e despacha ao
        `TextoRico` dono do widget que recebeu a tecla (ver o cabeçalho).
        """
        texto = self.texto
        tags = list(texto.bindtags())
        tags.insert(1, BINDTAG)
        texto.bindtags(tuple(tags))
        q = self._quebra
        ligacoes = {
            "<Return>": lambda e: q(self.enter()), "<KP_Enter>": lambda e: q(self.enter()),
            "<Shift-Return>": lambda e: q(self.inserir_quebra_suave()),
            "<Control-Return>": self._tecla_quebra_de_pagina,
            "<BackSpace>": lambda e: q(self.backspace()), "<Delete>": lambda e: q(self._delete()),
            "<Key>": self._tecla,
            "<Tab>": lambda e: q(self._tab(1)), "<Shift-Tab>": lambda e: q(self._tab(-1)),
            "<Escape>": self._tecla_escape, "<Up>": lambda e: self._seta_vertical(-1),
            "<Down>": lambda e: self._seta_vertical(1), "<Left>": lambda e: self._seta_horizontal(-1),
            "<Right>": lambda e: self._seta_horizontal(1), "<MouseWheel>": self._roda,
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
        self.ligacoes = ligacoes
        _INSTANCIAS[str(texto)] = self
        texto.bind("<Destroy>", self._esquecer_instancia, add="+")
        if not texto.bind_class(BINDTAG):
            for sequencia in ligacoes:
                texto.bind_class(BINDTAG, sequencia, _despachar(sequencia))

    def _esquecer_instancia(self, evento: Any) -> None:
        if str(getattr(evento, "widget", "")) == str(self.texto):
            _INSTANCIAS.pop(str(self.texto), None)

    @staticmethod
    def _quebra(_resultado: Any = None) -> str:
        return "break"

    def _tab(self, direcao: int) -> bool:
        """`Tab`/`Shift+Tab`: entre células numa tabela; nível do item numa lista; senão um tabulador."""
        if self.celula and self.ao_tab is not None:
            return bool(self.ao_tab(direcao))
        if direcao > 0:
            return self.nivel(1) or self.inserir("\t")
        return self.nivel(-1)

    def _tecla_escape(self, evento: Any) -> str | None:
        """`Esc` numa célula sai da tabela; numa nota volta à referência; senão segue para a janela."""
        if self.celula and self.ao_escape is not None:
            self.ao_escape()
            return "break"
        if self.em_nota():
            self.voltar_da_nota()
            return "break"
        return None

    def _tecla_quebra_de_pagina(self, evento: Any) -> str:
        if not self.celula:
            self.inserir_quebra_de_pagina()
        return "break"

    def _seta_vertical(self, direcao: int) -> str | None:
        """Numa célula, seta para cima na primeira linha (ou para baixo na última) sai da célula."""
        if not self.celula or self.ao_sair_vertical is None:
            return None
        # `-displaylines` so vale com o widget mapeado (a largura decide onde a linha dobra); sem tela, `-lines`.
        unidade = "displaylines" if self.texto.winfo_ismapped() else "lines"
        fim = f"{self._fim_de(self._ordem[-1])}-1c" if self._ordem else "end-1c"
        try:
            if direcao < 0:
                na_borda = _contagem(self.texto.count("1.0", "insert", unidade)) == 0
            else:
                na_borda = _contagem(self.texto.count("insert", fim, unidade)) == 0
        except tk.TclError:
            na_borda = True
        if not na_borda:
            return None
        self.ao_sair_vertical(direcao)
        return "break"

    def _seta_horizontal(self, direcao: int) -> str | None:
        if not self.celula or self.ao_sair_horizontal is None:
            return None
        fim = f"{self._fim_de(self._ordem[-1])}-1c" if self._ordem else "end-1c"
        if direcao < 0 and self.texto.compare("insert", "==", "1.0"):
            self.ao_sair_horizontal(-1)
            return "break"
        if direcao > 0 and self.texto.compare("insert", ">=", fim):
            self.ao_sair_horizontal(1)
            return "break"
        return None

    def _roda(self, evento: Any) -> str | None:
        """A roda numa célula rola o texto de fora (§8.6)."""
        if not self.celula or self.dono is None:
            return None
        delta = getattr(evento, "delta", 0) or 0
        try:
            self._raiz().texto.yview_scroll(-int(delta / 120) if delta else 0, "units")
        except tk.TclError:
            pass
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
        """`Delete`: sobre um objeto ou uma referência de nota, seleciona; no fim do bloco, junta o seguinte."""
        if self.selecao():
            return self.apagar_selecao()
        indice = self.texto.index("insert")
        bloco_id = self._bloco_em(indice)
        if bloco_id is None:
            return False
        if self._sobre_objeto(indice):
            if not isinstance(self._modelo.get(bloco_id), FaixaDeNotas):
                self.selecionar_objeto(bloco_id)
            return False
        if self._e_referencia_de_nota(indice):
            self.selecionar_indices(indice, f"{indice}+1c")
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


class _SemCalha:
    """O que uma célula tem no lugar da calha: nada que desenhe."""

    def redesenhar(self) -> None:
        pass

    def marcar(self, bloco_id: str, tipo: str | None) -> None:
        pass

    def limpar(self) -> None:
        pass


def _despachar(sequencia: str) -> Callable[[Any], Any]:
    """O handler da bindtag de classe: acha o `TextoRico` do widget do evento e chama o dele."""
    def handler(evento: Any) -> Any:
        dono = _INSTANCIAS.get(str(getattr(evento, "widget", "")))
        if dono is None:
            return None
        ligacao = dono.ligacoes.get(sequencia)
        return ligacao(evento) if ligacao is not None else None
    return handler


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
