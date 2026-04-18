import os
import sys


CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
APP_DIR = os.path.join(PROJECT_ROOT, "hiremind")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app  # noqa: E402
