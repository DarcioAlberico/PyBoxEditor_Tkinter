"""A barra de menus por etapa do trabalho, com mnemônicos (2026-09-18).

Antes eram 40 comandos num "Ferramentas" só, sem Editar, sem Ajuda, com o
número de fase do roadmap no rótulo e "(OCR)" querendo dizer Tesseract. Os
testes fixam o que a reorganização prometeu: cada menu tem mnemônico, o modo
de reconhecimento recomendado é o primeiro, nenhum rótulo cita fase, nenhum
rótulo tem mojibake, e todo comando que existia continua existindo em algum
menu.
"""

import re
import sys
from tkinter import messagebox

import pytest
from PIL import Image

from conftest import raiz_tk


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (400, 100), color=255)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _entradas(menu):
    fim = menu.index("end")
    return [] if fim is None else list(range(fim + 1))


def _comandos(menu):
    """`[(rótulo, comando?)]` do menu e dos submenus, na ordem."""
    saida = []
    for j in _entradas(menu):
        tipo = menu.type(j)
        if tipo == "command":
            saida.append(menu.entrycget(j, "label"))
        elif tipo == "cascade":
            saida.extend(_comandos(menu.nametowidget(menu.entrycget(j, "menu"))))
    return saida


def _cascatas(barra):
    return {barra.entrycget(i, "label"): barra.nametowidget(barra.entrycget(i, "menu"))
            for i in _entradas(barra) if barra.type(i) == "cascade"}


def test_os_menus_seguem_o_fluxo_e_tem_mnemonico():
    with _App() as app:
        barra = app.win.parent.nametowidget(app.win.parent.cget("menu"))
        rotulos = [barra.entrycget(i, "label") for i in _entradas(barra)
                   if barra.type(i) == "cascade"]
        assert rotulos == ["Arquivo", "Editar", "Reconhecer", "Revisar", "Modelo",
                           "PDF", "Notação", "Ferramentas", "Ajuda"]
        mnemonicos = [barra.entrycget(i, "underline") for i in _entradas(barra)
                      if barra.type(i) == "cascade"]
        assert all(int(u) >= 0 for u in mnemonicos), mnemonicos
        letras = [r[int(u)].lower() for r, u in zip(rotulos, mnemonicos)]
        assert len(set(letras)) == len(letras), f"mnemônico repetido: {letras}"


def test_o_modo_recomendado_e_o_primeiro_do_reconhecer():
    with _App() as app:
        barra = app.win.parent.nametowidget(app.win.parent.cget("menu"))
        reconhecer = _cascatas(barra)["Reconhecer"]
        primeiro = reconhecer.entrycget(0, "label")
        assert "Neural" in primeiro and "recomendado" in primeiro
        assert "Tesseract (por caractere)" in _comandos(reconhecer)


def test_nenhum_rotulo_cita_fase_nem_tem_mojibake():
    with _App() as app:
        barra = app.win.parent.nametowidget(app.win.parent.cget("menu"))
        todos = []
        for nome, menu in _cascatas(barra).items():
            todos.append(nome)
            todos.extend(_comandos(menu))
        for rotulo in todos:
            assert not re.search(r"\(Fase \d", rotulo), rotulo
            assert not re.search("Ã[§£©¡³ªº]", rotulo), rotulo


def test_todo_comando_de_antes_continua_em_algum_menu():
    """Os handlers do "Ferramentas" de antes, um a um, ainda estão ligados."""
    with _App() as app:
        w = app.win
        barra = w.parent.nametowidget(w.parent.cget("menu"))
        rotulos = set()
        for menu in _cascatas(barra).values():
            rotulos.update(_comandos(menu))
        esperados = [
            "Gerar boxes (OpenCV)", "Janela de rotulagem de linhas...",
            "Tesseract (por caractere)", "EasyOCR (por caractere)",
            "PaddleOCR (por caractere)", "EasyOCR (por linha)",
            "Modelo treinado por linha (CRNN)",
            "Detectar e reconhecer (Neural — recomendado)",
            "Detectar e reconhecer (Híbrido: k-NN + EasyOCR)",
            "Detectar e reconhecer (EasyOCR por linha)",
            "Detectar e reconhecer (EasyOCR por caractere)",
            "Aprender com a página atual (coletar)", "Verificar base de treino...",
            "Corrigir base de treino...", "Treinar rede neural de glifos",
            "Treinar OCR de linhas (linhas + engines)", "Validar dataset de linhas...",
            "Abrir relatório do OCR de linhas", "Avaliar modelo de linhas...",
            "Revisar dataset de linhas...", "Relatório do último treino...",
            "Validar notação de xadrez...", "Partidas em PGN...",
            "Ler posição dos diagramas...", "Treinar modelo de diagramas...",
            "Treinamento geral neural (lote)", "Importar imagens de caracteres",
            "Aplicar a todos os semelhantes...", "Dividir box selecionado",
            "Excluir box selecionado",
            "Substituir glifos de xadrez em PDF (texto)...",
            "Gerar PDF pesquisável (OCR)...",
            "Substituir glifos em PDF escaneado (neural)...",
            "Corrigir mapeamento de caracteres do PDF...",
            "Livro (EPUB/DOCX, pelo nosso OCR)...",
            "Documento editorial (JSON/HTML/TXT/PDF/EPUB/DOCX)...",
            "Revisar documento editorial...", "Preparar dataset de correções...",
            "Criar recortes para revisão...", "Promover recortes revistos para a base...",
            "Desfazer", "Refazer", "Atalhos de teclado...",
        ]
        faltam = [r for r in esperados if r not in rotulos]
        assert not faltam, faltam


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
