"""
Os relatórios do livro (ED-08; SPEC_EDITOR §9 "Reports", §9.8): arquivos, imagens,
classes CSS, links e referências, caracteres, fontes e glifos, diagramas — e as duas
limpezas que saem deles, "Apagar recursos não usados" e "Apagar classes CSS não usadas".

Cada relatório devolve `Linha`s (arquivo, onde, mensagem, dados), que a janela põe no
painel Resultados; o `dados` leva o que a ativação precisa (o bloco, a linha da folha).
Tudo é lido do modelo e do texto dos recursos: quem lê o zip é `ler_recurso(recurso)`,
injetado — este módulo não abre arquivo. As fontes são a única parte que precisa de
biblioteca (`fitz.Font.has_glyph`, como `core/chess_pdf_processor.missing_glyphs`) e
ela é importada só ali, quando o relatório roda (DEC-07).

## Apagar classes não usadas preserva o resto byte a byte

A folha não passa por `css_minima.escrever` (que só conhece as propriedades da CSS
mínima e perderia as outras): o varredor de regras (`regras_da_folha`) acha o começo e o
fim de cada regra no texto, e só as regras cujos seletores são **todos** de classes não
usadas são cortadas — com o espaço em branco até a regra seguinte —, o resto fica como
está (AC-ED08-6).
"""

from __future__ import annotations

import os
import posixpath
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from core.editor import modelo, sumario
from core.editor.modelo import Capitulo, Diagrama, Figura, Livro, Recurso

