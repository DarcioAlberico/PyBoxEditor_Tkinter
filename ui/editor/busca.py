"""
O painel Busca do caderno de baixo: a caixa de localizar e substituir da §8.12, para
os dois modos (ED-06).

O painel não procura nada: recolhe as opções (`opcoes()`), guarda o histórico das
20 buscas e chama a janela por nome de comando (`ao_executar("localizar_proximo")`)
— o mesmo caminho do menu, da barra e do `F3`, por `janela.executar`, que é onde as
duas camadas de erro moram (§13.3). É a janela que sabe qual aba está aberta, em que
modo, e que traduz a ocorrência para uma seleção (`ui/editor/janela.py`,
`_registrar_comandos_da_ed06`). Os campos são `tk.StringVar`/`BooleanVar` públicos
para o teste preencher sem teclado (§14). `Esc` no painel devolve o foco ao editor
(o acorde de fundo da janela); `Enter` no campo é "localizar próximo", `Shift+Enter`
"anterior".
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from core.editor import busca as busca_mod
from core.editor.busca import Opcoes

CAMPOS_BOOLEANOS = (("maiusculas", "Maiúsculas"), ("palavra_inteira", "Palavra inteira"), ("regex", "Regex"),
                    ("dotall", "Dotall"), ("minimo", "Mínimo"), ("espaco_casa_nbsp", "Espaço casa inseparável"),
                    ("circular", "Circular"))
BOTOES = (("localizar_proximo", "Próximo", "F3"), ("localizar_anterior", "Anterior", "Shift+F3"),
          ("substituir_atual", "Substituir", ""), ("substituir_e_localizar", "Substituir e localizar", ""),
          ("substituir_todos", "Substituir todos", ""), ("contar_ocorrencias", "Contar", ""),
          ("listar_ocorrencias", "Listar", ""))


class PainelDeBusca(ttk.Frame):
    def __init__(self, master: tk.Misc, ao_executar: Callable[[str], Any], historico: Sequence[str] = (),
                 ao_gravar_historico: Callable[[list[str]], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.ao_executar = ao_executar
        self.ao_gravar_historico = ao_gravar_historico
        self.historico = busca_mod.Historico(list(historico))
        self.var_texto = tk.StringVar(master=self)
        self.var_substituto = tk.StringVar(master=self)
        self.var_escopo = tk.StringVar(master=self, value=busca_mod.ROTULOS_DOS_ESCOPOS["capitulo"])
        self.booleanas: dict[str, tk.BooleanVar] = {}
        for nome, _rotulo in CAMPOS_BOOLEANOS:
            self.booleanas[nome] = tk.BooleanVar(master=self, value=nome in ("espaco_casa_nbsp", "circular"))
        self._construir()

    def _construir(self) -> None:
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="Localizar:").grid(row=0, column=0, sticky="w", padx=(6, 4), pady=(4, 2))
        self.campo_texto = ttk.Combobox(self, textvariable=self.var_texto, values=list(self.historico.itens), width=40)
        self.campo_texto.grid(row=0, column=1, sticky="ew", pady=(4, 2))
        ttk.Label(self, text="Substituir por:").grid(row=1, column=0, sticky="w", padx=(6, 4), pady=2)
        self.campo_substituto = ttk.Entry(self, textvariable=self.var_substituto, width=40)
        self.campo_substituto.grid(row=1, column=1, sticky="ew", pady=2)
        opcoes = ttk.Frame(self)
        opcoes.grid(row=2, column=0, columnspan=3, sticky="w", padx=4)
        self.caixas: dict[str, ttk.Checkbutton] = {}
        for k, (nome, rotulo) in enumerate(CAMPOS_BOOLEANOS):
            caixa = ttk.Checkbutton(opcoes, text=rotulo, variable=self.booleanas[nome])
            caixa.grid(row=0, column=k, sticky="w", padx=(0, 6))
            self.caixas[nome] = caixa
        ttk.Label(opcoes, text="Escopo:").grid(row=1, column=0, sticky="w", pady=(2, 4))
        self.campo_escopo = ttk.Combobox(opcoes, textvariable=self.var_escopo, state="readonly", width=18,
                                         values=[busca_mod.ROTULOS_DOS_ESCOPOS[e] for e in busca_mod.ESCOPOS])
        self.campo_escopo.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 4))
        botoes = ttk.Frame(self)
        botoes.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(8, 6), pady=(4, 0))
        self.botoes: dict[str, ttk.Button] = {}
        for k, (comando, rotulo, _atalho) in enumerate(BOTOES):
            botao = ttk.Button(botoes, text=rotulo, command=lambda c=comando: self._executar(c), width=20)
            botao.grid(row=k // 4, column=k % 4, padx=1, pady=1, sticky="ew")
            self.botoes[comando] = botao
        self.campo_texto.bind("<Return>", lambda e: self._executar("localizar_proximo"))
        self.campo_texto.bind("<Shift-Return>", lambda e: self._executar("localizar_anterior"))
        self.campo_substituto.bind("<Return>", lambda e: self._executar("substituir_e_localizar"))
        self.campo_substituto.bind("<Shift-Return>", lambda e: self._executar("substituir_atual"))

    # -- API ---------------------------------------------------------------

    def _executar(self, comando: str) -> str:
        self.registrar_no_historico()
        self.ao_executar(comando)
        return "break"

    def opcoes(self, direcao: int = 1) -> Opcoes:
        """As opções da caixa, no vocabulário de `core/editor/busca.py`."""
        rotulo = self.var_escopo.get()
        escopo = next((e for e, r in busca_mod.ROTULOS_DOS_ESCOPOS.items() if r == rotulo), "capitulo")
        valores = {nome: bool(var.get()) for nome, var in self.booleanas.items()}
        return Opcoes(texto=self.var_texto.get(), substituto=self.var_substituto.get(), escopo=escopo,
                      direcao=direcao, **valores)

    def definir(self, texto: str | None = None, substituto: str | None = None, escopo: str | None = None,
                **booleanas: bool) -> None:
        if texto is not None:
            self.var_texto.set(texto)
        if substituto is not None:
            self.var_substituto.set(substituto)
        if escopo is not None:
            self.var_escopo.set(busca_mod.ROTULOS_DOS_ESCOPOS[escopo])
        for nome, valor in booleanas.items():
            self.booleanas[nome].set(bool(valor))

    def registrar_no_historico(self) -> list[str]:
        texto = self.var_texto.get()
        antes = list(self.historico.itens)
        itens = self.historico.registrar(texto)
        if itens != antes:
            self.campo_texto.configure(values=list(itens))
            if self.ao_gravar_historico is not None:
                self.ao_gravar_historico(list(itens))
        return itens

    def foco(self, campo: str = "texto") -> None:
        alvo = self.campo_substituto if campo == "substituto" else self.campo_texto
        alvo.focus_set()
        try:
            alvo.selection_range(0, "end")
        except tk.TclError:
            pass

    def escopo_possivel(self, escopos: Sequence[str]) -> None:
        """Só os escopos que fazem sentido agora (sem seleção, "Seleção" sai da lista)."""
        self.campo_escopo.configure(values=[busca_mod.ROTULOS_DOS_ESCOPOS[e] for e in escopos])
        atual = self.var_escopo.get()
        if atual not in self.campo_escopo["values"]:
            self.var_escopo.set(busca_mod.ROTULOS_DOS_ESCOPOS["capitulo"])


# ----------------------------------------------------------------------
# O buscador: a ocorrência do modelo vira seleção na aba, e volta
# ----------------------------------------------------------------------

TAG_DA_MARCA = "suspeito"           # a tag de tela (fundo amarelo) que mostra o "texto marcado"


def chave_do_cursor(widget: Any, alvos: Sequence[busca_mod.Alvo], indice: str = "insert") -> tuple:
    """
    A chave `(índice do alvo, deslocamento)` da posição `indice` do `TextoRico` — comparável
    com `Ocorrencia.chave`. Numa célula de tabela, a chave da célula. Fora de todo alvo (um
    objeto), a do primeiro alvo que vem depois.
    """
    ativo = widget.ativo() if hasattr(widget, "ativo") else widget
    if ativo is not widget:
        grade = _grade_de(ativo)
        if grade is not None:
            f, c = grade.celula_atual()
            tabela_id = grade.tabela.id
            bloco_id, desloc = ativo.posicao_de(indice)
            k = ativo.ordem.index(bloco_id) if bloco_id in ativo.ordem else 0
            for alvo in alvos:
                if alvo.bloco_id == tabela_id and alvo.caminho[:3] == ("celula", f, c) and alvo.caminho[3] == k:
                    return (alvo.indice, desloc)
            for alvo in alvos:
                if alvo.bloco_id == tabela_id and alvo.caminho[:3] == ("celula", f, c):
                    return (alvo.indice, 0)
            bloco_id = tabela_id
            desloc = 0
        else:
            bloco_id, desloc = widget.posicao_de(indice)
    else:
        bloco_id, desloc = widget.posicao_de(indice)
    if bloco_id is None:
        return (len(alvos), 0)
    do_bloco = [a for a in alvos if a.bloco_id == bloco_id]
    escolhido = None
    for alvo in do_bloco:
        if alvo.deslocamento is not None and alvo.deslocamento <= desloc <= alvo.deslocamento + len(alvo.texto):
            escolhido = alvo
    if escolhido is not None:
        return (escolhido.indice, desloc - (escolhido.deslocamento or 0))
    if do_bloco:
        return (do_bloco[0].indice, 0)
    ordem = list(widget.ordem_do_capitulo) if hasattr(widget, "ordem_do_capitulo") else []
    ordem += [i for i in widget.ordem if i not in ordem]
    posicao = ordem.index(bloco_id) if bloco_id in ordem else len(ordem)
    for alvo in alvos:
        if alvo.bloco_id in ordem and ordem.index(alvo.bloco_id) > posicao:
            return (alvo.indice, 0)
    return (len(alvos), 0)


def _grade_de(celula: Any) -> Any:
    from ui.editor.tabela import GradeDeTabela

    w = getattr(celula, "master", None)
    while w is not None and not isinstance(w, GradeDeTabela):
        w = getattr(w, "master", None)
    return w


def selecionar_ocorrencia(widget: Any, ocorrencia: busca_mod.Ocorrencia) -> bool:
    """A ocorrência vira a seleção no widget (texto rico ou editor de código); `False` se não deu."""
    if ocorrencia.cru:
        texto = widget.texto
        ini, fim = f"1.0+{ocorrencia.ini}c", f"1.0+{ocorrencia.fim}c"
        texto.tag_remove("sel", "1.0", "end")
        texto.tag_add("sel", ini, fim)
        texto.mark_set("insert", fim)
        texto.see(ini)
        return True
    alvo = ocorrencia.alvo
    assert alvo is not None
    caminho = alvo.caminho
    if alvo.enderecavel:
        base = alvo.deslocamento or 0
        if alvo.bloco_id not in widget.ordem:
            return False
        widget.selecionar(base + ocorrencia.ini, base + ocorrencia.fim, alvo.bloco_id)
        widget.texto.see("insert")
        return True
    if caminho[0] == "celula":
        grade = widget.widget_do_objeto(alvo.bloco_id)
        if grade is None or not hasattr(grade, "celula"):
            widget.selecionar_objeto(alvo.bloco_id)
            return True
        _c, f, c, k = caminho
        celula = grade.entrar(f, c)
        ordem = celula.ordem
        if k < len(ordem):
            celula.selecionar(ocorrencia.ini, ocorrencia.fim, ordem[k])
        return True
    widget.selecionar_objeto(alvo.bloco_id)
    return True


def aplicar_no_widget(widget: Any, cap: Any, ocorrencia: busca_mod.Ocorrencia, novo: str) -> None:
    """A substituição de uma ocorrência feita **no widget** (que registra o ponto de desfazer)."""
    if ocorrencia.cru:
        widget.substituir_intervalo(f"1.0+{ocorrencia.ini}c", f"1.0+{ocorrencia.fim}c", novo)
        return
    alvo = ocorrencia.alvo
    assert alvo is not None
    caminho = alvo.caminho
    if caminho[0] == "nota":
        nota = cap.nota(caminho[1])
        if nota is None:
            raise ValueError(f"a nota {caminho[1]} já não existe")
        paragrafo = nota.blocos[caminho[2]]
        novo_paragrafo = busca_mod.substituir_no_paragrafo(paragrafo, ocorrencia.ini, ocorrencia.fim, novo)
        widget._reescrever_bloco(paragrafo.id, novo_paragrafo)
        widget.ir_para(paragrafo.id, ocorrencia.ini + len(novo))
        return
    if caminho[0] == "celula":
        grade = widget.widget_do_objeto(alvo.bloco_id)
        if grade is not None and hasattr(grade, "celula"):
            _c, f, c, k = caminho
            celula = grade.celula(f, c)
            ordem = celula.ordem
            if k < len(ordem):
                paragrafo = celula.modelo_de(ordem[k])
                novo_paragrafo = busca_mod.substituir_no_paragrafo(paragrafo, ocorrencia.ini, ocorrencia.fim, novo)
                celula._reescrever_bloco(ordem[k], novo_paragrafo)
                celula.ir_para(ordem[k], ocorrencia.ini + len(novo))
                return
    novo_bloco = busca_mod.bloco_substituido(cap, ocorrencia, novo)
    from ui.editor.texto_rico import TIPOS_DE_OBJETO

    if isinstance(novo_bloco, TIPOS_DE_OBJETO):
        widget.substituir_objeto(alvo.bloco_id, novo_bloco)
    else:
        widget._reescrever_bloco(alvo.bloco_id, novo_bloco)
        if alvo.enderecavel:
            widget.ir_para(alvo.bloco_id, (alvo.deslocamento or 0) + ocorrencia.ini + len(novo))


class Buscador:
    """
    Os comandos da §8.12 na janela: sabe qual aba está ativa e em que modo, procura no
    widget (a aba aberta) ou no modelo (o capítulo fechado), e traduz a ocorrência em
    seleção. `atual` é a ocorrência selecionada (a que "Substituir" troca).
    """

    def __init__(self, janela: Any, painel: PainelDeBusca):
        self.j = janela
        self.painel = painel
        self.atual: busca_mod.Ocorrencia | None = None
        self.marcas: dict[str, Any] = {}            # arquivo → o "texto marcado" (§8.12)
        self.comandos = {
            "localizar": self.localizar, "substituir": self.substituir,
            "localizar_proximo": lambda: self.localizar_seguinte(1),
            "localizar_anterior": lambda: self.localizar_seguinte(-1),
            "substituir_atual": self.substituir_atual, "substituir_e_localizar": self.substituir_e_localizar,
            "substituir_todos": self.substituir_todos, "contar_ocorrencias": self.contar,
            "listar_ocorrencias": self.listar, "marcar_texto": self.marcar_texto,
            "marcar_arquivo": self.marcar_arquivo,
        }

    # -- abrir a caixa ------------------------------------------------------

    def _mostrar(self, campo: str) -> None:
        j = self.j
        if not j.paineis["busca"].visivel:
            j.mostrar_painel("busca", True)
        j._focar_inferior(self.painel)
        editor = j.editor_ativo()
        if editor is not None:
            selecao = editor.selecao()
            if selecao:
                texto = editor.texto.get(*selecao)
                if 0 < len(texto) <= 200 and "\n" not in texto:
                    self.painel.definir(texto=texto)
        escopos = list(busca_mod.ESCOPOS)
        if editor is None or not editor.selecao():
            escopos.remove("selecao")
        self.painel.escopo_possivel(escopos)
        self.painel.foco(campo)

    def localizar(self) -> None:
        self._mostrar("texto")

    def substituir(self) -> None:
        self._mostrar("substituto")

    # -- os arquivos e as ocorrências de cada um ----------------------------

    def _opcoes(self, direcao: int = 1) -> busca_mod.Opcoes:
        return self.painel.opcoes(direcao)

    def _arquivos(self, opcoes: busca_mod.Opcoes) -> list[str]:
        """Os capítulos do escopo, na ordem da espinha."""
        j = self.j
        projeto = j._exigir_projeto()
        aba = j.aba_ativa()
        capitulos = [c.arquivo for c in projeto.livro.capitulos]
        if opcoes.escopo in ("capitulo", "selecao", "marcado"):
            if aba is None or aba.tipo not in ("capitulo", "recurso"):
                raise ValueError("abra um capítulo para procurar nele")
            return [aba.arquivo]
        if opcoes.escopo == "livro":
            return capitulos
        if opcoes.escopo == "abas":
            abertas = {a.arquivo for a in j.abas.abas if a.tipo == "capitulo"}
            return [c for c in capitulos if c in abertas]
        marcados = set(getattr(j, "arquivos_marcados", ()))
        if not marcados:
            raise ValueError("nenhum arquivo marcado: use Editar → Marcar arquivo para a busca")
        return [c for c in capitulos if c in marcados]

    def _ocorrencias(self, arquivo: str, padrao: Any, opcoes: busca_mod.Opcoes) -> list[busca_mod.Ocorrencia]:
        j = self.j
        aba = j.abas.por_arquivo(arquivo)
        if aba is not None and aba.widget is not None:
            if aba.modo == "texto":
                cap = aba.widget.sincronizar()
                ocorrencias = busca_mod.procurar_em_alvos(busca_mod.alvos_do_capitulo(cap), padrao)
            else:
                ocorrencias = busca_mod.procurar_no_cru(aba.widget.texto_todo(), padrao, arquivo)
            if aba is j.aba_ativa():
                ocorrencias = self._filtrar(aba, ocorrencias, opcoes)
            return ocorrencias
        cap = j._exigir_projeto().livro.capitulo(arquivo)
        if cap is None:
            return []
        return busca_mod.procurar_no_capitulo(cap, padrao)

    def _filtrar(self, aba: Any, ocorrencias: list[busca_mod.Ocorrencia],
                 opcoes: busca_mod.Opcoes) -> list[busca_mod.Ocorrencia]:
        """Só o que cai na seleção ou no texto marcado, quando o escopo é um deles."""
        if opcoes.escopo == "selecao":
            faixa = self._faixa_da_selecao(aba)
            if faixa is None:
                raise ValueError("não há seleção: escolha outro escopo")
        elif opcoes.escopo == "marcado":
            faixa = self.marcas.get(aba.arquivo)
            if faixa is None:
                raise ValueError("não há texto marcado neste arquivo (Editar → Marcar texto para a busca)")
        else:
            return ocorrencias
        ini, fim = faixa
        return [o for o in ocorrencias if ini <= o.chave and o.chave[:-1] + (o.fim,) <= fim]

    def _faixa_da_selecao(self, aba: Any) -> tuple[tuple, tuple] | None:
        editor = aba.widget
        ativo = editor.ativo() if hasattr(editor, "ativo") else editor
        selecao = ativo.selecao()
        if not selecao:
            return None
        if aba.modo == "codigo":
            return self._chaves_do_cru(editor, selecao[0]), self._chaves_do_cru(editor, selecao[1])
        alvos = busca_mod.alvos_do_capitulo(editor.sincronizar())
        return chave_do_cursor(editor, alvos, selecao[0]), chave_do_cursor(editor, alvos, selecao[1])

    @staticmethod
    def _chaves_do_cru(editor: Any, indice: str) -> tuple:
        n = editor.texto.count("1.0", indice, "chars")
        n = int(n[0]) if isinstance(n, (tuple, list)) else int(n or 0)
        return (n,)

    def _chave_atual(self, aba: Any, direcao: int, alvos: Sequence[busca_mod.Alvo] | None) -> tuple:
        editor = aba.widget
        ativo = editor.ativo() if hasattr(editor, "ativo") else editor
        selecao = ativo.selecao()
        indice = selecao[0] if (selecao and direcao < 0) else (selecao[1] if selecao else "insert")
        if aba.modo == "codigo":
            return self._chaves_do_cru(editor, indice)
        return chave_do_cursor(editor, alvos or [], indice)

    # -- localizar --------------------------------------------------------

    def localizar_seguinte(self, direcao: int = 1) -> busca_mod.Ocorrencia | None:
        j = self.j
        opcoes = self._opcoes(direcao)
        padrao = busca_mod.compilar(opcoes)
        self.painel.registrar_no_historico()
        arquivos = self._arquivos(opcoes)
        aba = j.aba_ativa()
        atual = aba.arquivo if aba is not None and aba.arquivo in arquivos else None
        if atual is None:
            ordem = list(arquivos) if direcao > 0 else list(reversed(arquivos))
        else:
            k = arquivos.index(atual)
            ordem = (arquivos[k:] + arquivos[:k]) if direcao > 0 else (arquivos[k::-1] + arquivos[:k:-1])
        deu_a_volta = False
        for n, arquivo in enumerate(ordem):
            ocorrencias = self._ocorrencias(arquivo, padrao, opcoes)
            if not ocorrencias:
                continue
            if n == 0 and atual is not None:
                alvos = busca_mod.alvos_do_capitulo(aba.widget.sincronizar()) if aba.modo == "texto" else None
                chave = self._chave_atual(aba, direcao, alvos)
                achada, _volta = busca_mod.proxima(ocorrencias, chave, direcao, circular=False)
                if achada is None:
                    if len(ordem) == 1 and opcoes.circular:
                        achada = ocorrencias[0] if direcao > 0 else ocorrencias[-1]
                        deu_a_volta = True
                    else:
                        continue
            else:
                achada = ocorrencias[0] if direcao > 0 else ocorrencias[-1]
            self._ir(arquivo, achada)
            total = len(ocorrencias)
            posicao = ocorrencias.index(achada) + 1
            aviso = " (voltou ao início)" if deu_a_volta else ""
            j.status(f"{posicao} de {total} em {arquivo}{aviso}")
            return achada
        if atual is not None and opcoes.circular and len(ordem) > 1:
            ocorrencias = self._ocorrencias(atual, padrao, opcoes)
            if ocorrencias:
                achada = ocorrencias[0] if direcao > 0 else ocorrencias[-1]
                self._ir(atual, achada)
                j.status(f"1 de {len(ocorrencias)} em {atual} (voltou ao início)")
                return achada
        self.atual = None
        j.status(f"“{opcoes.texto}” não encontrado" + ("" if opcoes.circular else " a partir do cursor"))
        return None

    def _ir(self, arquivo: str, ocorrencia: busca_mod.Ocorrencia) -> None:
        j = self.j
        aba = j.abas.por_arquivo(arquivo)
        if aba is None:
            projeto = j._exigir_projeto()
            if projeto.livro.capitulo(arquivo) is not None:
                aba = j.abrir_capitulo(arquivo, modo="codigo" if ocorrencia.cru else None)
            else:
                aba = j.abrir_recurso(arquivo)
        else:
            j.abas.selecionar(aba)
            j._trocou_de_aba(aba)
        if ocorrencia.cru and aba.modo != "codigo":
            aba = j.abrir_capitulo(arquivo, modo="codigo")
        selecionar_ocorrencia(aba.widget, ocorrencia)
        self.atual = ocorrencia
        try:
            aba.widget.foco()
        except Exception:      # noqa: BLE001 — uma janela escondida não dá foco
            pass

    # -- substituir ---------------------------------------------------------

    def _ocorrencia_selecionada(self, padrao: Any, opcoes: busca_mod.Opcoes) -> busca_mod.Ocorrencia | None:
        """A ocorrência que a seleção atual é — recalculada, porque o texto pode ter mudado."""
        j = self.j
        aba = j.aba_ativa()
        if aba is None or aba.widget is None:
            return None
        editor = aba.widget
        ativo = editor.ativo() if hasattr(editor, "ativo") else editor
        selecao = ativo.selecao()
        if not selecao:
            return None
        texto_selecionado = ativo.texto.get(*selecao)
        ocorrencias = self._ocorrencias(aba.arquivo, padrao, opcoes)
        if aba.modo == "codigo":
            chave = self._chaves_do_cru(editor, selecao[0])
        else:
            alvos = busca_mod.alvos_do_capitulo(editor.sincronizar())
            chave = chave_do_cursor(editor, alvos, selecao[0])
        for o in ocorrencias:
            if o.chave == chave and o.texto == texto_selecionado:
                return o
        if self.atual is not None:
            for o in ocorrencias:
                if o.chave == self.atual.chave and o.texto == self.atual.texto == texto_selecionado:
                    return o
        return None

    def substituir_atual(self) -> str | None:
        j = self.j
        opcoes = self._opcoes()
        padrao = busca_mod.compilar(opcoes)
        aba = j.aba_ativa()
        if aba is None:
            raise ValueError("Nenhuma aba aberta.")
        if aba.somente_leitura:
            raise ValueError(f"{aba.nome} abre só para leitura.")
        ocorrencia = self._ocorrencia_selecionada(padrao, opcoes)
        if ocorrencia is None:
            raise ValueError("selecione uma ocorrência primeiro (Localizar próximo)")
        novo = busca_mod.expandir(ocorrencia, opcoes.substituto, opcoes)
        cap = aba.widget.sincronizar() if aba.modo == "texto" else None
        aplicar_no_widget(aba.widget, cap, ocorrencia, novo)
        self.atual = None
        j.status(f"Substituído: “{ocorrencia.texto}” → “{novo}”")
        return novo

    def substituir_e_localizar(self) -> busca_mod.Ocorrencia | None:
        self.substituir_atual()
        return self.localizar_seguinte(self._opcoes().direcao)

    def substituir_todos(self) -> dict[str, int]:
        j = self.j
        projeto = j._exigir_projeto()
        opcoes = self._opcoes()
        padrao = busca_mod.compilar(opcoes)
        self.painel.registrar_no_historico()
        contagem: dict[str, int] = {}
        for arquivo in self._arquivos(opcoes):
            aba = j.abas.por_arquivo(arquivo)
            if aba is not None and aba.widget is not None:
                if aba.somente_leitura:
                    continue
                ocorrencias = self._ocorrencias(arquivo, padrao, opcoes)
                if not ocorrencias:
                    continue
                if aba.modo == "codigo":
                    if aba is j.aba_ativa() and opcoes.escopo in ("selecao", "marcado"):
                        with aba.widget._grupo():
                            for o in reversed(ocorrencias):
                                aplicar_no_widget(aba.widget, None, o,
                                                  busca_mod.expandir(o, opcoes.substituto, opcoes))
                        n = len(ocorrencias)
                    else:
                        n = aba.widget.substituir_todos(
                            padrao, lambda m: busca_mod.expandir(
                                busca_mod.Ocorrencia(arquivo, m.start(), m.end(), m.group(0), None, m),
                                opcoes.substituto, opcoes))
                else:
                    widget = aba.widget
                    widget._abrir_composto("substituir todos")
                    try:
                        for o in reversed(ocorrencias):
                            cap = widget.sincronizar()
                            aplicar_no_widget(widget, cap, o, busca_mod.expandir(o, opcoes.substituto, opcoes))
                    finally:
                        widget._fechar_composto()
                    n = len(ocorrencias)
            else:
                cap = projeto.livro.capitulo(arquivo)
                if cap is None:
                    continue
                n = busca_mod.substituir_tudo_no_capitulo(cap, padrao, opcoes.substituto, opcoes,
                                                          historico=projeto.historico)
                if n:
                    projeto.marcar_sujo()
            if n:
                contagem[arquivo] = n
        total = sum(contagem.values())
        self.atual = None
        from ui.editor.resultados import Resultado

        j.resultados.definir([Resultado(a, "", f"{n} substituição(ões)") for a, n in contagem.items()],
                             f"Substituir todos: {total} em {len(contagem)} arquivo(s)")
        j.status(f"{total} substituição(ões) em {len(contagem)} arquivo(s)")
        j.log.info("Substituir todos: %r → %r: %d em %d arquivo(s).", opcoes.texto, opcoes.substituto, total,
                   len(contagem))
        j.atualizar()
        return contagem

    # -- contar e listar ------------------------------------------------------

    def contar(self) -> dict[str, int]:
        j = self.j
        opcoes = self._opcoes()
        padrao = busca_mod.compilar(opcoes)
        contagem = {}
        for arquivo in self._arquivos(opcoes):
            n = len(self._ocorrencias(arquivo, padrao, opcoes))
            if n:
                contagem[arquivo] = n
        total = sum(contagem.values())
        j.status(f"“{opcoes.texto}”: {total} ocorrência(s) em {len(contagem)} arquivo(s)")
        j.caixas.informar("\n".join([f"“{opcoes.texto}”: {total} ocorrência(s)"]
                                    + [f"  {a}: {n}" for a, n in contagem.items()]), "Contar")
        return contagem

    def listar(self) -> list:
        j = self.j
        from ui.editor.resultados import Resultado

        opcoes = self._opcoes()
        padrao = busca_mod.compilar(opcoes)
        self.painel.registrar_no_historico()
        itens = []
        for arquivo in self._arquivos(opcoes):
            for o in self._ocorrencias(arquivo, padrao, opcoes):
                dados: dict[str, Any] = {"comprimento": o.fim - o.ini}
                if o.cru:
                    dados.update(linha=o.linha, coluna=o.coluna)
                elif o.alvo is not None and o.alvo.enderecavel:
                    dados.update(bloco=o.alvo.bloco_id, deslocamento=(o.alvo.deslocamento or 0) + o.ini)
                elif o.alvo is not None:
                    dados.update(bloco=o.alvo.bloco_id)
                itens.append(Resultado(arquivo, o.onde, o.contexto, dados))
        j.resultados.definir(itens, f"“{opcoes.texto}”: {len(itens)} ocorrência(s)")
        j._focar_inferior(j.resultados, j.resultados.foco)
        j.status(f"{len(itens)} ocorrência(s) listada(s)")
        return itens

    # -- marcar ---------------------------------------------------------------

    def marcar_texto(self) -> bool:
        """Com seleção, marca-a como o escopo "texto marcado"; sem seleção, desmarca."""
        j = self.j
        aba = j.aba_ativa()
        if aba is None or aba.widget is None:
            raise ValueError("Nenhuma aba aberta.")
        editor = aba.widget
        ativo = editor.ativo() if hasattr(editor, "ativo") else editor
        selecao = ativo.selecao()
        texto = ativo.texto
        texto.tag_remove(TAG_DA_MARCA, "1.0", "end")
        if not selecao:
            self.marcas.pop(aba.arquivo, None)
            j.status("Marca de texto retirada.")
            return False
        faixa = self._faixa_da_selecao(aba)
        assert faixa is not None
        self.marcas[aba.arquivo] = faixa
        if aba.modo == "codigo":
            texto.tag_configure(TAG_DA_MARCA, background="#fff3a0")
        texto.tag_add(TAG_DA_MARCA, *selecao)
        self.painel.definir(escopo="marcado")
        j.status("Texto marcado para a busca (escopo “Texto marcado”).")
        return True

    def marcar_arquivo(self, arquivo: str | None = None) -> bool:
        """Alterna a marca do arquivo focado no navegador (ou da aba ativa) para o escopo "arquivos marcados"."""
        j = self.j
        if arquivo is None:
            iid = j.navegador.focus()
            if iid and not iid.startswith("grupo:"):
                arquivo = iid
            else:
                aba = j.aba_ativa()
                arquivo = aba.arquivo if aba is not None else None
        if not arquivo:
            raise ValueError("escolha um arquivo no navegador")
        marcados = j.arquivos_marcados
        if arquivo in marcados:
            marcados.discard(arquivo)
            marcado = False
        else:
            marcados.add(arquivo)
            marcado = True
        j.atualizar_navegador()
        try:
            j.navegador.focus(arquivo)
            j.navegador.selection_set(arquivo)
        except Exception:      # noqa: BLE001 — a entrada pode não existir mais
            pass
        j.status(f"{arquivo}: {'marcado' if marcado else 'desmarcado'} para a busca ({len(marcados)} marcado(s))")
        return marcado


__all__ = ["PainelDeBusca", "CAMPOS_BOOLEANOS", "BOTOES", "Buscador", "chave_do_cursor", "selecionar_ocorrencia",
           "aplicar_no_widget", "TAG_DA_MARCA"]
