# Pega TODO este archivo en una celda Python de tu propio notebook de Colab.
# Descarga primero el ZIP de la rama nueva: GitHub > Code > Download ZIP.
# No uses el ZIP de master ni publiques celdas que contengan tokens.

PROJECT_DIR = globals().get("PROJECT_DIR", "")          # Vacío: pide subir ZIP. O ruta al código YA extraído.
BOT_TOKEN = globals().get("BOT_TOKEN", "")            # Mejor vacío: lee Secretos de Colab o pide entrada oculta.
OWNER_ID = globals().get("OWNER_ID", "")             # Tu ID numérico; vacío: lee Secretos o pide entrada.
AUTHORIZED_USERS = globals().get("AUTHORIZED_USERS", "")     # Opcional: "123456,789012"
MAX_DOWNLOAD_MB = globals().get("MAX_DOWNLOAD_MB", 45)
TASK_TIMEOUT = globals().get("TASK_TIMEOUT", 1800)
RCLONE_DESTINATION = globals().get("RCLONE_DESTINATION", "")   # Opcional: "drive:Bot" (requiere configurar rclone).
RCLONE_CONFIG = globals().get("RCLONE_CONFIG", "")        # Opcional: ruta al rcl.conf ya subido al runtime.
INSTALL_RCLONE = globals().get("INSTALL_RCLONE", False)   # True solo si usarás /mirror y no está instalado.

import io
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from getpass import getpass

if sys.version_info < (3, 10):
    raise RuntimeError("Selecciona un runtime de Colab con Python 3.10 o posterior.")
if "BOT_PROCESS" in globals() and BOT_PROCESS.poll() is None:
    raise RuntimeError("Detén la instancia del bot antes de reinstalar.")

if PROJECT_DIR.strip():
    PROJECT = Path(PROJECT_DIR).expanduser().resolve()
else:
    from google.colab import files
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError("Sube únicamente el ZIP del código nuevo.")
    name, payload = next(iter(uploaded.items()))
    if not name.lower().endswith('.zip') or len(payload) > 25 * 1024 * 1024:
        raise ValueError("Se necesita un ZIP de código de menos de 25 MiB.")
    PROJECT = Path(tempfile.mkdtemp(prefix='zmhk-'))
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) > 200 or sum(e.file_size for e in entries) > 25 * 1024 * 1024:
            raise ValueError("ZIP demasiado grande.")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("ZIP con rutas no permitidas.")
        archive.extractall(PROJECT)
    del uploaded, payload
    # El ZIP de GitHub tiene una carpeta raíz; el paquete local no.
    if not (PROJECT / 'bot' / '__main__.py').is_file():
        folders = [p for p in PROJECT.iterdir() if p.is_dir()]
        if len(folders) == 1:
            PROJECT = folders[0]
if not (PROJECT / 'bot' / '__main__.py').is_file() or not (PROJECT / 'requirements.txt').is_file():
    raise ValueError("No es ZMHK 2. Descarga el ZIP de arena/44c5e389-zmhk-deploy, no el de master.")


def checked(args, stage, **kwargs):
    print(stage, flush=True)
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, **kwargs)
    if result.returncode:
        print(result.stdout[-12000:])
        raise RuntimeError(f"Falló: {stage}. Copia el error anterior SIN credenciales para revisarlo.")
    return result


VENV = PROJECT / '.venv-colab'
PYTHON = str(VENV / 'bin' / 'python')
result = subprocess.run([sys.executable, '-m', 'venv', str(VENV)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if result.returncode:
    # Algunos runtimes no incluyen ensurepip/python3-venv. No modifica el Python de Colab.
    bootstrap = Path(tempfile.mkdtemp(prefix='zmhk-bootstrap-'))
    checked([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
             '--target', str(bootstrap), 'virtualenv==20.36.1'], 'Instalando alternativa a venv...')
    bootstrap_env = os.environ.copy()
    bootstrap_env['PYTHONPATH'] = str(bootstrap)
    checked([sys.executable, '-m', 'virtualenv', '--python', sys.executable, str(VENV)],
            'Creando entorno aislado con virtualenv...', env=bootstrap_env)
checked([PYTHON, '-m', 'pip', 'install', '--upgrade', 'pip'], 'Preparando pip...')
checked([PYTHON, '-m', 'pip', 'install', '-r', str(PROJECT / 'requirements.txt')],
        'Instalando dependencias del bot...')
checked([PYTHON, '-m', 'pip', 'check'], 'Comprobando dependencias...')
checked([PYTHON, '-c', 'import telegram, dotenv, httpx, yt_dlp'], 'Comprobando imports...')

# El bot arranca sin apt, ffmpeg ni rclone. rclone solo es necesario para /mirror.
if INSTALL_RCLONE and not shutil.which('rclone'):
    checked(['apt-get', 'update', '-qq'], 'Actualizando índice de apt...')
    checked(['apt-get', 'install', '-y', '--no-install-recommends', 'rclone'], 'Instalando rclone...')


def get_secret(name, value):
    if str(value).strip():
        return str(value).strip()
    try:
        from google.colab import userdata
        try:
            value = userdata.get(name)
        except (userdata.SecretNotFoundError, userdata.NotebookAccessError):
            value = ''
    except ImportError:
        value = ''
    return str(value).strip() if value else getpass(f'{name}: ').strip()


BOT_ENV = os.environ.copy()
BOT_ENV.update({
    'BOT_TOKEN': get_secret('BOT_TOKEN', BOT_TOKEN),
    'OWNER_ID': get_secret('OWNER_ID', OWNER_ID),
    'AUTHORIZED_USERS': str(AUTHORIZED_USERS),
    'DOWNLOAD_DIR': str(PROJECT / 'downloads'),
    'MAX_DOWNLOAD_MB': str(MAX_DOWNLOAD_MB),
    'TASK_TIMEOUT': str(TASK_TIMEOUT),
    'RCLONE_DESTINATION': RCLONE_DESTINATION.strip(),
})
BOT_ENV.pop('RCLONE_CONFIG', None)
if RCLONE_CONFIG.strip():
    config_path = Path(RCLONE_CONFIG).expanduser().resolve()
    if not config_path.is_file():
        raise ValueError('RCLONE_CONFIG no existe. Sube el archivo o deja la variable vacía.')
    config_path.chmod(0o600)
    BOT_ENV['RCLONE_CONFIG'] = str(config_path)
# La validación no imprime el token ni el entorno.
checked([PYTHON, '-c', 'from bot.config import Settings; Settings.from_env()'],
        'Validando configuración...', cwd=PROJECT, env=BOT_ENV)
BOT_TOKEN = ''
print('Listo. Instalado y configurado; el bot aún no está en ejecución.')