_RE_CLASSE_NO_XHTML = re.compile(r'\bclass\s*=\s*"([^"]*)"')
_RE_ID_NO_XHTML = re.compile(r'\bid\s*=\s*"([^"]*)"')
_RE_HREF_NO_XHTML = re.compile(r'\b(?:href|src|xlink:href|poster)\s*=\s*"([^"]*)"')
_RE_CLASSE_NO_SELETOR = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
_RE_URL_CSS = re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""")
#: `Ã©`, `Ã§`, `Â `…: UTF-8 lido como Latin-1 (o `Ã` ou `Â` seguido de um byte de continuação).
_RE_MOJIBAKE = re.compile("[" + chr(0xC3) + chr(0xC2) + "][" + chr(0x80) + "-" + chr(0xBF) + "]")
MIME_CSS = "text/css"
TIPOS_DE_FONTE = ("font/", "application/vnd.ms-opentype", "application/font-woff", "application/x-font-ttf",
                  "application/x-font-opentype")
RELATORIOS = ("arquivos", "imagens", "classes", "links", "caracteres", "fontes", "diagramas")
ROTULOS_DOS_RELATORIOS = {"arquivos": "Arquivos", "imagens": "Imagens", "classes": "Classes CSS",
                          "links": "Links e referências", "caracteres": "Caracteres", "fontes": "Fontes e glifos",
                          "diagramas": "Diagramas"}


@dataclass
class Linha:
    arquivo: str
    onde: str
    mensagem: str
    dados: dict[str, Any] = field(default_factory=dict)
    gravidade: str = "info"           # "info" | "aviso" | "erro"


LerRecurso = Callable[[Recurso], bytes]


def _texto_do(recurso: Recurso, ler: LerRecurso | None) -> str:
    if recurso.texto_cru is not None:
        return recurso.texto_cru
    dados = recurso.dados
    if dados is None and ler is not None:
        try:
            dados = ler(recurso)
        except FileNotFoundError:
            dados = None
    return (dados or b"").decode("utf-8", errors="replace")


def _cru_do_capitulo(cap: Capitulo) -> str:
    """O XHTML do capítulo como texto (o cru, ou o escrito do modelo) — para o que se procura por regex."""
    if cap.texto_cru is not None:
        return cap.texto_cru
    from core.editor import xhtml

    return xhtml.escrever(cap)


def _relativo_ao_opf(href: str, de_arquivo: str) -> str:
    caminho = href.partition("#")[0]
    if not caminho or "://" in caminho or caminho.startswith(("mailto:", "data:", "tel:")):
        return ""
    pasta = posixpath.dirname(de_arquivo)
    return posixpath.normpath(posixpath.join(pasta, caminho)) if pasta else posixpath.normpath(caminho)


# ----------------------------------------------------------------------
# Uso de recursos, classes e ids
# ----------------------------------------------------------------------

def recursos_referenciados(livro: Livro, ler: LerRecurso | None = None) -> dict[str, set[str]]:
    """`{href do recurso: {quem o usa}}` — pelo modelo, pelo XHTML cru, pelas folhas (`url()`) e pela capa."""
    usos: dict[str, set[str]] = {}

    def usar(href: str, por: str) -> None:
        if href:
            usos.setdefault(href, set()).add(por)

    for cap in livro.capitulos:
        for folha in cap.folhas:
            usar(folha, cap.arquivo)
        if cap.texto_cru is None:
            for bloco in modelo.blocos_do_capitulo(cap):
                if isinstance(bloco, Figura):
                    usar(bloco.recurso, cap.arquivo)
                elif isinstance(bloco, Diagrama):
                    usar(bloco.recorte, cap.arquivo)
                    usar(bloco.imagem, cap.arquivo)
                    if bloco.modo == "png":
                        from core.editor import xhtml

                        usar(xhtml.imagem_do_diagrama(bloco, _pasta_de_imagens(livro)), cap.arquivo)
                elif isinstance(bloco, modelo.IlhaBruta):
                    for m in _RE_HREF_NO_XHTML.finditer(bloco.xhtml):
                        usar(_relativo_ao_opf(m.group(1), cap.arquivo), cap.arquivo)
                for trecho in modelo._todos_os_trechos(bloco):
                    if trecho.ilha:
                        for m in _RE_HREF_NO_XHTML.finditer(trecho.ilha):
                            usar(_relativo_ao_opf(m.group(1), cap.arquivo), cap.arquivo)
            if cap.cabeca_extra:
                for m in _RE_HREF_NO_XHTML.finditer(cap.cabeca_extra):
                    usar(_relativo_ao_opf(m.group(1), cap.arquivo), cap.arquivo)
        else:
            for m in _RE_HREF_NO_XHTML.finditer(cap.texto_cru):
                usar(_relativo_ao_opf(m.group(1), cap.arquivo), cap.arquivo)
    for href, recurso in livro.recursos.items():
        if recurso.tipo_mime == MIME_CSS:
            texto = _texto_do(recurso, ler)
            for m in _RE_URL_CSS.finditer(texto):
                usar(_relativo_ao_opf(m.group(2), href), href)
    if livro.metadados.capa:
        usar(livro.metadados.capa, "capa")
    for folha in livro.folhas:
        usar(folha, "livro")
    return usos


def _pasta_de_imagens(livro: Livro) -> str:
    from core.editor import epub

    return epub.pasta_de_imagens(livro)


def recursos_nao_usados(livro: Livro, ler: LerRecurso | None = None) -> list[str]:
    """Os recursos do manifesto que nada referencia (folhas, imagens, fontes, o que for) — não o nav nem o NCX."""
    usos = recursos_referenciados(livro, ler)
    fora = {livro.nav, livro.ncx, livro.opf}
    return [href for href, r in livro.recursos.items() if href not in usos and href not in fora and r.no_manifesto]


def classes_usadas(livro: Livro) -> dict[str, set[str]]:
    """`{classe: {arquivos que a usam}}` — do modelo (classes, papéis, estilos) e do XHTML cru."""
    usos: dict[str, set[str]] = {}
    for cap in livro.capitulos:
        for classe in _RE_CLASSE_NO_XHTML.findall(_cru_do_capitulo(cap)):
            for nome in classe.split():
                usos.setdefault(nome, set()).add(cap.arquivo)
    return usos


@dataclass
class RegraDaFolha:
    seletores: list[str]
    inicio: int                        # do seletor (depois do espaço em branco anterior)
    fim: int                           # depois do `}` e do espaço em branco até a regra seguinte
    aninhada: bool = False             # dentro de um `@media`/`@supports`


def regras_da_folha(css: str) -> list[RegraDaFolha]:
    """
    As regras de uma folha com os limites no texto: pula comentários e strings, entra em
    `@media {…}` (as regras de dentro saem marcadas `aninhada`) e ignora `@font-face`,
    `@import` e o resto das `@`.
    """
    saida: list[RegraDaFolha] = []
    n = len(css)
    i = 0

    def pular_brancos_e_comentarios(k: int) -> int:
        while k < n:
            if css[k].isspace():
                k += 1
            elif css.startswith("/*", k):
                fim = css.find("*/", k + 2)
                k = n if fim == -1 else fim + 2
            else:
                break
        return k

    def fim_do_bloco(abre: int) -> int:
        nivel = 0
        k = abre
        while k < n:
            c = css[k]
            if css.startswith("/*", k):
                fim = css.find("*/", k + 2)
                k = n if fim == -1 else fim + 2
                continue
            if c in "\"'":
                fecha = css.find(c, k + 1)
                k = n if fecha == -1 else fecha + 1
                continue
            if c == "{":
                nivel += 1
            elif c == "}":
                nivel -= 1
                if nivel == 0:
                    return k
            k += 1
        return n - 1

    def varrer(ini: int, limite: int, aninhada: bool) -> None:
        k = pular_brancos_e_comentarios(ini)
        while k < limite:
            abre = css.find("{", k, limite)
            ponto_e_virgula = css.find(";", k, limite)
            if abre == -1:
                break
            if css[k] == "@" and (ponto_e_virgula != -1 and ponto_e_virgula < abre):
                k = pular_brancos_e_comentarios(ponto_e_virgula + 1)
                continue
            fecha = fim_do_bloco(abre)
            cabeca = css[k:abre].strip()
            proximo = pular_brancos_e_comentarios(fecha + 1)
            if cabeca.startswith("@"):
                if cabeca.lower().startswith(("@media", "@supports", "@document")):
                    varrer(abre + 1, fecha, True)
            else:
                seletores = [s.strip() for s in cabeca.split(",") if s.strip()]
                saida.append(RegraDaFolha(seletores, k, min(proximo, limite), aninhada))
            k = proximo
    varrer(i, n, False)
    return saida


def classes_definidas(css: str) -> dict[str, list[RegraDaFolha]]:
    """`{classe: [regras em que aparece]}`."""
    saida: dict[str, list[RegraDaFolha]] = {}
    for regra in regras_da_folha(css):
        for seletor in regra.seletores:
            for classe in _RE_CLASSE_NO_SELETOR.findall(seletor):
                saida.setdefault(classe, []).append(regra)
    return saida


def apagar_classes_nao_usadas(css: str, usadas: Iterable[str]) -> tuple[str, list[str]]:
    """
    A folha sem as regras cujos seletores são todos `.classe` (com ou sem elemento) de
    classes que ninguém usa; o resto fica byte a byte. Devolve `(folha, classes apagadas)`.
    """
    usadas = set(usadas)
    apagar: list[RegraDaFolha] = []
    apagadas: list[str] = []
    for regra in regras_da_folha(css):
        classes_da_regra = []
        so_de_classe = True
        for seletor in regra.seletores:
            classes = _RE_CLASSE_NO_SELETOR.findall(seletor)
            if not classes:
                so_de_classe = False
                break
            classes_da_regra.extend(classes)
        if so_de_classe and classes_da_regra and all(c not in usadas for c in classes_da_regra):
            apagar.append(regra)
            apagadas.extend(c for c in classes_da_regra if c not in apagadas)
    for regra in sorted(apagar, key=lambda r: r.inicio, reverse=True):
        css = css[:regra.inicio] + css[regra.fim:]
    return css, apagadas


# ----------------------------------------------------------------------
# Os relatórios
# ----------------------------------------------------------------------

def arquivos(livro: Livro, ler: LerRecurso | None = None) -> list[Linha]:
    """Cada arquivo do livro: tipo, tamanho (do texto ou dos dados), e por quem é usado."""
    usos = recursos_referenciados(livro, ler)
    saida: list[Linha] = []
    for cap in livro.capitulos:
        tamanho = len((cap.texto_cru or "").encode("utf-8")) if cap.texto_cru is not None else \
            sum(len(modelo.texto_de(b)) for b in cap.blocos)
        saida.append(Linha(cap.arquivo, "capítulo", f"{len(cap.blocos)} bloco(s), {len(cap.notas)} nota(s), "
                                                    f"{tamanho:,} bytes".replace(",", "."),
                           {"tipo": "capitulo"}))
    for href, recurso in livro.recursos.items():
        dados = recurso.dados
        if dados is None and recurso.texto_cru is not None:
            dados = recurso.texto_cru.encode("utf-8")
        if dados is None and ler is not None:
            try:
                dados = ler(recurso)
            except FileNotFoundError:
                dados = None
        tamanho = f"{len(dados):,} bytes".replace(",", ".") if dados is not None else "(no zip)"
        por = sorted(usos.get(href, ()))
        saida.append(Linha(href, recurso.tipo_mime, f"{tamanho}; usado por: {', '.join(por) if por else 'ninguém'}",
                           {"tipo": "recurso", "usos": por}, "aviso" if not por and recurso.no_manifesto else "info"))
    return saida


def imagens(livro: Livro, ler: LerRecurso | None = None) -> list[Linha]:
    """As imagens: onde cada uma é usada; a não usada é aviso; a figura que aponta para o que não existe, erro."""
    usos = recursos_referenciados(livro, ler)
    saida: list[Linha] = []
    for href, recurso in livro.recursos.items():
        if not recurso.tipo_mime.startswith("image/"):
            continue
        por = sorted(usos.get(href, ()))
        if por:
            saida.append(Linha(href, recurso.tipo_mime, f"usada em {', '.join(por)}", {"usos": por}))
        else:
            saida.append(Linha(href, recurso.tipo_mime, "imagem não usada", {"usos": []}, "aviso"))
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Figura) and bloco.recurso not in livro.recursos:
                saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"figura aponta para imagem inexistente: "
                                                                      f"{bloco.recurso}", {"bloco": bloco.id}, "erro"))
            elif isinstance(bloco, Figura) and not bloco.alt:
                saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"figura sem texto alternativo: {bloco.recurso}",
                                   {"bloco": bloco.id}, "aviso"))
    return saida


def classes(livro: Livro, ler: LerRecurso | None = None) -> list[Linha]:
    """As classes usadas sem definição em folha alguma, e as definidas sem uso (por folha)."""
    usadas = classes_usadas(livro)
    definidas: dict[str, list[tuple[str, RegraDaFolha]]] = {}
    for href, recurso in livro.recursos.items():
        if recurso.tipo_mime != MIME_CSS:
            continue
        for classe, regras in classes_definidas(_texto_do(recurso, ler)).items():
            definidas.setdefault(classe, []).extend((href, r) for r in regras)
    saida: list[Linha] = []
    for classe in sorted(usadas):
        if classe not in definidas:
            arquivos_ = sorted(usadas[classe])
            saida.append(Linha(arquivos_[0], f"classe {classe}", f"classe usada e não definida em folha alguma "
                                                                 f"({len(arquivos_)} arquivo(s))",
                               {"classe": classe, "arquivos": arquivos_}, "aviso"))
    for classe in sorted(definidas):
        if classe not in usadas:
            href, regra = definidas[classe][0]
            saida.append(Linha(href, f"classe {classe}", "classe definida e não usada", {"classe": classe,
                                                                                       "inicio": regra.inicio}, "info"))
    return saida


def _ids_por_arquivo(livro: Livro) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    for cap in livro.capitulos:
        if cap.texto_cru is not None:
            ids[cap.arquivo] = set(_RE_ID_NO_XHTML.findall(cap.texto_cru))
        else:
            ids[cap.arquivo] = {b.id for b in modelo.blocos_do_capitulo(cap)} | {n.id for n in cap.notas}
    return ids


def links(livro: Livro) -> list[Linha]:
    """§9.8: links quebrados, `ref` sem alvo, notas sem referência, âncoras persistentes sem quem as aponte."""
    ids = _ids_por_arquivo(livro)
    saida: list[Linha] = []
    apontadas: set[tuple[str, str]] = set()
    for cap in livro.capitulos:
        if cap.texto_cru is not None:
            for m in _RE_HREF_NO_XHTML.finditer(cap.texto_cru):
                href = m.group(1)
                arquivo, _, ancora = href.partition("#")
                if "://" in arquivo or arquivo.startswith(("mailto:", "data:", "tel:")):
                    continue
                alvo = _relativo_ao_opf(arquivo, cap.arquivo) if arquivo else cap.arquivo
                if alvo in ids:
                    if ancora and ancora not in ids[alvo] and not ancora.startswith("pg-"):
                        saida.append(Linha(cap.arquivo, "link", f"âncora inexistente: {href}", {}, "erro"))
                    elif ancora:
                        apontadas.add((alvo, ancora))
                elif alvo not in livro.recursos and alvo != livro.nav:
                    saida.append(Linha(cap.arquivo, "link", f"destino inexistente: {href}", {}, "erro"))
            continue
        referenciadas: set[str] = set()
        for bloco in modelo.blocos_do_capitulo(cap):
            for trecho in modelo._todos_os_trechos(bloco):
                if trecho.nota:
                    referenciadas.add(trecho.nota)
                    if cap.nota(trecho.nota) is None:
                        saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"referência a nota inexistente: "
                                                                             f"{trecho.nota}", {"bloco": bloco.id},
                                           "erro"))
                alvo_href = trecho.link
                if not alvo_href or "://" in alvo_href or alvo_href.startswith(("mailto:", "data:", "tel:")):
                    continue
                arquivo, _, ancora = alvo_href.partition("#")
                alvo = arquivo or cap.arquivo
                if alvo not in ids:
                    if alvo not in livro.recursos:
                        gravidade = "erro"
                        rotulo = "ref sem alvo" if trecho.ref else "link quebrado"
                        saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"{rotulo}: {alvo_href}",
                                           {"bloco": bloco.id}, gravidade))
                elif ancora and ancora not in ids[alvo] and not ancora.startswith("pg-"):
                    rotulo = "ref sem alvo" if trecho.ref else "link para âncora inexistente"
                    saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"{rotulo}: {alvo_href}", {"bloco": bloco.id},
                                       "erro"))
                elif ancora:
                    apontadas.add((alvo, ancora))
        for nota in cap.notas:
            if nota.id not in referenciadas:
                saida.append(Linha(cap.arquivo, f"nota {nota.id}", "nota sem referência no texto",
                                   {"bloco": nota.blocos[0].id if nota.blocos else ""}, "aviso"))
    for entrada in sumario._todos(livro.sumario):
        arquivo, _, ancora = entrada.destino.partition("#")
        if ancora:
            apontadas.add((arquivo, ancora))
    for _tipo, destino in livro.marcos:
        arquivo, _, ancora = destino.partition("#")
        if ancora:
            apontadas.add((arquivo, ancora))
    for cap in livro.capitulos:
        if cap.texto_cru is not None:
            continue
        for bloco in cap.blocos:
            if bloco.id_persistente and not isinstance(bloco, (modelo.Titulo, modelo.MarcaDePagina)) \
                    and (cap.arquivo, bloco.id) not in apontadas and not modelo.id_gerado(bloco.id):
                saida.append(Linha(cap.arquivo, f"bloco {bloco.id}", f"âncora sem quem a aponte: #{bloco.id}",
                                   {"bloco": bloco.id}, "info"))
    return saida


def _texto_visivel(cap: Capitulo) -> str:
    if cap.texto_cru is not None:
        return re.sub(r"<[^>]*>", " ", cap.texto_cru)
    partes = [modelo.texto_de(b) for b in cap.blocos] + [modelo.texto_de(n) for n in cap.notas]
    return "\n".join(partes)


def caracteres(livro: Livro, cobre: Callable[[str], bool] | None = None) -> list[Linha]:
    """
    Os caracteres fora do comum (não ASCII, não espaço) com a contagem e os arquivos:
    mojibake (`Ã©`, `Ã§`…) é erro; um caractere que nenhuma fonte embutida desenha
    (`cobre(c)` é falso) é aviso — `♕` sem fonte (AC-ED08-5).
    """
    contagem: Counter = Counter()
    onde: dict[str, set[str]] = {}
    mojibake: dict[str, set[str]] = {}
    for cap in livro.capitulos:
        texto = _texto_visivel(cap)
        for m in _RE_MOJIBAKE.finditer(texto):
            mojibake.setdefault(m.group(0), set()).add(cap.arquivo)
        for c in texto:
            if ord(c) < 128 or c.isspace():
                continue
            contagem[c] += 1
            onde.setdefault(c, set()).add(cap.arquivo)
    saida: list[Linha] = []
    for seq, arquivos_ in sorted(mojibake.items()):
        saida.append(Linha(sorted(arquivos_)[0], repr(seq), f"caracteres com Ã (texto lido na codificação errada): "
                                                          f"{seq!r} em {len(arquivos_)} arquivo(s)",
                           {"sequencia": seq, "arquivos": sorted(arquivos_)}, "erro"))
    for c, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0])):
        try:
            nome = unicodedata.name(c).lower()
        except ValueError:
            nome = f"U+{ord(c):04X}"
        arquivos_ = sorted(onde[c])
        sem_fonte = cobre is not None and not cobre(c)
        mensagem = f"{c}  U+{ord(c):04X} {nome}: {n}× em {len(arquivos_)} arquivo(s)"
        if sem_fonte:
            mensagem += " — nenhuma fonte embutida desenha"
        saida.append(Linha(arquivos_[0], c, mensagem, {"caractere": c, "arquivos": arquivos_, "contagem": n},
                           "aviso" if sem_fonte else "info"))
    return saida


def fontes_do_livro(livro: Livro) -> list[str]:
    return [h for h, r in livro.recursos.items() if any(r.tipo_mime.startswith(t) for t in TIPOS_DE_FONTE)]


def cobertura_das_fontes(livro: Livro, ler: LerRecurso | None, pasta_temporaria: str) -> Callable[[str], bool] | None:
    """
    `cobre(c)`: alguma fonte embutida desenha `c`? `None` quando o livro não embute fonte
    (aí não há o que conferir). Usa o `fitz.Font.has_glyph` de
    `core/chess_pdf_processor.py`, importado só aqui.
    """
    caminhos = []
    for href in fontes_do_livro(livro):
        recurso = livro.recursos[href]
        dados = recurso.dados
        if dados is None and ler is not None:
            try:
                dados = ler(recurso)
            except FileNotFoundError:
                dados = None
        if not dados:
            continue
        caminho = os.path.join(pasta_temporaria, posixpath.basename(href))
        with open(caminho, "wb") as f:
            f.write(dados)
        caminhos.append(caminho)
    if not caminhos:
        return None
    try:
        import fitz
    except ImportError:
        return None
    fontes = []
    for caminho in caminhos:
        try:
            fontes.append(fitz.Font(fontfile=caminho))
        except Exception:      # noqa: BLE001 — uma fonte ilegível não derruba o relatório
            continue
    if not fontes:
        return None
    cache: dict[str, bool] = {}

    def cobre(c: str) -> bool:
        if c not in cache:
            cache[c] = any(f.has_glyph(ord(c)) for f in fontes)
        return cache[c]

    return cobre


def fontes(livro: Livro, ler: LerRecurso | None, pasta_temporaria: str) -> list[Linha]:
    """As fontes embutidas, as famílias das folhas (`@font-face`) e os símbolos do livro que nenhuma desenha."""
    from core.editor import css_minima

    saida: list[Linha] = []
    declaradas: dict[str, str] = {}
    for href, recurso in livro.recursos.items():
        if recurso.tipo_mime == MIME_CSS:
            try:
                folha = css_minima.ler(_texto_do(recurso, ler))
            except Exception:      # noqa: BLE001 — folha ilegível
                continue
            for face in folha.fontes:
                declaradas[face.familia] = _relativo_ao_opf(face.arquivo, href)
    embutidas = fontes_do_livro(livro)
    for href in embutidas:
        familias = [f for f, arq in declaradas.items() if arq == href]
        saida.append(Linha(href, "fonte", "fonte embutida" + (f" ({', '.join(familias)})" if familias
                                                               else " — sem @font-face que a declare"),
                           {"familias": familias}, "info" if familias else "aviso"))
    for familia, arquivo in declaradas.items():
        if arquivo not in livro.recursos:
            saida.append(Linha(arquivo, "@font-face", f"a família {familia!r} aponta para fonte inexistente", {},
                               "erro"))
    cobre = cobertura_das_fontes(livro, ler, pasta_temporaria)
    if cobre is None:
        if not embutidas:
            saida.append(Linha("", "fontes", "o livro não embute fonte nenhuma: os símbolos dependem do leitor", {},
                               "info"))
        return saida
    faltam: dict[str, set[str]] = {}
    for cap in livro.capitulos:
        for c in set(_texto_visivel(cap)):
            if ord(c) >= 0x2000 and not c.isspace() and not cobre(c):
                faltam.setdefault(c, set()).add(cap.arquivo)
    for c, arquivos_ in sorted(faltam.items()):
        saida.append(Linha(sorted(arquivos_)[0], c, f"{c} U+{ord(c):04X}: nenhuma fonte embutida desenha",
                           {"caractere": c, "arquivos": sorted(arquivos_)}, "aviso"))
    return saida


def diagramas(livro: Livro) -> list[Linha]:
    """Os diagramas a revisar (`estado`), sem legenda, com lado desconhecido, ou com imagem que não existe."""
    saida: list[Linha] = []
    n = 0
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if not isinstance(bloco, Diagrama):
                continue
            n += 1
            problemas = []
            if bloco.estado == "revisar":
                problemas.append("revisar" + (f" ({bloco.aviso})" if bloco.aviso else ""))
            if not bloco.legenda:
                problemas.append("sem legenda")
            if not bloco.lado:
                problemas.append("lado a jogar desconhecido")
            if bloco.imagem and bloco.imagem not in livro.recursos:
                problemas.append(f"imagem inexistente: {bloco.imagem}")
            if bloco.recorte and bloco.recorte not in livro.recursos:
                problemas.append(f"recorte inexistente: {bloco.recorte}")
            gravidade = "aviso" if problemas else "info"
            saida.append(Linha(cap.arquivo, f"diagrama {n}", (f"{bloco.posicao} — " + "; ".join(problemas))
                               if problemas else f"{bloco.posicao} — ok", {"bloco": bloco.id}, gravidade))
    return saida


def relatorio(nome: str, livro: Livro, ler: LerRecurso | None = None, pasta_temporaria: str = "") -> list[Linha]:
    """Um relatório pelo nome (`RELATORIOS`)."""
    if nome == "arquivos":
        return arquivos(livro, ler)
    if nome == "imagens":
        return imagens(livro, ler)
    if nome == "classes":
        return classes(livro, ler)
    if nome == "links":
        return links(livro)
    if nome == "caracteres":
        cobre = cobertura_das_fontes(livro, ler, pasta_temporaria) if pasta_temporaria else None
        return caracteres(livro, cobre)
    if nome == "fontes":
        return fontes(livro, ler, pasta_temporaria)
    if nome == "diagramas":
        return diagramas(livro)
    raise ValueError(f"relatório desconhecido: {nome!r}")


__all__ = ["Linha", "RELATORIOS", "ROTULOS_DOS_RELATORIOS", "relatorio", "arquivos", "imagens", "classes", "links",
           "caracteres", "fontes", "diagramas", "recursos_referenciados", "recursos_nao_usados", "classes_usadas",
           "classes_definidas", "regras_da_folha", "apagar_classes_nao_usadas", "cobertura_das_fontes",
           "fontes_do_livro"]
