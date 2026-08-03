import tkinter as tk
import sys

try:
    print("Creating root...")
    root = tk.Tk()
    print("Root created.")
    
    label = tk.Label(root, text="Hello Tkinter")
    label.pack()
    
    print("Scheduling destroy...")
    root.after(1000, root.destroy)
    
    print("Mainloop...")
    root.mainloop()
    print("Mainloop finished.")
except Exception as e:
    print(f"Tkinter error: {e}")
    sys.exit(1)
