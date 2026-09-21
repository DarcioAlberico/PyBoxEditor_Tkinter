"""
As fontes que o livro embute: quais precisa, de onde vêm, e como entram no EPUB
(ED-10; SPEC_EDITOR §10.1 "fontes usadas copiadas com `@font-face` relativo").

## O que o livro precisa

Duas famílias de fonte não vêm do leitor: a **fonte de diagrama** (um `Diagrama` em
modo `fonte` é texto naquela fonte — sem ela o tabuleiro vira `rmblkans`) e a **fonte
dos símbolos** (as figurinas e os sinais de avaliação, `⩲` e companhia, que a Times
New Roman não desenha — `Trecho.familia == "simbolos"` e todo caractere acima de
`PISO_DO_SIMBOLO`). É o mesmo critério de `exportar.para_epub`, medido no texto: um
livro sem símbolo não carrega os 641 KB da Noto, e o recorte de 5 KB
(`SimbolosDeXadrez.ttf`) vem primeiro quando cobre o que há.

## Por que este módulo lê a fonte à mão

`render_diagrama` traz `fitz` e `PIL`; `exportar` traz `core.livro` (numpy, cv2). O
que se precisa aqui cabe em duas tabelas do SFNT: o `name` (a família, que é o que a
CSS pede) e o `cmap` (que caracteres a fonte desenha, formatos 4 e 12) — cinquenta
linhas de `struct`, e a gravação do livro continua sem carregar o OCR (DEC-07). O
mapa das fontes de diagrama é lido do JSON de `render_diagrama` sem importá-lo.

## Como entram no livro

`embutir(livro)` copia o arquivo de cada fonte que falta para a pasta de fontes do
livro (a que ele já usa; `Fonts/` no livro novo; `fonts/` no EPUB de hoje) como
`Recurso`, e reescreve na folha padrão um bloco marcado `/* pybox:fontes */` com o
`@font-face` (a `src` relativa **à folha**, não ao OPF) e a regra que liga a família
ao seletor — `div.diagrama.<classe> p` ou `span.sim`. Uma família que alguma folha
já declara em `@font-face` (o EPUB de hoje) não é declarada de novo; o bloco é
regenerado a cada gravação, e o resto da folha não é tocado (como o de hifenização).
"""

from __future__ import annotations

import json
import os
import posixpath
import struct
from typing import Iterable

from core.editor import css_minima, modelo
from core.editor.modelo import Diagrama, Livro, Recurso
from core.estilo_do_livro import PISO_DO_SIMBOLO, classe_da_fonte

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAMINHO_DOS_MAPAS = os.path.join(_RAIZ, "core", "dados", "fontes_de_diagrama.json")
#: As fontes de símbolos, na ordem de preferência: o recorte, depois a inteira.
FONTES_DE_SIMBOLOS = (os.path.join(_RAIZ, "assets", "fonts", "SimbolosDeXadrez.ttf"),
                      os.path.join(_RAIZ, "assets", "fonts", "NotoSansSymbols2-Regular.ttf"))
TIPOS_MIME = {".otf": "font/otf", ".ttf": "font/ttf", ".woff": "font/woff", ".woff2": "font/woff2"}
MARCA_DAS_FONTES = "/* pybox:fontes */"
FIM_DAS_FONTES = "/* /pybox:fontes */"


# ----------------------------------------------------------------------
# O arquivo da fonte, lido à mão
# ----------------------------------------------------------------------

