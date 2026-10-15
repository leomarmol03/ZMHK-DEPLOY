"""Paquete de distribución mediante lista permitida, nunca incluye credenciales."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'bot/__init__.py', 'bot/__main__.py', 'bot/config.py', 'bot/downloads.py',
    'requirements.txt', 'config.env.example', 'README.md', 'LICENSE', 'start.sh',
    'ZMHK-Colab.ipynb', 'tools/colab_install.py', 'tools/colab_run.py',
)


def build(output=None):
    output = Path(output) if output else ROOT / 'artifacts' / 'ZMHK-Colab.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    return output


if __name__ == '__main__':
    print(build())
