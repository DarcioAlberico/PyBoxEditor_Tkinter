"""
A ponte com o documento editorial (ED-11; SPEC_EDITOR §10.6.5, §10.7, DEC-10, AC-008).

## Ida: o documento vira livro

`de_documento(documento)` monta um `Livro` do `EditorialDocument` com o mapa da §10.6.5
na letra: `paragraph` → `Paragrafo` (`bold_spans` → negrito), `heading` → `Titulo`,
`caption` → `Paragrafo(estilo="legenda")`, `chess_sequence` → `notacao`, `diagram` →
`Diagrama` com `lado=""` (DEC-06) e o recorte impresso como recurso — sem `fen`, ou
`origin == "faixa"`, vira `Figura` com aviso —, `table` → `Tabela`, toda página nova →
`MarcaDePagina(page_index + 1)` (o índice do PDF, não o fólio), `page_break` no meio da
página → `QuebraDePagina` (a marca da página já está no começo dela),
`header`/`footer` ignorados com aviso, `unknown` → `Paragrafo` com aviso. **Todo bloco
leva a `Origem`** (`page_id`, `bloco_id`, página, caixa), que o XHTML escreve como
`data-origem-*`; o bloco que o pipeline pôs na fila leva `extras["data-suspeito"]`
com os códigos dos motivos. Um capítulo por título de nível 1 (`dividir="titulo"`) ou
um por página (`dividir="pagina"`). `de_paginas` passa as `PaginaExtraida` do leitor
pelo adapter e cai aqui; `ler` abre o JSON gravado.

## Volta: o que mudou vira evento

`eventos_de(livro, documento)` compara o **valor** de cada bloco com origem com a decisão
atual do documento e devolve `Mudanca(bloco_id, after, motivo)`: texto para parágrafo,
o dicionário inteiro da decisão com `fen`/`orientation` trocados para diagrama (senão
`png_base64` e `font` se perderiam), `rows` para tabela; `after=None` é o bloco apagado
(rejeitar); os blocos **fundidos** (`origem.fundidas`) dão `edit` no primeiro e `reject`
nos demais; o bloco novo não dá evento — vai ao relatório. `gravar_eventos` abre a
`ReviewSession.from_journal` no diário que o pipeline convencionou
(`metadata["review_journal_path"]`, `<arquivo>.review.jsonl`) e grava `edit`/`reject`
com `reason_codes=("editor",)`, `user="editor"`. **Formato não viaja** (DEC-10): o
negrito e o itálico do bloco editado ficam no livro, e o relatório da ponte o diz.

Só `core.editorial_model` é importado no topo (é leve); `core.editorial_review` puxa a
cadeia do OCR e entra só em `gravar_eventos` (DEC-07).
"""

from __future__ import annotations

import base64
import copy
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, NamedTuple

from core.editor import epub, modelo, sumario
from core.editor.conversao import Cronometro, RelatorioDeConversao
from core.editor.modelo import (Bloco, Capitulo, Celula, Diagrama, Figura, Livro, MarcaDePagina, Metadados, Origem,
                                Paragrafo, Recurso, Tabela, Titulo, Trecho)
from core.editorial_model import EditorialBlock, EditorialDocument, EditorialPage

#: Os códigos de procedência que o adapter põe em toda decisão — não são motivo de suspeita
#: (a mesma lista de `core.editorial_suspeitas.PROCEDENCIA`, copiada para não importar o OCR).
PROCEDENCIA = frozenset({"legacy_adapter", "page_result_region", "page_result_text"})
TIPOS_DE_TEXTO = ("paragraph", "heading", "caption", "chess_sequence", "unknown")
ESTILO_DO_TIPO = {"paragraph": "corpo", "caption": "legenda", "chess_sequence": "notacao", "unknown": "corpo"}
#: O que não vira bloco do livro — e por isso não dá evento quando "falta".
TIPOS_FORA_DO_LIVRO = ("header", "footer", "page_break")
SUFIXO_DO_DIARIO = ".review.jsonl"


# ----------------------------------------------------------------------
# Ida: documento → livro
# ----------------------------------------------------------------------

