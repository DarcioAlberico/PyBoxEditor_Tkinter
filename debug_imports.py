import sys
print("Testing imports...")
try:
    import numpy
    print(f"numpy: {numpy.__version__}")
except ImportError as e:
    print(f"numpy failed: {e}")

try:
    import cv2
    print(f"cv2: {cv2.__version__}")
except ImportError as e:
    print(f"cv2 failed: {e}")

try:
    from PIL import Image
    print(f"PIL: {Image.__version__}")
except ImportError as e:
    print(f"PIL failed: {e}")

try:
    import pytesseract
    print(f"pytesseract: {pytesseract.get_tesseract_version()}")
except Exception as e:
    print(f"pytesseract failed: {e}")
