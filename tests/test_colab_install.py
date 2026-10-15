import json
from pathlib import Path
import runpy
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def test_installer_fallback_is_isolated(tmp_path, monkeypatch):
    (tmp_path / 'bot').mkdir()
    (tmp_path / 'bot' / '__main__.py').touch()
    (tmp_path / 'requirements.txt').touch()
    commands = []
    def run(args, **kwargs):
        commands.append((args, kwargs))
        # Simula un runtime sin ensurepip. Todas las etapas siguientes funcionan.
        return SimpleNamespace(returncode=1 if args[1:3] == ['-m', 'venv'] else 0, stdout='')
    monkeypatch.setattr('subprocess.run', run)
    ctx = runpy.run_path(str(ROOT / 'tools/colab_install.py'), init_globals={
        'PROJECT_DIR': str(tmp_path), 'BOT_TOKEN': '123:fake', 'OWNER_ID': '42',
        'MAX_DOWNLOAD_MB': 12,
    })
    assert any('virtualenv==20.36.1' in args and '--target' in args for args, _ in commands)
    assert any(args[1:3] == ['-m', 'virtualenv'] and kwargs['env']['PYTHONPATH']
               for args, kwargs in commands)
    assert not any(args[0] == 'apt-get' for args, _ in commands)
    assert ctx['BOT_ENV']['MAX_DOWNLOAD_MB'] == '12'
    assert ctx['BOT_ENV']['OWNER_ID'] == '42'
    assert ctx['BOT_TOKEN'] == ''


def test_notebook_uses_exact_installer_and_launcher():
    nb = json.loads((ROOT / 'ZMHK-Colab.ipynb').read_text())
    code = [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']
    assert (ROOT / 'tools/colab_install.py').read_text() in code
    assert (ROOT / 'tools/colab_run.py').read_text() in code
