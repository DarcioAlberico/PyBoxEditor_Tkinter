import argparse
import os
import sys
import time
import tkinter as tk


import traceback
from datetime import datetime, timezone
from tkinter import messagebox

from config.paths import crash_log_path, ensure_data_dir

#: Tamanho desejado da janela. Não é imposto: ver `_geometria_que_cabe`.
LARGURA_DESEJADA, ALTURA_DESEJADA = 1600, 900

#: Abaixo disto a barra de navegação começa a perder botão. Medida: as peças
#: essenciais (anterior, próxima, "ir para") exigem ~330 px, e o resto da
#: janela — canvas, barra lateral, editor — não cabe com folga em menos que
#: isto. Com o mínimo, o Windows impede o usuário de encolher até sumir controle.
LARGURA_MINIMA, ALTURA_MINIMA = 1024, 640

#: A mesma exceção de callback repetida dentro deste prazo vai só para o log.
SILENCIO_APOS_REPETICAO_S = 3.0


def _declarar_dpi():
    """
    Diz ao Windows que o processo sabe lidar com DPI — **antes** de `tk.Tk()`.

    Sem isto o processo é "DPI unaware" (medido: `GetProcessDpiAwareness` = 0
    no interpretador do projeto), e num monitor a 125–150% o Windows estica a
    janela inteira como bitmap: o scan no canvas, que é o objeto da revisão,
    chega borrado, e a fonte de figurinas perde o traço fino. Com a declaração
    o Tk desenha no DPI real e o `tk scaling` (abaixo) mantém as fontes em
    pontos com o tamanho de sempre.

    Só no Windows, e só se a chamada existir — em outro sistema, ou num Windows
    anterior ao 8.1, não há nada a declarar.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE; cai para o system-aware se a
        # versão não tiver o per-monitor.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _ajustar_escala(root):
    """As fontes em pontos continuam do tamanho de sempre no DPI real."""
    try:
        dpi = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass


def _geometria_que_cabe(root):
    """
    Uma janela que **cabe na tela**, centralizada.

    `geometry("1600x900")` fixo era um defeito de verdade: numa tela de 1366 px
    (ou em 1600 px com escalonamento de 125%, que é o padrão de fábrica em muito
    notebook), a janela nascia mais larga que o monitor e o lado direito ficava
    fora da tela — inalcançável, sem barra de rolagem que o trouxesse de volta.
    O sintoma relatado foi "o botão de próxima página não aparece".
    """
    disponivel_l = root.winfo_screenwidth() - 80
    disponivel_a = root.winfo_screenheight() - 120
    largura = max(400, min(LARGURA_DESEJADA, disponivel_l))
    altura = max(300, min(ALTURA_DESEJADA, disponivel_a))
    x = max(0, (root.winfo_screenwidth() - largura) // 2)
    y = max(0, (root.winfo_screenheight() - altura) // 3)
    return f"{largura}x{altura}+{x}+{y}"


def _gravar_no_log(texto: str) -> str:
    """Anexa `texto` ao log de falhas no diretório de dados e devolve o caminho."""
    caminho_log = ensure_data_dir() / crash_log_path().name
    with open(caminho_log, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now(timezone.utc).isoformat(timespec='seconds')} ===\n")
        f.write(texto)
    return str(caminho_log)


def _instalar_relator_de_callbacks(root):
    """
    Uma exceção num callback do Tk vai para o log **e** para uma caixa.

    O `try/except` em volta do `mainloop` só vê o que sai do laço; a exceção
    dentro de um handler de botão o Tk imprime em `stderr` e segue — e o app
    aberto por atalho (`pythonw`) não tem `stderr`: o erro sumia sem deixar
    rastro nem para o usuário nem para quem fosse diagnosticar depois.

    **A caixa não se repete.** Um handler de movimento (`<B1-Motion>`) que
    falha, falha a cada pixel até o botão ser solto; com uma caixa modal por
    ocorrência, seriam dezenas empilhadas. A mesma exceção dentro de
    `SILENCIO_APOS_REPETICAO_S` só vai para o log.
    """
    ultima = {"chave": None, "quando": 0.0}

    def relatar(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            caminho = _gravar_no_log(texto)
        except OSError:
            caminho = "(não foi possível gravar o log)"
        print(texto, file=sys.stderr)
        chave = (tipo.__name__, str(valor))
        agora = time.monotonic()
        if chave == ultima["chave"] and agora - ultima["quando"] < SILENCIO_APOS_REPETICAO_S:
            ultima["quando"] = agora
            return
        ultima.update(chave=chave, quando=agora)
        try:
            messagebox.showerror(
                "Erro inesperado",
                f"{tipo.__name__}: {valor}\n\n"
                f"O detalhe completo foi gravado em:\n{caminho}")
        except tk.TclError:
            pass
    root.report_callback_exception = relatar


def _argumentos(argv=None):
    """
    `appy.py` abre a janela principal; `appy.py --editor [livro.epub]` abre só o editor
    de livros (SPEC_EDITOR §7.2), sem `MainWindow` nem modelo neural — é por isso que
    o `from ui.main_window import MainWindow` mora dentro de `main()`, e não no topo.
    """
    parser = argparse.ArgumentParser(prog="appy.py", description="PyBoxEditor")
    parser.add_argument("--editor", nargs="?", const="", default=None, metavar="ARQUIVO",
                        help="abre só o editor de livros, com o EPUB dado (opcional)")
    parser.add_argument("--fechar-apos", type=float, default=None, metavar="N",
                        help="fecha sozinho depois de N segundos (para conferência automática)")
    parser.add_argument("--diagnostico-modulos", action="store_true",
                        help="imprime os módulos pesados que estão carregados (deve ser nenhum no editor)")
    return parser.parse_args(argv)


MODULOS_PESADOS = ("torch", "easyocr", "cv2", "numpy", "fitz", "PIL", "docx", "ui.main_window")


def _diagnostico_de_modulos():
    carregados = sorted(m for m in MODULOS_PESADOS if m in sys.modules)
    print("modulos pesados carregados:", carregados or "nenhum", flush=True)
    return carregados


def editor(arquivo="", fechar_apos=None, diagnostico=False):
    """
    Só o editor de livros (ED-02): a raiz fica escondida e a `JanelaDoEditor` é a
    janela; fechar o editor encerra o processo. `fechar_apos` descarta sem perguntar
    — é o caminho da conferência por subprocesso (AC-ED02-7).
    """
    _declarar_dpi()
    from ui.editor.janela import JanelaDoEditor

    root = tk.Tk()
    _ajustar_escala(root)
    _instalar_relator_de_callbacks(root)
    root.withdraw()
    # `PYBOXEDITOR_SETTINGS` aponta outro settings.json (o teste por subprocesso usa um temporário).
    settings = None
    if os.environ.get("PYBOXEDITOR_SETTINGS"):
        from config.settings import Settings

        settings = Settings(os.environ["PYBOXEDITOR_SETTINGS"])
    janela = JanelaDoEditor(root, ao_fechar=root.destroy, settings=settings)
    if "layout" not in (janela.settings.get("editor") or {}):
        janela.geometry(_geometria_que_cabe(root))
    janela.minsize(min(LARGURA_MINIMA, root.winfo_screenwidth()), min(ALTURA_MINIMA, root.winfo_screenheight()))
    if arquivo:
        janela.executar("abrir", arquivo)
    if diagnostico:
        _diagnostico_de_modulos()
    if fechar_apos is not None:
        def fechar():
            janela.caixas.pergunta = lambda *a, **k: False
            janela.fechar()
        root.after(int(max(0.0, fechar_apos) * 1000), fechar)
    root.mainloop()


def main(argv=None):
    argumentos = _argumentos(argv)
    if argumentos.editor is not None:
        editor(argumentos.editor, argumentos.fechar_apos, argumentos.diagnostico_modulos)
        return
    from ui.main_window import MainWindow

    _declarar_dpi()
    try:
        root = tk.Tk()
        _ajustar_escala(root)
        _instalar_relator_de_callbacks(root)
        root.title("PyBoxEditor")
        root.geometry(_geometria_que_cabe(root))
        root.minsize(min(LARGURA_MINIMA, root.winfo_screenwidth()),
                     min(ALTURA_MINIMA, root.winfo_screenheight()))

        app = MainWindow(root)
        app.pack(fill="both", expand=True)

        root.mainloop()
    except Exception as e:
        err_msg = traceback.format_exc()
        try:
            caminho_log = _gravar_no_log(err_msg)
        except OSError:
            caminho_log = "(não foi possível gravar o log)"
        # Senta que lá vem a história... se o root não foi criado, messagebox precisa de um
        try:
            messagebox.showerror(
                "Erro Fatal", f"Ocorreu um erro:\n{e}\n\nVerifique {caminho_log}"
            )
        except Exception:
            # Fallback se o tk não estiver inicializado
            print(err_msg)


if __name__ == "__main__":
    main()