def _tabelas(dados: bytes) -> dict[bytes, bytes]:
    """As tabelas de um SFNT (TTF, OTF, ou a primeira fonte de um TTC); vazio se não é fonte."""
    if len(dados) < 12:
        return {}
    deslocamento = struct.unpack(">I", dados[12:16])[0] if dados[:4] == b"ttcf" else 0
    if dados[deslocamento:deslocamento + 4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return {}
    quantas = struct.unpack(">H", dados[deslocamento + 4:deslocamento + 6])[0]
    tabelas: dict[bytes, bytes] = {}
    for k in range(quantas):
        registro = deslocamento + 12 + 16 * k
        if registro + 16 > len(dados):
            break
        tag = dados[registro:registro + 4]
        inicio, tamanho = struct.unpack(">II", dados[registro + 8:registro + 16])
        tabelas[tag] = dados[inicio:inicio + tamanho]
    return tabelas


def familia_dos_dados(dados: bytes) -> str | None:
    """A família (nameID 16, senão 1, de preferência em inglês) da tabela `name`; `None` se não é fonte."""
    tabela = _tabelas(dados).get(b"name")
    if not tabela or len(tabela) < 6:
        return None
    _formato, quantos, inicio_das_strings = struct.unpack(">HHH", tabela[:6])
    candidatos: dict[int, str] = {}
    for k in range(quantos):
        registro = 6 + 12 * k
        if registro + 12 > len(tabela):
            break
        plataforma, _codificacao, idioma, name_id, comprimento, desloc = struct.unpack(
            ">HHHHHH", tabela[registro:registro + 12])
        if name_id not in (1, 16):
            continue
        bruto = tabela[inicio_das_strings + desloc:inicio_das_strings + desloc + comprimento]
        try:
            texto = bruto.decode("utf-16-be") if plataforma in (0, 3) else bruto.decode("latin-1")
        except UnicodeDecodeError:
            continue
        prioridade = (0 if name_id == 16 else 1) * 10 + (0 if idioma in (0x409, 0) else 1)
        if texto.strip() and prioridade not in candidatos:
            candidatos[prioridade] = texto.strip()
    return candidatos[min(candidatos)] if candidatos else None


def familia_do_arquivo(caminho: str) -> str | None:
    """A família de um TTF/OTF do disco (o que `ui/fontes.registrar_arquivo` usa); `None` se não é fonte."""
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError:
        return None
    return familia_dos_dados(dados)


def caracteres_dos_dados(dados: bytes) -> set[int] | None:
    """Os pontos de código que a fonte desenha (cmap formatos 4 e 12); `None` sem cmap legível."""
    cmap = _tabelas(dados).get(b"cmap")
    if not cmap or len(cmap) < 4:
        return None
    quantas = struct.unpack(">H", cmap[2:4])[0]
    saida: set[int] = set()
    lidas = False
    for k in range(quantas):
        registro = 4 + 8 * k
        if registro + 8 > len(cmap):
            break
        _plataforma, _codificacao, desloc = struct.unpack(">HHI", cmap[registro:registro + 8])
        if desloc + 4 > len(cmap):
            continue
        formato = struct.unpack(">H", cmap[desloc:desloc + 2])[0]
        if formato == 4:
            lidas = True
            seg_x2 = struct.unpack(">H", cmap[desloc + 6:desloc + 8])[0]
            n = seg_x2 // 2
            fins = struct.unpack(f">{n}H", cmap[desloc + 14:desloc + 14 + seg_x2])
            inicios = struct.unpack(f">{n}H", cmap[desloc + 16 + seg_x2:desloc + 16 + 2 * seg_x2])
            deltas = struct.unpack(f">{n}h", cmap[desloc + 16 + 2 * seg_x2:desloc + 16 + 3 * seg_x2])
            base_dos_offsets = desloc + 16 + 3 * seg_x2
            offsets = struct.unpack(f">{n}H", cmap[base_dos_offsets:base_dos_offsets + seg_x2])
            for i, (inicio, fim, delta, offset) in enumerate(zip(inicios, fins, deltas, offsets)):
                if inicio == 0xFFFF:
                    continue
                for c in range(inicio, min(fim, 0xFFFE) + 1):
                    if offset == 0:
                        glifo = (c + delta) & 0xFFFF
                    else:
                        indice = base_dos_offsets + 2 * i + offset + 2 * (c - inicio)
                        if indice + 2 > len(cmap):
                            continue
                        glifo = struct.unpack(">H", cmap[indice:indice + 2])[0]
                        if glifo:
                            glifo = (glifo + delta) & 0xFFFF
                    if glifo:      # o glifo 0 é o "não desenha"
                        saida.add(c)
        elif formato == 12:
            lidas = True
            grupos = struct.unpack(">I", cmap[desloc + 12:desloc + 16])[0]
            base = desloc + 16
            for g in range(grupos):
                if base + 12 * g + 12 > len(cmap):
                    break
                inicio, fim, _glifo = struct.unpack(">III", cmap[base + 12 * g:base + 12 * g + 12])
                if fim - inicio > 0x20000:
                    fim = inicio + 0x20000
                saida.update(range(inicio, fim + 1))
    return saida if lidas else None


def desenha(caminho: str, caracteres: Iterable[str]) -> str:
    """Os caracteres de `caracteres` que a fonte do arquivo desenha, na ordem dada."""
    try:
        with open(caminho, "rb") as f:
            pontos = caracteres_dos_dados(f.read())
    except OSError:
        return ""
    if pontos is None:
        return ""
    return "".join(c for c in caracteres if ord(c) in pontos)


# ----------------------------------------------------------------------
# O que o livro precisa
# ----------------------------------------------------------------------

def _mapas() -> dict:
    try:
        with open(CAMINHO_DOS_MAPAS, encoding="utf-8") as f:
            return json.load(f)["fontes"]
    except (OSError, ValueError, KeyError):
        return {}


def arquivo_da_fonte_de_diagrama(nome: str) -> str | None:
    """O arquivo no disco de uma fonte de diagrama do mapa de `render_diagrama`; `None` se não há."""
    bruto = _mapas().get(nome)
    if not bruto or not bruto.get("arquivo"):
        return None
    caminho = bruto["arquivo"]
    if not os.path.isabs(caminho):
        caminho = os.path.join(_RAIZ, caminho)
    return caminho if os.path.exists(caminho) else None


def e_fonte_de_diagrama(familia: str) -> bool:
    return bool(familia) and (familia in _mapas() or familia.endswith("-Diagram"))


def simbolos_de(texto: str) -> str:
    """Os caracteres do texto que precisam da fonte de recurso (acima de `PISO_DO_SIMBOLO`), únicos e ordenados."""
    return "".join(sorted({c for c in texto if ord(c) >= PISO_DO_SIMBOLO}))


def fonte_dos_simbolos(texto: str, candidatas: Iterable[str] = FONTES_DE_SIMBOLOS) -> tuple[str, str, str] | None:
    """
    `(família, arquivo, caracteres cobertos)` da fonte de símbolos que o texto pede — a
    de maior cobertura, o recorte em empate —, ou `None` quando o texto não tem símbolo
    ou nenhuma candidata desenha algum.
    """
    precisa = simbolos_de(texto)
    if not precisa:
        return None
    melhor: tuple[str, str, str] | None = None
    for caminho in candidatas:
        if not os.path.exists(caminho):
            continue
        cobertos = desenha(caminho, precisa)
        if cobertos and (melhor is None or len(cobertos) > len(melhor[2])):
            familia = familia_do_arquivo(caminho) or os.path.splitext(os.path.basename(caminho))[0]
            melhor = (familia, caminho, cobertos)
        if melhor is not None and len(melhor[2]) == len(precisa):
            break
    return melhor


def texto_com_simbolos(livro: Livro) -> str:
    """Só o que importa para a escolha da fonte: os trechos em `simbolos` e os caracteres altos."""
    partes: list[str] = []
    for cap in livro.capitulos:
        if cap.texto_cru is not None:
            partes.append(simbolos_de(cap.texto_cru))
            continue
        for trecho in modelo.trechos_do_capitulo(cap):
            if trecho.familia == "simbolos":
                partes.append(trecho.texto)
            else:
                partes.append(simbolos_de(trecho.texto))
    return "".join(partes)


def fontes_de_diagrama_usadas(livro: Livro) -> list[str]:
    """Os nomes das fontes de diagrama que o livro usa (diagramas em `fonte` e trechos naquela família)."""
    nomes: list[str] = []
    for cap in livro.capitulos:
        if cap.texto_cru is not None:
            for nome in _mapas():
                if f'"{nome}"' in cap.texto_cru or classe_da_fonte(nome) in cap.texto_cru:
                    nomes.append(nome)
            continue
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Diagrama) and bloco.modo == "fonte" and bloco.fonte:
                nomes.append(bloco.fonte)
        for trecho in modelo.trechos_do_capitulo(cap):
            if trecho.familia and trecho.familia != "simbolos" and e_fonte_de_diagrama(trecho.familia):
                nomes.append(trecho.familia)
    return list(dict.fromkeys(nomes))


