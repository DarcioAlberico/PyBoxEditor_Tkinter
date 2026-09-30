"""
Arquivo → Abrir PDF… na janela do editor (ED-17; docs/ANALISE_JANELA_EDITOR.md §4.4).

`LeituraDePdf` pede o arquivo, mostra o `DialogoAbrirPdf`, dispara a `abrir_pdf.Tarefa`
(o OCR num processo à parte, DEC-07) e a acompanha pelo `after` — a janela nunca espera
o outro processo. No fim, o JSON editorial vira **livro novo** pela ponte da ED-11
(`conversoes.abrir_documento_editorial`), um capítulo por página ou por título, com as
marcas de página e a origem de cada bloco; o diário da revisão fica ao lado do JSON.

Pontos de injeção para o teste: `pedir_pedido(pdf)` (a caixa), `python` (o interpretador
do processo) e `mostrar_progresso` (a janelinha).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from core.editor import abrir_pdf as ap

INTERVALO_MS = 150
TIPOS_DE_PDF = (("PDF", "*.pdf"), ("Todos os arquivos", "*.*"))


class LeituraDePdf:
    def __init__(self, janela: Any):
        self.j = janela
        self.tarefa: ap.Tarefa | None = None
        self.pedido: ap.Pedido | None = None
        self.progresso: Any = None
        self.python: str | None = None
        self.mostrar_progresso = True
        self.pedir_pedido: Callable[[str], ap.Pedido | None] = self._dialogo
        self.ao_terminar: Callable[[Any], Any] | None = None     # o teste espera por aqui
        self._agendado: str | None = None
        self._fim: dict | None = None
        self._erro: dict | None = None
        self.ultimo_erro = ""
        self.comandos = {"abrir_pdf": self.abrir_pdf, "cancelar_pdf": self.cancelar}

    # -- pedir ------------------------------------------------------------------------

    def _preferencias(self) -> dict[str, Any]:
        prefs = self.j._preferencia("abrir_pdf", {})
        return dict(prefs) if isinstance(prefs, dict) else {}

    def _dialogo(self, pdf: str) -> ap.Pedido | None:
        from ui.editor.dialogo_pdf import DialogoAbrirPdf

        return DialogoAbrirPdf(self.j, pdf, self._preferencias()).mostrar()

    def abrir_pdf(self, caminho: str | None = None, pedido: ap.Pedido | None = None) -> ap.Pedido | None:
        """Arquivo → Abrir PDF…: escolhe o PDF e as páginas e dispara a leitura (devolve o pedido)."""
        j = self.j
        if self.tarefa is not None and not self.tarefa.terminou:
            raise ValueError("já há um PDF sendo lido (Arquivo → Cancelar leitura do PDF para parar)")
        if pedido is None:
            if caminho is None:
                prefs = self._preferencias()
                caminho = j.caixas.abrir(TIPOS_DE_PDF, prefs.get("pasta", ""), "Abrir PDF no editor")
                if not caminho:
                    return None
            caminho = os.path.abspath(os.fspath(caminho))
            if not os.path.isfile(caminho):
                raise ValueError(f"o arquivo não existe: {caminho}")
            pedido = self.pedir_pedido(caminho)
            if pedido is None:
                return None
        self._guardar(pedido)
        self.iniciar(pedido)
        return pedido

    def _guardar(self, pedido: ap.Pedido) -> None:
        prefs = self._preferencias()
        prefs.update(pasta=os.path.dirname(pedido.pdf), idioma=pedido.idioma, camada=pedido.camada,
                     dividir=pedido.dividir, reparar=pedido.reparar)
        self.j._gravar_preferencia("abrir_pdf", prefs)

    # -- ler ----------------------------------------------------------------------------

    def iniciar(self, pedido: ap.Pedido) -> ap.Tarefa:
        j = self.j
        self.pedido = pedido
        self.ultimo_erro = ""
        self._fim = self._erro = None
        argv = ap.comando(pedido, self.python)
        self.tarefa = ap.Tarefa(argv).iniciar()
        faixa = ap.texto_da_faixa(pedido.paginas)
        j.log.info("Lendo %s, páginas %s (%s, %s) → %s.", os.path.basename(pedido.pdf), faixa, pedido.camada,
                   pedido.idioma, pedido.saida)
        j.status(f"Lendo {os.path.basename(pedido.pdf)}, páginas {faixa}…")
        if self.mostrar_progresso:
            from ui.editor.dialogo_pdf import ProgressoDePdf

            self.progresso = ProgressoDePdf(j, f"Lendo {os.path.basename(pedido.pdf)}", self.cancelar)
        self._agendar()
        return self.tarefa

    def _agendar(self) -> None:
        try:
            self._agendado = self.j.after(INTERVALO_MS, self.acompanhar)
        except Exception:      # noqa: BLE001 — a janela fechou
            self._agendado = None

    def acompanhar(self) -> bool:
        """Lê os eventos que chegaram; `True` enquanto a tarefa corre (o `after` se reagenda)."""
        self._agendado = None
        tarefa = self.tarefa
        if tarefa is None:
            return False
        # O `fim` chega antes de o processo sair: ele fica guardado entre uma rodada e outra.
        for evento in tarefa.eventos():
            tipo = evento.get("evento")
            if tipo == "progresso":
                atual, total = int(evento.get("atual", 0)), int(evento.get("total", 0))
                if self.progresso is not None:
                    self.progresso.progresso(atual, total)
                self.j.status(f"Lendo o PDF: página {min(atual + 1, total)} de {total}…" if atual < total
                              else "Montando o livro…")
            elif tipo == "etapa":
                if self.progresso is not None:
                    self.progresso.texto(str(evento.get("texto", "")))
            elif tipo == "fim":
                self._fim = evento
            elif tipo == "erro":
                self._erro = evento
        if not tarefa.terminou:
            self._agendar()
            return True
        # Os eventos que chegaram entre a última leitura e o fim do processo.
        for evento in tarefa.eventos():
            if evento.get("evento") == "fim":
                self._fim = evento
            elif evento.get("evento") == "erro":
                self._erro = evento
        self._fechar_progresso()
        resultado = self._concluir(tarefa, self._fim, self._erro)
        if self.ao_terminar is not None:
            self.ao_terminar(resultado)
        return False

    def _concluir(self, tarefa: ap.Tarefa, fim: dict | None, erro: dict | None) -> Any:
        j = self.j
        self.tarefa = None
        if tarefa.cancelada:
            j.status("Leitura do PDF cancelada.")
            j.log.info("Leitura do PDF cancelada.")
            return None
        if fim is None or tarefa.codigo != 0:
            mensagem = (erro or {}).get("mensagem") or f"o processo de leitura saiu com o código {tarefa.codigo}"
            self.ultimo_erro = str(mensagem)
            j.log.error("A leitura do PDF falhou: %s\n%s", mensagem, tarefa.stderr()[-2000:])
            j.status("A leitura do PDF falhou (detalhes em Mensagens).")
            j.caixas.entrada(f"Não foi possível ler o PDF:\n\n{mensagem}", "Abrir PDF")
            return None
        arquivo = str(fim.get("arquivo") or (self.pedido.saida if self.pedido else ""))
        for aviso in fim.get("avisos") or ():
            j.log.warning("PDF: %s", aviso)
        from core.editorial_model import EditorialDocument

        documento = EditorialDocument.load_json(arquivo)
        dividir = self.pedido.dividir if self.pedido is not None else "pagina"
        projeto = j.conversoes.abrir_documento_editorial(documento, arquivo, dividir)
        if projeto is not None:
            j.status(f"PDF aberto como livro novo: {fim.get('paginas', '?')} página(s) de "
                     f"{os.path.basename(self.pedido.pdf) if self.pedido else ''} — Salvar como… grava o EPUB.")
        return projeto

    def cancelar(self) -> bool:
        """Arquivo → Cancelar leitura do PDF (e o botão da janelinha)."""
        if self.tarefa is None:
            self.j.status("Nenhum PDF sendo lido.")
            return False
        self.tarefa.cancelar()
        if self.progresso is not None:
            self.progresso.texto("Cancelando…")
        return True

    def _fechar_progresso(self) -> None:
        if self.progresso is not None:
            self.progresso.fechar()
            self.progresso = None

    def fechar(self) -> None:
        """A janela fechou: mata a leitura que estiver correndo."""
        if self._agendado is not None:
            try:
                self.j.after_cancel(self._agendado)
            except Exception:      # noqa: BLE001
                pass
            self._agendado = None
        if self.tarefa is not None:
            self.tarefa.cancelar()
            self.tarefa = None
        self._fechar_progresso()


__all__ = ["LeituraDePdf", "TIPOS_DE_PDF"]
