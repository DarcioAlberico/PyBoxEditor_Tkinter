"""
O ambiente dos testes da ED-04: um `TextoRico` solto (`Widget`) e uma `JanelaDoEditor`
com o livro completo de `editor_livros.livro_completo()` aberto e as caixas trocadas
por respostas prontas (`Janela`). Os quatro arquivos de teste da fase partilham isto.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

import editor_livros
from conftest import raiz_tk
from config.settings import Settings
from core.editor import epub, modelo as m
from core.editor.area_de_transferencia import AreaDeTransferencia
from ui.editor.janela import JanelaDoEditor
from ui.editor.texto_rico import TextoRico

_EPUB = {"pasta": None, "caminho": None}


def epub_completo() -> str:
    """O livro completo em EPUB, gerado uma vez por sessão; cada teste trabalha numa cópia."""
    if _EPUB["caminho"] is None:
        _EPUB["pasta"] = tempfile.mkdtemp(prefix="pbe-ed04-")
        _EPUB["caminho"] = os.path.join(_EPUB["pasta"], "completo.epub")
        epub.escrever(editor_livros.livro_completo(), _EPUB["caminho"])
    return _EPUB["caminho"]


def p(texto: str, **kw) -> m.Paragrafo:
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


class Widget:
    """Um `TextoRico` numa janela `withdraw`n, com o capítulo dado."""

    def __init__(self, blocos=None, notas=None, **kw):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.w = TextoRico(self.raiz, **kw)
        self.w.pack(fill="both", expand=True)
        self.cap = None
        if blocos is not None:
            self.cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=blocos, notas=list(notas or []))
            self.w.carregar(self.cap)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        try:
            self.raiz.destroy()
        except Exception:
            pass

    def blocos(self):
        return self.w.sincronizar().blocos

    def notas(self):
        return self.w.sincronizar().notas

    def textos(self):
        return [m.texto_de(b) for b in self.blocos()]


class Caixas:
    """As respostas injetadas e o registro do que a janela pediu."""

    def __init__(self, janela):
        self.chamadas = []
        self.pergunta_resposta = True
        self.texto_resposta = ""
        self.inteiro_resposta = 1
        self.escolha_resposta = 0
        self.formulario_resposta = None
        self.ilha_resposta = None
        self.tabela_resposta = None
        self.imagem_resposta = ""
        self.diagrama_resposta = None
        c = janela.caixas
        c.entrada = lambda mensagem, *a, **k: self.chamadas.append(("entrada", mensagem))
        c.falha = lambda mensagem, detalhe: self.chamadas.append(("falha", mensagem, detalhe))
        c.informar = lambda mensagem, *a, **k: self.chamadas.append(("informar", mensagem))
        c.pergunta = lambda mensagem, *a, **k: (self.chamadas.append(("pergunta", mensagem)), self.pergunta_resposta)[1]
        c.pedir_texto = lambda *a, **k: self.texto_resposta
        c.pedir_inteiro = lambda *a, **k: self.inteiro_resposta
        c.escolher = lambda *a, **k: self.escolha_resposta
        c.formulario = lambda *a, **k: self.formulario_resposta
        c.texto = lambda titulo, conteudo, *a, **k: self.chamadas.append(("texto", titulo, conteudo))
        c.conclusao = lambda titulo, linhas, caminho, **k: self.chamadas.append(("conclusao", titulo, list(linhas),
                                                                                caminho))
        c.abrir = lambda *a, **k: ""
        c.abrir_imagem = lambda *a, **k: self.imagem_resposta
        c.salvar_como = lambda *a, **k: ""
        c.ilha = lambda xhtml="", titulo="": (self.chamadas.append(("ilha", xhtml)), self.ilha_resposta)[1]
        c.tabela = lambda: self.tabela_resposta
        c.diagrama = lambda diagrama=None, **k: (self.chamadas.append(("diagrama", diagrama)),
                                                 self.diagrama_resposta)[1]

    def entradas(self):
        return [c[1] for c in self.chamadas if c[0] == "entrada"]

    def falhas(self):
        return [c for c in self.chamadas if c[0] == "falha"]


class Sistema:
    """A área de transferência do sistema, de mentira: texto e imagem injetáveis."""

    def __init__(self):
        self.texto = ""
        self.imagem = None

    def ler(self):
        return self.texto

    def gravar(self, texto):
        self.texto = texto

    def ler_imagem(self):
        return self.imagem


class Janela:
    """A `JanelaDoEditor` com uma cópia do livro completo aberta (ou vazia, com `abrir=False`)."""

    def __init__(self, abrir=True):
        self.abrir_livro = abrir

    def __enter__(self):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.pasta = tempfile.mkdtemp(prefix="pbe-ed04-janela-")
        self.settings = Settings(os.path.join(self.pasta, "settings.json"))
        self.j = JanelaDoEditor(self.raiz, settings=self.settings)
        self.j.withdraw()
        self.caixas = Caixas(self.j)
        self.sistema = Sistema()
        self.j.area = AreaDeTransferencia(self.sistema.ler, self.sistema.gravar, self.sistema.ler_imagem)
        self.epub = None
        if self.abrir_livro:
            self.epub = os.path.join(self.pasta, "livro.epub")
            shutil.copy(epub_completo(), self.epub)
            self.j.executar("abrir", self.epub)
        return self

    def __exit__(self, *a):
        try:
            if self.j.winfo_exists():
                self.caixas.pergunta_resposta = False
                self.j.fechar()
            self.raiz.destroy()
        except Exception:
            pass
        shutil.rmtree(self.pasta, ignore_errors=True)

    @property
    def texto(self) -> TextoRico:
        return self.j.aba_ativa().widget

    def bloco(self, predicado):
        """O primeiro bloco do capítulo ativo que satisfaz `predicado`."""
        return next(b for b in self.texto.sincronizar().blocos if predicado(b))

    def deslocamento_do_link(self, paragrafo, href) -> int:
        desloc = 0
        for tr in paragrafo.trechos:
            if tr.link == href:
                return desloc
            desloc += len(tr.texto) + (1 if tr.quebra_antes else 0)
        raise AssertionError(f"sem link {href} no parágrafo")
