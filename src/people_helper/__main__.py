"""Entry point for `python -m people_helper`.

Equivalent to running `python people_helper.py` from a clone, but works
after `pip install` (where there's no `people_helper.py` script on disk).
"""

import os
import sys

# When running as `python -m people_helper` from a clone (not installed),
# we need the src/ dir on the path. This is a no-op when installed.
_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..", "..")
if os.path.isdir(_src):
    sys.path.insert(0, _src)

# Import the CLI main function from the top-level script's logic.
# We inline the main() here rather than importing from people_helper.py
# (which lives at the repo root and isn't part of the installed package).
from people_helper.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
