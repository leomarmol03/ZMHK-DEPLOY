import ast
import json
from pathlib import Path
from zipfile import ZipFile

from tools.package_colab import build, FILES

ROOT = Path(__file__).resolve().parents[1]


def test_notebook_clean_and_syntactically_valid():
    notebook = json.loads((ROOT / 'ZMHK-Colab.ipynb').read_text())
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            assert cell['outputs'] == []
            assert cell['execution_count'] is None
            ast.parse(''.join(cell['source']))


def test_distribution_is_allowlisted(tmp_path):
    output = build(tmp_path / 'test.zip')
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == set(FILES)
        assert 'bot/__main__.py' in archive.namelist()
        assert not set(archive.namelist()) & {'config.env', 'rcl.conf', '.netrc', 'cookies.txt'}