def necessarias(livro: Livro) -> tuple[dict[str, str], tuple[str, str, str] | None, list[str]]:
    """
    `(fontes de diagrama {nome: arquivo}, fonte dos símbolos ou None, avisos)` — o que o
    livro precisa embutir, resolvido para arquivos do disco.
    """
    avisos: list[str] = []
    diagramas: dict[str, str] = {}
    for nome in fontes_de_diagrama_usadas(livro):
        arquivo = arquivo_da_fonte_de_diagrama(nome)
        if arquivo is None:
            avisos.append(f"fonte de diagrama sem arquivo no mapa, não embutida: {nome}")
            continue
        diagramas[nome] = arquivo
    simbolos = fonte_dos_simbolos(texto_com_simbolos(livro))
    return diagramas, simbolos, avisos


# ----------------------------------------------------------------------
# Embutir no livro
# ----------------------------------------------------------------------

def _e_fonte(recurso: Recurso) -> bool:
    return recurso.tipo_mime.startswith("font/") or recurso.tipo_mime in (
        "application/vnd.ms-opentype", "application/font-sfnt", "application/x-font-ttf",
        "application/x-font-otf", "application/font-woff", "application/font-woff2")


def pasta_de_fontes(livro: Livro) -> str:
    """A pasta das fontes: a que o livro usa; senão `fonts/` ao lado de `imagens/` (o EPUB de hoje); senão `Fonts`."""
    for caminho, recurso in livro.recursos.items():
        if _e_fonte(recurso) and recurso.no_manifesto:
            return posixpath.dirname(caminho) or "."
    for caminho, recurso in livro.recursos.items():
        if recurso.tipo_mime.startswith("image/") and recurso.no_manifesto:
            pasta = posixpath.dirname(caminho)
            if pasta and pasta[:1].islower():
                return posixpath.join(posixpath.dirname(pasta), "fonts") if "/" in pasta else "fonts"
            break
    return "Fonts"


