"""
As buscas salvas (ED-06b; SPEC_EDITOR §8.12 "buscas salvas com grupos e execução em
lote", §9.4): uma busca com nome e grupo guarda as opções da caixa (`busca.Opcoes`), e
um grupo roda em lote — cada busca é um "substituir todos" no escopo dela, e o resumo
diz quantas trocas cada uma fez, por arquivo.

Moram em `Settings` (`editor.buscas_salvas`, uma lista de dicionários, como as outras
preferências) e vão e voltam de um JSON à parte para partilhar entre livros e máquinas
(o "Search Editor" do Sigil exporta igual). O lote não sabe substituir: recebe
`executar(opcoes) -> {arquivo: n}` de quem sabe (o `Buscador` da janela) e só soma.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Sequence

from core.editor.busca import Opcoes

CHAVE = "buscas_salvas"
VERSAO = 1
_CAMPOS_DE_OPCOES = {f.name for f in fields(Opcoes)}


@dataclass
class BuscaSalva:
    nome: str
    grupo: str = ""
    opcoes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.nome = str(self.nome).strip()
        if not self.nome:
            raise ValueError("a busca salva precisa de um nome")
        self.grupo = str(self.grupo or "").strip()
        self.opcoes = {k: v for k, v in dict(self.opcoes).items() if k in _CAMPOS_DE_OPCOES}

    def como_opcoes(self) -> Opcoes:
        return Opcoes(**self.opcoes)

    @classmethod
    def de_opcoes(cls, nome: str, opcoes: Opcoes, grupo: str = "") -> "BuscaSalva":
        return cls(nome, grupo, asdict(opcoes))


@dataclass
class Resumo:
    """O que um lote fez: por busca, a contagem por arquivo."""

    por_busca: dict[str, dict[str, int]] = field(default_factory=dict)
    erros: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(sum(c.values()) for c in self.por_busca.values())

    def linhas(self) -> list[str]:
        saida = [f"Lote: {self.total} substituição(ões) em {len(self.por_busca)} busca(s)"]
        for nome, contagem in self.por_busca.items():
            n = sum(contagem.values())
            saida.append(f"  {nome}: {n}" + (f" ({', '.join(f'{a}: {k}' for a, k in contagem.items())})"
                                              if contagem else ""))
        for nome, erro in self.erros.items():
            saida.append(f"  {nome}: erro — {erro}")
        return saida


class Colecao:
    """As buscas salvas, na ordem em que foram guardadas; `gravar` as põe nas preferências."""

    def __init__(self, buscas: Sequence[BuscaSalva] = (), gravador: Callable[[list[dict]], Any] | None = None):
        self.buscas: list[BuscaSalva] = list(buscas)
        self.gravador = gravador

    # -- persistência --------------------------------------------------------

    @classmethod
    def carregar(cls, dados: Any, gravador: Callable[[list[dict]], Any] | None = None) -> "Colecao":
        """De `Settings.get("editor")["buscas_salvas"]` (ou de qualquer lista de dicionários)."""
        buscas = []
        for item in (dados or []):
            try:
                buscas.append(BuscaSalva(**{k: item[k] for k in ("nome", "grupo", "opcoes") if k in item}))
            except (TypeError, ValueError):
                continue
        return cls(buscas, gravador)

    def como_lista(self) -> list[dict]:
        return [asdict(b) for b in self.buscas]

    def gravar(self) -> None:
        if self.gravador is not None:
            self.gravador(self.como_lista())

    # -- consultas -------------------------------------------------------------

    def nomes(self) -> list[str]:
        return [b.nome for b in self.buscas]

    def grupos(self) -> list[str]:
        vistos: list[str] = []
        for b in self.buscas:
            if b.grupo and b.grupo not in vistos:
                vistos.append(b.grupo)
        return vistos

    def por_nome(self, nome: str) -> BuscaSalva | None:
        return next((b for b in self.buscas if b.nome == nome), None)

    def do_grupo(self, grupo: str) -> list[BuscaSalva]:
        return [b for b in self.buscas if b.grupo == grupo]

    # -- edição ------------------------------------------------------------------

    def guardar(self, busca: BuscaSalva) -> BuscaSalva:
        """Acrescenta, ou troca a de mesmo nome; grava."""
        existente = self.por_nome(busca.nome)
        if existente is not None:
            self.buscas[self.buscas.index(existente)] = busca
        else:
            self.buscas.append(busca)
        self.gravar()
        return busca

    def remover(self, nome: str) -> bool:
        existente = self.por_nome(nome)
        if existente is None:
            return False
        self.buscas.remove(existente)
        self.gravar()
        return True

    # -- lote ------------------------------------------------------------------

    def em_lote(self, nomes: Sequence[str], executar: Callable[[Opcoes], dict[str, int]]) -> Resumo:
        """Roda as buscas `nomes` em ordem; `executar(opcoes)` é o "substituir todos" de quem sabe."""
        resumo = Resumo()
        for nome in nomes:
            busca = self.por_nome(nome)
            if busca is None:
                resumo.erros[nome] = "não existe"
                continue
            try:
                resumo.por_busca[nome] = dict(executar(busca.como_opcoes()))
            except ValueError as erro:
                resumo.erros[nome] = str(erro)
        return resumo

    def grupo_em_lote(self, grupo: str, executar: Callable[[Opcoes], dict[str, int]]) -> Resumo:
        return self.em_lote([b.nome for b in self.do_grupo(grupo)], executar)

    # -- JSON -----------------------------------------------------------------------

    def exportar_json(self, caminho: str, nomes: Sequence[str] | None = None) -> int:
        escolhidas = [b for b in self.buscas if nomes is None or b.nome in set(nomes)]
        dados = {"formato": "pybox-buscas", "versao": VERSAO, "buscas": [asdict(b) for b in escolhidas]}
        pasta = os.path.dirname(os.path.abspath(caminho))
        os.makedirs(pasta, exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        return len(escolhidas)

    def importar_json(self, caminho: str) -> int:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict) or dados.get("formato") != "pybox-buscas":
            raise ValueError(f"{os.path.basename(caminho)} não é um arquivo de buscas salvas do PyBoxEditor")
        n = 0
        for item in dados.get("buscas", []):
            try:
                busca = BuscaSalva(**{k: item[k] for k in ("nome", "grupo", "opcoes") if k in item})
            except (TypeError, ValueError):
                continue
            existente = self.por_nome(busca.nome)
            if existente is not None:
                self.buscas[self.buscas.index(existente)] = busca
            else:
                self.buscas.append(busca)
            n += 1
        self.gravar()
        return n


__all__ = ["BuscaSalva", "Colecao", "Resumo", "CHAVE", "VERSAO"]
