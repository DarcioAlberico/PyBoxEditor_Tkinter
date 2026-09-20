"""
As operações de nível livro: renomear, excluir, mover, anexar, dividir e juntar
capítulos — reescrevendo espinha, sumário, marcos e todo link que apontava para o que
mudou (ED-01; SPEC_EDITOR §5.2, §9.5).

## Por que isto não mora em `modelo.py`

`modelo.dividir_capitulo` parte um capítulo em dois e leva cada nota para o lado da
sua referência — e só. Quem aponta para os blocos que mudaram de arquivo (um link
noutro capítulo, uma entrada do sumário, um marco) mora **fora** do capítulo, e é do
livro inteiro que estas funções cuidam. O modelo continua puro por capítulo; aqui é
o único lugar que sabe que `Text/cap-0001.xhtml#x` virou `Text/cap-0001-1.xhtml#x`.

## Duas reescritas, e o que cada uma toca

- **Por arquivo** (`renomear`, `renomear_varios`, `anexar`): um mapa `href antigo →
  novo` aplicado de uma vez sobre `Capitulo.arquivo`, `Trecho.link`, `Capitulo.folhas`,
  `Figura.recurso`, `Diagrama.recorte`/`imagem`, o sumário, os marcos, a capa, as
  folhas do livro, e — por texto, porque ali o modelo não entra — as ilhas, a
  `cabeca_extra`, o `texto_cru` e os `url()` das folhas de estilo. Nesses textos os
  caminhos são relativos **ao arquivo que os contém**, e o próprio arquivo pode ter
  mudado de pasta: por isso todo caminho que resolve para algo conhecido é
  recalculado, e não só os do mapa.
- **Por alvo** (`dividir`, `juntar`): um mapa `arquivo#id → arquivo#id` sobre os links,
  o sumário e os marcos. Um `#id` nu é do capítulo em que está (INV-01), e vira
  `arquivo#id` quando o bloco e o link ficam em arquivos diferentes.

## `juntar_por_titulo` e as páginas do impresso

O EPUB de hoje é uma página do scan por arquivo (`pagina-0012.xhtml`, `<title>Página
12</title>`) e não tem `hr.pagina`. Juntar essas páginas em capítulos por `<h1>` é
o que faz o livro virar livro — e a fronteira de cada arquivo vira uma
`MarcaDePagina(12)` sintetizada do `<title>` ou do nome, para a `page-list` do nav
continuar dizendo onde cada página do impresso começa (§6.1).
"""

from __future__ import annotations

import copy
import posixpath
import re
from typing import Iterable, Sequence

from core.editor import modelo
from core.editor.modelo import (Capitulo, Diagrama, EntradaDeSumario, Figura, Livro, MarcaDePagina,
                                Recurso, Separador, Titulo)