def familias_declaradas(livro: Livro, ler_recurso=None) -> set[str]:
    """As famílias que alguma folha do livro já declara em `@font-face` (fora do bloco marcado)."""
    saida: set[str] = set()
    for href in livro.folhas:
        texto = _texto_da_folha(livro, href, ler_recurso)
        if texto is None:
            continue
        texto = folha_com_fontes(texto, "")
        try:
            saida.update(f.familia for f in css_minima.ler(texto).fontes)
        except Exception:      # noqa: BLE001 — uma folha que o leitor mínimo recusa não impede a gravação
            continue
    return saida


def _texto_da_folha(livro: Livro, href: str, ler_recurso=None) -> str | None:
    recurso = livro.recurso(href)
    if recurso is None:
        return None
    if recurso.texto_cru is not None:
        return recurso.texto_cru
    if recurso.dados is not None:
        return recurso.dados.decode("utf-8", errors="replace").lstrip("﻿")
    if ler_recurso is not None:
        try:
            return ler_recurso(recurso)
        except Exception:      # noqa: BLE001 — a folha que não se consegue ler fica como está
            return None
    return None


def folha_com_fontes(css: str, bloco: str) -> str:
    """A folha com o bloco marcado `pybox:fontes` trocado por `bloco` (vazio = tirado), sem tocar no resto."""
    ini = css.find(MARCA_DAS_FONTES)
    if ini != -1:
        fim = css.find(FIM_DAS_FONTES, ini)
        fim = len(css) if fim == -1 else fim + len(FIM_DAS_FONTES)
        if fim < len(css) and css[fim] == "\n":
            fim += 1
        css = css[:ini] + css[fim:]
    if not bloco:
        return css
    if css and not css.endswith("\n"):
        css += "\n"
    return css + MARCA_DAS_FONTES + "\n" + bloco.rstrip("\n") + "\n" + FIM_DAS_FONTES + "\n"


