"""
Do `tk.Text` de volta ao modelo: `dump_para_blocos` lê o que `Text.dump(…, all=True)`
devolve e reconstrói os blocos e as notas; `indice_de` converte uma posição do modelo
numa posição do widget (ED-03; SPEC_EDITOR DEC-03 "Identidade de bloco", §8.15).

## Como o capítulo mora no widget

Cada bloco começa numa marca `bloco:<id>` e vai até a marca seguinte (ou `end`); o seu
último caractere é o `\\n` que o separa do próximo. Dentro de um bloco pode haver
outros `\\n`, todos etiquetados: `qs` (quebra suave — `<br/>`), `qp` (parágrafo dentro
de citação ou de item), `qi:<nível>` (item de lista seguinte). O texto de um trecho
carrega as tags de caractere (`b`, `i`, `link:…`); o que é só da tela (`fonte:*`,
`protegido`, `invisivel`, `marcador`) é descartado aqui. Um objeto (diagrama, figura,
tabela, ilha, marca de página, separador) é uma janela embutida de um caractere, e o
`RegistroDeObjetos` diz que bloco ela é: o bloco volta **intacto**, byte a byte no
caso da ilha. A referência de nota é um caractere protegido com a tag `nota:<id>`; a
marca de página inline, um caractere protegido com `pagina:<n>`. Depois do último
bloco pode vir a **faixa de notas** (ED-04): o marco `FaixaDeNotas` (uma janela, que não
volta) e os parágrafos de cada nota, com a tag `dn:<id>|<tipo>` — eles voltam agrupados
como `Nota`, e não como bloco.

**Puro.** Este módulo não importa Tk: recebe a lista do `dump` (tuplas `(chave, valor,
índice)`) e um dicionário `nome da janela → bloco ou trecho`, e é o que o teste de
propriedade sobre 100 capítulos gerados exercita sem display.
"""

from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from core.editor import modelo
from core.editor.modelo import (Bloco, Citacao, ItemDeLista, Lista, Nota, Paragrafo, Titulo, Trecho)
from ui.editor import tags as T

PREFIXO_DA_MARCA = "bloco:"
#: O id do pseudo-bloco que abre a faixa de notas no fim do capítulo (ED-04, §8.8).
ID_DA_FAIXA = "faixa:notas"


@dataclass(kw_only=True)
class FaixaDeNotas(Bloco):
    """
    O marco da faixa de notas: um pseudo-bloco desenhado como objeto ("Notas") depois do
    último bloco do capítulo. Os parágrafos que vêm depois dele levam a tag `dn:<id da
    nota>|<tipo>` e voltam do `dump` como `Nota`, não como bloco; o próprio marco nunca
    volta (ED-04).
    """

    id: str = ID_DA_FAIXA


# ----------------------------------------------------------------------
# Os segmentos: o dump achatado em (texto | janela, tags ativas)
# ----------------------------------------------------------------------

class _Segmento:
    __slots__ = ("tipo", "valor", "tags", "indice")

    def __init__(self, tipo: str, valor: str, tags: frozenset, indice: str):
        self.tipo = tipo          # "texto" | "janela" | "imagem"
        self.valor = valor
        self.tags = tags
        self.indice = indice


def _segmentar(itens: Sequence[tuple]) -> list[tuple[str, list[_Segmento]]]:
    """`[(id_do_bloco, segmentos)]` na ordem do texto; o que vem antes da primeira marca é ignorado."""
    ativas: set[str] = set()
    blocos: list[tuple[str, list[_Segmento]]] = []
    atual: list[_Segmento] | None = None
    for chave, valor, indice in itens:
        if chave == "tagon":
            ativas.add(valor)
        elif chave == "tagoff":
            ativas.discard(valor)
        elif chave == "mark":
            if valor.startswith(PREFIXO_DA_MARCA):
                atual = []
                blocos.append((valor[len(PREFIXO_DA_MARCA):], atual))
        elif chave == "text":
            if atual is not None and valor:
                atual.append(_Segmento("texto", valor, frozenset(ativas), indice))
        elif chave in ("window", "image"):
            if atual is not None:
                atual.append(_Segmento("janela" if chave == "window" else "imagem", valor, frozenset(ativas), indice))
    # Marcas coincidentes: só a última (a mais nova) tem conteúdo; as vazias são blocos apagados.
    return [(id_, segs) for id_, segs in blocos if segs]


