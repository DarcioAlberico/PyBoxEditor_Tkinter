"""
Perfis de mapeamento por fonte (F2.4, SPEC §4.5).

Havia um `DEFAULT_MAPPING_PROFILE` único no `chess_pdf_processor.py`, e ele
assume uma convenção: maiúscula = peça branca, minúscula = peça preta. Duas
coisas quebravam nisso.

**1. Nem toda fonte usa KQRBNP.** As Chess Diagram TTF mapeiam as peças noutras
letras, e não havia onde dizer isso.

**2. A convenção erra dentro do próprio livro.** Medido na F2.3, `Bb5` saía como
`♗♝5`: o `B` é o bispo, certo, mas o `b` — que ali é a **coluna b** — também
estava no perfil e virou bispo preto. E, pela F1.1, estes livros usam **um
conjunto só de figurinas para os dois lados**: quem diz a cor é a paridade do
lance, não o glifo. Para eles a convenção de minúsculas simplesmente não vale, e
o perfil `figurina_unica` mapeia só as maiúsculas — `Bb5` vira `♗b5`.

Não dá para escolher entre as duas por heurística: nas fontes figurinas de verdade
as minúsculas **são** peças pretas, e num livro que use as duas caixas o
`figurina_unica` perderia as peças pretas. É decisão por livro, que é exatamente
o que um perfil é.

Os limiares de detecção de diagrama vêm junto porque também são por livro: fonte
com subset e nome aleatório (`ABCD+F1`) muda a proporção de spans que o
`is_block_a_diagram` enxerga.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


PASTA_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "profiles")

MODOS = ("unicode",)


class PerfilInvalido(ValueError):
    """O arquivo de perfil não tem a forma esperada."""


@dataclass
class Perfil:
    nome: str
    mapeamento: Dict[str, str]
    padroes_de_fonte: List[str] = field(default_factory=list)
    modo: str = "unicode"
    # limiares de `is_block_a_diagram`, hoje literais no código
    min_linhas_diagrama: int = 4
    razao_span_xadrez: float = 0.7
    origem: str = ""

    def casa_com_fonte(self, nome_da_fonte: str) -> bool:
        if not nome_da_fonte:
            return False
        alvo = nome_da_fonte.lower()
        return any(p.lower() in alvo for p in self.padroes_de_fonte)

    def __str__(self):
        return f"{self.nome} ({len(self.mapeamento)} mapeamentos)"


def _exigir(condicao, mensagem, caminho):
    if not condicao:
        raise PerfilInvalido(f"{caminho}: {mensagem}")


def de_dicionario(dados: dict, origem: str = "") -> Perfil:
    """Valida e converte o JSON de um perfil."""
    _exigir(isinstance(dados, dict), "o conteúdo não é um objeto JSON", origem)

    nome = dados.get("name") or dados.get("nome")
    _exigir(nome, "falta o campo 'name'", origem)

    mapeamento = dados.get("mapping") or dados.get("mapeamento")
    _exigir(isinstance(mapeamento, dict) and mapeamento,
            "falta o campo 'mapping', ou ele está vazio", origem)
    for de, para in mapeamento.items():
        _exigir(isinstance(de, str) and isinstance(para, str),
                f"mapeamento {de!r} -> {para!r} não é texto para texto", origem)
        # Um caractere de entrada, senão a substituição caractere a caractere de
        # `process_span` nunca acharia a chave e o perfil ficaria inerte.
        _exigir(len(de) == 1,
                f"a chave {de!r} tem {len(de)} caracteres; deve ter 1", origem)

    modo = dados.get("mode") or dados.get("modo") or "unicode"
    _exigir(modo in MODOS, f"modo {modo!r} desconhecido (use um de {MODOS})", origem)

    padroes = dados.get("font_patterns") or dados.get("padroes_de_fonte") or []
    _exigir(isinstance(padroes, list) and all(isinstance(p, str) for p in padroes),
            "'font_patterns' deve ser uma lista de textos", origem)

    deteccao = dados.get("diagram_detection") or dados.get("deteccao_de_diagrama") or {}
    _exigir(isinstance(deteccao, dict), "'diagram_detection' deve ser um objeto", origem)

    min_linhas = deteccao.get("min_lines", deteccao.get("min_linhas", 4))
    razao = deteccao.get("chess_span_ratio", deteccao.get("razao_span_xadrez", 0.7))
    _exigir(isinstance(min_linhas, int) and min_linhas >= 1,
            "'min_lines' deve ser inteiro >= 1", origem)
    _exigir(isinstance(razao, (int, float)) and 0.0 < razao <= 1.0,
            "'chess_span_ratio' deve estar em (0, 1]", origem)

    return Perfil(nome=nome, mapeamento=dict(mapeamento),
                  padroes_de_fonte=list(padroes), modo=modo,
                  min_linhas_diagrama=int(min_linhas),
                  razao_span_xadrez=float(razao), origem=origem)


def carregar(caminho: str) -> Perfil:
    with open(caminho, encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError as e:
            raise PerfilInvalido(f"{caminho}: JSON inválido ({e})") from e
    return de_dicionario(dados, origem=caminho)


def carregar_todos(pasta: Optional[str] = None) -> List[Perfil]:
    """
    Todos os perfis de uma pasta, em ordem de nome de arquivo.

    Perfil quebrado **interrompe** a carga em vez de ser pulado em silêncio: um
    perfil que não carrega faz a conversão cair no padrão, e o usuário veria o
    livro convertido com o mapeamento errado sem nenhum aviso.
    """
    pasta = pasta or PASTA_PADRAO
    if not os.path.isdir(pasta):
        return []
    return [carregar(os.path.join(pasta, nome))
            for nome in sorted(os.listdir(pasta))
            if nome.endswith(".json")]


def escolher(nome_da_fonte: str, perfis: Optional[List[Perfil]] = None) -> Optional[Perfil]:
    """
    Primeiro perfil cujos `font_patterns` casam com a fonte. None se nenhum.

    A ordem é a do nome do arquivo, então `00_` a `99_` dá controle de
    precedência sem inventar um campo de prioridade.
    """
    for perfil in (perfis if perfis is not None else carregar_todos()):
        if perfil.casa_com_fonte(nome_da_fonte):
            return perfil
    return None