def _regra(familia: str, src: str, seletor: str, reserva: str) -> str:
    return (f'@font-face {{ font-family: "{familia}"; font-weight: normal; font-style: normal;\n'
            f'  src: url("{src}"); }}\n'
            f'{seletor} {{ font-family: "{familia}", {reserva}; }}\n')


def embutir(livro: Livro, ler_recurso=None) -> tuple[list[str], list[str]]:
    """
    Põe no livro as fontes que ele precisa e não tem, e regenera o bloco `pybox:fontes`
    da folha padrão. Devolve `(hrefs das fontes embutidas agora, avisos)`. Sem folha
    padrão, as fontes entram e a regra fica por conta de quem a escrever (aviso).
    """
    diagramas, simbolos, avisos = necessarias(livro)
    if not diagramas and simbolos is None:
        _tirar_bloco(livro, ler_recurso)
        return [], avisos
    pasta = pasta_de_fontes(livro)
    por_nome = {posixpath.basename(c).lower(): c for c, r in livro.recursos.items() if _e_fonte(r)}
    novos: list[str] = []

    def por(arquivo: str) -> str:
        base = os.path.basename(arquivo)
        if base.lower() in por_nome:
            return por_nome[base.lower()]
        href = posixpath.join(pasta, base) if pasta != "." else base
        with open(arquivo, "rb") as f:
            dados = f.read()
        livro.recursos[href] = Recurso(caminho=href, tipo_mime=TIPOS_MIME.get(os.path.splitext(base)[1].lower(),
                                                                                "font/otf"), dados=dados)
        por_nome[base.lower()] = href
        novos.append(href)
        return href

    hrefs = {nome: por(arquivo) for nome, arquivo in diagramas.items()}
    href_simbolos = por(simbolos[1]) if simbolos else ""
    if not livro.folhas or livro.recurso(livro.folhas[0]) is None:
        avisos.append("livro sem folha padrão: as fontes foram embutidas sem @font-face")
        return novos, avisos
    folha = livro.folhas[0]
    declaradas = familias_declaradas(livro, ler_recurso)
    pasta_da_folha = posixpath.dirname(folha)
    regras: list[str] = []
    for nome, href in hrefs.items():
        if nome in declaradas:
            continue
        src = posixpath.relpath(href, pasta_da_folha) if pasta_da_folha else href
        regras.append(_regra(nome, src, f"div.diagrama.{classe_da_fonte(nome)} p", "monospace"))
    if simbolos and simbolos[0] not in declaradas:
        src = posixpath.relpath(href_simbolos, pasta_da_folha) if pasta_da_folha else href_simbolos
        regras.append(_regra(simbolos[0], src, "span.sim", "serif"))
    recurso = livro.recurso(folha)
    atual = _texto_da_folha(livro, folha, ler_recurso)
    if atual is None:
        avisos.append(f"folha padrão ilegível, @font-face não escrito: {folha}")
        return novos, avisos
    novo = folha_com_fontes(atual, "".join(regras))
    if novo != atual:
        if recurso.texto_cru is not None:
            recurso.texto_cru = novo
        else:
            recurso.dados = novo.encode("utf-8")
    return novos, avisos


def _tirar_bloco(livro: Livro, ler_recurso=None) -> None:
    """Sem fonte necessária, o bloco marcado (de uma gravação anterior) sai da folha."""
    if not livro.folhas:
        return
    recurso = livro.recurso(livro.folhas[0])
    atual = _texto_da_folha(livro, livro.folhas[0], ler_recurso) if recurso is not None else None
    if atual is None or MARCA_DAS_FONTES not in atual:
        return
    novo = folha_com_fontes(atual, "")
    if recurso.texto_cru is not None:
        recurso.texto_cru = novo
    else:
        recurso.dados = novo.encode("utf-8")


__all__ = ["familia_do_arquivo", "familia_dos_dados", "caracteres_dos_dados", "desenha", "simbolos_de",
           "fonte_dos_simbolos", "fontes_de_diagrama_usadas", "arquivo_da_fonte_de_diagrama", "necessarias",
           "pasta_de_fontes", "familias_declaradas", "folha_com_fontes", "embutir", "FONTES_DE_SIMBOLOS",
           "MARCA_DAS_FONTES", "FIM_DAS_FONTES"]
