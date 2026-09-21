"""
A grade de tabela do modo texto (ED-04; SPEC_EDITOR §8.6).

Uma `Tabela` do modelo entra no `tk.Text` do capítulo como um objeto (`window_create`)
que é esta grade: um `ttk.Frame` com uma célula `TextoRico` por `Celula`, criada em
modo célula (sem calha nem barra, uma linha de altura que cresce com o texto — `count
-displaylines` depois de cada mudança). Cada célula é um editor completo: negrito,
link, nota de rodapé, dois parágrafos — tudo o que um `<td>` do dialeto aceita.

## O modelo é vivo

A grade não guarda o modelo entre edições: `modelo()` sincroniza as células e monta a
`Tabela` na hora, e é isso que o `RegistroDeObjetos` do texto de fora pergunta
(`atualizar`) quando o `dump` chega ao objeto. Toda edição numa célula avisa o texto
de fora (`ao_mudar`), que relê o bloco pelo registro e registra **um ponto de desfazer
sobre a tabela inteira** — desfazer redesenha o capítulo, e a grade nasce de novo do
modelo (DEC-04). Por isso a célula delega `desfazer`/`refazer` ao dono.

## Teclado

`Tab`/`Shift+Tab` entre células (na última, `Tab` cria uma fila); `Esc` sai para o
texto de fora; seta para cima na primeira linha sobe de célula e, na primeira fila, sai
para o bloco anterior; seta para baixo faz o simétrico; a roda do mouse rola o texto de
fora. `Enter` sobre a tabela (no texto de fora) entra na primeira célula (`entrar()`).
Sem mesclar, sem aninhar, e no máximo `LIMITE` células — acima disso a tabela é
desenhada como caixa (edita-se no modo código).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from core.editor.modelo import Celula, Paragrafo, Tabela

LIMITE = 400
COR_DA_GRADE = "#9a9a9a"
FUNDO_DO_CABECALHO = "#eeeeee"
FUNDO_SELECIONADO = "#b8d4ff"


class GradeDeTabela(ttk.Frame):
    def __init__(self, master: tk.Misc, tabela: Tabela,
                 criar_celula: Callable[[tk.Misc, Sequence[Paragrafo]], Any],
                 ao_mudar: Callable[[bool], Any] | None = None, ao_sair: Callable[[int], Any] | None = None,
                 ao_ativar: Callable[[Any], Any] | None = None, largura_px: int = 480, **kw: Any):
        super().__init__(master, **kw)
        if len(tabela.filas) * tabela.colunas > LIMITE:
            raise ValueError(f"tabela com {len(tabela.filas) * tabela.colunas} células passa do limite de {LIMITE}")
        self.tabela = tabela
        self.criar_celula = criar_celula
        self.ao_mudar = ao_mudar
        self.ao_sair = ao_sair
        self.ao_ativar = ao_ativar
        self.largura_px = int(largura_px)
        self.objeto = tabela
        self.inline = False
        self.celulas: list[list[Any]] = []
        self._cabecalhos: list[list[bool]] = []
        self._alinhamentos: list[list[str]] = []
        self._selecionada = False
        self._montando = False
        self._atual: tuple[int, int] = (0, 0)      # a ultima celula em que se entrou (vale sem foco real)
        self.legenda = tk.Label(self, text="", foreground="#444444", background="#ffffff", anchor="w")
        self.grade = tk.Frame(self, background=COR_DA_GRADE, takefocus=0)
        self._ajuste_agendado: str | None = None
        # A altura das celulas depende da largura de verdade: refeita quando a grade aparece ou muda de tamanho.
        self.grade.bind("<Configure>", lambda e: self._agendar_ajuste(), add="+")
        self.grade.bind("<Map>", lambda e: self._agendar_ajuste(), add="+")
        self._montar(tabela)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar(self, tabela: Tabela) -> None:
        self._montando = True
        try:
            for fila in self.celulas:
                for celula in fila:
                    try:
                        celula.destroy()
                    except tk.TclError:
                        pass
            self.celulas = []
            self._cabecalhos = [[c.cabecalho for c in fila] for fila in tabela.filas]
            self._alinhamentos = [[c.alinhamento for c in fila] for fila in tabela.filas]
            self.tabela = tabela
            self._rotular_legenda()
            colunas = max(1, tabela.colunas)
            largura_chars = max(6, min(40, (self.largura_px // 8) // colunas))
            for f, fila in enumerate(tabela.filas):
                linha = []
                for c, celula in enumerate(fila):
                    editor = self.criar_celula(self.grade, list(celula.blocos))
                    editor.texto.configure(width=largura_chars)
                    self._ligar_celula(editor, f, c)
                    if celula.cabecalho:
                        editor.texto.configure(background=FUNDO_DO_CABECALHO)
                    editor.grid(row=f, column=c, sticky="nsew", padx=1, pady=1)
                    linha.append(editor)
                self.celulas.append(linha)
            for c in range(colunas):
                self.grade.columnconfigure(c, weight=1)
            self.grade.pack(fill="x")
        finally:
            self._montando = False

    def _rotular_legenda(self) -> None:
        """A legenda (com o numero) acima da grade; sem legenda nem numero, nada."""
        tabela = self.tabela
        texto = "".join(t.texto for t in tabela.legenda)
        if tabela.numero is not None:
            texto = f"Tabela {tabela.numero}" + (f". {texto}" if texto else "")
        self.legenda.pack_forget()
        self.grade.pack_forget()
        if texto:
            self.legenda.configure(text=texto)
            self.legenda.pack(fill="x")

    def _ligar_celula(self, editor: Any, f: int, c: int) -> None:
        editor.ao_tab = lambda direcao, f=f, c=c: self._tab(f, c, direcao)
        editor.ao_escape = lambda f=f, c=c: self.sair(0)
        editor.ao_sair_vertical = lambda direcao, f=f, c=c: self._vertical(f, c, direcao)
        editor.ao_sair_horizontal = lambda direcao, f=f, c=c: self._horizontal(f, c, direcao)
        editor.texto.bind("<<Mudou>>", lambda e, ed=editor: self._mudou(ed), add="+")
        editor.texto.bind("<FocusIn>", lambda e, f=f, c=c: self._entrou(f, c), add="+")

    def _agendar_ajuste(self) -> None:
        if self._ajuste_agendado is not None:
            return
        try:
            self._ajuste_agendado = self.after_idle(self.ajustar_alturas)
        except tk.TclError:
            self._ajuste_agendado = None

    def ajustar_alturas(self) -> None:
        """A altura de cada célula pelas linhas exibidas (o que a largura real da grade decide)."""
        self._ajuste_agendado = None
        for fila in self.celulas:
            for editor in fila:
                try:
                    editor.ajustar_altura()
                except tk.TclError:
                    pass

    def _entrou(self, f: int, c: int) -> None:
        self._atual = (f, c)
        self.selecionar(False)

    def _mudou(self, editor: Any) -> None:
        if self._montando:
            return
        editor.ajustar_altura()
        if self.ao_mudar is not None:
            self.ao_mudar(False)          # edicao de texto: coalesce com a digitacao

    # ------------------------------------------------------------------
    # O modelo
    # ------------------------------------------------------------------

    def modelo(self) -> Tabela:
        """A `Tabela` atual: as células sincronizadas, os cabeçalhos e alinhamentos, a legenda e o resto."""
        base = self.tabela
        filas: list[list[Celula]] = []
        for f, fila in enumerate(self.celulas):
            saida = []
            for c, editor in enumerate(fila):
                blocos = editor.sincronizar()
                if not isinstance(blocos, list):
                    blocos = list(blocos.blocos)
                paragrafos = [b for b in blocos if isinstance(b, Paragrafo)]
                if len(paragrafos) == 1 and not paragrafos[0].trechos and not self._tinha_paragrafo(f, c):
                    paragrafos = []
                saida.append(Celula(blocos=paragrafos, cabecalho=self._cabecalhos[f][c],
                                    alinhamento=self._alinhamentos[f][c]))
            filas.append(saida)
        cabecalho = bool(filas and filas[0] and all(c.cabecalho for c in filas[0]))
        nova = Tabela(filas=filas, primeira_fila_cabecalho=cabecalho, legenda=list(base.legenda),
                      numero=base.numero, largura_pct=base.largura_pct, id=base.id,
                      id_persistente=base.id_persistente, classe=base.classe, extras=dict(base.extras),
                      origem=base.origem, linha_fonte=base.linha_fonte)
        self.tabela = nova
        return nova

    def _tinha_paragrafo(self, f: int, c: int) -> bool:
        try:
            return bool(self.tabela.filas[f][c].blocos)
        except IndexError:
            return False

    @property
    def texto(self) -> str:
        return f"Tabela: {len(self.celulas)}×{len(self.celulas[0]) if self.celulas else 0}"

    def dica(self) -> str:
        return "Tab e Shift+Tab entre células; Esc sai; Alt+Enter: propriedades"

    def selecionar(self, sim: bool) -> None:
        self._selecionada = bool(sim)
        self.grade.configure(background=FUNDO_SELECIONADO if sim else COR_DA_GRADE)

    def atualizar(self, tabela: Tabela) -> None:
        """Propriedades aplicadas de fora (legenda, cabeçalho, largura): redesenha do modelo dado."""
        foco = self.celula_com_foco()
        self._montar(tabela)
        if foco is not None:
            self.entrar(*foco)
        else:
            self._atual = (0, 0)

    # ------------------------------------------------------------------
    # Foco e navegação
    # ------------------------------------------------------------------

    def celula_com_foco(self) -> tuple[int, int] | None:
        """`(fila, coluna)` da célula com o foco de verdade; `None` quando o foco está fora da grade."""
        try:
            foco = self.focus_get()
        except (tk.TclError, KeyError):
            return None
        for f, fila in enumerate(self.celulas):
            for c, editor in enumerate(fila):
                if foco is editor.texto:
                    return f, c
        return None

    def celula_atual(self) -> tuple[int, int]:
        """A célula corrente: a com o foco, senão a última em que se entrou (a janela pode não ter foco)."""
        foco = self.celula_com_foco()
        if foco is not None:
            self._atual = foco
        f, c = self._atual
        if not self.celulas:
            return 0, 0
        return max(0, min(f, len(self.celulas) - 1)), max(0, min(c, len(self.celulas[0]) - 1))

    def celula(self, f: int, c: int) -> Any:
        return self.celulas[f][c]

    def entrar(self, f: int = 0, c: int = 0) -> Any:
        """Foco na célula (a primeira por omissão), com o cursor no fim dela."""
        if not self.celulas:
            return None
        f = max(0, min(f, len(self.celulas) - 1))
        c = max(0, min(c, len(self.celulas[f]) - 1))
        editor = self.celulas[f][c]
        self._atual = (f, c)
        editor.foco()
        editor.ir_para_o_fim()
        return editor

    def sair(self, direcao: int = 0) -> None:
        """Devolve o foco ao texto de fora: antes da tabela (−1), depois (+1) ou sobre ela (0)."""
        if self.ao_sair is not None:
            self.ao_sair(direcao)

    def _posicao_seguinte(self, f: int, c: int, direcao: int) -> tuple[int, int] | None:
        colunas = len(self.celulas[0]) if self.celulas else 0
        n = f * colunas + c + direcao
        if n < 0 or n >= len(self.celulas) * colunas:
            return None
        return divmod(n, colunas)

    def proxima_celula(self) -> Any:
        """`Tab`: a célula seguinte; na última, cria uma fila e vai à primeira célula dela."""
        atual = self.celula_atual()
        alvo = self._posicao_seguinte(*atual, 1)
        if alvo is None:
            self.inserir_fila(depois=True, fila=len(self.celulas) - 1)
            alvo = (len(self.celulas) - 1, 0)
        return self.entrar(*alvo)

    def celula_anterior(self) -> Any:
        atual = self.celula_atual()
        alvo = self._posicao_seguinte(*atual, -1)
        if alvo is None:
            self.sair(-1)
            return None
        return self.entrar(*alvo)

    def _tab(self, f: int, c: int, direcao: int) -> bool:
        if direcao > 0:
            self.proxima_celula()
        else:
            self.celula_anterior()
        return True

    def _vertical(self, f: int, c: int, direcao: int) -> bool:
        alvo = f + direcao
        if 0 <= alvo < len(self.celulas):
            self.entrar(alvo, c)
        else:
            self.sair(direcao)
        return True

    def _horizontal(self, f: int, c: int, direcao: int) -> bool:
        alvo = self._posicao_seguinte(f, c, direcao)
        if alvo is None:
            self.sair(direcao)
        else:
            self.entrar(*alvo)
        return True

    # ------------------------------------------------------------------
    # Filas e colunas (Formatar → Tabela ▸)
    # ------------------------------------------------------------------

    def _reconstruir(self, tabela: Tabela, foco: tuple[int, int] | None) -> Tabela:
        self._montar(tabela)
        if foco is not None:
            self.entrar(*foco)
        if self.ao_mudar is not None:
            self.ao_mudar(True)           # mudanca de estrutura: um ponto proprio
        return tabela

    def _fila_e_coluna(self, fila: int | None, coluna: int | None) -> tuple[int, int]:
        atual = self.celula_atual()
        return (atual[0] if fila is None else fila), (atual[1] if coluna is None else coluna)

    def inserir_fila(self, depois: bool = True, fila: int | None = None) -> Tabela:
        atual = self.modelo()
        f, _c = self._fila_e_coluna(fila, None)
        nova = [Celula(blocos=[]) for _ in range(atual.colunas)]
        filas = list(atual.filas)
        filas.insert(f + 1 if depois else f, nova)
        atual.filas = filas
        atual.primeira_fila_cabecalho = bool(filas[0] and all(c.cabecalho for c in filas[0]))
        return self._reconstruir(atual, (f + 1 if depois else f, 0))

    def inserir_coluna(self, depois: bool = True, coluna: int | None = None) -> Tabela:
        atual = self.modelo()
        f, c = self._fila_e_coluna(None, coluna)
        alvo = c + 1 if depois else c
        for k, fila in enumerate(atual.filas):
            fila.insert(alvo, Celula(blocos=[], cabecalho=bool(k == 0 and atual.primeira_fila_cabecalho)))
        return self._reconstruir(atual, (f, alvo))

    def excluir_fila(self, fila: int | None = None) -> Tabela:
        atual = self.modelo()
        f, c = self._fila_e_coluna(fila, None)
        if len(atual.filas) <= 1:
            raise ValueError("a tabela tem uma fila só: para tirá-la, apague a tabela")
        del atual.filas[f]
        return self._reconstruir(atual, (min(f, len(atual.filas) - 1), c))

    def excluir_coluna(self, coluna: int | None = None) -> Tabela:
        atual = self.modelo()
        f, c = self._fila_e_coluna(None, coluna)
        if atual.colunas <= 1:
            raise ValueError("a tabela tem uma coluna só: para tirá-la, apague a tabela")
        for fila in atual.filas:
            del fila[c]
        return self._reconstruir(atual, (f, min(c, atual.colunas - 1)))

    def alternar_cabecalho(self) -> Tabela:
        """A primeira fila passa a (ou deixa de) ser cabeçalho — `<th>` em toda célula dela."""
        atual = self.modelo()
        ligar = not atual.primeira_fila_cabecalho
        for celula in atual.filas[0]:
            celula.cabecalho = ligar
        atual.primeira_fila_cabecalho = ligar
        return self._reconstruir(atual, self.celula_com_foco() or self._atual)


__all__ = ["GradeDeTabela", "LIMITE"]
