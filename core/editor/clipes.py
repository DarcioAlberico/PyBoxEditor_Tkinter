"""
Clipes: trechos de XHTML (ou de texto) que se inserem com um clique ou um atalho,
em grupos, com `\\1` para a seleção (ED-07; SPEC_EDITOR §9 "Clips / Clip Editor").

O modelo do Sigil, sem o editor de tabela dele: um clipe tem nome, grupo e texto; no
texto, `\\1` é o que estava selecionado no momento de aplicar (e `\\0` também, por
hábito de quem vem de regex). `\\2`…`\\9` são os grupos de um `padrao` opcional —
uma expressão regular casada contra a seleção —, para um clipe que transforma o
que envolve ("23...Rxe4" → `<span class="lance">23…♖xe4</span>` com o número num
grupo e o lance noutro). Sem seleção, `\\1` é vazio e o cursor fica onde o `\\1`
estava, que é o que faz `<strong>\\1</strong>` servir de "abre negrito aqui".

Persistem em `Settings["editor"]["clipes"]` (§7.6): uma lista de dicionários, que é
o que `para_dict`/`de_dict` produzem; um arquivo de clipes também se exporta e
importa em JSON, para levar de uma máquina a outra.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

CHAVE_NAS_PREFERENCIAS = "clipes"
GRUPO_PADRAO = "Geral"
_RE_REFERENCIA = re.compile(r"\\([0-9])")


@dataclass
class Clipe:
    nome: str
    texto: str
    grupo: str = GRUPO_PADRAO
    padrao: str = ""            # regex casada contra a seleção; grupos viram \2…\9
    atalho: str = ""            # texto informativo ("Ctrl+Shift+1"); quem liga é a janela

    def __post_init__(self) -> None:
        self.nome = str(self.nome).strip()
        if not self.nome:
            raise ValueError("clipe sem nome")
        self.texto = str(self.texto)
        self.grupo = str(self.grupo).strip() or GRUPO_PADRAO
        if self.padrao:
            try:
                re.compile(self.padrao)      # um padrão inválido é erro na hora de criar, não de usar
            except re.error as erro:
                raise ValueError(f"padrão inválido em {self.nome!r}: {erro}") from None

    def aplicar(self, selecao: str = "") -> tuple[str, int]:
        """
        O texto com `\\1` (e `\\0`) trocados pela seleção e `\\2`…`\\9` pelos grupos do
        `padrao`; devolve também **onde o cursor fica** (a posição do primeiro `\\1`,
        ou o fim do texto).
        """
        grupos: dict[str, str] = {"0": selecao, "1": selecao}
        if self.padrao:
            m = re.search(self.padrao, selecao) if selecao else None
            if m:
                for i, valor in enumerate(m.groups(), start=1):
                    grupos[str(i + 1)] = valor or ""
        cursor = -1
        saida: list[str] = []
        posicao = 0
        for m in _RE_REFERENCIA.finditer(self.texto):
            saida.append(self.texto[posicao:m.start()])
            valor = grupos.get(m.group(1), "")
            if m.group(1) == "1" and cursor < 0 and not selecao:
                cursor = sum(len(p) for p in saida)
            saida.append(valor)
            posicao = m.end()
        saida.append(self.texto[posicao:])
        resultado = "".join(saida)
        return resultado, (cursor if cursor >= 0 else len(resultado))

    def para_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class Clipes:
    """A coleção, em ordem: `adicionar`, `remover`, `renomear`, `mover`, `grupos`, `do_grupo`, `por_nome`."""

    itens: list[Clipe] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.itens)

    def __iter__(self):
        return iter(self.itens)

    def por_nome(self, nome: str, grupo: str | None = None) -> Clipe | None:
        for clipe in self.itens:
            if clipe.nome == nome and (grupo is None or clipe.grupo == grupo):
                return clipe
        return None

    def adicionar(self, clipe: Clipe, posicao: int | None = None) -> Clipe:
        if self.por_nome(clipe.nome, clipe.grupo) is not None:
            raise ValueError(f"já existe o clipe {clipe.nome!r} no grupo {clipe.grupo!r}")
        if posicao is None:
            self.itens.append(clipe)
        else:
            self.itens.insert(max(0, min(posicao, len(self.itens))), clipe)
        return clipe

    def remover(self, nome: str, grupo: str | None = None) -> Clipe:
        clipe = self.por_nome(nome, grupo)
        if clipe is None:
            raise KeyError(f"clipe inexistente: {nome}")
        self.itens.remove(clipe)
        return clipe

    def renomear(self, nome: str, novo: str, grupo: str | None = None) -> Clipe:
        clipe = self.por_nome(nome, grupo)
        if clipe is None:
            raise KeyError(f"clipe inexistente: {nome}")
        if self.por_nome(novo, clipe.grupo) is not None:
            raise ValueError(f"já existe o clipe {novo!r} no grupo {clipe.grupo!r}")
        clipe.nome = novo.strip() or clipe.nome
        return clipe

    def mover(self, nome: str, para: int, grupo: str | None = None) -> None:
        clipe = self.remover(nome, grupo)
        self.itens.insert(max(0, min(para, len(self.itens))), clipe)

    def grupos(self) -> list[str]:
        """Os grupos na ordem em que aparecem (o padrão primeiro, se existir)."""
        vistos: list[str] = []
        for clipe in self.itens:
            if clipe.grupo not in vistos:
                vistos.append(clipe.grupo)
        if GRUPO_PADRAO in vistos:
            vistos.remove(GRUPO_PADRAO)
            vistos.insert(0, GRUPO_PADRAO)
        return vistos

    def do_grupo(self, grupo: str) -> list[Clipe]:
        return [c for c in self.itens if c.grupo == grupo]

    # -- persistência ------------------------------------------------------

    def para_lista(self) -> list[dict[str, str]]:
        return [c.para_dict() for c in self.itens]

    @classmethod
    def de_lista(cls, dados: Iterable[Any]) -> "Clipes":
        clipes = cls()
        for item in dados or []:
            if not isinstance(item, dict) or not item.get("nome"):
                continue
            try:
                clipes.adicionar(Clipe(nome=item.get("nome", ""), texto=item.get("texto", ""),
                                       grupo=item.get("grupo", GRUPO_PADRAO), padrao=item.get("padrao", ""),
                                       atalho=item.get("atalho", "")))
            except ValueError:
                continue         # um clipe repetido ou com padrão inválido não derruba os outros
        return clipes

    @classmethod
    def carregar(cls, settings: Any) -> "Clipes":
        editor = settings.get("editor", {}) or {}
        dados = editor.get(CHAVE_NAS_PREFERENCIAS) if isinstance(editor, dict) else None
        if dados is None:
            return cls.padrao()
        return cls.de_lista(dados)

    def salvar(self, settings: Any) -> None:
        editor = settings.get("editor", {}) or {}
        editor = dict(editor) if isinstance(editor, dict) else {}
        editor[CHAVE_NAS_PREFERENCIAS] = self.para_lista()
        settings.set("editor", editor)
        settings.save()

    def exportar(self, caminho: str) -> None:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.para_lista(), f, ensure_ascii=False, indent=2)

    def importar(self, caminho: str, substituir: bool = False) -> int:
        """Lê um JSON de clipes; os que colidem em nome e grupo ficam de fora (ou trocam, com `substituir`)."""
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        novos = Clipes.de_lista(dados)
        n = 0
        for clipe in novos:
            existente = self.por_nome(clipe.nome, clipe.grupo)
            if existente is not None:
                if not substituir:
                    continue
                self.itens.remove(existente)
            self.itens.append(clipe)
            n += 1
        return n

    @classmethod
    def padrao(cls) -> "Clipes":
        """Os clipes de fábrica: o que um livro de xadrez pede toda hora."""
        clipes = cls()
        for nome, texto, grupo in CLIPES_DE_FABRICA:
            clipes.adicionar(Clipe(nome=nome, texto=texto, grupo=grupo))
        return clipes


CLIPES_DE_FABRICA: Sequence[tuple[str, str, str]] = (
    ("Negrito", "<strong>\\1</strong>", GRUPO_PADRAO),
    ("Itálico", "<em>\\1</em>", GRUPO_PADRAO),
    ("Parágrafo", "<p>\\1</p>", GRUPO_PADRAO),
    ("Quebra de linha", "<br/>", GRUPO_PADRAO),
    ("Espaço inseparável", "&#160;", GRUPO_PADRAO),
    ("Lance", '<span class="lance">\\1</span>', "Xadrez"),
    ("Comentário", '<span class="com">\\1</span>', "Xadrez"),
    ("Notação", '<p class="notacao">\\1</p>', "Xadrez"),
    ("Cabeçalho de diagrama", '<p class="cabecalho-diagrama">\\1</p>', "Xadrez"),
    ("Nota de rodapé", '<a epub:type="noteref" role="doc-noteref" href="#\\1">\\1</a>', "Notas"),
    ("Marcador de divisão", '<hr class="divisao"/>', "Estrutura"),
    ("Quebra de página", '<hr class="quebra"/>', "Estrutura"),
)