# ----------------------------------------------------------------------
# De segmentos a trechos
# ----------------------------------------------------------------------

def _trecho_de(texto: str, tags: frozenset) -> Trecho:
    t = Trecho(texto=texto)
    for tag in tags:
        if tag == "b":
            t.negrito = True
        elif tag == "i":
            t.italico = True
        elif tag == "u":
            t.sublinhado = True
        elif tag == "s":
            t.tachado = True
        elif tag == "vers":
            t.versalete = True
        elif tag == "sobre":
            t.posicao = "sobre"
        elif tag == "sub":
            t.posicao = "sub"
        elif tag == "code":
            t.codigo = True
        elif tag.startswith("fam:"):
            t.familia = T.valor(tag)
        elif tag.startswith("corpo:"):
            try:
                t.corpo_pt = float(T.valor(tag))
            except ValueError:
                pass
        elif tag.startswith("cor:"):
            t.cor = T.valor(tag)
        elif tag.startswith("fundo:"):
            t.fundo = T.valor(tag)
        elif tag.startswith("cls:"):
            t.classe = T.valor(tag)
        elif tag.startswith("lang:"):
            t.lang = T.valor(tag)
        elif tag.startswith("tit:"):
            t.titulo = T.valor(tag)
        elif tag.startswith("link:"):
            t.link = T.valor(tag)
        elif tag.startswith("ref:"):
            t.ref = T.valor(tag)
        elif tag.startswith("papel:"):
            t.papel = T.valor(tag)
        elif tag.startswith("nag:"):
            try:
                t.nag = int(T.valor(tag))
            except ValueError:
                pass
        elif tag.startswith("chave:"):
            t.chave = T.valor(tag)
    return t


def _trechos_de(segmentos: Sequence[_Segmento], registro: Mapping[str, Any]) -> list[Trecho]:
    """Os trechos de um parágrafo (os segmentos entre duas quebras de bloco/item)."""
    saida: list[Trecho] = []
    quebra_pendente = False
    pagina_pendente: int | None = None

    def pendentes(t: Trecho) -> Trecho:
        nonlocal quebra_pendente, pagina_pendente
        if quebra_pendente:
            t.quebra_antes = True
            quebra_pendente = False
        if pagina_pendente is not None:
            t.pagina = pagina_pendente
            pagina_pendente = None
        return t

    for seg in segmentos:
        tags = seg.tags
        if seg.tipo in ("janela", "imagem"):
            objeto = registro.get(seg.valor)
            if isinstance(objeto, Trecho):
                copia = copy.deepcopy(objeto)
                copia.quebra_antes = False
                copia.pagina = None
                saida.append(pendentes(copia))
            continue
        nota = next((T.valor(t) for t in tags if t.startswith("nota:")), "")
        if nota:
            saida.append(pendentes(Trecho(nota=nota)))
            continue
        pagina = next((T.valor(t) for t in tags if t.startswith("pagina:")), "")
        if pagina:
            try:
                pagina_pendente = int(pagina)
            except ValueError:
                pass
            continue
        if "invisivel" in tags or "marcador" in tags:
            continue
        if "qs" in tags:
            # A quebra suave: cada `\n` deste segmento é um `quebra_antes` do que vem depois.
            for _ in seg.valor:
                if quebra_pendente:
                    saida.append(Trecho(quebra_antes=True))
                quebra_pendente = True
            continue
        texto = seg.valor
        if not texto:
            continue
        saida.append(pendentes(_trecho_de(texto, tags)))
    if quebra_pendente:
        saida.append(Trecho(quebra_antes=True))
    if pagina_pendente is not None:
        saida.append(Trecho(pagina=pagina_pendente))
    return modelo.trechos_normalizados(saida)


# ----------------------------------------------------------------------
# De segmentos a blocos
# ----------------------------------------------------------------------

def _partir_em(segmentos: Sequence[_Segmento], quebra: str) -> list[list[_Segmento]]:
    """Parte a lista de segmentos nos `\\n` etiquetados com `quebra` (`qp`) ou prefixo (`qi:`)."""
    partes: list[list[_Segmento]] = [[]]
    for seg in segmentos:
        e_quebra = seg.tipo == "texto" and any(t == quebra or (quebra.endswith(":") and t.startswith(quebra))
                                                for t in seg.tags)
        if e_quebra:
            for _ in seg.valor:
                partes.append([])
            continue
        partes[-1].append(seg)
    return partes


