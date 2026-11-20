#!/usr/bin/python3 -I
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from luomax.cli import main

if __name__ == "__main__":
    sys.exit(main())