def _posicao(fen: str) -> str:
    return (fen or "").split()[0] if fen else ""


def _fen_completo(fen: str) -> str:
    """O FEN do IR pode vir só com a colocação; o `Diagrama` quer o FEN inteiro (lado por convenção)."""
    partes = (fen or "").split()
    if len(partes) >= 2:
        return " ".join(partes)
    return f"{partes[0]} w - - 0 1" if partes else ""


def _casa_valida(casa: str) -> bool:
    """`c6` sim, `z9` não — a marca que não é casa não entra no diagrama do editor."""
    return len(casa) == 2 and casa[0] in "abcdefgh" and casa[1] in "12345678"


def _codigos_de_suspeita(block: EditorialBlock) -> str:
    """Os códigos que fazem do bloco um suspeito (§10.6.5), ou "" quando não é."""
    codigos = [c for c in block.decision.reason_codes if c not in PROCEDENCIA]
    if not codigos and (block.metadata.get("review_required") or block.decision.status == "unresolved"):
        codigos = ["review_required" if block.metadata.get("review_required") else block.decision.status]
    return " ".join(dict.fromkeys(codigos))


def _caixa_de(block: EditorialBlock) -> tuple[int, int, int, int] | None:
    valor = block.decision.value
    if isinstance(valor, dict) and valor.get("bbox") and len(valor["bbox"]) == 4:
        return tuple(int(v) for v in valor["bbox"])
    for ref in block.source_refs:
        if ref.bbox:
            return tuple(ref.bbox)
    return None