def _sem_o_fim(segmentos: list[_Segmento]) -> list[_Segmento]:
    """Tira o `\\n` terminal do bloco (o separador entre blocos), que não é conteúdo."""
    segs = list(segmentos)
    while segs and segs[-1].tipo == "texto":
        ultimo = segs[-1]
        if ultimo.valor.endswith("\n") and not any(T.e_quebra(t) for t in ultimo.tags):
            valor = ultimo.valor[:-1]
            segs.pop()
            if valor:
                segs.append(_Segmento("texto", valor, ultimo.tags, ultimo.indice))
            break
        break
    return segs


def _tags_do_bloco(segmentos: Sequence[_Segmento]) -> set[str]:
    """As tags de parágrafo presentes no primeiro segmento com conteúdo (cobrem o bloco inteiro)."""
    for seg in segmentos:
        if seg.tipo == "texto" and ("marcador" in seg.tags or "invisivel" in seg.tags):
            continue
        return {t for t in seg.tags if T.e_de_paragrafo(t) or t.startswith(_PREFIXOS_DE_BLOCO)}
    for seg in segmentos:
        return {t for t in seg.tags if T.e_de_paragrafo(t) or t.startswith(_PREFIXOS_DE_BLOCO)}
    return set()


_PREFIXOS_DE_BLOCO = ("lista:", "marc:", "ini:", "sub:", "pid:", "pcls:", "pex:")


def codificar_extras(p: Paragrafo) -> str:
    """`extras` e `origem` de um parágrafo interno numa tag (`pex:`), em base64 de JSON."""
    dados = {"extras": dict(p.extras), "origem": modelo.para_dict(p.origem)}
    return base64.urlsafe_b64encode(json.dumps(dados, ensure_ascii=False).encode("utf-8")).decode("ascii")


