"""Day 2 -- the tests.

Kept dependency-free like the rest of Sthenos: every test is a function
taking no arguments and asserting, which pytest collects on sight and
tests/__main__.py can run without pytest installed. No fixtures, no
plugins, no conftest -- a test that needs a working directory makes one.

These pin the parts a demo run cannot: the deny regexes (a small edit
stops one matching and nothing visibly breaks), the schema derived from
each signature, and the failure strings tools return instead of raising.
"""

import logging
import os
import sys

# Tests import Sthenos, and the runner may be invoked from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Blocking a command logs a warning by design, and the deny-list tests
# trip every pattern several times over. With no handler configured
# Python's fallback prints each one, burying the results the run is for.
logging.getLogger("Sthenos").setLevel(logging.CRITICAL)
