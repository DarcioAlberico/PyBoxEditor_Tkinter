import sys
import traceback

try:
    import appy
    print("Successfully imported appy")
    appy.main()
except Exception:
    with open("error_log.txt", "w") as f:
        traceback.print_exc(file=f)
    traceback.print_exc()
    print("\nError captured in error_log.txt")