class _Construtor:
    def __init__(self, documento: EditorialDocument, relatorio: RelatorioDeConversao, dividir: str):
        self.doc = documento
        self.relatorio = relatorio
        self.dividir = dividir
        self.recursos: dict[str, Recurso] = {}
        self.capitulos: list[list[Bloco]] = [[]]
        self.ignorados = 0
        self.rejeitados = 0

    # -- capítulos ----------------------------------------------------------

    def _novo_capitulo(self) -> None:
        atual = self.capitulos[-1]
        # as marcas de página que acabaram de entrar pertencem ao capítulo que começa
        marcas: list[Bloco] = []
        while atual and isinstance(atual[-1], MarcaDePagina):
            marcas.insert(0, atual.pop())
        if atual:
            self.capitulos.append(marcas)
        else:
            atual.extend(marcas)                                     # o corrente está vazio: continua nele

    def _acrescentar(self, bloco: Bloco) -> None:
        atual = self.capitulos[-1]
        if isinstance(bloco, MarcaDePagina) and atual and isinstance(atual[-1], MarcaDePagina) \
                and atual[-1].pagina == bloco.pagina:
            return                                                   # a mesma página, marcada duas vezes
        atual.append(bloco)

    # -- os blocos ----------------------------------------------------------

    def _origem(self, page: EditorialPage, block: EditorialBlock) -> Origem:
        return Origem(page_id=page.page_id, bloco_id=block.id, pagina=page.page_index, caixa=_caixa_de(block))

    def _marcar(self, bloco: Bloco, page: EditorialPage, block: EditorialBlock) -> Bloco:
        bloco.origem = self._origem(page, block)
        suspeita = _codigos_de_suspeita(block)
        if suspeita:
            bloco.extras["data-suspeito"] = suspeita
        return bloco

    def _recurso(self, nome: str, dados: bytes) -> str:
        caminho = f"Images/{nome}"
        self.recursos[caminho] = Recurso(caminho=caminho, tipo_mime="image/png", dados=dados)
        return caminho

    def _texto(self, page: EditorialPage, block: EditorialBlock) -> Bloco:
        valor = block.decision.value
        texto = valor if isinstance(valor, str) else ("" if valor is None else str(valor))
        if block.kind == "heading":
            nivel = block.style.get("heading_level")
            try:
                nivel = int(nivel) if nivel is not None else 2
            except (TypeError, ValueError):
                nivel = 2
            bloco: Paragrafo = Titulo(trechos=[Trecho(texto=texto)], nivel=max(1, min(6, nivel)))
        else:
            bloco = Paragrafo(trechos=[Trecho(texto=texto)], estilo=ESTILO_DO_TIPO.get(block.kind, "corpo"))
            if block.kind == "unknown":
                self.relatorio.aviso(f"página {page.page_index + 1}, bloco {block.id}: tipo desconhecido "
                                     f"({block.metadata.get('legacy_type', '?')}) virou parágrafo")
        for par in block.style.get("bold_spans") or []:
            try:
                ini, fim = int(par[0]), int(par[1])
            except (TypeError, ValueError, IndexError):
                continue
            ini, fim = max(0, ini), min(len(texto), fim)
            if ini < fim:
                modelo.aplicar_formato(bloco, ini, fim, negrito=True)
        return bloco

    def _diagrama(self, page: EditorialPage, block: EditorialBlock) -> Bloco:
        valor = block.decision.value if isinstance(block.decision.value, dict) else {}
        fen = str(valor.get("fen") or "")
        origin = str(valor.get("origin") or "")
        png = b""
        if valor.get("png_base64"):
            try:
                png = base64.b64decode(valor["png_base64"])
            except (ValueError, TypeError):
                png = b""
        nome = f"{page.page_id}-{block.order:04d}"
        if fen and origin != "faixa" and modelo.fen_valido(_fen_completo(fen)):
            recorte = self._recurso(f"recorte-{nome}.png", png) if png and origin != "render" else ""
            fonte = str(valor.get("font") or "") or modelo.FONTE_PADRAO
            return Diagrama(fen=_fen_completo(fen), lado="",
                            orientacao="preta" if str(valor.get("orientation") or "") == "preta" else "branca",
                            coordenadas=bool(valor.get("coordinates")), fonte=fonte, modo="png", recorte=recorte,
                            aviso=str(valor.get("warning") or ""),
                            # As casas que o livro marcou (F110, lidas da camada do PDF).
                            marcas=[str(c) for c in valor.get("marks") or [] if _casa_valida(str(c))])
        aviso = str(valor.get("warning") or "") or ("diagrama numa faixa da página" if origin == "faixa"
                                                    else "diagrama sem posição lida")
        self.relatorio.aviso(f"página {page.page_index + 1}, bloco {block.id}: {aviso} — ficou como figura")
        if not png:
            return Paragrafo(trechos=[Trecho(texto=f"[diagrama sem imagem: {aviso}]")], estilo="legenda")
        return Figura(recurso=self._recurso(f"figura-{nome}.png", png), alt=aviso, extras={"title": aviso})

    def _tabela(self, block: EditorialBlock) -> Bloco:
        valor = block.decision.value if isinstance(block.decision.value, dict) else {}
        filas = [[str(c) for c in fila] for fila in valor.get("rows") or []]
        largura = max((len(f) for f in filas), default=0)
        celulas = [[Celula(blocos=[Paragrafo(trechos=[Trecho(texto=c)] if c else [])])
                    for c in fila + [""] * (largura - len(fila))] for fila in filas]
        if not celulas:
            celulas = [[Celula(blocos=[Paragrafo(trechos=[])])]]
        return Tabela(filas=celulas)

    def _blocos_de(self, page: EditorialPage, block: EditorialBlock) -> list[Bloco]:
        if block.decision.status == "rejected":
            self.rejeitados += 1
            return []
        if block.kind in ("header", "footer"):
            self.ignorados += 1
            self.relatorio.aviso(f"página {page.page_index + 1}: {block.kind} ignorado ({block.id})")
            return []
        if block.kind == "page_break":
            # A marca da página já entrou quando a página começou (§6.1: a marca impressa não é
            # quebra); uma quebra no meio da página é uma quebra de verdade — sem origem, porque
            # não tem valor que se edite.
            return [modelo.QuebraDePagina()]
        # `figure` e a `caption` com imagem passam pelo mesmo lugar do diagrama
        # (item 4 da revisão de 2026-09-18): as três vêm de uma `livro.Figura`,
        # e é `_diagrama` quem sabe quando ela tem posição e quando é só a
        # imagem — a faixa do exercício e a página inteira nunca têm.
        valor_do_bloco = block.decision.value
        if block.kind in ("diagram", "figure") or (
                block.kind == "caption" and isinstance(valor_do_bloco, dict)
                and valor_do_bloco.get("png_base64")):
            bloco = self._diagrama(page, block)
        elif block.kind == "table":
            bloco = self._tabela(block)
        else:
            bloco = self._texto(page, block)
        return [self._marcar(bloco, page, block)]

    # -- o livro ------------------------------------------------------------

    def montar(self) -> Livro:
        doc = self.doc
        for k, page in enumerate(sorted(doc.pages, key=lambda p: p.page_index)):
            if self.dividir == "pagina" and k:
                self._novo_capitulo()
            self._acrescentar(MarcaDePagina(pagina=page.page_index + 1))
            for block in sorted(page.blocks, key=lambda b: b.order):
                if self.dividir == "titulo" and block.kind == "heading" \
                        and int(block.style.get("heading_level") or 2) == 1 \
                        and block.decision.status != "rejected":
                    self._novo_capitulo()
                for bloco in self._blocos_de(page, block):
                    self._acrescentar(bloco)
        grupos = [g for g in self.capitulos if g] or [[Paragrafo(trechos=[])]]
        titulo = doc.title or next((modelo.texto_de(b) for g in grupos for b in g
                                    if isinstance(b, Titulo) and b.nivel == 1), "") or doc.document_id
        livro = epub.novo_livro(titulo, "", doc.language or "und", ncx=True)
        padrao = livro.folhas[0]
        livro.capitulos = [Capitulo(arquivo=f"Text/cap-{k:04d}.xhtml", blocos=g, folhas=[padrao],
                                    idioma=doc.language or "") for k, g in enumerate(grupos, 1)]
        livro.metadados = Metadados(titulo=titulo, idioma=doc.language or "und",
                                    identificador=livro.metadados.identificador)
        livro.recursos.update(self.recursos)
        livro.sumario = sumario.gerar_dos_titulos(livro)
        livro.marcos = [("bodymatter", livro.capitulos[0].arquivo)]
        livro.origem.pdf = str(doc.metadata.get("source_path") or "")
        livro.origem.diario = str(doc.metadata.get("review_journal_path") or "")
        self.relatorio.metadados.update({"paginas": len(doc.pages), "ignorados": self.ignorados,
                                         "rejeitados": self.rejeitados, "documento": doc.document_id})
        return livro


