"""
Uma caixa só para exportar o livro: o arquivo, as páginas, a leitura e o diagrama.

Até 2026-09-18 a exportação era um assistente de até **catorze caixas
modais** em sequência — arquivo, intervalo (duas), destino, redesenhar,
fonte embutida, coordenadas (duas), a caixa do diagrama, idioma, coletar,
teto, reparo de colagem, modelo de linha —, sem voltar, sem ver o conjunto, e
sem memória: quem exportava o mesmo livro pela terceira vez respondia as
catorze de novo. `config/settings.py` existia para guardar escolhas e nunca
tinha sido instanciado.

Aqui é um formulário: o que se escolhe fica visível junto, cada escolha
explica o custo dela na própria linha (o reparo de colagem é doze vezes mais
lento; o modelo de linha só entra se passa no portão), e o que foi escolhido
da última vez volta preenchido (`Settings`, chave `exportacao`). A amostra do
diagrama é a de `PainelDoDiagrama` — o desenho de verdade, na fonte e na
moldura escolhidas.

O resultado é um `OpcoesDeExportacao`, e é ele que a ação de menu consome:
nada de estado espalhado por doze variáveis locais. A caixa é a mesma para a
exportação de livro (EPUB/DOCX) e para o documento editorial (JSON/HTML/TXT/
PDF/EPUB/DOCX): muda a lista de formatos, e só.

**Cancelar é desistir**, como na caixa do diagrama de antes: um livro de 264
páginas escrito com o padrão porque alguém apertou Escape é o pior desfecho
possível.
"""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import asdict, dataclass, field, fields
from tkinter import filedialog, ttk
from typing import Any, Callable, List, Optional, Sequence, Tuple

from core import coleta, livro, render_diagrama
from core.exportar import CORPO_PADRAO_PT
from ui.dialogo_do_diagrama import PainelDoDiagrama

#: Os formatos que cada ação oferece: (extensão, rótulo).
FORMATOS_DE_LIVRO = (("epub", "EPUB (leitor de livros)"),
                     ("docx", "DOCX (Word)"))
FORMATOS_EDITORIAIS = (("epub", "EPUB (leitor de livros)"),
                       ("docx", "DOCX (Word)"),
                       ("pdf", "PDF pesquisável (o scan com camada de texto)"),
                       ("html", "HTML"),
                       ("json", "JSON (documento editorial)"),
                       ("txt", "Texto"))

#: A chave do `Settings` em que as escolhas ficam guardadas.
CHAVE_DAS_OPCOES = "exportacao"
CHAVE_DO_DIRETORIO_DE_ENTRADA = "ultimo_diretorio_de_entrada"
CHAVE_DO_DIRETORIO_DE_SAIDA = "ultimo_diretorio_de_saida"