def _decodificar_extras(valor: str) -> dict[str, Any]:
    try:
        dados = json.loads(base64.urlsafe_b64decode(valor.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError):
        return {}
    saida: dict[str, Any] = {}
    if dados.get("extras"):
        saida["extras"] = {str(k): str(v) for k, v in dados["extras"].items()}
    if dados.get("origem"):
        saida["origem"] = modelo.de_dict(dados["origem"])
    return saida


def _base_interna(tags_do_bloco: set[str], anterior: Bloco | None) -> dict[str, Any]:
    """O id persistente, a classe e os extras de um parágrafo interno (tags `pid:`/`pcls:`/`pex:`)."""
    base: dict[str, Any] = {}
    pid = next((T.valor(t) for t in tags_do_bloco if t.startswith("pid:")), "")
    if pid:
        base["id"], base["id_persistente"] = pid, True
    classe = next((T.valor(t) for t in tags_do_bloco if t.startswith("pcls:")), "")
    if classe:
        base["classe"] = classe
    pex = next((T.valor(t) for t in tags_do_bloco if t.startswith("pex:")), "")
    if pex:
        base.update(_decodificar_extras(pex))
    return base


def _paragrafos_internos(bloco: Bloco) -> list[Paragrafo]:
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


def _campos_de_paragrafo(tags_do_bloco: set[str]) -> dict[str, Any]:
    campos: dict[str, Any] = {}
    for tag in tags_do_bloco:
        pref = T.prefixo(tag)
        try:
            if pref == "al:":
                campos["alinhamento"] = T.valor(tag)
            elif pref == "rec1:":
                campos["recuo_primeira_em"] = float(T.valor(tag))
            elif pref == "recE:":
                campos["recuo_esquerda_em"] = float(T.valor(tag))
            elif pref == "recD:":
                campos["recuo_direita_em"] = float(T.valor(tag))
            elif pref == "antes:":
                campos["antes_em"] = float(T.valor(tag))
            elif pref == "depois:":
                campos["depois_em"] = float(T.valor(tag))
            elif pref == "entre:":
                campos["entrelinha"] = float(T.valor(tag))
            elif tag == "manter":
                campos["manter_com_proximo"] = True
            elif tag == "manterl":
                campos["manter_linhas"] = True
        except ValueError:
            continue
    return campos


def _base_de(anterior: Bloco | None, id_: str) -> dict[str, Any]:
    """O que não está nas tags: id, persistência, classe, extras, origem — do bloco anterior."""
    if anterior is None:
        return {"id": id_}
    return {"id": anterior.id, "id_persistente": anterior.id_persistente, "classe": anterior.classe,
            "extras": dict(anterior.extras), "origem": copy.deepcopy(anterior.origem),
            "linha_fonte": anterior.linha_fonte}


def _paragrafo(segmentos: Sequence[_Segmento], registro: Mapping[str, Any], estilo: str,
               campos: dict[str, Any], base: dict[str, Any]) -> Paragrafo:
    trechos = _trechos_de(segmentos, registro)
    if estilo.startswith("titulo") and estilo[6:].isdigit():
        return Titulo(trechos=trechos, nivel=int(estilo[6:]), **campos, **base)
    return Paragrafo(trechos=trechos, estilo=estilo, **campos, **base)


def _lista(segmentos: Sequence[_Segmento], registro: Mapping[str, Any], tags_do_bloco: set[str],
           base: dict[str, Any], anterior: Bloco | None = None) -> Lista:
    ordenada = "lista:o" in tags_do_bloco
    marcador = next((T.valor(t) for t in tags_do_bloco if t.startswith("marc:")), "")
    inicio = next((T.valor(t) for t in tags_do_bloco if t.startswith("ini:")), "1")
    itens_crus: list[tuple[int, list[Paragrafo], dict[str, Any]]] = []
    for pedaco in _partir_em(segmentos, "qi:"):
        nivel = 1
        sub: dict[str, Any] = {}
        for seg in pedaco:
            achado = next((T.valor(t) for t in seg.tags if t.startswith("li:")), "")
            if achado.isdigit():
                nivel = int(achado)
                sub = _sublista_de(next((T.valor(t) for t in seg.tags if t.startswith("sub:")), ""))
                break
        paragrafos = []
        for p in _partir_em(pedaco, "qp"):
            tags_do_paragrafo = _tags_do_bloco(p)
            campos = _campos_de_paragrafo(tags_do_paragrafo)
            paragrafos.append(_paragrafo(p, registro, "corpo", campos, _base_interna(tags_do_paragrafo, anterior)))
        paragrafos = [p for p in paragrafos if p.trechos] or [Paragrafo(trechos=[])]
        itens_crus.append((nivel, paragrafos, sub))

    def montar(indice: int, nivel: int) -> tuple[list[ItemDeLista], int]:
        itens: list[ItemDeLista] = []
        while indice < len(itens_crus):
            n, paragrafos, sub = itens_crus[indice]
            if n < nivel:
                break
            if n > nivel:
                filhos, indice = montar(indice, n)
                sublista = Lista(ordenada=sub.get("ordenada", ordenada), itens=filhos,
                                 inicio=sub.get("inicio", 1), marcador=sub.get("marcador", ""))
                if itens:
                    itens[-1].filhos = sublista
                else:
                    itens.append(ItemDeLista(paragrafos=[Paragrafo(trechos=[])], filhos=sublista))
                continue
            itens.append(ItemDeLista(paragrafos=paragrafos))
            indice += 1
        return itens, indice

    itens, _ = montar(0, 1)
    try:
        inicio_n = int(inicio)
    except ValueError:
        inicio_n = 1
    return Lista(ordenada=ordenada, itens=itens or [ItemDeLista(paragrafos=[Paragrafo(trechos=[])])],
                 inicio=inicio_n, marcador=marcador, **base)


def _sublista_de(valor: str) -> dict[str, Any]:
    """`o|alfa|5` (da tag `sub:`) → os atributos da lista aninhada a que o item pertence."""
    if not valor:
        return {}
    partes = valor.split("|")
    saida: dict[str, Any] = {"ordenada": partes[0] == "o"}
    if len(partes) > 1:
        saida["marcador"] = partes[1]
    if len(partes) > 2 and partes[2].lstrip("-").isdigit():
        saida["inicio"] = int(partes[2])
    return saida


def _citacao(segmentos: Sequence[_Segmento], registro: Mapping[str, Any], base: dict[str, Any],
             anterior: Bloco | None = None) -> Citacao:
    paragrafos = []
    for p in _partir_em(segmentos, "qp"):
        tags_do_paragrafo = _tags_do_bloco(p)
        campos = _campos_de_paragrafo(tags_do_paragrafo)
        paragrafos.append(_paragrafo(p, registro, "citacao", campos, _base_interna(tags_do_paragrafo, anterior)))
    return Citacao(blocos=[p for p in paragrafos if p.trechos] or [Paragrafo(trechos=[], estilo="citacao")], **base)


def nota_da_tag(tags: Iterable[str]) -> tuple[str, str] | None:
    """`(id da nota, tipo)` da tag `dn:<id>|<tipo>` de um parágrafo da faixa de notas; `None` fora dela."""
    for tag in tags:
        if tag.startswith("dn:"):
            id_, _, tipo = T.valor(tag).partition("|")
            return id_, (tipo or "rodape")
    return None


def dump_para_blocos(itens: Sequence[tuple], registro: Mapping[str, Any],
                     anteriores: Mapping[str, Bloco] | None = None) -> tuple[list[Bloco], list[Nota]]:
    """
    Os blocos do capítulo a partir do `dump` do widget, e as notas da faixa de notas
    (os parágrafos com a tag `dn:<id>|<tipo>`, agrupados por nota, na ordem em que
    aparecem). Uma nota que está em `anteriores` e não foi desenhada volta como estava.
    """
    anteriores = dict(anteriores or {})
    blocos: list[Bloco] = []
    notas: dict[str, Nota] = {}
    for id_, segmentos in _segmentar(itens):
        anterior = anteriores.get(id_)
        # Um objeto: a janela embutida diz o bloco, que volta intacto; o marco da faixa não volta.
        janela = next((s for s in segmentos if s.tipo in ("janela", "imagem")), None)
        if janela is not None and isinstance(registro.get(janela.valor), Bloco):
            objeto = registro[janela.valor]
            if not isinstance(objeto, FaixaDeNotas):
                blocos.append(objeto)
            continue
        segs = _sem_o_fim(segmentos)
        tags_do_bloco = _tags_do_bloco(segmentos)
        base = _base_de(anterior if isinstance(anterior, Bloco) else None, id_)
        anterior_bloco = anterior if isinstance(anterior, Bloco) else None
        nota = nota_da_tag(tags_do_bloco)
        if nota is not None:
            estilo = next((T.valor(t) for t in tags_do_bloco if t.startswith("p:")), "nota") or "nota"
            paragrafo = _paragrafo(segs, registro, estilo, _campos_de_paragrafo(tags_do_bloco), base)
            nota_id, tipo = nota
            if nota_id not in notas:
                notas[nota_id] = Nota(id=nota_id, tipo=tipo, blocos=[])
            notas[nota_id].blocos.append(paragrafo)
            continue
        if any(t.startswith("lista:") for t in tags_do_bloco):
            blocos.append(_lista(segs, registro, tags_do_bloco, base, anterior_bloco))
            continue
        if "cit" in tags_do_bloco:
            blocos.append(_citacao(segs, registro, base, anterior_bloco))
            continue
        estilo = next((T.valor(t) for t in tags_do_bloco if t.startswith("p:")), "corpo") or "corpo"
        blocos.append(_paragrafo(segs, registro, estilo, _campos_de_paragrafo(tags_do_bloco), base))
    saida = list(notas.values())
    saida += [b for b in anteriores.values() if isinstance(b, Nota) and b.id not in notas]
    return blocos, saida


# ----------------------------------------------------------------------
# Posição do modelo → posição do widget
# ----------------------------------------------------------------------

def indice_de(itens: Sequence[tuple], bloco_id: str, deslocamento: int) -> str | None:
    """
    O índice do widget do `deslocamento`-ésimo caractere do **modelo** dentro do bloco
    (`texto_de` do parágrafo: quebra suave conta um), pulando o que é só da tela —
    marcador de lista, invisíveis, referência de nota, marca de página. `None` se não há.
    """
    for id_, segmentos in _segmentar(itens):
        if id_ != bloco_id:
            continue
        andados = 0
        for seg in segmentos:
            if seg.tipo != "texto":
                continue
            tags = seg.tags
            e_quebra = any(T.e_quebra(t) for t in tags)
            if "invisivel" in tags or "marcador" in tags or ("protegido" in tags and not e_quebra):
                continue
            linha, coluna = seg.indice.split(".")
            for k, ch in enumerate(seg.valor):
                if andados == deslocamento:
                    return f"{linha}.{int(coluna) + k}"
                andados += 1
        ultimo = segmentos[-1]
        if ultimo.tipo == "texto":
            linha, coluna = ultimo.indice.split(".")
            return f"{linha}.{int(coluna) + len(ultimo.valor)}"
        return None
    return None