def de_documento(documento: EditorialDocument, *, dividir: str = "titulo", caminho: str = "") \
        -> tuple[Livro, RelatorioDeConversao]:
    """`(Livro, relatório)` do documento editorial (§10.6.5); `caminho` é o JSON de onde ele veio, se veio."""
    if dividir not in ("titulo", "pagina"):
        raise ValueError(f"dividir inválido: {dividir!r} (use 'titulo' ou 'pagina')")
    relatorio = RelatorioDeConversao(formato="editorial", arquivos=[caminho] if caminho else [])
    with Cronometro(relatorio):
        livro = _Construtor(documento, relatorio, dividir).montar()
        if caminho:
            livro.origem.documento_editorial = os.path.abspath(os.fspath(caminho))
    relatorio.contar(livro)
    return livro, relatorio


def de_paginas(paginas: Iterable[Any], *, document_id: str = "document", titulo: str = "", idioma: str = "und",
               dividir: str = "titulo") -> tuple[Livro, RelatorioDeConversao]:
    """As `PaginaExtraida` do leitor (`core.livro`) pelo adapter, e daí `de_documento`."""
    from core.editorial_adapters import paginas_extraidas_para_documento

    documento = paginas_extraidas_para_documento(list(paginas), document_id=document_id, title=titulo,
                                                 language=idioma)
    return de_documento(documento, dividir=dividir)


def ler(caminho: str, *, dividir: str = "titulo") -> tuple[Livro, RelatorioDeConversao]:
    """O JSON do documento editorial → `(Livro, relatório)`; `ValueError` no que não é um documento."""
    caminho = os.fspath(caminho)
    try:
        documento = EditorialDocument.load_json(caminho)
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise ValueError(f"não é um documento editorial: {caminho} ({erro})") from None
    return de_documento(documento, dividir=dividir, caminho=caminho)


