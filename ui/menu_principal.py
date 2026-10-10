"""
A barra de menus da janela principal, numa tabela declarativa (PD-22).

Até aqui `MainWindow._build_menu` montava os dez menus à mão — 199 linhas de
`add_command` —, e quem quisesse saber o que a janela oferece, ou conferir que todo
comando continua em algum menu (`tests/test_menu_por_fluxo.py`), tinha de percorrê-las.
Aqui a barra é uma tabela: cada `Menu` tem o rótulo, o mnemônico e os itens; cada
`Item` tem o rótulo, o **nome do método da janela** que executa — resolvido na hora
do clique, para quem troca o método num teste continuar sendo ouvido —, o acelerador,
o mnemônico e, quando há, os argumentos fixos ou o submenu. É o padrão de
`ui/editor/menus.py`, sem as fases e os modos que só o editor tem.

**A ordem é a do fluxo do trabalho, e não a da origem do código** (2026-09-18). Até
então eram 40 comandos num único "Ferramentas": nove modos de reconhecimento
misturados com treino, PDF, exportação e revisão, sem Editar, sem Exibir, sem Ajuda,
e com número de fase do roadmap no rótulo. Agora: abrir e exportar em Arquivo;
desfazer e o modo de digitação em Editar; **Reconhecer** com o modo recomendado
primeiro — "Neural" é a cadeia medida (rede própria → k-NN → EasyOCR), e "(OCR)" era
o Tesseract sem que ninguém soubesse; os "Preencher" agem sobre os boxes que já estão
na tela, e quem moveu ou dividiu box à mão não pode usar "Detectar", que os regenera;
**Revisar** para as filas e os recortes; **Modelo** para tudo que treina; **PDF** para
o que mexe no arquivo sem OCR; Ferramentas fica com o que age sobre os boxes da tela.
Cada menu tem um mnemônico (`underline`): Alt+A abre Arquivo, Alt+R Reconhecer, e
assim por diante — o teclado chega a tudo, que é a regra do resto da janela.

**Exibir** tem os atalhos em Ctrl, e não nas teclas soltas `+ − 0 F` que a revisão de
2026-09-18 listou: no modo digitação toda tecla imprimível vai para o box (o `<Key>`
da raiz), e `+`, `-` e `0` são caracteres da notação — pela mesma razão o Dividir
virou Ctrl+D e o Enquadrar é F4. Ctrl+0 ajusta e Ctrl+1 é 100%, como no Acrobat.

O menu Notação continua montado em código, da tabela de NAGs (`core/nags.py`), e o
menu de contexto da lista também; os dois moram aqui, com a lista de atalhos que o
menu Ajuda mostra.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Any, Sequence

from core import nags
from core.nags import NAGS_POR_FAMILIA
from ui.dialogo_rotulagem import DialogoRotulagem


@dataclass(frozen=True)
class Item:
    rotulo: str
    #: O nome do método da janela que executa, ou um caminho nela (`canvas.aproximar`).
    comando: str = ""
    acelerador: str = ""
    #: O índice da letra sublinhada; `None` é sem mnemônico.
    mnemonico: int | None = None
    #: Argumentos fixos da chamada (`proximo_pendente(1)`).
    args: tuple = ()
    #: O submenu, quando o item é uma cascata.
    filhos: tuple["Item", ...] = ()
    separador: bool = False


SEP = Item("", separador=True)


def _item(rotulo: str, comando: str, acelerador: str = "", mnemonico: int | None = None,
          *args: Any) -> Item:
    return Item(rotulo, comando, acelerador, mnemonico, tuple(args))


@dataclass(frozen=True)
class Menu:
    rotulo: str
    mnemonico: int
    itens: tuple[Item, ...] = ()
    #: `"notacao"`: o menu montado em código, da tabela de NAGs.
    dinamico: str = ""


ARQUIVO = (
    _item("Abrir...", "abrir_documento", "Ctrl+O", 0),
    _item("Abrir imagem...", "open_image"),
    _item("Abrir PDF...", "open_pdf"),
    _item("Salvar .box (página atual)", "save_box_file", "Ctrl+S", 0),
    _item("Salvar todas as páginas...", "save_all_pages", "Ctrl+Shift+S"),
    _item("Carregar .box", "load_box_file"),
    SEP,
    _item("Gravar rascunho agora", "salvar_rascunho_agora", "Ctrl+B"),
    SEP,
    Item("Exportar", mnemonico=0, filhos=(
        _item("Livro (EPUB/DOCX, pelo nosso OCR)...", "exportar_livro_action", "", 0),
        _item("Documento editorial (JSON/HTML/TXT/PDF/EPUB/DOCX)...",
              "processar_documento_editorial_action", "", 0),
        _item("Partidas em PGN...", "exportar_pgn", "", 0),
        _item("PDF pesquisável (OCR)...", "gerar_pdf_pesquisavel_action", "", 4),
    )),
    SEP,
    _item("Editor de livro...", "abrir_editor_de_livro", "", 0),
    SEP,
    _item("Sair", "_on_close", "", 1),
)

EDITAR = (
    _item("Desfazer", "_perform_undo", "Ctrl+Z", 0),
    _item("Refazer", "_perform_redo", "Ctrl+Y", 0),
    SEP,
    _item("Modo digitação", "alternar_modo_digitacao", "F2", 5),
    _item("Próximo box pendente", "proximo_pendente", "F3", 0, 1),
    _item("Box pendente anterior", "proximo_pendente", "Shift+F3", None, -1),
)

EXIBIR = (
    _item("Ajustar à janela", "canvas.ajustar_a_janela", "Ctrl+0", 0),
    _item("Tamanho real (100%)", "canvas.tamanho_real", "Ctrl+1", 0),
    _item("Aumentar o zoom", "canvas.aproximar", "Ctrl+=", 0, 1),
    _item("Diminuir o zoom", "canvas.aproximar", "Ctrl+-", 0, -1),
    SEP,
    _item("Enquadrar box selecionado", "_on_key_zoom", "F4", 0, None),
)

RECONHECER = (
    _item("Detectar e reconhecer (Neural — recomendado)", "generate_and_fill_neural", "", 0),
    _item("Detectar e reconhecer (Híbrido: k-NN + EasyOCR)", "generate_and_fill_combined"),
    _item("Detectar e reconhecer (EasyOCR por linha)", "generate_and_fill_linha"),
    _item("Detectar e reconhecer (EasyOCR por caractere)", "generate_and_fill_easyocr"),
    SEP,
    Item("Preencher os boxes existentes", mnemonico=0, filhos=(
        _item("Tesseract (por caractere)", "auto_fill_characters", "", 0),
        _item("EasyOCR (por caractere)", "auto_fill_characters_easyocr", "", 0),
        _item("EasyOCR (por linha)", "auto_fill_characters_linha", "", 9),
        _item("PaddleOCR (por caractere)", "auto_fill_characters_paddleocr", "", 0),
        _item("Modelo treinado por linha (CRNN)", "auto_fill_characters_linha_treinada", "", 0),
    )),
    SEP,
    _item("Ler posição dos diagramas...", "extrair_diagramas", "", 0),
    _item("Validar notação de xadrez...", "validar_notacao", "", 0),
)

REVISAR = (
    _item("Revisar documento editorial...", "revisar_documento_editorial_action", "", 0),
    _item("Preparar dataset de correções...", "preparar_dataset_correcoes_action", "", 0),
    SEP,
    _item("Janela de rotulagem de linhas...", "abrir_janela_rotulagem", "", 0),
    _item("Revisar dataset de linhas...", "abrir_revisao_dataset_linhas"),
    SEP,
    _item("Criar recortes para revisão...", "criar_recortes_action", "", 0),
    _item("Promover recortes revistos para a base...", "promover_revisao_action"),
)

MODELO = (
    _item("Aprender com a página atual (coletar)", "learn_from_current_page", "", 0),
    _item("Verificar base de treino...", "verificar_base_treino", "", 0),
    _item("Corrigir base de treino...", "corrigir_base_treino", "", 0),
    _item("Treinar rede neural de glifos", "train_neural_network", "", 0),
    _item("Treinamento geral neural (lote)", "run_general_neural_training"),
    _item("Importar imagens de caracteres", "import_character_images"),
    SEP,
    _item("Treinar OCR de linhas (linhas + engines)", "train_line_ocr"),
    _item("Validar dataset de linhas...", "validar_dataset_linhas"),
    _item("Avaliar modelo de linhas...", "avaliar_modelo_linhas"),
    _item("Abrir relatório do OCR de linhas", "abrir_relatorio_ocr_linhas"),
    _item("Relatório do último treino...", "abrir_relatorio_treino"),
    SEP,
    _item("Treinar modelo de diagramas...", "treinar_modelo_diagramas"),
)

PDF = (
    _item("Substituir glifos de xadrez em PDF (texto)...", "substitute_chess_glyphs_action", "", 0),
    _item("Substituir glifos em PDF escaneado (neural)...", "substitute_glyphs_neural_action"),
    _item("Corrigir mapeamento de caracteres do PDF...", "corrigir_mapeamento_action", "", 0),
    _item("Gerar PDF pesquisável (OCR)...", "gerar_pdf_pesquisavel_action", "", 0),
)

FERRAMENTAS = (
    _item("Gerar boxes (OpenCV)", "generate_boxes_opencv", "", 0),
    SEP,
    _item("Aplicar a todos os semelhantes...", "aplicar_aos_semelhantes", "Ctrl+E", 0),
    _item("Dividir box selecionado", "split_selected_box", "Ctrl+D", 0),
    _item("Excluir box selecionado", "delete_selected_box", "Del", 0),
)

AJUDA = (
    _item("Atalhos de teclado...", "mostrar_atalhos", "", 0),
    _item("Sobre o PyBoxEditor...", "mostrar_sobre", "", 0),
)

#: A barra, na ordem do fluxo. O mnemônico de cada menu é único (o teste confere).
BARRA = (
    Menu("Arquivo", 0, ARQUIVO),
    Menu("Editar", 0, EDITAR),
    Menu("Exibir", 1, EXIBIR),
    Menu("Reconhecer", 0, RECONHECER),
    Menu("Revisar", 2, REVISAR),
    Menu("Modelo", 0, MODELO),
    Menu("PDF", 0, PDF),
    Menu("Notação", 0, dinamico="notacao"),
    Menu("Ferramentas", 0, FERRAMENTAS),
    Menu("Ajuda", 2, AJUDA),
)

#: O que a tela responde ao teclado, para o menu Ajuda. Uma lista só, para o atalho
#: que não está no menu — F2, F3, Tab, a roda do mouse — ter onde ser descoberto.
ATALHOS = (
    ("Ctrl+O", "Abrir documento"),
    ("Ctrl+S / Ctrl+Shift+S", "Salvar o .box da página / de todas as páginas"),
    ("Ctrl+B", "Gravar o rascunho agora"),
    ("Ctrl+Z / Ctrl+Y", "Desfazer / refazer"),
    ("Ctrl+F", "Buscar caractere na lista"),
    ("Ctrl+G", "Ir para a página"),
    ("Ctrl+E", "Aplicar o caractere a todos os semelhantes"),
    ("Ctrl+D", "Dividir o box selecionado"),
    ("Del / Backspace", "Excluir o box selecionado (fora de um campo de texto)"),
    ("Tab / Shift+Tab", "Próximo / anterior box, com o foco no campo do caractere"),
    ("↑ / ↓", "Box anterior / seguinte na lista"),
    ("Enter (no campo)", "Aplicar o caractere e avançar"),
    ("F2", "Ligar/desligar o modo de digitação"),
    ("Esc", "Sair do modo de digitação"),
    ("F3 / Shift+F3", "Próximo / anterior box pendente"),
    ("F4", "Enquadrar o box selecionado"),
    ("Ctrl+0 / Ctrl+1", "Ajustar a página à janela / tamanho real (100%)"),
    ("Ctrl+= / Ctrl+-", "Aumentar / diminuir o zoom"),
    ("PgUp / PgDn", "Página anterior / seguinte"),
    ("Roda do mouse", "Rola a página; Shift+roda para o lado; Ctrl+roda dá zoom no cursor"),
    ("Botão direito / duplo clique", "Arrasta a página / enquadra o box"),
    ("Na revisão editorial: A / R / D / S", "Aceitar / rejeitar / adiar / aceitar semelhantes"),
    ("Na revisão editorial: N ou espaço / G", "Próximo item / abrir o diagrama"),
    ("Na revisão editorial: Ctrl+Enter / Ctrl+Z", "Salvar o valor editado / desfazer um passo"),
)


def todos_os_itens(itens: Sequence[Item] | None = None) -> list[Item]:
    """Os itens de comando da barra, com os dos submenus, na ordem — para quem confere."""
    if itens is None:
        itens = tuple(item for menu in BARRA for item in menu.itens)
    saida: list[Item] = []
    for item in itens:
        if item.separador:
            continue
        if item.filhos:
            saida.extend(todos_os_itens(item.filhos))
        else:
            saida.append(item)
    return saida


def _resolver(janela: Any, caminho: str) -> Any:
    """O método da janela que o item executa — `canvas.aproximar` desce pelos atributos."""
    alvo = janela
    for parte in caminho.split("."):
        alvo = getattr(alvo, parte)
    return alvo


class MenuPrincipal:
    """A barra, o menu Notação, o menu de contexto e os diálogos do Ajuda; `janela` é a `MainWindow`."""

    def __init__(self, janela):
        self.janela = janela

    def montar(self) -> tk.Menu:
        """Monta a barra da tabela `BARRA` e a liga à raiz da janela."""
        barra = tk.Menu(self.janela.parent)
        self.janela.parent.config(menu=barra)
        for menu in BARRA:
            if menu.dinamico == "notacao":
                self._menu_notacao(barra)
                continue
            m = tk.Menu(barra, tearoff=0)
            self._preencher(m, menu.itens)
            barra.add_cascade(label=menu.rotulo, menu=m, underline=menu.mnemonico)
        return barra

    def _preencher(self, menu: tk.Menu, itens: Sequence[Item]) -> None:
        for item in itens:
            if item.separador:
                menu.add_separator()
            elif item.filhos:
                sub = tk.Menu(menu, tearoff=0)
                self._preencher(sub, item.filhos)
                menu.add_cascade(label=item.rotulo, menu=sub, underline=item.mnemonico)
            else:
                opcoes: dict[str, Any] = {"label": item.rotulo, "command": self._comando(item)}
                if item.acelerador:
                    opcoes["accelerator"] = item.acelerador
                if item.mnemonico is not None:
                    opcoes["underline"] = item.mnemonico
                menu.add_command(**opcoes)

    def _comando(self, item: Item):
        # Resolvido na hora do clique, e não na montagem: quem troca o método da
        # janela num teste (`win.open_pdf = …`) continua sendo ouvido pelo menu.
        return lambda: _resolver(self.janela, item.comando)(*item.args)

    def _menu_notacao(self, menubar: tk.Menu) -> None:
        """
        O menu **Notação**: a tabela completa de NAGs do padrão PGN.

        A barra rápida tem os 23 símbolos do "Key to symbols used" destes livros,
        que é o que se digita o dia inteiro. Este menu tem os 169 do padrão, que é
        outra coisa: serve para o símbolo que aparece uma vez em duzentas páginas e
        para saber que `$26` existe e chama-se "vantagem de espaço".

        **Em submenus por família, e não em coluna única.** Cento e sessenta e nove
        itens a ~20 px pedem 3.400 px de altura; o Tk não avisa que não cabe — ele
        quebra o menu em colunas lado a lado, e a lista deixa de ter ordem visível.
        Vinte e duas famílias cabem numa coluna de 440 px.

        **O item só fica clicável se houver o que escrever no box.** Duas razões
        para não haver, e o rótulo diz qual: `—` no lugar do símbolo é NAG que o
        padrão definiu sem forma impressa (`$24`, "leve vantagem de espaço" — 121
        dos 169 são assim); "(sem fonte)" é símbolo que existe mas que nenhuma
        fonte do disco desenha, medido em `nags.sem_glifo()`. Deixar o segundo caso
        clicável escreveria no box um caractere que vira retângulo vazio no PDF sem
        erro nenhum no caminho — o defeito do `·` da SPEC §4.2.
        """
        m_nag = tk.Menu(menubar, tearoff=0)

        # Uma medição só para as 169 entradas (17 ms), em vez de uma por item.
        ausentes = nags.sem_glifo()

        for titulo, familia in nags.FAMILIAS:
            sub = tk.Menu(m_nag, tearoff=0)
            for nag in familia:
                if nags.desenhavel(nag, ausentes):
                    sub.add_command(label=nags.rotulo(nag),
                                    command=lambda s=nag.simbolo: self.janela.apply_nag(s))
                else:
                    sufixo = "   (sem fonte)" if nag.simbolo else ""
                    sub.add_command(label=nags.rotulo(nag) + sufixo,
                                    state="disabled")
            m_nag.add_cascade(label=titulo, menu=sub)

        menubar.add_cascade(label="Notação", menu=m_nag, underline=0)

    def _build_context_menu(self) -> None:
        """O menu de contexto da lista de boxes: aplicar aos semelhantes e os NAGs por família."""
        janela = self.janela
        janela.context_menu = tk.Menu(janela, tearoff=0)
        janela.context_menu.add_command(label="Aplicar a todos os semelhantes...",
                                        accelerator="Ctrl+E",
                                        command=janela.aplicar_aos_semelhantes)
        janela.context_menu.add_separator()
        for k, (_, familia) in enumerate(NAGS_POR_FAMILIA):
            if k:
                janela.context_menu.add_separator()
            for nag_char, desc in familia:
                janela.context_menu.add_command(
                    label=f"{nag_char} ({desc})",
                    command=lambda c=nag_char: janela.apply_nag(c)
                )

        janela.listbox.bind("<Button-3>", janela.show_context_menu)

    def show_context_menu(self, event) -> None:
        janela = self.janela
        if not janela.boxes:
            return

        if event.widget == janela.listbox:
            idx = janela.listbox.nearest(event.y)
            if idx >= 0:
                janela.listbox.selection_clear(0, tk.END)
                janela.listbox.selection_set(idx)
                janela.select_box(idx)

        janela.context_menu.tk_popup(event.x_root, event.y_root)

    def mostrar_atalhos(self) -> None:
        """A lista de atalhos, num diálogo que dá para copiar."""
        from tkinter import scrolledtext
        janela = tk.Toplevel(self.janela.parent)
        janela.title("Atalhos de teclado")
        janela.transient(self.janela.parent)
        texto = scrolledtext.ScrolledText(janela, width=72, height=min(24, len(ATALHOS) + 2),
                                          font=("Consolas", 10), wrap="none")
        largura = max(len(tecla) for tecla, _ in ATALHOS)
        texto.insert("1.0", "\n".join(f"{tecla:<{largura}}  {descricao}"
                                       for tecla, descricao in ATALHOS))
        texto.config(state="disabled")
        texto.pack(fill="both", expand=True, padx=8, pady=8)
        tk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=(0, 8))
        janela.bind("<Escape>", lambda e: janela.destroy())

    def mostrar_sobre(self) -> None:
        messagebox.showinfo(
            "Sobre o PyBoxEditor",
            "PyBoxEditor — editor de boxes e pipeline de OCR para livros e "
            "diagramas de xadrez.\n\n"
            "Leitura de livro: rede própria de glifos + Tesseract, fundidos "
            "palavra a palavra (o lance fica com a rede, a prosa com o "
            "Tesseract). Diagramas: detecção do tabuleiro, duas redes por casa "
            "e filtro de legalidade.\n\n"
            "Ferramentas → Ajuda → Atalhos de teclado lista tudo que a tela "
            "responde ao teclado.")

    def abrir_janela_rotulagem(self) -> None:
        """Abre a revisão focada de glifos para a página atual."""
        if self.janela._busy("A rotulagem"):
            return
        if self.janela.image is None:
            messagebox.showinfo("Rotulagem", "Abra uma imagem ou PDF primeiro.")
            return
        DialogoRotulagem(self.janela)
