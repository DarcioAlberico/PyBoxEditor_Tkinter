"""
Os erros **confiantes** da cadeia de glifos, garimpados contra a referência.

A OCR-14 (item 5 da revisão de 2026-09-18) é o resíduo que a fila de suspeitas
não alcança: `⩲` lido como `±`, `♕c1` por `♕e1`, `gxh6` por `g16`. Não são
leituras hesitantes — a medição da F22 registrou **mediana 1,00 de confiança
nos tokens errados** —, e é isso que os põe fora do alcance de qualquer régua
de confiança: para o programa, eles não são dúvida nenhuma.

O que sobra é treino dirigido. E treino dirigido precisa, antes de tudo, de uma
lista: *que par de glifos a cadeia troca, quantas vezes, e onde está cada
recorte*. É o que este módulo produz — e é só isso que ele faz. Ele não treina,
não rotula base e não escreve em `training_data/`: a etapa do meio continua
sendo humana, pela mesma razão que `core/coleta.py` explica em detalhe
(gravar o palpite do modelo como verdade é treiná-lo no próprio erro).

## Como o garimpo acha o recorte

A referência humana é texto de página; a cadeia produz caractere a caractere,
cada um com a caixa de onde saiu. Alinhando os dois — tokens primeiro, pela
mesma régua de Levenshtein do A/B (`ocr_ab.alinhar_tokens`), e caracteres dentro
do token depois — cada divergência vira um `ErroConfiante` com a caixa do glifo,
a confiança com que ele foi lido e o domínio do token (lance ou prosa).

**A dobra tipográfica é a do A/B**, e pelo mesmo motivo: contar `–` contra `-`
mediria a convenção de impressão, não o reconhecimento. Aqui ela é feita
caractere a caractere, guardando de que caixa cada um veio, porque uma dobra que
muda o comprimento do texto (`…` vira `...`) desalinharia o mapa.

**Buraco e invenção entram na lista, e marcados.** O que a cadeia comeu não tem
caixa própria — vai com a do vizinho e `lido=""` —, e o que ela inventou vai com
`esperado=""`. Os dois são material de treino de natureza diferente do par
trocado, e quem lê a tabela precisa saber qual é qual.
"""

from __future__ import annotations

import collections
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from core.ocr_ab import _TIPOGRAFIA, _dominio_do_token, alinhar_tokens, normalizar_tipografia

#: Acima desta confiança, a leitura errada é **afirmação** — o assunto da
#: OCR-14. Abaixo, o erro já é alcançável pela fila de suspeitas e pela coleta
#: de baixa confiança (`core/coleta.py`), que existem desde a F2.7.
PISO_DE_CONFIANCA = 0.90


@dataclass(frozen=True)
class CaractereLido:
    """Um caractere que a cadeia escreveu, e de onde ele saiu.

    `caixa` é a do glifo na página, em pixels da imagem lida; `indice_do_box` é
    a posição dele na lista de boxes da página, que é como `core/coleta.py` e o
    `marcador_confianca` de `livro._texto_da_linha` o endereçam.
    """

    texto: str
    confianca: float = 1.0
    caixa: tuple[int, int, int, int] | None = None
    indice_do_box: int = -1
    linha: int = -1


@dataclass(frozen=True)
class ErroConfiante:
    """Uma divergência entre a cadeia e a referência humana, com a procedência."""

    esperado: str
    lido: str
    confianca: float
    dominio: str
    token_esperado: str
    token_lido: str
    caixa: tuple[int, int, int, int] | None = None
    indice_do_box: int = -1
    linha: int = -1
    pagina: int = 0

    @property
    def especie(self) -> str:
        """`troca`, `buraco` (a cadeia comeu) ou `invencao` (a cadeia pôs)."""
        if not self.lido:
            return "buraco"
        if not self.esperado:
            return "invencao"
        return "troca"

    @property
    def confiante(self) -> bool:
        return self.confianca >= PISO_DE_CONFIANCA

    def to_dict(self) -> dict[str, Any]:
        return {"esperado": self.esperado, "lido": self.lido,
                "confianca": round(float(self.confianca), 4),
                "dominio": self.dominio, "especie": self.especie,
                "token_esperado": self.token_esperado,
                "token_lido": self.token_lido,
                "caixa": list(self.caixa) if self.caixa else None,
                "indice_do_box": self.indice_do_box, "linha": self.linha,
                "pagina": self.pagina}


def dobrar_caractere(caractere: str) -> str:
    """A dobra tipográfica do A/B, aplicada a um caractere só."""
    return unicodedata.normalize("NFKC", str(caractere).translate(_TIPOGRAFIA))


def _texto_com_origem(lidos: Sequence[CaractereLido]) -> tuple[str, list[int]]:
    """O texto dobrado da página e, por posição, o índice do `CaractereLido`.

    Uma dobra que cresce (`…` vira `...`) faz três posições apontarem para a
    mesma caixa — que é a resposta certa: as três saíram daquele glifo.
    """
    texto: list[str] = []
    origem: list[int] = []
    for indice, item in enumerate(lidos):
        for caractere in dobrar_caractere(item.texto):
            texto.append(caractere)
            origem.append(indice)
    return "".join(texto), origem


def _tokens_com_posicao(texto: str) -> list[tuple[str, int]]:
    """Os tokens do texto e a posição em que cada um começa."""
    saida: list[tuple[str, int]] = []
    inicio = -1
    for posicao, caractere in enumerate(texto):
        if caractere.isspace():
            if inicio >= 0:
                saida.append((texto[inicio:posicao], inicio))
                inicio = -1
        elif inicio < 0:
            inicio = posicao
    if inicio >= 0:
        saida.append((texto[inicio:], inicio))
    return saida