def caminho_do_diario(documento: EditorialDocument, caminho: str = "") -> str:
    """O diário do pipeline (`review_journal_path`), ou o `<arquivo>.review.jsonl` ao lado do JSON/EPUB (DEC-10)."""
    diario = str(documento.metadata.get("review_journal_path") or "")
    if diario:
        return diario
    if caminho:
        base, _ext = os.path.splitext(os.fspath(caminho))
        return base + SUFIXO_DO_DIARIO
    return ""


# ----------------------------------------------------------------------
# Volta: livro → eventos
# ----------------------------------------------------------------------

class Mudanca(NamedTuple):
    bloco_id: str          # o `EditorialBlock.id`
    after: Any             # o valor novo, no formato do IR; `None` = o bloco saiu (rejeitar)
    motivo: str            # "editado" | "apagado" | "fundido" (o primeiro) | "fundido_apagado" (os demais)


def _texto_da_celula(celula: Celula) -> str:
    return "\n".join(modelo.texto_de(p) for p in celula.blocos)


def _valor_de(bloco: Bloco, block: EditorialBlock) -> Any:
    """O valor do bloco do livro no formato do IR do `block`; `None` quando os tipos não casam."""
    valor = block.decision.value
    if block.kind in TIPOS_DE_TEXTO and isinstance(bloco, Paragrafo):
        return modelo.texto_de(bloco)
    if block.kind == "table" and isinstance(bloco, Tabela):
        filas = [[_texto_da_celula(c) for c in fila] for fila in bloco.filas]
        antes = [[str(c) for c in fila] for fila in (valor.get("rows") if isinstance(valor, dict) else []) or []]
        largura = max((len(f) for f in antes), default=0)
        if filas == [fila + [""] * (largura - len(fila)) for fila in antes]:
            return valor                                     # só o preenchimento retangular da ida: nada mudou
        return {"rows": filas}
    if block.kind == "diagram" and isinstance(bloco, Diagrama) and isinstance(valor, dict):
        novo = copy.deepcopy(valor)
        if _posicao(bloco.fen) != _posicao(str(valor.get("fen") or "")):
            novo["fen"] = bloco.fen
        orientacao_antes = str(valor.get("orientation") or "branca")
        if bloco.orientacao != orientacao_antes:
            novo["orientation"] = bloco.orientacao
        return novo
    return None


def _blocos_com_origem(livro: Livro) -> tuple[dict[str, Bloco], dict[str, str], list[Bloco], list[str]]:
    """`(principal por bloco_id, fundida → id do bloco que a absorveu, blocos novos, avisos)`."""
    principais: dict[str, Bloco] = {}
    fundidas: dict[str, str] = {}
    novos: list[Bloco] = []
    avisos: list[str] = []
    for cap in livro.capitulos:
        for bloco in cap.blocos:                        # só o nível de cima: a célula de tabela não é bloco novo
            if isinstance(bloco, (MarcaDePagina, modelo.QuebraDePagina, modelo.Separador)):
                continue
            if bloco.origem is None:
                novos.append(bloco)
                continue
            if bloco.origem.bloco_id in principais:
                avisos.append(f"{cap.arquivo}: o bloco {bloco.id} repete a origem {bloco.origem.bloco_id}; "
                              f"tratado como bloco novo")
                novos.append(bloco)
                continue
            principais[bloco.origem.bloco_id] = bloco
            for outra in bloco.origem.fundidas:
                fundidas.setdefault(outra.bloco_id, bloco.origem.bloco_id)
    return principais, fundidas, novos, avisos


