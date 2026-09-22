"""
O projeto aberto na sessão: o livro, o caminho, o sujo, o histórico, o rascunho
automático, os recentes e os pontos de verificação (ED-01; SPEC_EDITOR §7.6, §9
"Checkpoints", DEC-04).

## O que é o projeto, e o que não é

`Projeto` é o que a janela segura: um `Livro` e o que se sabe sobre ele — de onde
veio, se mudou desde a última gravação, o que se pode desfazer. Ele não desenha
nada e não conhece o Tk; o `tique()` do rascunho é chamado por um `after` da janela,
e o relógio é injetável para o teste não esperar sessenta segundos de verdade.

## Rascunho

A cada tique, se o livro está sujo e mudou desde o último rascunho (`revisao`), e
passou o intervalo, o rascunho grava `<livro>.epub.autosave.json` — o modelo em
`para_dict`, com `texto_cru` e com os recursos que **só existem na memória** em
base64 (os que ainda estão no zip de origem continuam lá, e o JSON só diz onde). Um
livro sem caminho vai para `data_dir()/rascunhos/<uuid>.json`. `salvar` apaga o
rascunho; `fechar` também, porque quem descartou escolheu descartar. Quem grava é
o `gravador` injetado — o padrão escreve atômico na própria thread; a janela pode
dar um que grave em segundo plano.

## Pontos de verificação

Uma cópia datada do EPUB em `<livro>.checkpoints/` (o Sigil faz igual). "Comparar"
escreve o livro atual num EPUB temporário e faz `difflib` entrada por entrada;
"Restaurar" põe o livro do ponto no lugar do atual, **sem gravar** — é a gravação
seguinte que decide.

## A ponte com o documento editorial (ED-11, DEC-10)

Um projeto que veio do pipeline carrega `documento_editorial` (o `EditorialDocument`)
e `diario` (o `review_journal_path`). `salvar_como` grava o EPUB e, com documento,
chama `importar_ir.gravar_eventos`: cada bloco com origem cujo valor mudou vira um
evento no diário, o documento projetado passa a ser o da sessão e o relatório da
gravação recebe as linhas da ponte (`ponte`). Abrir um EPUB que guarda
`pybox:documento_editorial` recarrega o JSON, se ele ainda existe — a ponte sobrevive
à sessão.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from core.editor import epub, modelo
from core.editor.conversao import RelatorioDeConversao
from core.editor.historico import Historico
from core.editor.modelo import Livro

SUFIXO_DO_RASCUNHO = ".autosave.json"
SUFIXO_DOS_CHECKPOINTS = ".checkpoints"
VERSAO_DO_RASCUNHO = 1
_TEXTUAIS = (".xhtml", ".html", ".htm", ".css", ".opf", ".ncx", ".xml", ".svg", ".txt", ".js", ".json")


def pasta_de_rascunhos() -> str:
    """`data_dir()/rascunhos` — o lugar dos livros sem caminho e dos seus pontos de verificação."""
    from config.paths import data_dir

    return os.path.join(str(data_dir()), "rascunhos")


# ----------------------------------------------------------------------
# Projeto
# ----------------------------------------------------------------------

@dataclass
class Checkpoint:
    caminho: str
    quando: str            # "AAAAMMDD-HHMMSS"
    rotulo: str = ""

    @property
    def nome(self) -> str:
        return os.path.basename(self.caminho)


@dataclass
class Diferenca:
    """Uma entrada do zip que difere entre o ponto de verificação e o livro atual."""

    arquivo: str
    estado: str            # "alterado" | "novo" | "removido"
    diff: str = ""         # unificado, só para entradas de texto

    def __str__(self) -> str:
        return f"{self.estado}: {self.arquivo}"


class Projeto:
    """Um livro aberto: o modelo, o caminho, o sujo, o histórico (DEC-04) e os checkpoints."""

    def __init__(self, livro: Livro, caminho: str | None = None,
                 relatorio: RelatorioDeConversao | None = None,
                 relogio: Callable[[], float] = time.monotonic):
        self.livro = livro
        self.caminho = os.fspath(caminho) if caminho else None
        self.relatorio = relatorio
        self.relogio = relogio
        self.historico = Historico(relogio=relogio)
        self.sujo = False
        #: Cresce a cada `marcar_sujo`; é o que o rascunho compara para não regravar o mesmo.
        self.revisao = 0
        self.uuid = uuid.uuid4().hex
        #: A ponte (ED-11): o `EditorialDocument` de que o livro veio, o diário e o último relatório dela.
        self.documento_editorial: Any = None
        self.diario: str = ""
        self.ponte: Any = None

    # -- abrir e criar ----------------------------------------------------

    @classmethod
    def abrir(cls, caminho: str, **kw: Any) -> "Projeto":
        livro, relatorio = epub.ler(caminho)
        projeto = cls(livro, caminho, relatorio, **kw)
        projeto.religar_documento_editorial()
        return projeto

    def religar_documento_editorial(self) -> bool:
        """O JSON que `pybox:documento_editorial` aponta, quando existe: a ponte volta a valer (DEC-10)."""
        caminho = self.livro.origem.documento_editorial
        if not caminho or not os.path.isfile(caminho):
            return False
        from core.editor import importar_ir
        from core.editorial_model import EditorialDocument

        try:
            self.documento_editorial = EditorialDocument.load_json(caminho)
        except (OSError, ValueError, KeyError, TypeError) as erro:
            if self.relatorio is not None:
                self.relatorio.aviso(f"documento editorial ilegível, ponte desligada: {caminho} ({erro})")
            return False
        self.diario = self.livro.origem.diario or importar_ir.caminho_do_diario(self.documento_editorial, caminho)
        return True

    @classmethod
    def novo(cls, titulo: str = "Livro novo", autor: str = "", idioma: str = "pt", **kw: Any) -> "Projeto":
        return cls(epub.novo_livro(titulo, autor, idioma), None, None, **kw)

    # -- estado -----------------------------------------------------------

    @property
    def nome(self) -> str:
        """O que vai no título da janela: o arquivo, ou o título do livro novo."""
        if self.caminho:
            return os.path.basename(self.caminho)
        return self.livro.metadados.titulo or "Livro novo"

    def marcar_sujo(self) -> None:
        self.sujo = True
        self.revisao += 1

    # -- gravar -----------------------------------------------------------

    def salvar(self, **opcoes: Any) -> RelatorioDeConversao:
        """Grava no caminho do projeto; sem caminho, é `salvar_como` que se quer."""
        if not self.caminho:
            raise ValueError("o projeto não tem caminho; use salvar_como")
        return self.salvar_como(self.caminho, **opcoes)

    def salvar_como(self, caminho: str, **opcoes: Any) -> RelatorioDeConversao:
        rascunho_antigo = self.caminho_do_rascunho()
        if self.documento_editorial is not None:
            from core.editor import importar_ir

            self.diario = self.diario or importar_ir.caminho_do_diario(self.documento_editorial, caminho)
            self.livro.origem.diario = self.diario
        relatorio = epub.escrever(self.livro, caminho, **opcoes)
        epub.descarregar(self.livro)
        self.caminho = os.fspath(caminho)
        self.sujo = False
        self.relatorio = relatorio
        for velho in {rascunho_antigo, self.caminho_do_rascunho()}:
            _apagar(velho)
        if self.documento_editorial is not None:
            self.ponte = importar_ir.gravar_eventos(self.livro, self.documento_editorial, self.diario)
            self.documento_editorial = self.ponte.documento
            relatorio.avisos.extend(self.ponte.linhas())
            relatorio.metadados["ponte"] = {"eventos": self.ponte.eventos, "editados": self.ponte.editados,
                                            "apagados": self.ponte.apagados, "fundidos": self.ponte.fundidos,
                                            "novos": len(self.ponte.novos), "diario": self.ponte.diario}
        return relatorio

    def reverter(self) -> RelatorioDeConversao:
        """Volta ao que está no disco: relê o EPUB, limpa o histórico e o sujo."""
        if not self.caminho:
            raise ValueError("o projeto não tem caminho para reverter")
        self.livro, self.relatorio = epub.ler(self.caminho)
        self.historico.limpar()
        self.sujo = False
        self.revisao += 1
        return self.relatorio

    def fechar(self) -> None:
        """Descarta o rascunho (quem fechou sem salvar, escolheu) e limpa o histórico."""
        _apagar(self.caminho_do_rascunho())
        self.historico.limpar()

    # -- rascunho ---------------------------------------------------------

    def caminho_do_rascunho(self, pasta: str | None = None) -> str:
        if self.caminho:
            return self.caminho + SUFIXO_DO_RASCUNHO
        return os.path.join(pasta or pasta_de_rascunhos(), self.uuid + ".json")

    # -- pontos de verificação --------------------------------------------

    def pasta_de_checkpoints(self, pasta: str | None = None) -> str:
        if self.caminho:
            return self.caminho + SUFIXO_DOS_CHECKPOINTS
        return os.path.join(pasta or pasta_de_rascunhos(), self.uuid + SUFIXO_DOS_CHECKPOINTS)

    def checkpoint(self, rotulo: str = "", pasta: str | None = None) -> Checkpoint:
        """Grava o livro **atual** (não o do disco) como cópia datada em `<livro>.checkpoints/`."""
        destino = self.pasta_de_checkpoints(pasta)
        os.makedirs(destino, exist_ok=True)
        quando = time.strftime("%Y%m%d-%H%M%S")
        base = quando + (("-" + _nome_seguro(rotulo)) if rotulo else "")
        caminho = os.path.join(destino, base + ".epub")
        n = 1
        while os.path.exists(caminho):
            n += 1
            caminho = os.path.join(destino, f"{base}-{n}.epub")
        zip_antes = self.livro.zip_de_origem
        epub.escrever(self.livro, caminho)
        # O checkpoint é cópia, não destino: os recursos continuam vindo de onde vinham (a
        # gravação acabou de carregar na memória os que ainda estavam no zip).
        self.livro.zip_de_origem = zip_antes
        return Checkpoint(caminho, quando, rotulo)

    def checkpoints(self, pasta: str | None = None) -> list[Checkpoint]:
        destino = self.pasta_de_checkpoints(pasta)
        if not os.path.isdir(destino):
            return []
        saida = []
        for nome in sorted(os.listdir(destino)):
            if not nome.endswith(".epub"):
                continue
            quando, _, resto = nome[:-5].partition("-")
            quando2, _, rotulo = resto.partition("-")
            saida.append(Checkpoint(os.path.join(destino, nome), f"{quando}-{quando2}", rotulo))
        return saida

    def diferenca(self, cp: Checkpoint) -> list[Diferenca]:
        """As entradas que diferem entre o ponto e o livro atual (`difflib` nas de texto)."""
        pasta = tempfile.mkdtemp(prefix="pbe-diff-")
        zip_antes = self.livro.zip_de_origem
        try:
            atual = os.path.join(pasta, "atual.epub")
            epub.escrever(self.livro, atual)
            de = _entradas(cp.caminho)
            para = _entradas(atual)
        finally:
            self.livro.zip_de_origem = zip_antes
            shutil.rmtree(pasta, ignore_errors=True)
        saida: list[Diferenca] = []
        for nome in sorted(set(de) | set(para)):
            if nome not in para:
                saida.append(Diferenca(nome, "removido"))
            elif nome not in de:
                saida.append(Diferenca(nome, "novo"))
            elif de[nome] != para[nome]:
                diff = ""
                if nome.lower().endswith(_TEXTUAIS):
                    a = de[nome].decode("utf-8", errors="replace").splitlines(keepends=True)
                    b = para[nome].decode("utf-8", errors="replace").splitlines(keepends=True)
                    diff = "".join(difflib.unified_diff(a, b, "checkpoint/" + nome, "atual/" + nome, n=2))
                saida.append(Diferenca(nome, "alterado", diff))
        return saida

    def restaurar(self, cp: Checkpoint) -> RelatorioDeConversao:
        """O livro do ponto vira o livro atual — sujo, sem gravar; o histórico zera."""
        livro, relatorio = epub.ler(cp.caminho)
        self.livro = livro
        self.historico.limpar()
        self.marcar_sujo()
        return relatorio


def _nome_seguro(rotulo: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in rotulo.strip())[:40] or "ponto"


def _entradas(caminho: str) -> dict[str, bytes]:
    with zipfile.ZipFile(caminho) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def _apagar(caminho: str) -> None:
    try:
        os.unlink(caminho)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Rascunho automático
# ----------------------------------------------------------------------

def gravar_json_atomico(caminho: str, dados: dict) -> None:
    """O gravador padrão: temporário ao lado e `os.replace`, como o `document_service`."""
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(temporario, caminho)


class Rascunho:
    """
    `tique()` a cada segundo; a cada `intervalo_s` de livro sujo e mudado, grava o
    rascunho. `gravar()` força (fechar a principal ou o processo com o editor sujo).
    """

    def __init__(self, projeto: Projeto, gravador: Callable[[str, dict], None] = gravar_json_atomico,
                 relogio: Callable[[], float] = time.monotonic, intervalo_s: float = 60.0,
                 pasta: str | None = None):
        self.projeto = projeto
        self.gravador = gravador
        self.relogio = relogio
        self.intervalo_s = float(intervalo_s)
        self.pasta = pasta
        self._ultimo_tique = relogio()
        self._revisao_gravada = -1
        self.ultimo_caminho: str | None = None

    @property
    def caminho(self) -> str:
        return self.projeto.caminho_do_rascunho(self.pasta)

    def tique(self) -> bool:
        """`True` quando gravou."""
        agora = self.relogio()
        if agora - self._ultimo_tique < self.intervalo_s:
            return False
        self._ultimo_tique = agora
        projeto = self.projeto
        if not projeto.sujo or projeto.revisao == self._revisao_gravada:
            return False
        self.gravar()
        return True

    def gravar(self) -> str:
        """Grava agora, sujo ou não, e devolve o caminho."""
        caminho = self.caminho
        self.gravador(caminho, self.conteudo())
        self._revisao_gravada = self.projeto.revisao
        self.ultimo_caminho = caminho
        return caminho

    def conteudo(self) -> dict:
        livro = self.projeto.livro
        return {
            "versao": VERSAO_DO_RASCUNHO,
            "quando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "caminho": self.projeto.caminho or "",
            "titulo": livro.metadados.titulo,
            "livro": modelo.para_dict(livro),
        }

    def apagar(self) -> None:
        _apagar(self.caminho)

    @staticmethod
    def pendentes(caminho_do_livro: str | None = None, pasta: str | None = None) -> list[str]:
        """
        Os rascunhos que existem: o do livro dado (para oferecer ao abrir), ou todos os
        de livros sem caminho em `data_dir()/rascunhos`.
        """
        if caminho_do_livro:
            rascunho = os.fspath(caminho_do_livro) + SUFIXO_DO_RASCUNHO
            return [rascunho] if os.path.isfile(rascunho) else []
        pasta = pasta or pasta_de_rascunhos()
        if not os.path.isdir(pasta):
            return []
        return sorted(os.path.join(pasta, n) for n in os.listdir(pasta) if n.endswith(".json"))

    @staticmethod
    def ler(caminho_do_rascunho: str) -> dict:
        with open(caminho_do_rascunho, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def restaurar(caminho_do_rascunho: str, **kw: Any) -> Projeto:
        """O projeto de volta do JSON, sujo — e o rascunho continua lá até a gravação seguinte."""
        dados = Rascunho.ler(caminho_do_rascunho)
        if dados.get("versao") != VERSAO_DO_RASCUNHO:
            raise ValueError(f"rascunho de versão desconhecida: {dados.get('versao')!r}")
        livro = modelo.de_dict(dados["livro"])
        projeto = Projeto(livro, dados.get("caminho") or None, **kw)
        if not projeto.caminho:
            nome = os.path.basename(caminho_do_rascunho)
            if nome.endswith(".json"):
                projeto.uuid = nome[:-5]
        projeto.marcar_sujo()
        return projeto


# ----------------------------------------------------------------------
# Recentes
# ----------------------------------------------------------------------

class Recentes:
    """Os dez últimos livros, em `Settings["editor"]["recentes"]`; os que sumiram do disco caem."""

    def __init__(self, settings: Any, limite: int = 10, existe: Callable[[str], bool] = os.path.isfile):
        self.settings = settings
        self.limite = int(limite)
        self.existe = existe

    def _editor(self) -> dict:
        editor = self.settings.get("editor", {})
        return dict(editor) if isinstance(editor, dict) else {}

    def _gravar(self, lista: Sequence[str]) -> None:
        editor = self._editor()
        editor["recentes"] = list(lista)
        self.settings.set("editor", editor)
        self.settings.save()

    def lista(self) -> list[str]:
        lista = [str(c) for c in self._editor().get("recentes", []) if self.existe(str(c))]
        lista = lista[: self.limite]
        if lista != self._editor().get("recentes", []):
            self._gravar(lista)
        return lista

    def adicionar(self, caminho: str) -> list[str]:
        caminho = os.path.abspath(os.fspath(caminho))
        lista = [c for c in self.lista() if os.path.abspath(c) != caminho]
        lista.insert(0, caminho)
        lista = lista[: self.limite]
        self._gravar(lista)
        return lista

    def remover(self, caminho: str) -> list[str]:
        caminho = os.path.abspath(os.fspath(caminho))
        lista = [c for c in self.lista() if os.path.abspath(c) != caminho]
        self._gravar(lista)
        return lista

    def limpar(self) -> None:
        self._gravar([])


__all__ = ["Projeto", "Checkpoint", "Diferenca", "Rascunho", "Recentes", "pasta_de_rascunhos",
           "gravar_json_atomico", "SUFIXO_DO_RASCUNHO", "SUFIXO_DOS_CHECKPOINTS"]
