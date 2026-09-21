"""
A ortografia do livro: o que é palavra, o que fica fora, e o léxico de cada idioma
(ED-06; SPEC_EDITOR §8.13).

## O que fica fora

Um livro de xadrez é metade notação, e a notação não é palavra: `12.Nf3`, `♘c6`, `±`,
`1-0` e `O-O` nunca chegam ao dicionário. A peneira é a mesma de
`core/notacao.py: e_token_de_notacao` — **copiada**, e não importada, porque
`core.notacao` traz `box_service` e o OpenCV, e o editor precisa abrir sem eles
(DEC-07); `tests/test_editor_ortografia.py` confere que a cópia não divergiu. Fica de
fora também o que o **modelo** já diz que não é prosa: o trecho com `papel` de lance,
NAG, figurina, jogador ou abertura, o trecho em `codigo`, a ilha, e o número. Palavra
toda em maiúsculas (`FIDE`, `ECO`) também fica — é a opção "ignorar MAIÚSCULAS" de
todo corretor, e num livro de xadrez as siglas são muitas.

## O léxico de cada idioma

O `lang` do trecho escolhe o léxico; sem `lang`, o idioma do capítulo; sem ele, o do
livro. O inglês é o `assets/lexico/en.txt.gz` de sempre (com os nomes); o português
chega na ED-06b (`pt.txt.gz`) — até lá, um léxico **vazio**, que não acusa nada
(`Lexico.sinaliza` é falso), em vez de acender a tela inteira. O dicionário do livro é
`<livro>.lexico.txt` ao lado do EPUB (`lexico.caminho_do_usuario(…, e_pdf=True)`, o
mesmo do PDF de que o livro veio), partilhado por todos os idiomas.

Os tokens vêm do adaptador da busca (`busca.alvos_do_capitulo`): a suspeita traz o
`Alvo` e os deslocamentos, que é o que o widget precisa para sublinhar e para pôr o
cursor nela.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from core.editor import busca, modelo
from core.editor.busca import Alvo
from core.editor.modelo import Capitulo, Livro, Paragrafo, Trecho

#: Cópia de `core/notacao.py` (ver o cabeçalho): as figurinas e as peneiras de notação.
FIGURINAS = "♔♕♖♗♘♙♚♛♜♝♞♟"
_PECAS_SAN = "KQRBN" + FIGURINAS
RE_LANCE_ESTRITO = re.compile(
    r"^(?:\d{1,3}\.(?:\.\.)?)?"
    r"(?:[" + _PECAS_SAN + r"]?[a-h]?[1-8]?x?[a-h][1-8](?:=[" + _PECAS_SAN + r"])?"
    r"|[O0]-[O0](?:-[O0])?)"
    r"[+#]?[!?]{0,2}[±∓⩱⩲=∞]?$")
RE_NUMERO_DE_LANCE = re.compile(r"^\d{1,3}\.(?:\.\.)?$")
RE_SINAL_DE_AVALIACAO = re.compile(r"^[+\-±∓⩱⩲=∞!?#□■△▼]+$")
RE_RESULTADO = re.compile(r"^(?:1[-–—]0|0[-–—]1|½[-–—]½|1/2[-–—]1/2)$")
_PONTUACAO_DE_BORDA = ",;:.)(\"'“”‘’"
#: Pontuação que cerca uma palavra e não faz parte dela (a `BORDAS` do léxico, mais o que o editor usa).
BORDAS = ".,;:!?()[]{}\"'‘’“”«»–—-*+…/\\"
PAPEIS_FORA = ("lance", "nag", "figurina", "jogador", "abertura")
_RE_TOKEN = re.compile(r"\S+")
_RE_APOSTROFO = re.compile(r"['’]")
_RE_HIFEN = re.compile(r"[-‐‑]")
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASTA_DOS_LEXICOS = os.path.join(_RAIZ, "assets", "lexico")


def e_notacao(token: str) -> bool:
    """A cópia de `notacao.e_token_de_notacao`: lance, número de lance, sinal ou resultado."""
    if not token:
        return False
    if any(c in FIGURINAS for c in token):
        return True
    if RE_NUMERO_DE_LANCE.match(token) or RE_SINAL_DE_AVALIACAO.match(token):
        return True
    nucleo = token.strip(_PONTUACAO_DE_BORDA)
    if not nucleo:
        return False
    return RE_LANCE_ESTRITO.match(nucleo) is not None or RE_RESULTADO.match(nucleo) is not None


def nucleo(token: str) -> tuple[str, int]:
    """`(núcleo, deslocamento)`: o token sem a pontuação das pontas (nunca do meio)."""
    i, j = 0, len(token)
    while i < j and not token[i].isalpha():
        i += 1
    while j > i and not token[j - 1].isalpha():
        j -= 1
    return token[i:j], i


# ----------------------------------------------------------------------
# Suspeitas
# ----------------------------------------------------------------------

@dataclass
class Suspeita:
    arquivo: str
    alvo: Alvo
    ini: int                          # em `alvo.texto`
    fim: int
    palavra: str
    idioma: str

    @property
    def contexto(self) -> str:
        texto = self.alvo.texto
        a, b = max(0, self.ini - 30), min(len(texto), self.fim + 30)
        return ("…" if a else "") + texto[a:b].replace("\n", " ") + ("…" if b < len(texto) else "")


def _mapa_de_formato(paragrafo: Paragrafo | None,
                     legenda: Sequence[Trecho] | None = None) -> list[tuple[int, int, Trecho]]:
    """`(ini, fim, trecho)` de cada trecho no texto do parágrafo (ou da legenda)."""
    saida: list[tuple[int, int, Trecho]] = []
    andado = 0
    for t in (paragrafo.trechos if paragrafo is not None else (legenda or [])):
        ini = andado + (1 if t.quebra_antes else 0)
        fim = ini + len(t.texto)
        saida.append((ini, fim, t))
        andado = fim
    return saida


def _trecho_em(mapa: Sequence[tuple[int, int, Trecho]], posicao: int) -> Trecho | None:
    for ini, fim, t in mapa:
        if ini <= posicao < fim:
            return t
    return None


def _idioma_do_trecho(trecho: Trecho | None, padrao: str) -> str:
    if trecho is not None and trecho.lang:
        return trecho.lang.split("-")[0].lower()
    return (padrao or "").split("-")[0].lower()


def palavras_do_alvo(alvo: Alvo, paragrafo: Paragrafo | None, legenda: Sequence[Trecho] | None = None,
                     idioma: str = "") -> list[tuple[int, int, str, str]]:
    """
    `(ini, fim, palavra, idioma)` de cada palavra candidata do alvo — já sem a notação,
    os números, as maiúsculas, o código, as ilhas e os trechos com papel de xadrez.
    """
    mapa = _mapa_de_formato(paragrafo, legenda)
    saida: list[tuple[int, int, str, str]] = []
    for m in _RE_TOKEN.finditer(alvo.texto):
        token = m.group(0)
        if e_notacao(token) or any(c.isdigit() for c in token):
            continue
        nuc, desloc = nucleo(token)
        if not nuc or not any(c.isalpha() for c in nuc):
            continue
        if any(c in FIGURINAS for c in nuc):
            continue
        if len(nuc) > 1 and nuc.isupper():
            continue
        ini = m.start() + desloc
        trecho = _trecho_em(mapa, ini)
        if trecho is not None and (trecho.papel in PAPEIS_FORA or trecho.codigo or trecho.ilha):
            continue
        saida.append((ini, ini + len(nuc), nuc, _idioma_do_trecho(trecho, idioma)))
    return saida


def conhecida(palavra: str, lex: Any) -> bool:
    """A palavra, ou cada parte dela (`Black's`, `Nimzo-Indian`), está no léxico?"""
    if lex.conhece(palavra):
        return True
    partes = [p for p in _RE_HIFEN.split(palavra) if p]
    if len(partes) > 1 and all(conhecida(p, lex) for p in partes):
        return True
    partes = [p for p in _RE_APOSTROFO.split(palavra) if p]
    if len(partes) > 1:
        cabeca = partes[0]
        resto = "".join(partes[1:]).lower()
        if lex.conhece(cabeca) and resto in ("s", "", "ll", "re", "ve", "d", "t", "m"):
            return True
    return False


def verificar(cap: Capitulo, lexico_de: Callable[[str], Any], idioma: str = "",
              ignoradas: Sequence[str] = ()) -> list[Suspeita]:
    """
    As palavras do capítulo que o léxico do seu idioma não conhece, em ordem de leitura.
    `lexico_de(idioma)` devolve o `Lexico`; um léxico que não `sinaliza` (vazio) não
    acusa nada. Um capítulo só em `texto_cru` não é verificado (é o modo código).
    """
    if cap.texto_cru is not None:
        return []
    idioma = cap.idioma or idioma
    ignoradas_baixas = {p.lower() for p in ignoradas}
    saida: list[Suspeita] = []
    cache: dict[str, Any] = {}
    for alvo in busca.alvos_do_capitulo(cap):
        paragrafo = busca.paragrafo_do_alvo(cap, alvo)
        legenda = None
        if alvo.caminho[0] == "legenda":
            bloco = cap.bloco(alvo.bloco_id)
            legenda = getattr(bloco, "legenda", None)
        for ini, fim, palavra, lang in palavras_do_alvo(alvo, paragrafo, legenda, idioma):
            if palavra.lower() in ignoradas_baixas:
                continue
            if lang not in cache:
                cache[lang] = lexico_de(lang)
            lex = cache[lang]
            if lex is None or not getattr(lex, "sinaliza", False):
                continue
            if conhecida(palavra, lex):
                continue
            saida.append(Suspeita(cap.arquivo, alvo, ini, fim, palavra, lang))
    return saida


def verificar_livro(livro: Livro, lexico_de: Callable[[str], Any], ignoradas: Sequence[str] = ()) -> list[Suspeita]:
    saida: list[Suspeita] = []
    for cap in livro.capitulos:
        saida.extend(verificar(cap, lexico_de, livro.metadados.idioma, ignoradas))
    return saida


# ----------------------------------------------------------------------
# Os léxicos e o dicionário do livro
# ----------------------------------------------------------------------

def caminho_do_dicionario(caminho_do_livro: str | None) -> str | None:
    """`<livro>.lexico.txt`, ao lado do EPUB (o mesmo arquivo do PDF de origem); `None` sem caminho."""
    if not caminho_do_livro:
        return None
    from core import lexico

    return lexico.caminho_do_usuario(caminho_do_livro, e_pdf=True)


def caminho_do_lexico(idioma: str) -> str | None:
    """O `assets/lexico/<idioma>.txt.gz` do idioma, se existe."""
    idioma = (idioma or "").split("-")[0].lower()
    if not idioma:
        return None
    caminho = os.path.join(PASTA_DOS_LEXICOS, f"{idioma}.txt.gz")
    return caminho if os.path.exists(caminho) else None


@dataclass
class Lexicos:
    """
    Os léxicos da sessão, um por idioma, com o dicionário do livro em todos; `ignoradas`
    são as "Ignorar todas" desta sessão. `carregar` importa `core.lexico` só aqui.
    """

    caminho_do_livro: str | None = None
    ignoradas: set[str] = field(default_factory=set)
    _por_idioma: dict[str, Any] = field(default_factory=dict, repr=False)

    def __call__(self, idioma: str) -> Any:
        return self.carregar(idioma)

    def carregar(self, idioma: str) -> Any:
        idioma = (idioma or "").split("-")[0].lower() or "en"
        if idioma in self._por_idioma:
            return self._por_idioma[idioma]
        from core import lexico

        usuario = caminho_do_dicionario(self.caminho_do_livro)
        if idioma == "en":
            lex = lexico.carregar(caminho_usuario=usuario, idioma="en")
        else:
            lex = lexico.carregar(caminho=caminho_do_lexico(idioma) or os.path.join(PASTA_DOS_LEXICOS, "nada"),
                                  caminho_usuario=usuario, idioma=idioma, nomes=False)
        self._por_idioma[idioma] = lex
        return lex

    def palavras_do_livro(self) -> list[str]:
        """O dicionário do livro, em ordem (o que está no arquivo, mais o acrescentado nesta sessão)."""
        palavras: set[str] = set()
        for lex in self._por_idioma.values():
            palavras |= set(lex.do_usuario)
        caminho = caminho_do_dicionario(self.caminho_do_livro)
        if caminho and os.path.exists(caminho):
            with open(caminho, encoding="utf-8", errors="replace") as f:
                palavras |= {ln.strip().lower() for ln in f if ln.strip()}
        return sorted(palavras)

    def adicionar(self, palavra: str) -> bool:
        """"Adicionar": entra em todos os léxicos carregados e no `<livro>.lexico.txt`; `False` se já estava."""
        from core import lexico

        nova = False
        for lex in self._por_idioma.values():
            nova = lex.acrescentar(palavra) or nova
        if not self._por_idioma:
            nova = True
        caminho = caminho_do_dicionario(self.caminho_do_livro)
        if caminho is None:
            raise ValueError("salve o livro antes: o dicionário do livro fica ao lado do EPUB")
        todas = set(self.palavras_do_livro()) | {palavra.strip().lower()}
        lexico.salvar_do_usuario(caminho, todas)
        return nova

    def remover(self, palavra: str) -> bool:
        from core import lexico

        baixa = palavra.strip().lower()
        estava = False
        for lex in self._por_idioma.values():
            if baixa in lex.do_usuario:
                lex.do_usuario.discard(baixa)
                estava = True
        caminho = caminho_do_dicionario(self.caminho_do_livro)
        if caminho is None:
            raise ValueError("salve o livro antes: o dicionário do livro fica ao lado do EPUB")
        todas = set(self.palavras_do_livro())
        if baixa in todas:
            estava = True
        todas.discard(baixa)
        lexico.salvar_do_usuario(caminho, todas)
        return estava

    def ignorar(self, palavra: str) -> None:
        self.ignoradas.add(palavra.lower())

    def sugestoes(self, palavra: str, idioma: str, n: int = 5) -> list[str]:
        from core import lexico

        lex = self.carregar(idioma)
        return lexico.sugestoes(palavra, lex, n)


def trocar(cap: Capitulo, suspeita: Suspeita, por: str) -> Any:
    """O bloco (ou a nota) da suspeita com a palavra trocada — o que o widget redesenha."""
    ocorrencia = busca.Ocorrencia(cap.arquivo, suspeita.ini, suspeita.fim, suspeita.palavra, suspeita.alvo)
    if suspeita.alvo.caminho[0] == "nota":
        return busca.nota_substituida(cap, ocorrencia, por)
    return busca.bloco_substituido(cap, ocorrencia, por)


def texto_do_capitulo(cap: Capitulo) -> str:
    return "\n".join(modelo.texto_de(b) for b in cap.blocos)


__all__ = ["Suspeita", "Lexicos", "verificar", "verificar_livro", "palavras_do_alvo", "conhecida", "e_notacao",
           "nucleo", "caminho_do_dicionario", "caminho_do_lexico", "trocar", "FIGURINAS", "PAPEIS_FORA",
           "PASTA_DOS_LEXICOS"]