_RE_ATRIBUTO_DE_CAMINHO = re.compile(r'\b(src|href|xlink:href|poster|data)="([^"]*)"')
_RE_URL_CSS = re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""")
_RE_PAGINA_NO_TITULO = re.compile(r"^\s*p[áa]g(?:ina)?\.?\s*(\d+)\s*$", re.IGNORECASE)
_RE_PAGINA_NO_NOME = re.compile(r"(?:^|[^0-9])(?:pagina|pag|page|pg|p)[-_]?(\d{1,5})\.[a-z]+$", re.IGNORECASE)


# ----------------------------------------------------------------------
# Nomes e percursos
# ----------------------------------------------------------------------

def hrefs_usados(livro: Livro) -> set[str]:
    usados = {c.arquivo for c in livro.capitulos} | set(livro.recursos)
    usados |= {h for h in (livro.nav, livro.ncx) if h}
    return usados


def nome_livre(livro: Livro, nome: str, reservados: Iterable[str] = ()) -> str:
    """`nome`, ou `raiz-1.ext`, `raiz-2.ext`… — o primeiro que não existe no livro."""
    usados = hrefs_usados(livro) | set(reservados)
    if nome not in usados:
        return nome
    raiz, ext = posixpath.splitext(nome)
    n = 1
    while f"{raiz}-{n}{ext}" in usados:
        n += 1
    return f"{raiz}-{n}{ext}"


def _capitulo(livro: Livro, href: str) -> Capitulo:
    cap = livro.capitulo(href)
    if cap is None:
        raise KeyError(f"capítulo inexistente: {href}")
    return cap


def _indice(livro: Livro, href: str) -> int:
    for i, cap in enumerate(livro.capitulos):
        if cap.arquivo == href:
            return i
    raise KeyError(f"capítulo inexistente: {href}")


def _e_externo(alvo: str) -> bool:
    return "://" in alvo or alvo.startswith(("mailto:", "tel:", "data:", "javascript:"))


def _em_modelo(cap: Capitulo) -> Capitulo:
    """
    O capítulo com o modelo como dono: um `texto_cru` (modo código) é convertido
    antes de dividir ou juntar — `ErroDeXhtml` se ele não estiver bem-formado.
    """
    if cap.texto_cru is None:
        return cap
    from core.editor import xhtml

    lido = xhtml.ler(cap.texto_cru, cap.arquivo)
    lido.linear = cap.linear
    lido.avisos = list(cap.avisos) + list(lido.avisos)
    return lido


def _ids_de(cap: Capitulo) -> set[str]:
    return {b.id for b in modelo.blocos_do_capitulo(cap)} | {n.id for n in cap.notas}


def _todas_as_entradas(entradas: Sequence[EntradaDeSumario]) -> list[EntradaDeSumario]:
    saida: list[EntradaDeSumario] = []
    for e in entradas:
        saida.append(e)
        saida.extend(_todas_as_entradas(e.filhos))
    return saida


# ----------------------------------------------------------------------
# Reescrita por arquivo
# ----------------------------------------------------------------------

def _troca_arquivo(valor: str, mapa: dict[str, str]) -> str:
    if not valor or _e_externo(valor) or valor.startswith("#"):
        return valor
    arquivo, sep, ancora = valor.partition("#")
    return mapa.get(arquivo, arquivo) + sep + ancora


def _reescrever_texto(texto: str, pasta_antiga: str, pasta_nova: str, mapa: dict[str, str],
                      conhecidos: set[str], padrao: re.Pattern) -> tuple[str, int]:
    """Os caminhos de um texto (ilha, `texto_cru`, CSS), relativos ao arquivo que os contém."""
    trocas = 0

    def trocar(m: re.Match) -> str:
        nonlocal trocas
        grupos = m.groups()
        valor = grupos[-1]
        if not valor or _e_externo(valor) or valor.startswith("#"):
            return m.group(0)
        caminho, sep, ancora = valor.partition("#")
        absoluto = posixpath.normpath(posixpath.join(pasta_antiga, caminho)) if pasta_antiga \
            else posixpath.normpath(caminho)
        if absoluto not in conhecidos:
            return m.group(0)
        novo = mapa.get(absoluto, absoluto)
        relativo = posixpath.relpath(novo, pasta_nova) if pasta_nova else novo
        if relativo == caminho:
            return m.group(0)
        trocas += 1
        inicio, fim = m.span(len(grupos))
        return m.group(0)[: inicio - m.start()] + relativo + sep + ancora + m.group(0)[fim - m.start():]

    return padrao.sub(trocar, texto), trocas


def _reescrever_hrefs(livro: Livro, mapa: dict[str, str]) -> int:
    """
    Aplica `mapa` (href antigo → novo, relativos ao OPF) ao livro inteiro, de uma
    vez — um `a→b, b→a` funciona porque cada valor é consultado uma só vez. Devolve
    quantas referências mudaram (sem contar os próprios renomeados).
    """
    from core.editor import epub

    mapa = {de: para for de, para in mapa.items() if de != para}
    if not mapa:
        return 0
    conhecidos = hrefs_usados(livro)
    trocas = 0

    def troca(valor: str) -> str:
        nonlocal trocas
        novo = _troca_arquivo(valor, mapa)
        if novo != valor:
            trocas += 1
        return novo

    for cap in livro.capitulos:
        pasta_antiga = posixpath.dirname(cap.arquivo)
        cap.arquivo = mapa.get(cap.arquivo, cap.arquivo)
        pasta_nova = posixpath.dirname(cap.arquivo)
        cap.folhas = [troca(f) for f in cap.folhas]
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Figura):
                bloco.recurso = troca(bloco.recurso)
            elif isinstance(bloco, Diagrama):
                bloco.recorte = troca(bloco.recorte)
                bloco.imagem = troca(bloco.imagem)
            elif isinstance(bloco, modelo.IlhaBruta):
                bloco.xhtml, n = _reescrever_texto(bloco.xhtml, pasta_antiga, pasta_nova, mapa, conhecidos,
                                                   _RE_ATRIBUTO_DE_CAMINHO)
                trocas += n
            for trecho in modelo._todos_os_trechos(bloco):
                trecho.link = troca(trecho.link)
                if trecho.ilha:
                    trecho.ilha, n = _reescrever_texto(trecho.ilha, pasta_antiga, pasta_nova, mapa, conhecidos,
                                                       _RE_ATRIBUTO_DE_CAMINHO)
                    trocas += n
        if cap.cabeca_extra:
            cap.cabeca_extra, n = _reescrever_texto(cap.cabeca_extra, pasta_antiga, pasta_nova, mapa,
                                                    conhecidos, _RE_ATRIBUTO_DE_CAMINHO)
            trocas += n
        if cap.texto_cru is not None:
            cap.texto_cru, n = _reescrever_texto(cap.texto_cru, pasta_antiga, pasta_nova, mapa, conhecidos,
                                                 _RE_ATRIBUTO_DE_CAMINHO)
            trocas += n
    recursos: dict[str, Recurso] = {}
    for href, recurso in livro.recursos.items():
        novo = mapa.get(href, href)
        if recurso.tipo_mime == "text/css" and recurso.no_manifesto:
            texto = recurso.texto_cru
            if texto is None:
                try:
                    texto = epub.dados_de(livro, recurso).decode("utf-8", errors="replace")
                except FileNotFoundError:
                    texto = None
            if texto is not None and "url(" in texto:
                reescrito, n = _reescrever_texto(texto, posixpath.dirname(href), posixpath.dirname(novo), mapa,
                                                 conhecidos, _RE_URL_CSS)
                if n:
                    trocas += n
                    if recurso.texto_cru is not None:
                        recurso.texto_cru = reescrito
                    else:
                        recurso.dados = reescrito.encode("utf-8")
        recurso.caminho = novo
        recursos[novo] = recurso
    livro.recursos = recursos
    livro.folhas = [troca(f) for f in livro.folhas]
    livro.metadados.capa = troca(livro.metadados.capa)
    for entrada in _todas_as_entradas(livro.sumario):
        entrada.destino = troca(entrada.destino)
    livro.marcos = [(tipo, troca(destino)) for tipo, destino in livro.marcos]
    return trocas


# ----------------------------------------------------------------------
# Reescrita por alvo (arquivo#id)
# ----------------------------------------------------------------------

def _reescrever_alvos(livro: Livro, mapa: dict[str, str], fora_de: Iterable[str] = ()) -> int:
    """
    `mapa`: `arquivo#id` antigo → novo. Um `#id` nu num capítulo `X` é `X#id`; o resultado
    volta nu quando fica no mesmo arquivo. `fora_de` são capítulos já tratados à mão.
    """
    trocas = 0
    fora = set(fora_de)

    def troca(valor: str, capitulo: str) -> str:
        nonlocal trocas
        if not valor or _e_externo(valor):
            return valor
        chave = capitulo + valor if valor.startswith("#") else valor
        if chave not in mapa:
            return valor
        novo = mapa[chave]
        trocas += 1
        arquivo, sep, ancora = novo.partition("#")
        return sep + ancora if arquivo == capitulo and ancora else novo

    for cap in livro.capitulos:
        if cap.arquivo in fora:
            continue
        for trecho in modelo.trechos_do_capitulo(cap):
            trecho.link = troca(trecho.link, cap.arquivo)
    for entrada in _todas_as_entradas(livro.sumario):
        entrada.destino = troca(entrada.destino, "")
    livro.marcos = [(tipo, troca(destino, "")) for tipo, destino in livro.marcos]
    return trocas


# ----------------------------------------------------------------------
# Renomear, excluir, mover, ordenar, folhas, cópia, anexar
# ----------------------------------------------------------------------

def renomear(livro: Livro, de: str, para: str) -> int:
    """
    Renomeia um capítulo ou recurso e reescreve tudo que apontava para ele; devolve
    quantas referências mudaram. `ValueError` se `para` já existe.
    """
    if de == para:
        return 0
    if de not in hrefs_usados(livro):
        raise KeyError(f"não existe no livro: {de}")
    if para in hrefs_usados(livro):
        raise ValueError(f"já existe no livro: {para}")
    return _reescrever_hrefs(livro, {de: para})


def renomear_varios(livro: Livro, padrao: str, capitulos: Sequence[str] | None = None) -> dict[str, str]:
    """
    Renumera os capítulos (todos, ou os de `capitulos`, na ordem da espinha) pelo
    `padrao` de `%d` — `"cap-%03d"` dá `cap-001`, `cap-002`… — mantendo pasta e
    extensão. Devolve o mapa do que mudou. É uma reescrita só, e por isso
    `cap-002 → cap-001` não colide com `cap-001 → cap-002`.
    """
    if "%" not in padrao:
        raise ValueError("o padrão precisa de um %d (ex.: cap-%03d)")
    escolhidos = [c for c in livro.capitulos if capitulos is None or c.arquivo in set(capitulos)]
    mapa: dict[str, str] = {}
    novos: set[str] = set()
    proprios: set[str] = set()          # os que já têm o nome que o padrão dá
    for n, cap in enumerate(escolhidos, start=1):
        pasta = posixpath.dirname(cap.arquivo)
        ext = posixpath.splitext(cap.arquivo)[1] or ".xhtml"
        novo = posixpath.join(pasta, (padrao % n) + ext) if pasta else (padrao % n) + ext
        if novo in novos:
            raise ValueError(f"o padrão gera o mesmo nome duas vezes: {novo}")
        novos.add(novo)
        if novo != cap.arquivo:
            mapa[cap.arquivo] = novo
        else:
            proprios.add(novo)
    intocados = hrefs_usados(livro) - set(mapa) - proprios
    colisao = novos & intocados
    if colisao:
        raise ValueError(f"nome novo colide com arquivo que não está sendo renomeado: {sorted(colisao)[0]}")
    _reescrever_hrefs(livro, mapa)
    return mapa


def excluir(livro: Livro, href: str) -> list[str]:
    """
    Tira um capítulo ou recurso do livro e devolve **quem apontava para ele**
    (`arquivo#id` do bloco com o link ou a figura; o capítulo cuja folha era esta;
    `sumário: rótulo`; `marco: tipo`; `capa`). Os links ficam como estão (INV-02: o
    alvo sumido é aviso, nunca apagado em silêncio); sumário, marcos, folhas e capa
    são limpos, porque um nav que aponta para nada é um EPUB inválido.
    """
    apontavam: list[str] = []
    for cap in livro.capitulos:
        if cap.arquivo == href:
            continue
        for bloco in modelo.blocos_do_capitulo(cap):
            aponta = False
            if isinstance(bloco, Figura) and bloco.recurso == href:
                aponta = True
            elif isinstance(bloco, Diagrama) and href in (bloco.recorte, bloco.imagem):
                aponta = True
            for trecho in modelo._todos_os_trechos(bloco):
                if trecho.link and not _e_externo(trecho.link) and trecho.link.split("#")[0] == href:
                    aponta = True
            if aponta:
                apontavam.append(f"{cap.arquivo}#{bloco.id}")
        if href in cap.folhas:
            apontavam.append(cap.arquivo)
            cap.folhas = [f for f in cap.folhas if f != href]
    for entrada in _todas_as_entradas(livro.sumario):
        if entrada.destino.split("#")[0] == href:
            apontavam.append(f"sumário: {entrada.rotulo}")
    livro.sumario = _sem_arquivo(livro.sumario, href)
    for tipo, destino in livro.marcos:
        if destino.split("#")[0] == href:
            apontavam.append(f"marco: {tipo}")
    livro.marcos = [(t, d) for t, d in livro.marcos if d.split("#")[0] != href]
    if livro.metadados.capa == href:
        apontavam.append("capa")
        livro.metadados.capa = ""
    livro.folhas = [f for f in livro.folhas if f != href]
    if livro.capitulo(href) is not None:
        i = _indice(livro, href)
        del livro.capitulos[i]
        if livro.nav_na_espinha is not None and livro.nav_na_espinha > i:
            livro.nav_na_espinha -= 1
    elif href in livro.recursos:
        del livro.recursos[href]
    else:
        raise KeyError(f"não existe no livro: {href}")
    return apontavam


def _sem_arquivo(entradas: Sequence[EntradaDeSumario], href: str) -> list[EntradaDeSumario]:
    saida = []
    for e in entradas:
        if e.destino.split("#")[0] == href:
            saida.extend(_sem_arquivo(e.filhos, href))      # os filhos sobem um nível
            continue
        e.filhos = _sem_arquivo(e.filhos, href)
        saida.append(e)
    return saida


def mover(livro: Livro, href: str, para: int) -> None:
    """Põe o capítulo na posição `para` da espinha (o arrastar do navegador)."""
    i = _indice(livro, href)
    cap = livro.capitulos.pop(i)
    livro.capitulos.insert(max(0, min(int(para), len(livro.capitulos))), cap)


def ordenar(livro: Livro, hrefs: Sequence[str]) -> None:
    """A espinha na ordem de `hrefs` — que tem de ser uma permutação dela."""
    por_href = {c.arquivo: c for c in livro.capitulos}
    if sorted(hrefs) != sorted(por_href):
        raise ValueError("a ordem nova não tem os mesmos capítulos da espinha")
    livro.capitulos = [por_href[h] for h in hrefs]


def vincular_folhas(livro: Livro, capitulos: Sequence[str] | None, folhas: Sequence[str],
                    substituir: bool = True) -> int:
    """Liga as folhas de estilo aos capítulos (`None` = todos); devolve quantos mudaram."""
    for folha in folhas:
        if folha not in livro.recursos:
            raise ValueError(f"folha de estilo inexistente: {folha}")
    escolhidos = set(capitulos) if capitulos is not None else None
    mudados = 0
    for cap in livro.capitulos:
        if escolhidos is not None and cap.arquivo not in escolhidos:
            continue
        novas = list(folhas) if substituir else cap.folhas + [f for f in folhas if f not in cap.folhas]
        if novas != cap.folhas:
            cap.folhas = novas
            mudados += 1
    return mudados


def adicionar_copia(livro: Livro, href: str) -> str:
    """Uma cópia do capítulo (logo depois dele) ou do recurso, com o próximo nome livre."""
    from core.editor import epub

    novo = nome_livre(livro, href)
    cap = livro.capitulo(href)
    if cap is not None:
        copia = copy.deepcopy(cap)
        copia.arquivo = novo
        livro.capitulos.insert(_indice(livro, href) + 1, copia)
        return novo
    if href in livro.recursos:
        original = livro.recursos[href]
        epub.dados_de(livro, original)
        copia = copy.deepcopy(original)
        copia.caminho = novo
        livro.recursos[novo] = copia
        return novo
    raise KeyError(f"não existe no livro: {href}")


def anexar(livro: Livro, outro: Livro) -> list[str]:
    """
    Põe os capítulos e recursos de `outro` no fim deste livro. Nome que colide é
    renomeado (e os links de `outro` reescritos antes de entrar); recurso igual byte a
    byte é compartilhado. Devolve os hrefs dos capítulos anexados, como ficaram.
    """
    from core.editor import epub

    outro = copy.deepcopy(outro)
    for recurso in outro.recursos.values():
        if recurso.dados is None and recurso.texto_cru is None:
            recurso.dados = epub.dados_de(outro, recurso)
    mapa: dict[str, str] = {}
    reservados: set[str] = set()
    compartilhados: set[str] = set()
    for cap in outro.capitulos:
        if cap.arquivo in hrefs_usados(livro) or cap.arquivo in reservados:
            mapa[cap.arquivo] = nome_livre(livro, cap.arquivo, reservados)
            reservados.add(mapa[cap.arquivo])
    for href, recurso in outro.recursos.items():
        if href in livro.recursos:
            meu = livro.recursos[href]
            if epub.dados_de(livro, meu) == epub.dados_de(outro, recurso):
                compartilhados.add(href)
                continue
        if href in hrefs_usados(livro) or href in reservados:
            mapa[href] = nome_livre(livro, href, reservados)
            reservados.add(mapa[href])
    _reescrever_hrefs(outro, mapa)
    for href, recurso in outro.recursos.items():
        if href not in compartilhados and href not in livro.recursos:
            livro.recursos[href] = recurso
    livro.capitulos.extend(outro.capitulos)
    livro.sumario.extend(outro.sumario)
    return [c.arquivo for c in outro.capitulos]


# ----------------------------------------------------------------------
# Dividir e juntar
# ----------------------------------------------------------------------

def dividir(livro: Livro, href: str, i_bloco: int, novo: str | None = None) -> str:
    """
    Parte o capítulo antes do bloco `i_bloco`; a segunda metade vira o capítulo
    `novo` (ou `raiz-1.xhtml`), logo depois. Links, sumário e marcos que apontavam
    para blocos da segunda metade passam a apontar para o arquivo novo. Devolve-o.
    """
    i = _indice(livro, href)
    cap = _em_modelo(livro.capitulos[i])
    novo = novo or nome_livre(livro, href)
    if novo in hrefs_usados(livro):
        raise ValueError(f"já existe no livro: {novo}")
    primeiro, segundo = modelo.dividir_capitulo(cap, i_bloco, novo)
    ids_primeiro, ids_segundo = _ids_de(primeiro), _ids_de(segundo)
    for trecho in modelo.trechos_do_capitulo(primeiro):
        if trecho.link.startswith("#") and trecho.link[1:] in ids_segundo:
            trecho.link = novo + trecho.link
    for trecho in modelo.trechos_do_capitulo(segundo):
        if trecho.link.startswith("#") and trecho.link[1:] in ids_primeiro:
            trecho.link = href + trecho.link
    livro.capitulos[i] = primeiro
    livro.capitulos.insert(i + 1, segundo)
    if livro.nav_na_espinha is not None and livro.nav_na_espinha > i:
        livro.nav_na_espinha += 1
    mapa = {f"{href}#{id_}": f"{novo}#{id_}" for id_ in ids_segundo}
    _reescrever_alvos(livro, mapa, fora_de=(href, novo))
    return novo


def juntar(livro: Livro, href: str) -> str:
    """
    Junta o capítulo `href` ao **anterior** ("Juntar com o anterior") e devolve o
    href do resultado. Ids que colidem são trocados no capítulo que entra, e todo
    link, entrada de sumário e marco que apontava para ele é reescrito.
    """
    i = _indice(livro, href)
    if i == 0:
        raise ValueError("o primeiro capítulo não tem anterior para juntar")
    anterior = _em_modelo(livro.capitulos[i - 1])
    este = _em_modelo(livro.capitulos[i])
    alvo = anterior.arquivo
    ids_anterior = _ids_de(anterior)
    trocas: dict[str, str] = {}
    for bloco in modelo.blocos_do_capitulo(este):
        if bloco.id in ids_anterior and not isinstance(bloco, MarcaDePagina):
            trocas[bloco.id] = modelo.id_novo()
            bloco.id = trocas[bloco.id]
    for nota in este.notas:
        if nota.id in ids_anterior:
            trocas[nota.id] = modelo.id_novo()
            nota.id = trocas[nota.id]
    if trocas:
        for trecho in modelo.trechos_do_capitulo(este):
            if trecho.nota in trocas:
                trecho.nota = trocas[trecho.nota]
            if trecho.link.startswith("#") and trecho.link[1:] in trocas:
                trecho.link = "#" + trocas[trecho.link[1:]]
    mapa = {f"{href}#{velho}": f"{alvo}#{novo}" for velho, novo in trocas.items()}
    for id_ in _ids_de(este):
        mapa.setdefault(f"{href}#{id_}", f"{alvo}#{id_}")
    mapa[href] = alvo
    juntado = modelo.juntar_capitulos(anterior, este)
    # Duas marcas da mesma página (só acontece juntando cópias): fica a primeira.
    vistos: set[str] = set()
    blocos = []
    for bloco in juntado.blocos:
        if isinstance(bloco, MarcaDePagina):
            if bloco.id in vistos:
                continue
            vistos.add(bloco.id)
        blocos.append(bloco)
    juntado.blocos = blocos
    if anterior.titulo and _RE_PAGINA_NO_TITULO.match(anterior.titulo):
        juntado.titulo = ""
    livro.capitulos[i - 1] = juntado
    del livro.capitulos[i]
    if livro.nav_na_espinha is not None and livro.nav_na_espinha > i:
        livro.nav_na_espinha -= 1
    _reescrever_alvos(livro, mapa)
    return alvo


def _cortes_por_titulo(cap: Capitulo, nivel: int) -> list[int]:
    """Os índices dos títulos de nível ≤ `nivel` que não abrem o capítulo (marcas de página não contam)."""
    primeiro_util = next((i for i, b in enumerate(cap.blocos) if not isinstance(b, MarcaDePagina)), 0)
    return [i for i, b in enumerate(cap.blocos)
            if isinstance(b, Titulo) and b.nivel <= nivel and i > primeiro_util]


def _nomes_das_partes(livro: Livro, href: str, quantos: int) -> list[str]:
    """`raiz-1`, `raiz-2`… na ordem do documento — os cortes são feitos de trás para a frente."""
    nomes: list[str] = []
    for _ in range(quantos):
        nomes.append(nome_livre(livro, href, nomes))
    return nomes


def dividir_por_titulo(livro: Livro, href: str, nivel: int = 1) -> list[str]:
    """Um capítulo por título de nível ≤ `nivel`; devolve os hrefs resultantes, na ordem."""
    cap = _em_modelo(_capitulo(livro, href))
    livro.capitulos[_indice(livro, href)] = cap
    cortes = _cortes_por_titulo(cap, nivel)
    nomes = _nomes_das_partes(livro, href, len(cortes))
    for corte, nome in zip(reversed(cortes), reversed(nomes)):
        dividir(livro, href, corte, nome)
    return [href] + nomes


def dividir_nos_marcadores(livro: Livro, href: str) -> list[str]:
    """
    Parte o capítulo em cada `<hr class="divisao"/>` (o "Split at Markers" do Sigil);
    o marcador some. Devolve os hrefs resultantes, na ordem.
    """
    cap = _em_modelo(_capitulo(livro, href))
    livro.capitulos[_indice(livro, href)] = cap
    cortes = [i for i, b in enumerate(cap.blocos)
              if isinstance(b, Separador) and "divisao" in b.classe.split() and i > 0]
    nomes = _nomes_das_partes(livro, href, len(cortes))
    for corte, nome in zip(reversed(cortes), reversed(nomes)):
        dividir(livro, href, corte, nome)
        del _capitulo(livro, nome).blocos[0]
    if cap.blocos and isinstance(cap.blocos[0], Separador) and "divisao" in cap.blocos[0].classe.split():
        del cap.blocos[0]
    return [href] + nomes


def pagina_do_arquivo(cap: Capitulo) -> int | None:
    """O número da página do impresso que este arquivo é: do `<title>` ("Página 12") ou do nome (`pagina-0012`)."""
    m = _RE_PAGINA_NO_TITULO.match(cap.titulo or "")
    if m:
        return int(m.group(1))
    m = _RE_PAGINA_NO_NOME.search(posixpath.basename(cap.arquivo))
    if m:
        return int(m.group(1))
    return None


def sintetizar_marcas_de_pagina(livro: Livro) -> int:
    """
    Põe uma `MarcaDePagina(n)` no começo de cada capítulo que é uma página do impresso
    e ainda não a tem (o EPUB de hoje). Devolve quantas entraram.
    """
    n_marcas = 0
    for i, cap in enumerate(livro.capitulos):
        cap = _em_modelo(cap)
        livro.capitulos[i] = cap
        n = pagina_do_arquivo(cap)
        if n is None:
            continue
        if any(isinstance(b, MarcaDePagina) and b.pagina == n for b in cap.blocos):
            continue
        if any(t.pagina == n for t in modelo.trechos_do_capitulo(cap)):
            continue
        cap.blocos.insert(0, MarcaDePagina(pagina=n))
        n_marcas += 1
    return n_marcas


def juntar_por_titulo(livro: Livro, nivel: int = 1) -> list[str]:
    """
    Das páginas do impresso aos capítulos: a fronteira de cada arquivo vira marca de
    página; cada título de nível ≤ `nivel` abre um capítulo; o que não começa com
    título junta-se ao anterior. Devolve os hrefs dos capítulos resultantes.
    """
    sintetizar_marcas_de_pagina(livro)
    for cap in list(livro.capitulos):
        if _cortes_por_titulo(cap, nivel):
            dividir_por_titulo(livro, cap.arquivo, nivel)

    def abre_capitulo(cap: Capitulo) -> bool:
        for bloco in cap.blocos:
            if isinstance(bloco, MarcaDePagina):
                continue
            return isinstance(bloco, Titulo) and bloco.nivel <= nivel
        return False

    cabecas: list[str] = []
    for cap in list(livro.capitulos):
        if not cabecas or abre_capitulo(cap):
            cabecas.append(cap.arquivo)
        else:
            juntar(livro, cap.arquivo)
    for cap in livro.capitulos:
        if cap.titulo and _RE_PAGINA_NO_TITULO.match(cap.titulo):
            cap.titulo = ""
    return cabecas


def blocos_do_livro(livro: Livro) -> list[tuple[Capitulo, modelo.Bloco]]:
    """Todo bloco do livro com o seu capítulo, na ordem de leitura (para quem conta ou busca)."""
    return [(cap, bloco) for cap in livro.capitulos for bloco in modelo.blocos_do_capitulo(cap)]