def eventos_de(livro: Livro, documento: EditorialDocument) -> list[Mudanca]:
    """As mudanças do livro em relação à decisão atual de cada bloco do documento (ver o cabeçalho)."""
    principais, fundidas, _novos, _avisos = _blocos_com_origem(livro)
    saida: list[Mudanca] = []
    for page in documento.pages:
        for block in sorted(page.blocks, key=lambda b: b.order):
            if block.kind in TIPOS_FORA_DO_LIVRO or block.decision.status == "rejected":
                continue
            bloco = principais.get(block.id)
            if bloco is None:
                if block.id in fundidas:
                    saida.append(Mudanca(block.id, None, "fundido_apagado"))
                else:
                    saida.append(Mudanca(block.id, None, "apagado"))
                continue
            after = _valor_de(bloco, block)
            if after is None or after == block.decision.value:
                continue
            saida.append(Mudanca(block.id, after, "fundido" if bloco.origem and bloco.origem.fundidas else "editado"))
    return saida


def _tem_formato(bloco: Bloco) -> bool:
    if not isinstance(bloco, Paragrafo):
        return False
    return any(t.negrito or t.italico or t.sublinhado or t.tachado or t.versalete or t.posicao for t in bloco.trechos)


@dataclass
class RelatorioDaPonte:
    """O que `gravar_eventos` fez: os eventos, o que ficou de fora e os avisos (§10.7)."""

    diario: str = ""
    mudancas: list[Mudanca] = field(default_factory=list)
    editados: int = 0
    apagados: int = 0
    fundidos: int = 0
    novos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    documento: Any = None

    @property
    def eventos(self) -> int:
        return len(self.mudancas)

    def linhas(self) -> list[str]:
        """O resumo para o relatório de conversão e o log."""
        saida = [f"Ponte com o documento editorial: {self.eventos} evento(s) no diário "
                 f"({self.editados} editado(s), {self.apagados} apagado(s), {self.fundidos} fundido(s))"]
        if self.novos:
            saida.append(f"Blocos novos, sem origem no documento (não geram evento): {len(self.novos)}")
        saida.extend(self.avisos)
        return saida


def gravar_eventos(livro: Livro, documento: EditorialDocument, diario: str, *, user: str = "editor") \
        -> RelatorioDaPonte:
    """
    Grava no diário os eventos das mudanças do livro (DEC-10, AC-008) e devolve o relatório,
    com o documento projetado (`sessao.document`) em `documento`. O diário de **outro**
    documento no mesmo caminho é ignorado (não se aplica, não se apaga), com aviso.
    """
    from core.editorial_review import ReviewJournal, ReviewSession

    relatorio = RelatorioDaPonte(diario=diario or "")
    journal = ReviewJournal(diario) if diario else ReviewJournal()
    try:
        sessao = ReviewSession.from_journal(documento, journal, user=user)
    except (ValueError, KeyError) as erro:
        sessao = ReviewSession(documento, journal=journal, user=user)
        relatorio.avisos.append(f"o diário {diario} não é deste documento e foi ignorado ({erro})")
    principais, _fundidas, novos, avisos = _blocos_com_origem(livro)
    relatorio.avisos.extend(avisos)
    relatorio.novos = [b.id for b in novos]
    relatorio.mudancas = eventos_de(livro, sessao.document)
    com_formato = 0
    for mudanca in relatorio.mudancas:
        if mudanca.after is None:
            sessao.reject(mudanca.bloco_id)
            if mudanca.motivo == "fundido_apagado":
                relatorio.fundidos += 1
            else:
                relatorio.apagados += 1
        else:
            sessao.edit(mudanca.bloco_id, mudanca.after, reason_codes=("editor",))
            if mudanca.motivo == "fundido":
                relatorio.fundidos += 1
            else:
                relatorio.editados += 1
            if _tem_formato(principais[mudanca.bloco_id]):
                com_formato += 1
    if com_formato:
        relatorio.avisos.append(f"o formato (negrito, itálico…) de {com_formato} bloco(s) editado(s) não viaja "
                                f"para o documento editorial: a ponte transporta só o texto (DEC-10, §10.7)")
    relatorio.documento = sessao.document
    return relatorio


__all__ = ["de_documento", "de_paginas", "ler", "caminho_do_diario", "eventos_de", "gravar_eventos", "Mudanca",
           "RelatorioDaPonte", "PROCEDENCIA", "SUFIXO_DO_DIARIO"]