@dataclass
class OpcoesDeExportacao:
    """O que a exportação precisa saber, num objeto só.

    `saida` e `paginas` são deste livro; o resto é preferência, e é o que
    `Settings` guarda entre uma exportação e outra (`para_settings`).
    `paginas` é `None` para o livro inteiro, ou a lista de índices (base 0).
    `coordenadas` tem os três valores de `livro.extrair`: `True`, `False` e
    `livro.COMO_NO_LIVRO`.
    """

    saida: str = ""
    formato: str = "epub"
    paginas: Optional[List[int]] = None
    idioma: str = "en"
    diagramas: str = "render"
    embutir_fonte: bool = False
    coordenadas: Any = False
    fonte: str = render_diagrama.FONTE_PADRAO
    moldura: Any = render_diagrama.MOLDURA_PADRAO
    cantos: str = render_diagrama.CANTO_PADRAO
    corpo_pt: float = CORPO_PADRAO_PT
    reparar: bool = False
    coletar: bool = False
    teto: Optional[int] = None
    modelo_de_linha: bool = False
    #: Ler da camada do PDF as páginas nascidas digitais (F110) — ligado por
    #: padrão, porque a régua (`pdf_nativo.avaliar_pagina`) só aceita a camada
    #: que é o texto do livro, e a digitalização vai ao OCR do mesmo jeito.
    ler_camada: bool = True
    extras: dict = field(default_factory=dict)

    #: O que não é preferência: caminho, páginas e o que a ação põe em `extras`.
    _POR_LIVRO = ("saida", "paginas", "extras")

    def para_settings(self) -> dict:
        """As preferências, prontas para o JSON do `Settings`."""
        dados = {k: v for k, v in asdict(self).items() if k not in self._POR_LIVRO}
        # `livro.COMO_NO_LIVRO` é uma string; `True`/`False` são JSON. Nada a
        # traduzir — só garantir que o que sai é o que entra.
        return dados

    @classmethod
    def de_settings(cls, dados: Optional[dict], **por_livro) -> "OpcoesDeExportacao":
        """As preferências guardadas, com os padrões para o que faltar e o
        que não faz sentido recusado (um `coordenadas` inventado, um corpo
        fora da régua, um formato que não existe)."""
        conhecidos = {f.name for f in fields(cls)} - set(cls._POR_LIVRO)
        if not isinstance(dados, dict):
            dados = {}   # JSON válido que não é objeto (schema de outra versão)
        limpos = {k: v for k, v in dados.items() if k in conhecidos}
        limpos.update(por_livro)   # o que é deste livro ganha do guardado
        opcoes = cls(**limpos)
        if opcoes.coordenadas not in (True, False, livro.COMO_NO_LIVRO):
            opcoes.coordenadas = False
        if opcoes.diagramas not in livro.MODOS_DE_DIAGRAMA:
            opcoes.diagramas = "render"
        if opcoes.idioma not in ("en", "pt"):
            opcoes.idioma = "en"
        try:
            opcoes.corpo_pt = float(opcoes.corpo_pt)
        except (TypeError, ValueError):
            opcoes.corpo_pt = CORPO_PADRAO_PT
        if opcoes.teto is not None:
            try:
                opcoes.teto = int(opcoes.teto)
            except (TypeError, ValueError):
                opcoes.teto = None
        if not isinstance(opcoes.ler_camada, bool):
            opcoes.ler_camada = True
        return opcoes

    @property
    def camada(self) -> str:
        """O `camada=` de `livro.extrair` (F110)."""
        return "auto" if self.ler_camada else "nunca"

    @property
    def diagramas_no_arquivo(self) -> str:
        """O `diagramas=` de `exportar.exportar`: fonte embutida só sobre o
        desenho — recorte de scan não vira letra."""
        return "fonte" if self.diagramas == "render" and self.embutir_fonte else "png"


