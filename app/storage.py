import os
from pathlib import Path


def photo_path(stored_path):
    return Path(os.getenv('DATA_DIR', 'data')) / stored_path
