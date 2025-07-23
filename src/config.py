import os
import tempfile

TEMP_DIR = tempfile.gettempdir()
TEMP_NOVEL = os.path.join(TEMP_DIR, 'novels')
TEMP_GENERATED = os.path.join(TEMP_DIR, 'generated')

os.makedirs(TEMP_NOVEL, exist_ok=True)
os.makedirs(TEMP_GENERATED, exist_ok=True)