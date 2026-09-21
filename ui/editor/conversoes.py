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
"""

from __future__ import annotations

import os
from typing import Any, Callable

from core.editor import epub, html_io, livro_ops, txt_io
from core.editor.projeto import Projeto

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
FASES_PRONTAS = ("ED-02", "ED-10")
TIPOS_DE_HTML = (("HTML/XHTML", "*.html *.htm *.xhtml"), ("Todos os arquivos", "*.*"))
TIPOS_DE_TXT = (("Texto", "*.txt"), ("Todos os arquivos", "*.*"))
TIPOS_DE_EPUB = (("Livro EPUB", "*.epub"), ("Todos os arquivos", "*.*"))
EXTENSOES_DE_HTML = (".html", ".htm", ".xhtml")
EXTENSOES_DE_TXT = (".txt",)


class Conversoes:
    def __init__(self, janela: Any):
        self.j = janela
        c = self
        self.comandos: dict[str, Callable[..., Any]] = {
            "exportar": c.exportar, "importar_html": c.importar_html, "importar_txt": c.importar_txt,
            "importar_epub": c.importar_epub, "dividir_por_titulo": c.dividir_por_titulo,
            "dividir_nos_marcadores": c.dividir_nos_marcadores, "juntar_por_titulo": c.juntar_por_titulo,
        }

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
        linhas.append(f"Tempo: {relatorio.tempo_s:.1f} s")
        if relatorio.avisos:
            linhas += ["", f"Avisos ({len(relatorio.avisos)}):"] + [f"  {a}" for a in relatorio.avisos[:20]]
            if len(relatorio.avisos) > 20:
                linhas.append(f"  … e mais {len(relatorio.avisos) - 20}")
        return linhas

    # -- exportar ---------------------------------------------------------------

    def exportar(self, formato: str | None = None, caminho: str | None = None) -> str | None:
        """
        A caixa de formato (§7.3): EPUB (uma cópia), HTML único, HTML em pasta e TXT; o
        que ainda não existe diz a fase. Devolve o caminho escrito (o `index.html` da pasta).
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
        if ext == ".epub":
            try:
                return epub.ler(caminho)
            except epub.ErroDeEpub as erro:
                raise ValueError(str(erro)) from None
        raise ValueError(f"não sei importar {ext or 'um arquivo sem extensão'}: use HTML, XHTML, TXT ou EPUB")

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
