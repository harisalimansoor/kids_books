"""GHOST image face-swap, added inside MyInteliBooks.

Not connected to workbook generation yet.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
