# Ejecutar después de colab_install.py dentro del mismo kernel de Colab.
import os
import signal
import subprocess

if 'BOT_ENV' not in globals() or 'PYTHON' not in globals() or 'PROJECT' not in globals():
    raise RuntimeError('Ejecuta primero la celda de instalación/configuración.')
if 'BOT_PROCESS' in globals() and BOT_PROCESS.poll() is None:
    raise RuntimeError('Ya hay una instancia activa. Deténla antes de iniciar otra.')
BOT_PROCESS = subprocess.Popen([PYTHON, '-m', 'bot'], cwd=PROJECT,
                               env=BOT_ENV, start_new_session=True)
try:
    code = BOT_PROCESS.wait()
    if code:
        print('El bot terminó con error. Revisa credenciales, red y otras instancias.')
except KeyboardInterrupt:
    print('Deteniendo el bot...')
    if BOT_PROCESS.poll() is None:
        try:
            os.killpg(BOT_PROCESS.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            BOT_PROCESS.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(BOT_PROCESS.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            BOT_PROCESS.wait()
    print('Bot detenido.')
