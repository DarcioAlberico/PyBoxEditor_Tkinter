import tkinter as tk
from ui.main_window import MainWindow


import traceback
from tkinter import messagebox

#: Tamanho desejado da janela. Não é imposto: ver `_geometria_que_cabe`.
LARGURA_DESEJADA, ALTURA_DESEJADA = 1600, 900

#: Abaixo disto a barra de navegação começa a perder botão. Medida: as peças
#: essenciais (anterior, próxima, "ir para") exigem ~330 px, e o resto da
#: janela — canvas, barra lateral, editor — não cabe com folga em menos que
#: isto. Com o mínimo, o Windows impede o usuário de encolher até sumir controle.
LARGURA_MINIMA, ALTURA_MINIMA = 1024, 640


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


def main():
    try:
        root = tk.Tk()
        root.title("PyBoxEditor (Tkinter Modular)")
        root.geometry(_geometria_que_cabe(root))
        root.minsize(min(LARGURA_MINIMA, root.winfo_screenwidth()),
                     min(ALTURA_MINIMA, root.winfo_screenheight()))

        app = MainWindow(root)
        app.pack(fill="both", expand=True)

        root.mainloop()
    except Exception as e:
        err_msg = traceback.format_exc()
        with open("crash_log.txt", "w") as f:
            f.write(err_msg)
        # Senta que lá vem a história... se o root não foi criado, messagebox precisa de um
        try:
            messagebox.showerror("Erro Fatal", f"Ocorreu um erro:\n{e}\n\nVerifique crash_log.txt")
        except:
            # Fallback se o tk não estiver inicializado
            print(err_msg)



if __name__ == "__main__":
    main()
