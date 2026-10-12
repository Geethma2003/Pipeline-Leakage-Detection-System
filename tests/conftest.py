import sys
import os
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
backend_dir = os.path.join(root_dir, "backend")

if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