def minerar(lidos: Sequence[CaractereLido], referencia: str, *,
            pagina: int = 0) -> list[ErroConfiante]:
    """As divergências entre o que a cadeia leu e o que a referência diz.

    Sai tudo — confiante ou não —, porque a régua do que é "confiante" é do
    chamador e muda com o que se quer medir; `ErroConfiante.confiante` responde
    pelo piso padrão.
    """
    texto, origem = _texto_com_origem(lidos)
    tokens_lidos = _tokens_com_posicao(texto)
    tokens_referencia = normalizar_tipografia(referencia).split()
    erros: list[ErroConfiante] = []
    pares = alinhar_tokens(tokens_referencia,
                           [token for token, _posicao in tokens_lidos])
    ordem = 0
    for esperado, lido in pares:
        posicao = None
        if lido is not None:
            # Os tokens lidos saem na ordem, e o alinhamento os consome na
            # ordem: o contador diz de qual deles este par veio.
            _token, posicao = tokens_lidos[ordem]
            ordem += 1
        if esperado is None or lido is None or esperado != lido:
            erros.extend(_erros_do_token(esperado, lido, posicao, lidos, origem,
                                         pagina=pagina))
    return erros


def _erros_do_token(esperado: str | None, lido: str | None, posicao: int | None,
                    lidos: Sequence[CaractereLido], origem: Sequence[int], *,
                    pagina: int) -> list[ErroConfiante]:
    """As divergências de caractere dentro de um par de tokens desalinhado."""
    dominio = _dominio_do_token(esperado or lido or "")
    saida: list[ErroConfiante] = []
    deslocamento = 0
    for caractere_esperado, caractere_lido in alinhar_tokens(esperado or "",
                                                             lido or ""):
        fonte = None
        if caractere_lido is not None and posicao is not None:
            indice = origem[posicao + deslocamento]
            fonte = lidos[indice]
            deslocamento += 1
        elif posicao is not None:
            # Buraco: não há glifo deste lado. A caixa do vizinho é o que
            # localiza o erro na página — e a espécie diz que ela é do vizinho.
            indice = origem[min(posicao + deslocamento, len(origem) - 1)]
            fonte = lidos[indice] if origem else None
        if caractere_esperado == caractere_lido:
            continue
        saida.append(ErroConfiante(
            esperado=caractere_esperado or "", lido=caractere_lido or "",
            confianca=float(getattr(fonte, "confianca", 0.0) or 0.0),
            dominio=dominio, token_esperado=esperado or "", token_lido=lido or "",
            caixa=getattr(fonte, "caixa", None),
            indice_do_box=int(getattr(fonte, "indice_do_box", -1)),
            linha=int(getattr(fonte, "linha", -1)), pagina=pagina))
    return saida


def tabela_de_confusao(erros: Iterable[ErroConfiante], *,
                       so_confiantes: bool = True) -> collections.Counter:
    """Quantas vezes cada `(lido, esperado)` aconteceu, do mais comum ao menos."""
    return collections.Counter(
        (erro.lido, erro.esperado) for erro in erros
        if not so_confiantes or erro.confiante)


@dataclass
class Resumo:
    """O que a página inteira diz sobre o resíduo confiante."""

    erros: list[ErroConfiante] = field(default_factory=list)

    @property
    def confiantes(self) -> list[ErroConfiante]:
        return [erro for erro in self.erros if erro.confiante]

    def no_dominio(self, dominio: str) -> "Resumo":
        """Só o que caiu em lance (`notation`) ou em prosa (`prose`).

        **A pergunta da OCR-14 é a do lance**, e não a da página: a fusão por
        palavra dá a prosa ao motor e guarda o lance da cadeia
        (`livro._fundir_por_palavra`), então o erro confiante da cadeia num
        token de prosa não chega ao livro — o do lance chega, e é o único que
        sobrevive à exportação. Medido na p. 30 do Aagaard em 2026-09-22: 177
        erros confiantes da cadeia, 154 deles em prosa e **23 em lance**.
        """
        if dominio in ("", "todos"):
            return Resumo(list(self.erros))
        return Resumo([erro for erro in self.erros if erro.dominio == dominio])

    def por_dominio(self) -> Mapping[str, int]:
        return collections.Counter(erro.dominio for erro in self.confiantes)

    def por_especie(self) -> Mapping[str, int]:
        return collections.Counter(erro.especie for erro in self.confiantes)

    def classes_a_treinar(self, *, minimo: int = 2) -> list[tuple[str, int]]:
        """As classes que mais ganhariam com amostra nova, da pior para a menos pior.

        É a classe **esperada** que se conta, e não a lida: o que falta ao
        modelo é exemplo do glifo que ele não reconhece. Trocas isoladas ficam
        de fora (`minimo`), porque uma amostra não move um classificador e a
        lista existe para dirigir esforço.
        """
        contagem = collections.Counter(
            erro.esperado for erro in self.confiantes
            if erro.esperado and erro.especie == "troca")
        return [(classe, n) for classe, n in contagem.most_common() if n >= minimo]

    def to_dict(self) -> dict[str, Any]:
        return {
            "erros": len(self.erros), "confiantes": len(self.confiantes),
            "por_dominio": dict(self.por_dominio()),
            "por_especie": dict(self.por_especie()),
            "confusoes": [{"lido": lido, "esperado": esperado, "vezes": vezes}
                          for (lido, esperado), vezes
                          in tabela_de_confusao(self.erros).most_common()],
            "classes_a_treinar": [{"classe": classe, "vezes": vezes}
                                  for classe, vezes in self.classes_a_treinar()],
        }
