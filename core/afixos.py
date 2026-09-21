"""
Um verificador Hunspell mínimo: as raízes com as suas flags e as regras de sufixo e
prefixo, consultadas **ao contrário** — da palavra para a raiz (ED-06b; SPEC_EDITOR
§8.13).

## Por que não uma lista de palavras

O léxico do inglês é uma lista chã (`assets/lexico/en.txt.gz`, 310 mil formas). O do
português não cabe assim: o VERO (o dicionário do LibreOffice) tem 307 mil raízes e 25
mil regras de afixo, e a expansão completa dá **10 milhões** de formas (2,7 milhões sem
as ênclises `amá-lo-ia`, 1,8 milhão sem diminutivos e superlativos) — 27 MB comprimidos
e meio minuto para carregar num `set`. As raízes com as flags e as regras cabem em 1,3 MB
e carregam em menos de um segundo; a pergunta "esta palavra existe?" passa a custar
algumas dezenas de consultas a dicionário.

## Como se consulta

`conhece(palavra)`: a palavra é raiz; ou termina num `add` de regra de sufixo cuja raiz
reconstruída (`palavra` sem o `add`, mais o `strip`) existe, tem a flag da regra e casa
a condição; ou começa num `add` de prefixo, idem; ou é prefixo + raiz + sufixo, quando as
duas regras são de produto cruzado (`Y`). As 26 regras com classe de continuação do
VERO (as siglas dos estados) são ignoradas. Tudo em minúsculas, como `Lexico.conhece`.

O arquivo (`assets/lexico/pt.hunspell.gz`, gerado por `scripts/gerar_lexico_pt.py`) é
texto UTF-8: as linhas `SFX`/`PFX` do `.aff`, uma linha `---`, e as entradas do `.dic`.
"""

from __future__ import annotations

import gzip
import os
import re
from dataclasses import dataclass, field
from typing import Iterable

SEPARADOR = "---"


@dataclass
class _Regra:
    flag: str
    strip: str
    add: str
    condicao: re.Pattern | None
    cruzado: bool


@dataclass
class Afixos:
    """Ver o cabeçalho. `raizes` é `raiz (minúscula) → flags`; as regras são indexadas pelo `add`."""

    raizes: dict[str, str] = field(default_factory=dict)
    sufixos: dict[str, list[_Regra]] = field(default_factory=dict)
    prefixos: dict[str, list[_Regra]] = field(default_factory=dict)
    maior_sufixo: int = 0
    maior_prefixo: int = 0

    # -- montagem ------------------------------------------------------------

    def adicionar_regra(self, tipo: str, flag: str, strip: str, add: str, condicao: str, cruzado: bool) -> None:
        strip = "" if strip == "0" else strip
        add = "" if add == "0" else add.partition("/")[0]
        e_sufixo = tipo == "SFX"
        padrao = None
        if condicao != ".":
            texto = condicao.replace("\\", "\\\\")
            padrao = re.compile((texto + "$") if e_sufixo else ("^" + texto), re.IGNORECASE)
        regra = _Regra(flag, strip.lower(), add.lower(), padrao, cruzado)
        alvo = self.sufixos if e_sufixo else self.prefixos
        alvo.setdefault(regra.add, []).append(regra)
        if e_sufixo:
            self.maior_sufixo = max(self.maior_sufixo, len(regra.add))
        else:
            self.maior_prefixo = max(self.maior_prefixo, len(regra.add))

    def adicionar_raiz(self, raiz: str, flags: str = "") -> None:
        baixa = raiz.lower()
        self.raizes[baixa] = self.raizes.get(baixa, "") + flags

    @classmethod
    def ler(cls, linhas: Iterable[str]) -> "Afixos":
        """Do texto do arquivo (ou de um `.aff` seguido de `---` e do `.dic`)."""
        afixos = cls()
        cabecalhos: dict[tuple[str, str], bool] = {}
        no_dic = False
        for linha in linhas:
            linha = linha.rstrip("\r\n")
            if not no_dic:
                if linha == SEPARADOR:
                    no_dic = True
                    continue
                partes = linha.split()
                if len(partes) < 4 or partes[0] not in ("SFX", "PFX"):
                    continue
                chave = (partes[0], partes[1])
                if chave not in cabecalhos:
                    cabecalhos[chave] = partes[2] == "Y"
                    if len(partes) == 4:
                        continue
                if len(partes) < 5:
                    continue
                afixos.adicionar_regra(partes[0], partes[1], partes[2], partes[3], partes[4], cabecalhos[chave])
                continue
            if not linha or linha.startswith("#") or linha.strip().isdigit():
                continue
            raiz, _, flags = linha.partition("/")
            raiz = raiz.split("\t")[0].strip()
            if raiz:
                afixos.adicionar_raiz(raiz, flags.split("\t")[0].strip())
        return afixos

    @classmethod
    def carregar(cls, caminho: str) -> "Afixos":
        abrir = gzip.open if caminho.endswith(".gz") else open
        with abrir(caminho, "rt", encoding="utf-8", errors="replace") as f:
            return cls.ler(f)

    # -- consulta --------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.raizes)

    @property
    def vazio(self) -> bool:
        return not self.raizes

    def _raiz_com(self, raiz: str, flag: str, condicao: re.Pattern | None) -> bool:
        flags = self.raizes.get(raiz)
        if flags is None or flag not in flags:
            return False
        return condicao is None or condicao.search(raiz) is not None

    def _raizes_por_sufixo(self, palavra: str, so_cruzadas: bool = False):
        """As raízes de que `palavra` pode ser a forma sufixada (a raiz existe, tem a flag e casa a condição)."""
        for k in range(0, min(self.maior_sufixo, len(palavra) - 1) + 1):
            add = palavra[len(palavra) - k:] if k else ""
            for regra in self.sufixos.get(add, ()):
                if so_cruzadas and not regra.cruzado:
                    continue
                raiz = (palavra[:len(palavra) - k] if k else palavra) + regra.strip
                if raiz and self._raiz_com(raiz, regra.flag, regra.condicao):
                    yield raiz

    def conhece(self, palavra: str) -> bool:
        palavra = palavra.lower()
        if not palavra:
            return False
        if palavra in self.raizes:
            return True
        for _raiz in self._raizes_por_sufixo(palavra):
            return True
        for k in range(1, min(self.maior_prefixo, len(palavra) - 1) + 1):
            add = palavra[:k]
            for regra in self.prefixos.get(add, ()):
                resto = regra.strip + palavra[k:]
                if self._raiz_com(resto, regra.flag, regra.condicao):
                    return True
                if regra.cruzado:
                    # prefixo + raiz + sufixo: a condição do prefixo é sobre a raiz, sem o sufixo
                    for raiz in self._raizes_por_sufixo(resto, so_cruzadas=True):
                        if self._raiz_com(raiz, regra.flag, regra.condicao):
                            return True
        return False


def carregar(caminho: str | None) -> Afixos | None:
    """O `Afixos` do arquivo, ou `None` quando não há arquivo."""
    if not caminho or not os.path.exists(caminho):
        return None
    return Afixos.carregar(caminho)


__all__ = ["Afixos", "carregar", "SEPARADOR"]
