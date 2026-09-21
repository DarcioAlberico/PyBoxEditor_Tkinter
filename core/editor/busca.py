"""
Localizar e substituir, sobre o modelo e sobre o XHTML cru (ED-06; SPEC_EDITOR §8.12,
§9.4).

## O adaptador de trechos

No modo texto a busca corre sobre o **texto do modelo** de cada parágrafo — o
`texto_de` que junta os trechos —, e não sobre o XHTML: "Nimzo**w**itsch" com o `w`
em negrito é `Nimzo<strong>w</strong>itsch` no arquivo, e só o adaptador acha a
palavra inteira (AC-ED06-1). Cada unidade pesquisável é um `Alvo`: o parágrafo (de
cima, de uma lista, de uma citação, de uma célula, de uma nota) ou a legenda de uma
figura, tabela ou diagrama, com o **deslocamento** dentro do bloco de cima — o número
que `TextoRico.indice_de(bloco_id, deslocamento)` converte em posição do widget. No
modo código (e num capítulo que só existe em `texto_cru`) a busca corre sobre o
texto cru, e a ocorrência tem linha e coluna.

## Substituir preserva o formato

`substituir_em_trechos` parte os trechos nas duas fronteiras da ocorrência
(`modelo._partir`), tira o que está dentro e põe o texto novo **com o formato do
primeiro caractere substituído** — como o Word. O que não tem comprimento no texto
(a referência de nota, a ilha inline, a marca de página) fica onde estava. Num
capítulo que não está aberto, `substituir_tudo_no_capitulo` mexe no modelo e registra
**um ponto por capítulo** no `Historico` (AC-ED06-2); o capítulo aberto é do widget,
que faz o mesmo pelo `_reescrever_bloco`.

## Circular

`proxima` recebe as ocorrências em ordem de leitura e a chave da posição do cursor;
com `circular`, a busca que chega ao fim volta ao começo e diz que voltou.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from core.editor import modelo
from core.editor.modelo import (Bloco, Capitulo, Citacao, Diagrama, Figura, Lista, Livro, MarcaDePagina, Nota,
                                Paragrafo, Tabela, Trecho)

ESCOPOS = ("selecao", "capitulo", "livro", "marcados", "abas", "marcado")
ROTULOS_DOS_ESCOPOS = {"selecao": "Seleção", "capitulo": "Capítulo atual", "livro": "Livro inteiro",
                       "marcados": "Arquivos marcados", "abas": "Abas abertas", "marcado": "Texto marcado"}
NBSP = "\u00a0"
LIMITE_DO_HISTORICO = 20
_RE_QUANTIFICADOR = re.compile(r"(\*|\+|\?|\{\d*,?\d*\})(?![?+])")


# ----------------------------------------------------------------------
# Opções e padrão
# ----------------------------------------------------------------------

@dataclass
class Opcoes:
    """A caixa da §8.12, campo a campo."""

    texto: str = ""
    substituto: str = ""
    maiusculas: bool = False          # diferencia maiúsculas de minúsculas
    palavra_inteira: bool = False
    regex: bool = False
    dotall: bool = False
    minimo: bool = False              # quantificadores mínimos (`.*` vira `.*?`)
    espaco_casa_nbsp: bool = True     # "espaço casa também o inseparável"
    circular: bool = True
    escopo: str = "capitulo"
    direcao: int = 1

    def __post_init__(self) -> None:
        if self.escopo not in ESCOPOS:
            raise ValueError(f"escopo desconhecido: {self.escopo!r}")
        self.direcao = 1 if int(self.direcao) >= 0 else -1


def _com_nbsp(padrao: str, regex: bool) -> str:
    """Todo espaço literal do padrão passa a casar também o U+00A0 (fora de uma classe `[…]`)."""
    saida: list[str] = []
    em_classe = False
    i = 0
    while i < len(padrao):
        c = padrao[i]
        if c == "\\" and i + 1 < len(padrao):
            if padrao[i + 1] == " " and not em_classe:
                saida.append(f"[ {NBSP}]")
            else:
                saida.append(padrao[i:i + 2])
            i += 2
            continue
        if regex and c == "[":
            em_classe = True
        elif regex and c == "]":
            em_classe = False
        if c == " " and not em_classe:
            saida.append(f"[ {NBSP}]")
        elif c == NBSP and not em_classe:
            saida.append(f"[ {NBSP}]")
        else:
            saida.append(c)
        i += 1
    return "".join(saida)


def compilar(opcoes: Opcoes) -> re.Pattern:
    """O `re.Pattern` das opções; um regex inválido é `ValueError` com a mensagem do `re`."""
    if not opcoes.texto:
        raise ValueError("digite o que procurar")
    padrao = opcoes.texto if opcoes.regex else re.escape(opcoes.texto)
    if opcoes.regex and opcoes.minimo:
        padrao = _RE_QUANTIFICADOR.sub(lambda m: m.group(1) + "?", padrao)
    if opcoes.espaco_casa_nbsp:
        padrao = _com_nbsp(padrao, opcoes.regex)
    if opcoes.palavra_inteira:
        padrao = rf"(?<!\w)(?:{padrao})(?!\w)"
    flags = re.MULTILINE
    if not opcoes.maiusculas:
        flags |= re.IGNORECASE
    if opcoes.dotall:
        flags |= re.DOTALL
    try:
        return re.compile(padrao, flags)
    except re.error as erro:
        raise ValueError(f"expressão regular inválida: {erro}") from None


# ----------------------------------------------------------------------
# Os alvos: o adaptador de trechos
# ----------------------------------------------------------------------

@dataclass
class Alvo:
    """Uma unidade de texto pesquisável de um capítulo (ver o cabeçalho)."""

    arquivo: str
    bloco_id: str                     # o bloco de cima (ou o parágrafo da nota, que é bloco no widget)
    texto: str                        # `texto_de` do parágrafo ou da legenda
    caminho: tuple                    # ("bloco",) | ("lista", k) | ("citacao", k) | ("celula", f, c, k)
    #                                 # | ("legenda",) | ("nota", id, k)
    deslocamento: int | None = 0      # onde `texto` começa no `texto_de` do bloco de cima; `None` = fora dele
    indice: int = 0                   # a posição do alvo na ordem de leitura do capítulo

    @property
    def enderecavel(self) -> bool:
        """Dá para pôr o cursor nele por `TextoRico.indice_de`?"""
        return self.deslocamento is not None


def _paragrafos_internos(bloco: Bloco) -> list[Paragrafo]:
    """Os parágrafos de uma lista (achatada, na ordem do desenho) ou de uma citação."""
    if isinstance(bloco, Citacao):
        return list(bloco.blocos)
    if isinstance(bloco, Lista):
        saida: list[Paragrafo] = []
        for item in bloco.itens:
            saida.extend(item.paragrafos)
            if item.filhos is not None:
                saida.extend(_paragrafos_internos(item.filhos))
        return saida
    return []


def alvos_do_capitulo(cap: Capitulo) -> list[Alvo]:
    """Os alvos do capítulo em ordem de leitura: blocos de cima, depois as notas."""
    alvos: list[Alvo] = []
    arquivo = cap.arquivo

    def novo(bloco_id: str, texto: str, caminho: tuple, deslocamento: int | None) -> None:
        alvos.append(Alvo(arquivo, bloco_id, texto, caminho, deslocamento, len(alvos)))

    for bloco in cap.blocos:
        if isinstance(bloco, Paragrafo):
            novo(bloco.id, modelo.texto_de(bloco), ("bloco",), 0)
        elif isinstance(bloco, (Lista, Citacao)):
            tipo = "lista" if isinstance(bloco, Lista) else "citacao"
            andados = 0
            for k, p in enumerate(_paragrafos_internos(bloco)):
                texto = modelo.texto_de(p)
                novo(bloco.id, texto, (tipo, k), andados)
                andados += len(texto) + 1
        elif isinstance(bloco, Tabela):
            for f, fila in enumerate(bloco.filas):
                for c, celula in enumerate(fila):
                    for k, p in enumerate(celula.blocos):
                        novo(bloco.id, modelo.texto_de(p), ("celula", f, c, k), None)
            if bloco.legenda:
                novo(bloco.id, "".join(t.texto for t in bloco.legenda), ("legenda",), None)
        elif isinstance(bloco, (Figura, Diagrama)):
            if bloco.legenda:
                novo(bloco.id, "".join(t.texto for t in bloco.legenda), ("legenda",), None)
    for nota in cap.notas:
        for k, p in enumerate(nota.blocos):
            novo(p.id, modelo.texto_de(p), ("nota", nota.id, k), 0)
    return alvos


def paragrafo_do_alvo(cap: Capitulo, alvo: Alvo) -> Paragrafo | None:
    """O parágrafo do modelo que o alvo descreve (`None` para uma legenda)."""
    caminho = alvo.caminho
    if caminho[0] == "nota":
        nota = cap.nota(caminho[1])
        return nota.blocos[caminho[2]] if nota is not None and caminho[2] < len(nota.blocos) else None
    bloco = cap.bloco(alvo.bloco_id)
    if bloco is None:
        return None
    if caminho[0] == "bloco":
        return bloco if isinstance(bloco, Paragrafo) else None
    if caminho[0] in ("lista", "citacao"):
        internos = _paragrafos_internos(bloco)
        return internos[caminho[1]] if caminho[1] < len(internos) else None
    if caminho[0] == "celula" and isinstance(bloco, Tabela):
        _c, f, c, k = caminho
        try:
            return bloco.filas[f][c].blocos[k]
        except IndexError:
            return None
    return None


# ----------------------------------------------------------------------
# Ocorrências
# ----------------------------------------------------------------------

@dataclass
class Ocorrencia:
    arquivo: str
    ini: int                          # no `alvo.texto`, ou no texto cru
    fim: int
    texto: str
    alvo: Alvo | None = None          # `None` no cru
    casamento: Any = None             # o `re.Match`, para o `\\1` do substituto
    linha: int = 0                    # só no cru
    coluna: int = 0
    contexto: str = ""

    @property
    def cru(self) -> bool:
        return self.alvo is None

    @property
    def onde(self) -> str:
        if self.cru:
            return f"linha {self.linha}, col {self.coluna}"
        caminho = self.alvo.caminho if self.alvo else ("bloco",)
        if caminho[0] == "nota":
            return f"nota {caminho[1]}"
        if caminho[0] == "celula":
            return f"tabela, célula {caminho[1] + 1},{caminho[2] + 1}"
        if caminho[0] == "legenda":
            return "legenda"
        return f"bloco {self.alvo.bloco_id}" if self.alvo else ""

    @property
    def chave(self) -> tuple:
        """A posição comparável dentro do arquivo (ordem de leitura)."""
        if self.cru:
            return (self.ini,)
        assert self.alvo is not None
        return (self.alvo.indice, self.ini)


def _contexto(texto: str, ini: int, fim: int, folga: int = 30) -> str:
    a, b = max(0, ini - folga), min(len(texto), fim + folga)
    trecho = texto[a:b].replace("\n", "⏎")
    return ("…" if a > 0 else "") + trecho + ("…" if b < len(texto) else "")


def procurar_em_alvos(alvos: Sequence[Alvo], padrao: re.Pattern) -> list[Ocorrencia]:
    saida: list[Ocorrencia] = []
    for alvo in alvos:
        for m in padrao.finditer(alvo.texto):
            if m.end() == m.start():
                continue              # um casamento vazio não é ocorrência
            saida.append(Ocorrencia(alvo.arquivo, m.start(), m.end(), m.group(0), alvo, m,
                                    contexto=_contexto(alvo.texto, m.start(), m.end())))
    return saida


def procurar_no_cru(texto: str, padrao: re.Pattern, arquivo: str = "") -> list[Ocorrencia]:
    """As ocorrências no texto cru, com linha e coluna (a partir de 1)."""
    saida: list[Ocorrencia] = []
    inicios = [0]
    for k, c in enumerate(texto):
        if c == "\n":
            inicios.append(k + 1)
    import bisect

    for m in padrao.finditer(texto):
        if m.end() == m.start():
            continue
        linha = bisect.bisect_right(inicios, m.start())
        coluna = m.start() - inicios[linha - 1] + 1
        saida.append(Ocorrencia(arquivo, m.start(), m.end(), m.group(0), None, m, linha, coluna,
                                _contexto(texto, m.start(), m.end())))
    return saida


def procurar_no_capitulo(cap: Capitulo, padrao: re.Pattern) -> list[Ocorrencia]:
    """No cru quando o capítulo só existe como `texto_cru`; senão pelo adaptador."""
    if cap.texto_cru is not None:
        return procurar_no_cru(cap.texto_cru, padrao, cap.arquivo)
    return procurar_em_alvos(alvos_do_capitulo(cap), padrao)


def procurar_no_livro(livro: Livro, padrao: re.Pattern,
                      arquivos: Iterable[str] | None = None) -> dict[str, list[Ocorrencia]]:
    """`{arquivo: ocorrências}` na ordem da espinha, só dos capítulos com alguma."""
    escolhidos = set(arquivos) if arquivos is not None else None
    saida: dict[str, list[Ocorrencia]] = {}
    for cap in livro.capitulos:
        if escolhidos is not None and cap.arquivo not in escolhidos:
            continue
        achadas = procurar_no_capitulo(cap, padrao)
        if achadas:
            saida[cap.arquivo] = achadas
    return saida


def contar_por_arquivo(livro: Livro, padrao: re.Pattern, arquivos: Iterable[str] | None = None) -> dict[str, int]:
    return {arquivo: len(lista) for arquivo, lista in procurar_no_livro(livro, padrao, arquivos).items()}


def proxima(ocorrencias: Sequence[Ocorrencia], posicao: tuple, direcao: int = 1,
            circular: bool = True) -> tuple[Ocorrencia | None, bool]:
    """
    A ocorrência seguinte (`direcao=1`: a primeira com chave ≥ `posicao`) ou a anterior
    (a última que termina antes de `posicao`); `(None, False)` quando não há; com
    `circular`, dá a volta e devolve `(ocorrência, True)`.
    """
    if not ocorrencias:
        return None, False
    if direcao >= 0:
        for o in ocorrencias:
            if o.chave >= tuple(posicao):
                return o, False
        return (ocorrencias[0], True) if circular else (None, False)
    for o in reversed(ocorrencias):
        fim = o.chave[:-1] + (o.fim,)
        if fim <= tuple(posicao):
            return o, False
    return (ocorrencias[-1], True) if circular else (None, False)


# ----------------------------------------------------------------------
# Substituir
# ----------------------------------------------------------------------

def expandir(ocorrencia: Ocorrencia, substituto: str, opcoes: Opcoes) -> str:
    """O texto que entra no lugar: com regex, `\\1` e `\\g<nome>` expandem-se."""
    if opcoes.regex and ocorrencia.casamento is not None:
        try:
            return ocorrencia.casamento.expand(substituto)
        except (re.error, IndexError) as erro:
            raise ValueError(f"substituto inválido: {erro}") from None
    return substituto


def substituir_em_trechos(trechos: Sequence[Trecho], ini: int, fim: int, novo: str) -> list[Trecho]:
    """
    Os trechos com `[ini, fim)` do texto trocado por `novo`, no formato do primeiro
    caractere trocado. Um `\\n` no substituto vira quebra suave; a marca de página do
    primeiro trecho trocado sobrevive nele.
    """
    if ini > fim:
        ini, fim = fim, ini
    partidos = modelo._partir(modelo._partir(list(trechos), ini), fim)
    saida: list[Trecho] = []
    molde: Trecho | None = None
    posto = False
    for trecho, dentro in modelo._no_intervalo(partidos, ini, fim):
        if dentro and not trecho.ilha:
            if molde is None:
                molde = trecho
            continue
        if molde is not None and not posto:
            saida.extend(_com_texto(molde, novo))
            posto = True
        saida.append(trecho)
    if molde is not None and not posto:
        saida.extend(_com_texto(molde, novo))
        posto = True
    if not posto:
        # Nada de texto dentro do intervalo (só ilhas, ou o intervalo vazio): o texto novo
        # entra no formato do vizinho da esquerda, na posição pedida.
        vizinho = next((t for t in reversed(saida) if t.texto), None) or Trecho()
        k = _indice_do_trecho_em(saida, ini)
        saida[k:k] = _com_texto(vizinho, novo, marca=False)
    return modelo.trechos_normalizados(saida)


def _com_texto(molde: Trecho, texto: str, marca: bool = True) -> list[Trecho]:
    """Um trecho por linha de `texto`, com o formato de `molde` (a primeira leva a marca de página dele)."""
    saida: list[Trecho] = []
    for k, parte in enumerate(texto.split("\n")):
        t = copy.copy(molde)
        t.texto = parte
        t.ilha = ""
        t.nota = ""
        t.quebra_antes = k > 0
        t.pagina = molde.pagina if (k == 0 and marca) else None
        saida.append(t)
    return saida


def _indice_do_trecho_em(trechos: Sequence[Trecho], posicao: int) -> int:
    """O índice do primeiro trecho que começa em `posicao` ou depois dela."""
    andado = 0
    for k, t in enumerate(trechos):
        if andado >= posicao:
            return k
        andado += len(t.texto) + (1 if t.quebra_antes else 0)
    return len(trechos)


def substituir_no_paragrafo(paragrafo: Paragrafo, ini: int, fim: int, novo: str) -> Paragrafo:
    """Uma cópia do parágrafo com a substituição feita."""
    copia = copy.copy(paragrafo)
    copia.trechos = substituir_em_trechos(paragrafo.trechos, ini, fim, novo)
    return copia


def bloco_substituido(cap: Capitulo, ocorrencia: Ocorrencia, novo: str) -> Bloco:
    """
    Uma cópia do bloco **de cima** da ocorrência com a substituição feita — o que o
    widget redesenha (`_reescrever_bloco`/`substituir_objeto`) e o que entra no modelo.
    """
    alvo = ocorrencia.alvo
    assert alvo is not None
    caminho = alvo.caminho
    if caminho[0] == "nota":
        nota = cap.nota(caminho[1])
        if nota is None:
            raise ValueError(f"a nota {caminho[1]} já não existe")
        return substituir_no_paragrafo(nota.blocos[caminho[2]], ocorrencia.ini, ocorrencia.fim, novo)
    bloco = cap.bloco(alvo.bloco_id)
    if bloco is None:
        raise ValueError(f"o bloco {alvo.bloco_id} já não está no capítulo")
    if caminho[0] == "bloco":
        assert isinstance(bloco, Paragrafo)
        return substituir_no_paragrafo(bloco, ocorrencia.ini, ocorrencia.fim, novo)
    copia = copy.deepcopy(bloco)
    if caminho[0] in ("lista", "citacao"):
        internos = _paragrafos_internos(copia)
        p = internos[caminho[1]]
        p.trechos = substituir_em_trechos(p.trechos, ocorrencia.ini, ocorrencia.fim, novo)
        return copia
    if caminho[0] == "celula":
        assert isinstance(copia, Tabela)
        _c, f, c, k = caminho
        p = copia.filas[f][c].blocos[k]
        p.trechos = substituir_em_trechos(p.trechos, ocorrencia.ini, ocorrencia.fim, novo)
        return copia
    if caminho[0] == "legenda":
        copia.legenda = substituir_em_trechos(copia.legenda, ocorrencia.ini, ocorrencia.fim, novo)   # type: ignore
        return copia
    raise ValueError(f"caminho desconhecido: {caminho}")


def nota_substituida(cap: Capitulo, ocorrencia: Ocorrencia, novo: str) -> Nota:
    """A nota inteira com o parágrafo trocado (o ponto de desfazer de uma nota é a nota)."""
    alvo = ocorrencia.alvo
    assert alvo is not None and alvo.caminho[0] == "nota"
    nota = cap.nota(alvo.caminho[1])
    if nota is None:
        raise ValueError(f"a nota {alvo.caminho[1]} já não existe")
    copia = copy.deepcopy(nota)
    copia.blocos[alvo.caminho[2]] = substituir_no_paragrafo(nota.blocos[alvo.caminho[2]], ocorrencia.ini,
                                                            ocorrencia.fim, novo)
    return copia


def substituir_tudo_no_capitulo(cap: Capitulo, padrao: re.Pattern, substituto: str, opcoes: Opcoes,
                                historico: Any = None, filtro: Callable[[Ocorrencia], bool] | None = None) -> int:
    """
    Toda ocorrência do capítulo (no modelo, ou no `texto_cru`) trocada, de trás para a
    frente para os deslocamentos continuarem valendo. Registra **um** ponto no
    `historico` com os blocos e notas tocados. Devolve quantas trocou.
    """
    ocorrencias = [o for o in procurar_no_capitulo(cap, padrao) if filtro is None or filtro(o)]
    if not ocorrencias:
        return 0
    if cap.texto_cru is not None:
        novo, n = substituir_tudo_no_cru(cap.texto_cru, padrao, substituto, opcoes, filtro)
        if n and historico is not None:
            historico.ponto(cap.arquivo, [], [], [], rotulo="substituir (código)")
        cap.texto_cru = novo
        return n
    antes: dict[str, Any] = {}
    depois: dict[str, Any] = {}
    indices: dict[str, int] = {}
    for o in reversed(ocorrencias):
        assert o.alvo is not None
        novo = expandir(o, substituto, opcoes)
        if o.alvo.caminho[0] == "nota":
            nota_id = o.alvo.caminho[1]
            nota = cap.nota(nota_id)
            if nota is None:
                continue
            antes.setdefault(nota_id, copy.deepcopy(nota))
            indices.setdefault(nota_id, cap.notas.index(nota))
            nova = nota_substituida(cap, o, novo)
            cap.notas[cap.notas.index(nota)] = nova
            depois[nota_id] = nova
        else:
            bloco = cap.bloco(o.alvo.bloco_id)
            if bloco is None:
                continue
            antes.setdefault(bloco.id, copy.deepcopy(bloco))
            indices.setdefault(bloco.id, cap.blocos.index(bloco))
            novo_bloco = bloco_substituido(cap, o, novo)
            cap.blocos[cap.blocos.index(bloco)] = novo_bloco
            depois[bloco.id] = novo_bloco
    if historico is not None and antes:
        ids = [i for i in antes]
        historico.ponto(cap.arquivo, ids, [antes[i] for i in ids], [depois[i] for i in ids],
                        rotulo="substituir todos", indices=indices)
    return len(ocorrencias)


def substituir_tudo_no_cru(texto: str, padrao: re.Pattern, substituto: str, opcoes: Opcoes,
                           filtro: Callable[[Ocorrencia], bool] | None = None) -> tuple[str, int]:
    """O texto cru com toda ocorrência trocada, e quantas foram."""
    ocorrencias = [o for o in procurar_no_cru(texto, padrao) if filtro is None or filtro(o)]
    partes: list[str] = []
    andado = 0
    for o in ocorrencias:
        partes.append(texto[andado:o.ini])
        partes.append(expandir(o, substituto, opcoes))
        andado = o.fim
    partes.append(texto[andado:])
    return "".join(partes), len(ocorrencias)


# ----------------------------------------------------------------------
# Ir para… (AC-ED06-4)
# ----------------------------------------------------------------------

TIPOS_DE_DESTINO = ("diagrama", "figura", "tabela", "pagina", "bloco", "capitulo")
_CLASSE_DO_TIPO = {"diagrama": Diagrama, "figura": Figura, "tabela": Tabela}


@dataclass
class Destino:
    arquivo: str
    bloco_id: str = ""
    deslocamento: int = 0

    @property
    def endereco(self) -> str:
        return f"{self.arquivo}#{self.bloco_id}" if self.bloco_id else self.arquivo


def destino(livro: Livro, tipo: str, n: int, arquivo_atual: str = "") -> Destino | None:
    """
    O n-ésimo diagrama, figura ou tabela do livro (em ordem de leitura); a página `n`
    do impresso (`MarcaDePagina` ou `Trecho.pagina`); o bloco `n` do capítulo atual; o
    capítulo `n` da espinha. `None` quando não há.
    """
    n = int(n)
    if tipo in _CLASSE_DO_TIPO:
        classe = _CLASSE_DO_TIPO[tipo]
        contados = 0
        for cap in livro.capitulos:
            for bloco in modelo.blocos_do_capitulo(cap):
                if isinstance(bloco, classe):
                    contados += 1
                    if contados == n:
                        return Destino(cap.arquivo, bloco.id)
        return None
    if tipo == "pagina":
        for cap in livro.capitulos:
            for bloco in modelo.blocos_do_capitulo(cap):
                if isinstance(bloco, MarcaDePagina) and bloco.pagina == n:
                    return Destino(cap.arquivo, bloco.id)
                if isinstance(bloco, Paragrafo):
                    andado = 0
                    for t in bloco.trechos:
                        if t.pagina == n:
                            return Destino(cap.arquivo, bloco.id, andado)
                        andado += len(t.texto) + (1 if t.quebra_antes else 0)
        return None
    if tipo == "bloco":
        cap = livro.capitulo(arquivo_atual) if arquivo_atual else (livro.capitulos[0] if livro.capitulos else None)
        if cap is None or not 1 <= n <= len(cap.blocos):
            return None
        return Destino(cap.arquivo, cap.blocos[n - 1].id)
    if tipo == "capitulo":
        if not 1 <= n <= len(livro.capitulos):
            return None
        return Destino(livro.capitulos[n - 1].arquivo)
    raise ValueError(f"tipo de destino desconhecido: {tipo!r}")


# ----------------------------------------------------------------------
# Histórico das buscas (as 20)
# ----------------------------------------------------------------------

@dataclass
class Historico:
    """As últimas buscas, sem repetição, a mais recente primeiro; gravado em `Settings` por quem chama."""

    itens: list[str] = field(default_factory=list)
    limite: int = LIMITE_DO_HISTORICO

    def registrar(self, texto: str) -> list[str]:
        texto = texto or ""
        if not texto.strip():
            return self.itens
        self.itens = [texto] + [t for t in self.itens if t != texto]
        del self.itens[self.limite:]
        return self.itens


__all__ = ["Opcoes", "ESCOPOS", "ROTULOS_DOS_ESCOPOS", "NBSP", "compilar", "Alvo", "alvos_do_capitulo",
           "paragrafo_do_alvo", "Ocorrencia", "procurar_em_alvos", "procurar_no_cru", "procurar_no_capitulo",
           "procurar_no_livro", "contar_por_arquivo", "proxima", "expandir", "substituir_em_trechos",
           "substituir_no_paragrafo", "bloco_substituido", "nota_substituida", "substituir_tudo_no_capitulo",
           "substituir_tudo_no_cru", "Destino", "destino", "TIPOS_DE_DESTINO", "Historico"]
