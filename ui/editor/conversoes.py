"""
Importar, exportar e reorganizar em capítulos, na janela (ED-10; SPEC_EDITOR §7.3
"Importar ▸", "Exportar…", §9.5, §10.2, §10.6, §10.8).

## O que mora aqui

`Conversoes(janela)` registra os comandos da seção ED-10 do menu: **Exportar…** (a
caixa de formato da §7.3 — EPUB, HTML único, HTML em pasta e TXT saem daqui; DOCX,
PDF e PGN dizem a fase que os traz), **Importar ▸ HTML/XHTML…, TXT…, EPUB para dentro
do livro…** e **Juntar em capítulos por título…, Dividir em capítulos por título…,
Dividir nos marcadores**. Como o resto do menu Livro (ED-08), toda ação é por comando,
com o alvo no navegador (senão a aba ativa) e as caixas em `janela.caixas`.

## Importar: para dentro do livro, ou como livro

Com um livro aberto, "Importar" **anexa** (`livro_ops.anexar`): os capítulos e os
recursos do arquivo entram no fim do livro, com os nomes que colidem renomeados e os
links reescritos (AC-ED10-5). Sem livro aberto, o importado **vira o livro** — um
projeto sem caminho, que "Salvar" pergunta onde gravar. "Abrir…" (ED-02) passou a
aceitar `.html`/`.xhtml`/`.txt` pelo mesmo caminho (§10.6 "Abrir / importar").

## Exportar não muda o projeto — quase

O EPUB exportado é uma cópia (o projeto continua no seu arquivo); mas o HTML e o EPUB
embutem as fontes que o livro usa (`core/editor/fontes.py`) e desenham os PNG dos
diagramas, e esses recursos **ficam** no livro — são dele. Quando entra recurso novo, o
livro fica sujo e o navegador é refeito; é honesto: ele ganhou arquivos.

## DOCX, PDF e PGN (ED-12)

"Exportar…" passou a escrever DOCX (`docx_io`), PDF paginado (`pdf_io`, com `Livro.pagina`)
e PGN (`pgn_io`, o capítulo ativo); "Imprimir…" é o PDF numa pasta temporária aberto no
leitor do sistema; "Importar ▸ DOCX…" lê pelo `docx_io.ler`; "Formato de página…" edita
o `FormatoDePagina` do livro numa caixa de formulário; "Exportar PGN do capítulo…" é o
mesmo PGN sem a caixa de formato. As opções de conversão vêm das preferências
(`modo_diagrama`, `notas`) — a caixa de formato não pergunta duas vezes.

## O documento editorial (ED-11)

"Importar ▸ JSON editorial…" e "Abrir…" com um `.json` montam o livro do
`EditorialDocument` (`core/editor/importar_ir.py`) **como livro** — um documento é um
livro inteiro, com a `Origem` em cada bloco e a ponte ligada (`Projeto.documento_editorial`
e `diario`); a janela principal chega aqui por `abrir_documento_editorial(documento,
caminho)`, com o documento da sessão e o arquivo que ela exportou (um EPUB vira o
caminho do projeto: Salvar grava nele).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from core.editor import docx_io, epub, html_io, importar_ir, livro_ops, modelo, pdf_io, pgn_io, txt_io
from core.editor.conversao import OpcoesDeConversao
from core.editor.projeto import Projeto
from ui.editor.operacoes import _lancar_padrao

#: (formato, rótulo, fase que o entrega, extensão, tipos da caixa de arquivo)
FORMATOS: tuple[tuple[str, str, str, str, tuple[tuple[str, str], ...]], ...] = (
    ("epub", "EPUB", "ED-02", ".epub", (("Livro EPUB", "*.epub"),)),
    ("html", "HTML único", "ED-10", ".html", (("HTML", "*.html *.htm"),)),
    ("html-pasta", "HTML em pasta", "ED-10", "", ()),
    ("txt", "TXT", "ED-10", ".txt", (("Texto", "*.txt"),)),
    ("docx", "DOCX", "ED-12", ".docx", (("Word", "*.docx"),)),
    ("pdf", "PDF paginado", "ED-12", ".pdf", (("PDF", "*.pdf"),)),
    ("pgn", "PGN", "ED-12", ".pgn", (("PGN", "*.pgn"),)),
)
FASES_PRONTAS = ("ED-02", "ED-10", "ED-12")
TIPOS_DE_DOCX = (("Word", "*.docx"), ("Todos os arquivos", "*.*"))
TIPOS_DE_PGN = (("PGN", "*.pgn"), ("Todos os arquivos", "*.*"))
EXTENSOES_DE_DOCX = (".docx",)
SIM_NAO = ("sim", "não")
CABECALHOS = ("titulo", "capitulo", "nenhum")
TIPOS_DE_HTML = (("HTML/XHTML", "*.html *.htm *.xhtml"), ("Todos os arquivos", "*.*"))
TIPOS_DE_TXT = (("Texto", "*.txt"), ("Todos os arquivos", "*.*"))
TIPOS_DE_EPUB = (("Livro EPUB", "*.epub"), ("Todos os arquivos", "*.*"))
EXTENSOES_DE_HTML = (".html", ".htm", ".xhtml")
EXTENSOES_DE_TXT = (".txt",)
EXTENSOES_DE_JSON = (".json",)
TIPOS_DE_JSON = (("Documento editorial", "*.json"), ("Todos os arquivos", "*.*"))


class Conversoes:
    def __init__(self, janela: Any):
        self.j = janela
        c = self
        self.comandos: dict[str, Callable[..., Any]] = {
            "exportar": c.exportar, "importar_html": c.importar_html, "importar_txt": c.importar_txt,
            "importar_epub": c.importar_epub, "dividir_por_titulo": c.dividir_por_titulo,
            "dividir_nos_marcadores": c.dividir_nos_marcadores, "juntar_por_titulo": c.juntar_por_titulo,
            # ED-11
            "importar_json": c.importar_json, "abrir_documento_editorial": c.abrir_documento_editorial,
            # ED-12
            "importar_docx": c.importar_docx, "imprimir": c.imprimir, "exportar_pgn": c.exportar_pgn,
            "formato_de_pagina": c.formato_de_pagina,
        }
        #: Quem abre o arquivo no programa do sistema ("Imprimir…"); o teste troca.
        self.abrir_no_sistema: Callable[[str], Any] = _lancar_padrao

    # -- utilidades -----------------------------------------------------------

    def _diretorio(self, chave: str) -> str:
        return self.j._preferencia("diretorios", {}).get(chave, "")

    def _guardar_diretorio(self, chave: str, caminho: str) -> None:
        j = self.j
        j._gravar_preferencia("diretorios", {**j._preferencia("diretorios", {}), chave: os.path.dirname(caminho)})

    def _linhas_do_relatorio(self, relatorio: Any) -> list[str]:
        linhas = [f"Capítulos: {relatorio.capitulos}", f"Blocos: {relatorio.blocos}",
                  f"Diagramas: {relatorio.diagramas_png} em imagem, {relatorio.diagramas_fonte} em fonte",
                  f"Figuras: {relatorio.figuras} · Notas: {relatorio.notas} · Ilhas: {relatorio.ilhas}"]
        if relatorio.fontes_embutidas:
            linhas.append(f"Fontes embutidas: {', '.join(relatorio.fontes_embutidas)}")
        if relatorio.metadados.get("paginas"):
            linhas.append(f"Páginas: {relatorio.metadados['paginas']}")
        if relatorio.metadados.get("partidas") is not None:
            linhas.append(f"Partidas: {relatorio.metadados['partidas']}")
        linhas.append(f"Tempo: {relatorio.tempo_s:.1f} s")
        linhas.append(f"Tempo: {relatorio.tempo_s:.1f} s")
        if relatorio.avisos:
            linhas += ["", f"Avisos ({len(relatorio.avisos)}):"] + [f"  {a}" for a in relatorio.avisos[:20]]
            if len(relatorio.avisos) > 20:
                linhas.append(f"  … e mais {len(relatorio.avisos) - 20}")
        return linhas

    # -- exportar ---------------------------------------------------------------

    def _opcoes(self) -> OpcoesDeConversao:
        """As opções de conversão (§10.8) que valem para DOCX e PDF: das preferências do editor."""
        j = self.j
        return OpcoesDeConversao(modo_de_diagrama=j._preferencia("modo_diagrama", "png") or "png",
                                 notas=j._preferencia("notas", "rodape") or "rodape",
                                 fonte=j._preferencia("fonte_diagrama", modelo.FONTE_PADRAO) or modelo.FONTE_PADRAO,
                                 idioma=j.projeto.livro.metadados.idioma if j.projeto is not None else "")

    def exportar(self, formato: str | None = None, caminho: str | None = None) -> str | None:
        """
        A caixa de formato (§7.3): EPUB (uma cópia), HTML único, HTML em pasta, TXT, DOCX, PDF
        paginado e PGN (o capítulo ativo). Devolve o caminho escrito (o `index.html` da pasta).
        """
        j = self.j
        projeto = j._exigir_projeto()
        if formato is None:
            rotulos = [rotulo + (f"  (chega na {fase})" if fase not in FASES_PRONTAS else "")
                       for _f, rotulo, fase, _e, _t in FORMATOS]
            indice = j.caixas.escolher("Exportar", "Formato:", rotulos, "Exportar…")
            if indice is None:
                return None
            formato = FORMATOS[indice][0]
        entrada = next((f for f in FORMATOS if f[0] == formato), None)
        if entrada is None:
            raise ValueError(f"formato desconhecido: {formato!r}")
        _formato, rotulo, fase, extensao, tipos = entrada
        if fase not in FASES_PRONTAS:
            raise ValueError(f"exportar em {formato} chega na {fase}")
        if formato == "pgn":
            return self.exportar_pgn(caminho)
        if caminho is None:
            base = _nome_seguro(projeto.livro.metadados.titulo)
            if formato == "html-pasta":
                caminho = j.caixas.escolher_pasta("Exportar HTML em pasta", self._diretorio("exportar"))
            else:
                caminho = j.caixas.salvar_como(base + extensao, tipos + (("Todos os arquivos", "*.*"),),
                                               diretorio=self._diretorio("exportar"), extensao=extensao,
                                               titulo=f"Exportar {rotulo}")
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if extensao and not caminho.lower().endswith(extensao):
            caminho += extensao
        j._validar_abas_de_codigo()
        j._sincronizar_tudo()
        livro = projeto.livro
        recursos_antes = set(livro.recursos)
        zip_antes = livro.zip_de_origem
        j.status(f"Exportando {rotulo}…")
        j.configure(cursor="watch")
        try:
            if formato == "epub":
                relatorio = epub.escrever(livro, caminho, ncx=j._preferencia("ncx", None))
                escrito = caminho
            elif formato == "html":
                relatorio = html_io.escrever_unico(livro, caminho)
                escrito = caminho
            elif formato == "html-pasta":
                relatorio = html_io.escrever_pasta(livro, caminho)
                escrito = relatorio.arquivos[0] if relatorio.arquivos else caminho
            elif formato == "docx":
                relatorio = docx_io.escrever(livro, caminho, self._opcoes())
                escrito = caminho
            elif formato == "pdf":
                relatorio = pdf_io.escrever(livro, caminho, self._opcoes())
                escrito = caminho
            else:
                relatorio = txt_io.escrever(livro, caminho)
                escrito = caminho
        finally:
            livro.zip_de_origem = zip_antes
            j.configure(cursor="")
        self._guardar_diretorio("exportar", caminho)
        if set(livro.recursos) != recursos_antes:
            projeto.marcar_sujo()
            j.atualizar_navegador()
        for aviso in relatorio.avisos[:50]:
            j.log.warning("%s", aviso)
        j.log.info("Exportado %s: %s.", rotulo, escrito)
        j.status(f"Exportado {rotulo}: {os.path.basename(escrito)}")
        j.caixas.conclusao("Livro exportado", self._linhas_do_relatorio(relatorio), escrito)
        j.atualizar()
        return escrito

    # -- importar ---------------------------------------------------------------

    def _ler(self, caminho: str) -> tuple[Any, Any]:
        """`(livro, relatório)` do arquivo, pelo formato da extensão; `ValueError` para o que não se lê."""
        ext = os.path.splitext(caminho)[1].lower()
        if ext in EXTENSOES_DE_HTML:
            return html_io.ler(caminho)
        if ext in EXTENSOES_DE_TXT:
            return txt_io.ler(caminho, idioma=self.j._preferencia("idioma_ortografia", "") or "pt")
        if ext in EXTENSOES_DE_DOCX:
            return docx_io.ler(caminho)
        if ext == ".epub":
            try:
                return epub.ler(caminho)
            except epub.ErroDeEpub as erro:
                raise ValueError(str(erro)) from None
        raise ValueError(f"não sei importar {ext or 'um arquivo sem extensão'}: use HTML, XHTML, TXT, DOCX ou EPUB")

    def _importar(self, caminho: str | None, tipos: tuple, titulo: str, chave: str) -> Any:
        j = self.j
        if caminho is None:
            caminho = j.caixas.abrir(tipos, self._diretorio(chave), titulo)
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if not os.path.isfile(caminho):
            raise ValueError(f"o arquivo não existe: {caminho}")
        j.status(f"Importando {os.path.basename(caminho)}…")
        j.configure(cursor="watch")
        try:
            livro, relatorio = self._ler(caminho)
        finally:
            j.configure(cursor="")
        self._guardar_diretorio(chave, caminho)
        if j.projeto is None:
            return self.abrir_como_livro(caminho, livro, relatorio)
        j._sincronizar_tudo()
        projeto = j.projeto
        anexados = livro_ops.anexar(projeto.livro, livro)
        projeto.marcar_sujo()
        j.atualizar_navegador()
        j.atualizar_sumario()
        j._atualizar_painel_de_estilos()
        for aviso in relatorio.avisos[:50]:
            j.log.warning("%s", aviso)
        j.log.info("Importado para dentro do livro: %s (%d capítulo(s): %s).", caminho, len(anexados),
                   ", ".join(anexados[:5]) + ("…" if len(anexados) > 5 else ""))
        j.status(f"Importado: {os.path.basename(caminho)} ({len(anexados)} capítulo(s))")
        if anexados:
            j.abrir_capitulo(anexados[0])
        j.atualizar()
        return anexados

    def abrir_como_livro(self, caminho: str, livro: Any = None, relatorio: Any = None) -> Projeto | None:
        """Um HTML ou TXT aberto **como livro**: um projeto sem caminho (Salvar pergunta onde)."""
        j = self.j
        if livro is None:
            if not j._confirmar_descarte():
                return None
            j.status(f"Abrindo {os.path.basename(caminho)}…")
            j.configure(cursor="watch")
            try:
                livro, relatorio = self._ler(caminho)
            finally:
                j.configure(cursor="")
        projeto = Projeto(livro, None, relatorio, relogio=j.relogio)
        j._instalar_projeto(projeto)
        projeto.marcar_sujo()
        j.log.info("Aberto como livro: %s (%d capítulos). Salvar pergunta onde gravar o EPUB.", caminho,
                   len(livro.capitulos))
        j.status(f"Aberto como livro: {os.path.basename(caminho)}")
        j.atualizar()
        return projeto

    def importar_html(self, caminho: str | None = None) -> Any:
        return self._importar(caminho, TIPOS_DE_HTML, "Importar HTML/XHTML", "importar")

    def importar_txt(self, caminho: str | None = None) -> Any:
        return self._importar(caminho, TIPOS_DE_TXT, "Importar TXT", "importar")

    def importar_epub(self, caminho: str | None = None) -> Any:
        return self._importar(caminho, TIPOS_DE_EPUB, "EPUB para dentro do livro", "importar")

    def importar_docx(self, caminho: str | None = None) -> Any:
        return self._importar(caminho, TIPOS_DE_DOCX, "Importar DOCX", "importar")

    # -- ED-12: imprimir, PGN, formato de página ----------------------------------

    def imprimir(self, caminho: str | None = None) -> str:
        """Imprimir… (§2.2, §10.5): o PDF paginado numa pasta temporária, aberto no leitor do sistema."""
        import tempfile

        j = self.j
        projeto = j._exigir_projeto()
        if caminho is None:
            caminho = os.path.join(tempfile.mkdtemp(prefix="pbe-imprimir-"),
                                   _nome_seguro(projeto.livro.metadados.titulo) + ".pdf")
        j._validar_abas_de_codigo()
        j._sincronizar_tudo()
        j.status("Gerando o PDF…")
        j.configure(cursor="watch")
        try:
            relatorio = pdf_io.escrever(projeto.livro, caminho, self._opcoes())
        finally:
            j.configure(cursor="")
        for aviso in relatorio.avisos[:50]:
            j.log.warning("%s", aviso)
        j.log.info("PDF para impressão: %s (%d páginas).", caminho, relatorio.metadados.get("paginas", 0))
        j.status(f"PDF gerado: {os.path.basename(caminho)} ({relatorio.metadados.get('paginas', 0)} páginas)")
        self.abrir_no_sistema(caminho)
        return caminho

    def exportar_pgn(self, caminho: str | None = None) -> str | None:
        """Exportar PGN do capítulo… (§11.8): o capítulo ativo, uma partida por segmento."""
        j = self.j
        projeto = j._exigir_projeto()
        aba = j.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("abra o capítulo cujas partidas quer exportar")
        j._sincronizar_tudo()
        cap = projeto.livro.capitulo(aba.arquivo)
        if cap is None:
            raise ValueError(f"capítulo não encontrado: {aba.arquivo}")
        if caminho is None:
            base = _nome_seguro(os.path.splitext(os.path.basename(cap.arquivo))[0])
            caminho = j.caixas.salvar_como(base + ".pgn", TIPOS_DE_PGN, diretorio=self._diretorio("exportar"),
                                           extensao=".pgn", titulo="Exportar PGN do capítulo")
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if not caminho.lower().endswith(".pgn"):
            caminho += ".pgn"
        relatorio = pgn_io.escrever(cap, caminho, projeto.livro)
        self._guardar_diretorio("exportar", caminho)
        for aviso in relatorio.avisos[:50]:
            j.log.warning("%s", aviso)
        partidas = relatorio.metadados.get("partidas", 0)
        j.log.info("Exportado PGN: %s (%d partida(s)).", caminho, partidas)
        j.status(f"Exportado PGN: {os.path.basename(caminho)} ({partidas} partida(s))")
        j.caixas.conclusao("PGN exportado", self._linhas_do_relatorio(relatorio), caminho)
        return caminho

    def formato_de_pagina(self, valores: dict[str, Any] | None = None) -> modelo.FormatoDePagina | None:
        """Formato de página… (§5 `FormatoDePagina`): papel, margens, cabeçalhos, numeração e hifenização."""
        j = self.j
        projeto = j._exigir_projeto()
        atual = projeto.livro.pagina
        if valores is None:
            sup, ext, inf, intr = atual.margens_mm
            campos = [("largura_mm", "Largura (mm):", f"{atual.largura_mm:g}"),
                      ("altura_mm", "Altura (mm):", f"{atual.altura_mm:g}"),
                      ("superior", "Margem superior (mm):", f"{sup:g}"),
                      ("externa", "Margem externa (mm):", f"{ext:g}"),
                      ("inferior", "Margem inferior (mm):", f"{inf:g}"),
                      ("interna", "Margem interna (mm):", f"{intr:g}"),
                      ("espelhadas", "Margens espelhadas:", "sim" if atual.espelhadas else "não"),
                      ("cabecalho_par", "Cabeçalho das páginas pares:", atual.cabecalho_par or "nenhum"),
                      ("cabecalho_impar", "Cabeçalho das páginas ímpares:", atual.cabecalho_impar or "nenhum"),
                      ("numerar_paginas", "Numerar páginas:", "sim" if atual.numerar_paginas else "não"),
                      ("hifenizar", "Hifenizar:", "sim" if atual.hifenizar else "não")]
            valores = j.caixas.formulario("Formato de página", campos,
                                          {"espelhadas": SIM_NAO, "cabecalho_par": CABECALHOS,
                                           "cabecalho_impar": CABECALHOS, "numerar_paginas": SIM_NAO,
                                           "hifenizar": SIM_NAO})
            if valores is None:
                return None
        try:
            numeros = {chave: float(str(valores.get(chave, getattr(atual, chave, 0))).replace(",", "."))
                       for chave in ("largura_mm", "altura_mm")}
            margens = tuple(float(str(valores.get(chave, padrao)).replace(",", "."))
                            for chave, padrao in zip(("superior", "externa", "inferior", "interna"), atual.margens_mm))
        except ValueError as erro:
            raise ValueError(f"medida inválida no formato de página: {erro}") from None
        if numeros["largura_mm"] <= 0 or numeros["altura_mm"] <= 0 or any(m < 0 for m in margens):
            raise ValueError("as medidas da página têm de ser positivas")
        if margens[1] + margens[3] >= numeros["largura_mm"] or margens[0] + margens[2] >= numeros["altura_mm"]:
            raise ValueError("as margens não deixam lugar para o texto")

        def sim(chave: str, padrao: bool) -> bool:
            valor = valores.get(chave, padrao)
            return valor if isinstance(valor, bool) else str(valor).strip().lower() in ("sim", "s", "true", "1")

        def cabecalho(chave: str, padrao: str) -> str:
            valor = str(valores.get(chave, padrao) or "").strip().lower()
            return "" if valor in ("", "nenhum") else valor

        novo = modelo.FormatoDePagina(
            largura_mm=numeros["largura_mm"], altura_mm=numeros["altura_mm"], margens_mm=margens,
            espelhadas=sim("espelhadas", atual.espelhadas),
            cabecalho_par=cabecalho("cabecalho_par", atual.cabecalho_par),
            cabecalho_impar=cabecalho("cabecalho_impar", atual.cabecalho_impar),
            numerar_paginas=sim("numerar_paginas", atual.numerar_paginas),
            hifenizar=sim("hifenizar", atual.hifenizar))
        if novo != atual:
            projeto.livro.pagina = novo
            projeto.marcar_sujo()
            j.atualizar()
        j.status(f"Formato de página: {novo.largura_mm:g} × {novo.altura_mm:g} mm"
                 + (", margens espelhadas" if novo.espelhadas else ""))
        return novo

    # -- o documento editorial (ED-11) ------------------------------------------

    def importar_json(self, caminho: str | None = None, dividir: str | None = None) -> Projeto | None:
        """Importar ▸ JSON editorial…: o documento vira o livro, com a ponte ligada (§10.6.5, DEC-10)."""
        j = self.j
        if caminho is None:
            caminho = j.caixas.abrir(TIPOS_DE_JSON, self._diretorio("importar"), "Importar JSON editorial")
            if not caminho:
                return None
        caminho = os.path.abspath(os.fspath(caminho))
        if not os.path.isfile(caminho):
            raise ValueError(f"o arquivo não existe: {caminho}")
        from core.editorial_model import EditorialDocument

        try:
            documento = EditorialDocument.load_json(caminho)
        except (OSError, ValueError, KeyError, TypeError) as erro:
            raise ValueError(f"não é um documento editorial: {os.path.basename(caminho)} ({erro})") from None
        self._guardar_diretorio("importar", caminho)
        return self.abrir_documento_editorial(documento, caminho, dividir)

    def abrir_documento_editorial(self, documento: Any, caminho: str = "", dividir: str | None = None) \
            -> Projeto | None:
        """
        O `EditorialDocument` aberto como livro (§7.2, §10.6.5): `caminho` é o JSON de onde ele
        veio ou o arquivo que a sessão exportou — um EPUB vira o caminho do projeto (Salvar grava
        nele); qualquer outro deixa o projeto sem caminho. A ponte fica em `Projeto`.
        """
        j = self.j
        if not j._confirmar_descarte():
            return None
        dividir = dividir or j._preferencia("dividir_documento_editorial", "titulo") or "titulo"
        caminho = os.path.abspath(os.fspath(caminho)) if caminho else ""
        json_de_origem = caminho if caminho.lower().endswith(EXTENSOES_DE_JSON) else ""
        j.status("Montando o livro do documento editorial…")
        j.configure(cursor="watch")
        try:
            livro, relatorio = importar_ir.de_documento(documento, dividir=dividir, caminho=json_de_origem)
        finally:
            j.configure(cursor="")
        projeto = Projeto(livro, caminho if caminho.lower().endswith(".epub") else None, relatorio, relogio=j.relogio)
        projeto.documento_editorial = documento
        projeto.diario = importar_ir.caminho_do_diario(documento, caminho or json_de_origem)
        livro.origem.diario = projeto.diario
        j._instalar_projeto(projeto)
        if not projeto.caminho:
            projeto.marcar_sujo()
        suspeitos = sum(1 for cap in livro.capitulos for b in cap.blocos if b.extras.get("data-suspeito"))
        j.log.info("Documento editorial aberto como livro: %s (%d capítulos, %d páginas, %d bloco(s) suspeito(s); "
                   "diário: %s).", documento.document_id, len(livro.capitulos),
                   relatorio.metadados.get("paginas", 0), suspeitos, projeto.diario or "(nenhum)")
        j.status(f"Documento editorial aberto: {documento.title or documento.document_id}"
                 + (f" — {suspeitos} bloco(s) suspeito(s) (! na calha)" if suspeitos else ""))
        j.atualizar()
        return projeto

    # -- dividir e juntar -------------------------------------------------------

    def _capitulo_alvo(self) -> str:
        j = self.j
        href = j.operacoes.alvo(so_capitulo=True)
        j._sincronizar_tudo()
        return href

    def dividir_por_titulo(self, nivel: int | None = None) -> list[str]:
        """Dividir em capítulos por título…: o capítulo alvo, um por título de nível ≤ `nivel`."""
        j = self.j
        href = self._capitulo_alvo()
        if nivel is None:
            nivel = j.caixas.pedir_inteiro("Dividir em capítulos por título", "Nível de título (1–6):", 1, 1, 6)
            if nivel is None:
                return []
        partes = livro_ops.dividir_por_titulo(j.projeto.livro, href, int(nivel))
        if len(partes) == 1:
            j.status(f"{href}: não há título de nível {nivel} depois do começo — nada a dividir")
            return partes
        j.operacoes._depois(*partes)
        j.log.info("Dividido por título (nível %d): %s → %d capítulos.", nivel, href, len(partes))
        j.status(f"Dividido em {len(partes)} capítulos")
        return partes

    def dividir_nos_marcadores(self) -> list[str]:
        """Dividir nos marcadores: em cada `<hr class="divisao"/>` do capítulo alvo."""
        j = self.j
        href = self._capitulo_alvo()
        partes = livro_ops.dividir_nos_marcadores(j.projeto.livro, href)
        if len(partes) == 1:
            j.status(f"{href}: sem marcador de divisão (<hr class=\"divisao\"/>) — nada a dividir")
            return partes
        j.operacoes._depois(*partes)
        j.log.info("Dividido nos marcadores: %s → %d capítulos.", href, len(partes))
        j.status(f"Dividido em {len(partes)} capítulos")
        return partes

    def juntar_por_titulo(self, nivel: int | None = None, confirmar: bool = True) -> list[str]:
        """Juntar em capítulos por título…: o livro inteiro, das páginas do impresso aos capítulos."""
        j = self.j
        projeto = j._exigir_projeto()
        if nivel is None:
            nivel = j.caixas.pedir_inteiro("Juntar em capítulos por título", "Nível de título (1–6):", 1, 1, 6)
            if nivel is None:
                return []
        if confirmar and not j.caixas.pergunta(
                f"Reorganizar o livro inteiro em capítulos por título de nível {nivel}?\n"
                "(A fronteira de cada arquivo vira marca de página; nada é gravado até você salvar.)",
                cancelar=False):
            return []
        j._sincronizar_tudo()
        antes = [c.arquivo for c in projeto.livro.capitulos]
        cabecas = livro_ops.juntar_por_titulo(projeto.livro, int(nivel))
        j.abas.fechar_todas()
        j.operacoes._depois()
        j.log.info("Juntado por título (nível %d): %d arquivos → %d capítulos.", nivel, len(antes), len(cabecas))
        j.status(f"{len(antes)} arquivos → {len(cabecas)} capítulos")
        if cabecas:
            j.abrir_capitulo(cabecas[0])
        return cabecas


def _nome_seguro(titulo: str) -> str:
    seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in (titulo or "livro")).strip() or "livro"
    return seguro[:60]


__all__ = ["Conversoes", "FORMATOS", "FASES_PRONTAS", "EXTENSOES_DE_HTML", "EXTENSOES_DE_TXT"]
