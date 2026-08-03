import tkinter as tk
from unittest.mock import MagicMock
import sys
import os
from PIL import Image
import numpy as np

# Create dummy image
img = Image.new('RGB', (100, 100), color = 'white')
img.save('test_image.png')

# Mock filedialog
import tkinter.filedialog
tkinter.filedialog.askopenfilename = MagicMock(return_value=os.path.abspath('test_image.png'))

try:
    from ui.main_window import MainWindow
    
    print("Initializing root...")
    root = tk.Tk()
    app = MainWindow(root)
    app.pack()

    print("Simulating Open Image...")
    app.open_image(os.path.abspath('test_image.png'))
    
    print("Simulating Generate Boxes (OpenCV)...")
    app.generate_boxes_opencv()
    
    print("Simulating OCR...")
    app.auto_fill_characters()
    
    print("Simulation completed successfully.")
    root.destroy()
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Simulation failed: {e}")
    sys.exit(1)
