import tkinter as tk
from ui.main_window import MainWindow


import traceback
from tkinter import messagebox

def main():
    try:
        root = tk.Tk()
        root.title("PyBoxEditor (Tkinter Modular)")
        root.geometry("1600x900")

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