class DialogoDeExportacao:
    """Pergunta tudo de uma vez. `mostrar()` devolve `OpcoesDeExportacao` ou `None`.

    `configuracoes` é uma função que devolve o `Settings` (chamada só aqui,
    para a caixa dublê dos testes não tocar o disco). `idioma_detectado` é o
    que a camada de texto do PDF disse, ou `None`; `motor_de_prosa` e
    `modelo_de_linha` são os pares `(disponível?, motivo)` das sondagens, que
    a caixa mostra ao lado da escolha em vez de perguntar depois.
    """

    def __init__(self, parent, *, entrada: str, total_paginas: int,
                 formatos: Sequence[Tuple[str, str]] = FORMATOS_DE_LIVRO,
                 configuracoes: Optional[Callable[[], Any]] = None,
                 idioma_detectado: Optional[str] = None,
                 motor_de_prosa: Tuple[bool, str] = (True, ""),
                 modelo_de_linha: Tuple[bool, str] = (False, ""),
                 titulo: str = "Exportar livro",
                 camada: Optional[Tuple[int, int]] = None):
        self.parent = parent
        self.entrada = entrada
        self.total_paginas = max(1, int(total_paginas))
        self.formatos = tuple(formatos)
        self.configuracoes = configuracoes
        self.idioma_detectado = idioma_detectado
        self.motor_de_prosa = motor_de_prosa
        self.modelo_de_linha = modelo_de_linha
        self.titulo = titulo
        #: `(aceitas, amostradas)` da régua da camada de texto
        #: (`pdf_nativo.avaliar`) numa amostra do PDF, ou `None`.
        self.camada = camada
        self.resultado: Optional[OpcoesDeExportacao] = None
        self._settings = None

    # ------------------------------------------------------------------
    # Construir
    # ------------------------------------------------------------------

    def _guardadas(self) -> OpcoesDeExportacao:
        if self.configuracoes is not None:
            try:
                self._settings = self.configuracoes()
            except Exception:  # noqa: BLE001 — preferência que não abre não barra a exportação
                self._settings = None
        dados = self._settings.get(CHAVE_DAS_OPCOES, {}) if self._settings else {}
        opcoes = OpcoesDeExportacao.de_settings(dados)
        if self.idioma_detectado in ("en", "pt"):
            opcoes.idioma = self.idioma_detectado
        extensoes = {ext for ext, _r in self.formatos}
        if opcoes.formato not in extensoes:
            opcoes.formato = self.formatos[0][0]
        return opcoes

    def mostrar(self) -> Optional[OpcoesDeExportacao]:
        self._construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    def _construir(self):
        guardadas = self._guardadas()
        self.top = tk.Toplevel(self.parent)
        self.top.title(self.titulo)
        self.top.transient(self.parent)
        self.top.resizable(False, False)
        self.top.protocol("WM_DELETE_WINDOW", self._cancelar)

        corpo = ttk.Frame(self.top, padding=12)
        corpo.pack(fill="both", expand=True)
        nome = os.path.basename(self.entrada)
        ttk.Label(corpo, text=f"{nome} — {self.total_paginas} página(s)",
                  font=("TkDefaultFont", 10, "bold")).grid(
                      row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        esquerda = ttk.Frame(corpo)
        esquerda.grid(row=1, column=0, sticky="nw", padx=(0, 14))
        self._construir_arquivo(esquerda, guardadas)
        self._construir_leitura(esquerda, guardadas)

        # A coluna da direita leva o diagrama e, embaixo dele, a camada de texto
        # (F110): ela é a mais baixa das duas — 383 px contra 459 e 543 da
        # esquerda —, e o quadro novo cabe ali sem a caixa do documento
        # editorial passar da altura da tela de 768 px.
        lado = ttk.Frame(corpo)
        lado.grid(row=1, column=1, sticky="nw")
        direita = ttk.LabelFrame(lado, text="diagramas", padding=8)
        direita.pack(fill="x")
        self._construir_diagramas(direita, guardadas)
        camada = ttk.LabelFrame(lado, text="camada de texto do PDF", padding=8)
        camada.pack(fill="x", pady=(8, 0))
        self._construir_camada(camada, guardadas)

        self.lbl_aviso = ttk.Label(corpo, foreground="#B71C1C", wraplength=760,
                                   justify="left")
        self.lbl_aviso.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botoes = ttk.Frame(corpo)
        botoes.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.btn_ok = ttk.Button(botoes, text="Exportar", command=self._confirmar,
                                 underline=0)
        self.btn_ok.pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self._cancelar,
                   underline=0).pack(side="right", padx=(0, 6))

        self.top.bind("<Return>", self._enter)
        self.top.bind("<Escape>", lambda _e: self._cancelar())
        self.top.bind("<Alt-e>", lambda _e: self._confirmar())
        self.top.bind("<Alt-c>", lambda _e: self._cancelar())
        self._validar()

    def _enter(self, event):
        """Enter confirma — menos dentro de um campo de texto, onde ele é o
        fim da digitação e não o do formulário: quem está no meio do caminho
        de saída não pode disparar a exportação sem querer."""
        if isinstance(getattr(event, "widget", None), (ttk.Entry, ttk.Spinbox, tk.Entry)):
            return None
        self._confirmar()
        return "break"

    def _construir_arquivo(self, pai, guardadas: OpcoesDeExportacao):
        quadro = ttk.LabelFrame(pai, text="arquivo", padding=8)
        quadro.pack(fill="x")

        ttk.Label(quadro, text="Formato:").grid(row=0, column=0, sticky="w")
        linha = ttk.Frame(quadro)
        linha.grid(row=0, column=1, sticky="w")
        self.var_formato = tk.StringVar(value=guardadas.formato)
        for ext, rotulo in self.formatos:
            ttk.Radiobutton(linha, text=rotulo, value=ext, variable=self.var_formato,
                            command=self._mudou_o_formato).pack(anchor="w")

        ttk.Label(quadro, text="Salvar em:").grid(row=1, column=0, sticky="w",
                                                   pady=(6, 0))
        caminho = ttk.Frame(quadro)
        caminho.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.var_saida = tk.StringVar(value=self._saida_sugerida(guardadas.formato))
        self.var_saida.trace_add("write", lambda *_a: self._validar())
        ttk.Entry(caminho, textvariable=self.var_saida, width=46).pack(side="left")
        ttk.Button(caminho, text="Procurar…", command=self._procurar).pack(
            side="left", padx=(6, 0))

        ttk.Label(quadro, text="Páginas:").grid(row=2, column=0, sticky="w",
                                                 pady=(6, 0))
        paginas = ttk.Frame(quadro)
        paginas.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.var_intervalo = tk.BooleanVar(value=False)
        ttk.Radiobutton(paginas, text=f"o livro inteiro ({self.total_paginas})",
                        value=False, variable=self.var_intervalo,
                        command=self._validar).pack(anchor="w")
        faixa = ttk.Frame(paginas)
        faixa.pack(anchor="w")
        ttk.Radiobutton(faixa, text="de", value=True, variable=self.var_intervalo,
                        command=self._validar).pack(side="left")
        self.var_de = tk.StringVar(value="1")
        self.var_ate = tk.StringVar(value=str(self.total_paginas))
        for var in (self.var_de, self.var_ate):
            var.trace_add("write", lambda *_a: self._validar())
        ttk.Entry(faixa, textvariable=self.var_de, width=5).pack(side="left", padx=(4, 4))
        ttk.Label(faixa, text="a").pack(side="left")
        ttk.Entry(faixa, textvariable=self.var_ate, width=5).pack(side="left", padx=(4, 0))
        if self.total_paginas == 1:
            for filho in faixa.winfo_children():
                filho.state(["disabled"])

    def _construir_leitura(self, pai, guardadas: OpcoesDeExportacao):
        quadro = ttk.LabelFrame(pai, text="leitura", padding=8)
        quadro.pack(fill="x", pady=(8, 0))

        ttk.Label(quadro, text="Idioma do livro:").grid(row=0, column=0, sticky="nw")
        idioma = ttk.Frame(quadro)
        idioma.grid(row=0, column=1, sticky="w")
        self.var_idioma = tk.StringVar(value=guardadas.idioma)
        ttk.Radiobutton(idioma, text="inglês", value="en",
                        variable=self.var_idioma).pack(side="left")
        ttk.Radiobutton(idioma, text="português", value="pt",
                        variable=self.var_idioma).pack(side="left", padx=(8, 0))
        origem = ("detectado pela camada de texto do PDF"
                  if self.idioma_detectado in ("en", "pt")
                  else "sem camada de texto que diga — decide a máscara de alfabeto")
        ttk.Label(quadro, text=origem, foreground="gray30", wraplength=330,
                  justify="left").grid(row=1, column=1, sticky="w")

        disponivel, motivo = self.motor_de_prosa
        ttk.Label(quadro, text="Motor de prosa:").grid(row=2, column=0, sticky="nw",
                                                        pady=(6, 0))
        if disponivel:
            texto, cor = f"Tesseract {motivo} disponível".strip(), "#2E7D32"
        else:
            texto, cor = (f"Tesseract indisponível: {motivo}. A prosa sairá só "
                          "com a cadeia própria (27% de erro contra 1% com os dois).",
                          "#B71C1C")
        ttk.Label(quadro, text=texto, foreground=cor, wraplength=330,
                  justify="left").grid(row=2, column=1, sticky="w", pady=(6, 0))

        self.var_reparar = tk.BooleanVar(value=guardadas.reparar)
        ttk.Checkbutton(quadro, text="Consertar as palavras que a colagem estragou "
                                     "(`Dmamic` → `Dynamic`)",
                        variable=self.var_reparar).grid(
                            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(quadro, foreground="gray30", wraplength=400, justify="left",
                  text="Exato (19 de 19 trocas medidas), mas lento: a extração "
                       "leva cerca de doze vezes mais."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", padx=(20, 0))

        utilizavel, motivo_modelo = self.modelo_de_linha
        self.var_modelo = tk.BooleanVar(value=guardadas.modelo_de_linha and utilizavel)
        chk = ttk.Checkbutton(quadro, text="Ler as faixas de fallback com o modelo "
                                           "de linha treinado",
                              variable=self.var_modelo)
        chk.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        if not utilizavel:
            chk.state(["disabled"])
            self.var_modelo.set(False)
        ttk.Label(quadro, foreground="gray30", wraplength=400, justify="left",
                  text=(f"{motivo_modelo[0].upper()}{motivo_modelo[1:]}."
                        if motivo_modelo else
                        "Sem ele, as faixas de fallback vão para o Tesseract.")
                  ).grid(row=6, column=0, columnspan=2, sticky="w", padx=(20, 0))

        self.var_coletar = tk.BooleanVar(value=guardadas.coletar)
        ttk.Checkbutton(quadro, text="Guardar os recortes de baixa confiança para revisão",
                        variable=self.var_coletar, command=self._validar).grid(
                            row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        teto = ttk.Frame(quadro)
        teto.grid(row=8, column=0, columnspan=2, sticky="w", padx=(20, 0))
        ttk.Label(teto, text="Teto por classe:").pack(side="left")
        self.var_teto = tk.StringVar(
            value="" if guardadas.teto is None else str(guardadas.teto))
        self.var_teto.trace_add("write", lambda *_a: self._validar())
        ttk.Entry(teto, textvariable=self.var_teto, width=7).pack(side="left", padx=(6, 6))
        ttk.Label(teto, text="(em branco: sem teto)", foreground="gray30").pack(side="left")
        ttk.Label(quadro, foreground="gray30", wraplength=400, justify="left",
                  text=f"Vão para '{coleta.PASTA_PADRAO}/' pelo palpite do modelo, "
                       "não para a base de treino; com teto, sorteados no livro inteiro."
                  ).grid(row=9, column=0, columnspan=2, sticky="w", padx=(20, 0))

    def _construir_diagramas(self, pai, guardadas: OpcoesDeExportacao):
        self.var_desenhar = tk.BooleanVar(value=guardadas.diagramas == "render")
        ttk.Checkbutton(pai, text="Redesenhar cada diagrama a partir da posição lida",
                        variable=self.var_desenhar, command=self._mudou_o_desenho).pack(
                            anchor="w")
        ttk.Label(pai, foreground="gray30", wraplength=640, justify="left",
                  text="Limpo, na fonte abaixo; onde a leitura não convence cai para "
                       "o recorte do scan (9% de 346 tabuleiros medidos)."
                  ).pack(anchor="w", padx=(20, 0))
        self.var_embutir = tk.BooleanVar(value=guardadas.embutir_fonte)
        self.chk_embutir = ttk.Checkbutton(
            pai, text="Como texto, com a fonte de xadrez embutida no arquivo",
            variable=self.var_embutir)
        self.chk_embutir.pack(anchor="w", pady=(6, 0))
        ttk.Label(pai, foreground="gray30", wraplength=640, justify="left",
                  text="Escala sem perder nitidez; exige leitor que respeite a fonte "
                       "embutida. Desligado, sai como imagem, que funciona em qualquer um."
                  ).pack(anchor="w", padx=(20, 0))

        coord = ttk.Frame(pai)
        coord.pack(anchor="w", pady=(8, 0))
        ttk.Label(coord, text="Coordenadas a–h / 1–8:").pack(side="left")
        self.var_coordenadas = tk.StringVar(value=self._coordenadas_para_texto(
            guardadas.coordenadas))
        for valor, rotulo in (("sem", "sem"), ("com", "com"),
                              ("livro", "como no livro, diagrama a diagrama")):
            ttk.Radiobutton(coord, text=rotulo, value=valor,
                            variable=self.var_coordenadas).pack(side="left", padx=(8, 0))

        self.painel = PainelDoDiagrama(
            pai, fonte=guardadas.fonte, moldura=guardadas.moldura,
            cantos=guardadas.cantos, corpo_pt=guardadas.corpo_pt,
            ao_mudar=self._validar, compacto=True)
        self.painel.pack(fill="x", pady=(10, 0))
        self._mudou_o_desenho()

    def _construir_camada(self, pai, guardadas: OpcoesDeExportacao):
        self.var_camada = tk.BooleanVar(value=guardadas.ler_camada)
        ttk.Checkbutton(pai, text="Ler do próprio PDF as páginas nascidas digitais — "
                                  "texto e diagramas exatos, sem OCR",
                        variable=self.var_camada).pack(anchor="w")
        self.lbl_camada = ttk.Label(pai, foreground="gray30", wraplength=640,
                                    justify="left", text=self._texto_da_camada())
        self.lbl_camada.pack(anchor="w", padx=(20, 0))

    def _texto_da_camada(self) -> str:
        """O que a régua achou na amostra — e o que se perde com a camada."""
        if self.camada is None:
            return ("A digitalização e o OCR de fábrica vão ao OCR de sempre; "
                    "a página da camada não entra na coleta nem na fila de revisão.")
        aceitas, amostradas = self.camada
        if not aceitas:
            return (f"Nenhuma das {amostradas} páginas amostradas é camada "
                    "tipográfica (digitalização ou OCR de fábrica): o livro vai ao OCR.")
        return (f"A régua aceitou {aceitas} de {amostradas} páginas amostradas; "
                "a página da camada não entra na coleta nem na fila de revisão.")

    # ------------------------------------------------------------------
    # Reagir
    # ------------------------------------------------------------------

    @staticmethod
    def _coordenadas_para_texto(valor) -> str:
        if valor == livro.COMO_NO_LIVRO:
            return "livro"
        return "com" if valor is True else "sem"

    @staticmethod
    def _coordenadas_de_texto(valor: str):
        return {"livro": livro.COMO_NO_LIVRO, "com": True}.get(valor, False)

    def _saida_sugerida(self, formato: str) -> str:
        """O caminho de saída: o nome do PDF com a extensão do formato, na pasta
        em que se salvou da última vez (ou na do PDF)."""
        pasta = None
        if self._settings is not None:
            pasta = self._settings.get(CHAVE_DO_DIRETORIO_DE_SAIDA)
        if not pasta or not os.path.isdir(pasta):
            pasta = os.path.dirname(self.entrada) or "."
        base = os.path.splitext(os.path.basename(self.entrada))[0] or "livro"
        return os.path.join(pasta, f"{base}.{formato}")

    def _mudou_o_formato(self):
        """A extensão do caminho acompanha o formato — e só ela."""
        atual = self.var_saida.get().strip()
        if atual:
            raiz, _ext = os.path.splitext(atual)
            self.var_saida.set(f"{raiz}.{self.var_formato.get()}")
        self._validar()

    def _procurar(self):
        atual = self.var_saida.get().strip()
        formato = self.var_formato.get()
        escolhido = filedialog.asksaveasfilename(
            parent=self.top, title="Salvar como...",
            defaultextension=f".{formato}",
            initialdir=os.path.dirname(atual) if atual else None,
            initialfile=os.path.basename(atual) if atual else None,
            filetypes=[(rotulo, f"*.{ext}") for ext, rotulo in self.formatos])
        if escolhido:
            ext = os.path.splitext(escolhido)[1].lstrip(".").lower()
            if ext in {e for e, _r in self.formatos}:
                self.var_formato.set(ext)
            self.var_saida.set(escolhido)
            self._validar()

    def _mudou_o_desenho(self):
        """A fonte embutida só faz sentido sobre o desenho: recorte de scan não
        vira letra. E o painel do diagrama só vale para o desenho."""
        desenhar = self.var_desenhar.get()
        self.chk_embutir.state(["!disabled"] if desenhar else ["disabled"])
        if not desenhar:
            self.var_embutir.set(False)
        self._validar()

    def _paginas(self) -> Tuple[Optional[List[int]], Optional[str]]:
        """`(páginas, erro)`: `None` para o livro inteiro."""
        if not self.var_intervalo.get():
            return None, None
        try:
            de, ate = int(self.var_de.get()), int(self.var_ate.get())
        except ValueError:
            return None, f"o intervalo pede dois números entre 1 e {self.total_paginas}"
        if not 1 <= de <= ate <= self.total_paginas:
            return None, f"o intervalo pede dois números entre 1 e {self.total_paginas}"
        return list(range(de - 1, ate)), None

    def _teto(self) -> Tuple[Optional[int], Optional[str]]:
        if not self.var_coletar.get():
            return None, None
        try:
            return coleta.teto_de_texto(self.var_teto.get()), None
        except ValueError as erro:
            return None, str(erro)

    def _montar(self) -> Tuple[Optional[OpcoesDeExportacao], Optional[str]]:
        """As opções do formulário, ou o motivo de ele ainda não estar pronto."""
        saida = self.var_saida.get().strip()
        if not saida:
            return None, "escolha onde salvar"
        formato = self.var_formato.get()
        ext = os.path.splitext(saida)[1].lstrip(".").lower()
        if ext != formato:
            return None, f"o arquivo precisa terminar em .{formato}"
        paginas, erro = self._paginas()
        if erro:
            return None, erro
        teto, erro = self._teto()
        if erro:
            return None, erro
        valores = self.painel.valores()
        if valores is None:
            return None, "o corpo do diagrama precisa ser um número na régua"
        fonte, moldura, cantos, corpo = valores
        return OpcoesDeExportacao(
            saida=saida, formato=formato, paginas=paginas,
            idioma=self.var_idioma.get(),
            diagramas="render" if self.var_desenhar.get() else "recorte",
            embutir_fonte=bool(self.var_embutir.get()),
            coordenadas=self._coordenadas_de_texto(self.var_coordenadas.get()),
            fonte=fonte, moldura=moldura, cantos=cantos, corpo_pt=corpo,
            reparar=bool(self.var_reparar.get()),
            coletar=bool(self.var_coletar.get()), teto=teto,
            modelo_de_linha=bool(self.var_modelo.get()),
            ler_camada=bool(self.var_camada.get())), None

    def _validar(self):
        if not hasattr(self, "btn_ok"):
            return
        opcoes, erro = self._montar()
        self.lbl_aviso.config(text=erro or "")
        self.btn_ok.state(["disabled"] if opcoes is None else ["!disabled"])

    # ------------------------------------------------------------------
    # Fechar
    # ------------------------------------------------------------------

    def _guardar(self, opcoes: OpcoesDeExportacao):
        if self._settings is None:
            return
        try:
            self._settings.set(CHAVE_DAS_OPCOES, opcoes.para_settings())
            self._settings.set(CHAVE_DO_DIRETORIO_DE_SAIDA,
                               os.path.dirname(os.path.abspath(opcoes.saida)))
            self._settings.save()
        except OSError:
            # A preferência que não grava não barra a exportação.
            pass

    def _confirmar(self):
        opcoes, _erro = self._montar()
        if opcoes is None:
            return
        self._guardar(opcoes)
        self.resultado = opcoes
        self.top.destroy()

    def _cancelar(self):
        self.resultado = None
        self.top.destroy()
