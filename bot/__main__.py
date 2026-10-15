"""Entrada independiente: python -m bot (polling, sin puertos públicos)."""

import asyncio
from functools import wraps
import logging
from pathlib import Path
import tempfile

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import Settings
from .downloads import TransferError, download_http, download_video, mirror_file, safe_name

LOG = logging.getLogger('zmhk')
TELEGRAM_UPLOAD_LIMIT = 49_000_000  # Margen bajo los 50 MB del Bot API público.
HELP = '''ZMHK 2 · Descargas privadas
/leech URL — descargar un enlace directo y enviarlo aquí
/ytdl URL — descargar un video y enviarlo aquí
/mirror URL — descargar un enlace directo y copiarlo a rclone
También puedes responder a un documento, video o audio con /leech o /mirror.
/status — consultar la tarea
/cancel — cancelar tu tarea y limpiar archivos
/help — mostrar esta ayuda
Una tarea a la vez. Telegram: envío hasta 49 MB y descarga hasta 20 MB.
Solo usa contenido que tengas permiso para descargar. Torrents no incluidos.'''


def restricted(callback):
    @wraps(callback)
    async def wrapped(update, context):
        settings = context.application.bot_data['settings']
        if not update.effective_user or update.effective_user.id not in settings.authorized_users:
            return
        if update.effective_message:
            return await callback(update, context)
    return wrapped


@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP)


@restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.application.bot_data
    task = state.get('task')
    await update.effective_message.reply_text('Hay una transferencia en curso.' if task and not task.done() else 'Sin tareas activas.')


@restricted
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.application.bot_data
    task = state.get('task')
    user = update.effective_user.id
    settings = state['settings']
    if task and not task.done() and user in (state.get('task_owner'), settings.owner_id):
        task.cancel()
        await update.effective_message.reply_text('Cancelación solicitada.')
    else:
        await update.effective_message.reply_text('No tienes una tarea activa para cancelar.')


async def transfer(update, context, mode, url, media):
    settings = context.application.bot_data['settings']
    message = update.effective_message
    # The entire task, including upload, has a time limit.
    async def execute():
        with tempfile.TemporaryDirectory(prefix='job-', dir=settings.download_dir) as tmp:
            directory = Path(tmp)
            limit = settings.max_bytes if mode == 'mirror' else min(settings.max_bytes, TELEGRAM_UPLOAD_LIMIT)
            if media:
                if not media.file_size or media.file_size > min(limit, 20_000_000):
                    raise TransferError('El Bot API público solo permite descargar archivos de Telegram hasta 20 MB.')
                file = directory / safe_name(getattr(media, 'file_name', None) or 'telegram.bin')
                await (await media.get_file()).download_to_drive(file)
            elif mode == 'ytdl':
                file = await download_video(url, directory, limit)
            else:
                file = await download_http(url, directory, limit)
            if not 0 < file.stat().st_size <= limit:
                raise TransferError('Archivo vacío o superior al límite permitido.')
            if mode == 'mirror':
                await mirror_file(file, settings.rclone_destination)
                await message.reply_text('Archivo copiado al destino de rclone.')
            else:
                with file.open('rb') as document:
                    await message.reply_document(document=document, filename=file.name,
                                                 read_timeout=180, write_timeout=180)
    try:
        await asyncio.wait_for(execute(), timeout=settings.timeout)
    except asyncio.CancelledError:
        await message.reply_text('Tarea cancelada; archivos temporales eliminados.')
        raise
    except asyncio.TimeoutError:
        await message.reply_text('Tiempo máximo agotado; archivos temporales eliminados.')
    except TransferError as error:
        await message.reply_text(str(error))
    except Exception as error:
        # Never log raw exceptions: Telegram URLs contain the bot token.
        LOG.warning('Transferencia fallida (%s).', type(error).__name__)
        await message.reply_text('No se pudo completar la transferencia. Revisa el enlace, la conexión y los permisos.')


@restricted
async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.application.bot_data
    message = update.effective_message
    mode = message.text.split()[0].split('@')[0].lstrip('/')
    active = state.get('task')
    if active and not active.done():
        await message.reply_text('Hay una tarea en curso. Usa /status o /cancel.')
        return
    if mode == 'mirror' and not state['settings'].rclone_destination:
        await message.reply_text('Primero configura RCLONE_DESTINATION y rclone.')
        return
    reply = message.reply_to_message
    media = (reply.document or reply.video or reply.audio) if reply and mode != 'ytdl' else None
    if not media and len(context.args) != 1:
        await message.reply_text(f'Uso: /{mode} URL' + (' o responde a un archivo.' if mode != 'ytdl' else ''))
        return
    await message.reply_text('Transferencia iniciada. Usa /cancel para detenerla.')
    state['task_owner'] = update.effective_user.id
    state['task'] = asyncio.create_task(
        transfer(update, context, mode, context.args[0] if context.args else '', media))
    state['task'].add_done_callback(task_finished)


def task_finished(task):
    if not task.cancelled() and task.exception() is not None:
        LOG.warning('No se pudo notificar el resultado (%s).', type(task.exception()).__name__)


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand('leech', 'Descargar enlace directo a Telegram'),
        BotCommand('ytdl', 'Descargar video a Telegram'),
        BotCommand('mirror', 'Copiar enlace directo a rclone'),
        BotCommand('status', 'Estado de tarea'), BotCommand('cancel', 'Cancelar tarea'),
        BotCommand('help', 'Ayuda'),
    ])


async def post_stop(application):
    task = application.bot_data.get('task')
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def error_handler(update, context):
    LOG.warning('Error de Telegram (%s). Comprueba la conexión y que no haya otra instancia.', type(context.error).__name__)


def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    # httpx INFO logs include Telegram request URLs and therefore credentials.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    try:
        settings = Settings.from_env()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    application = (Application.builder().token(settings.token).concurrent_updates(False)
                   .post_init(post_init).post_stop(post_stop).build())
    application.bot_data['settings'] = settings
    for command in ('start', 'help'):
        application.add_handler(CommandHandler(command, help_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CommandHandler(['leech', 'ytdl', 'mirror'], transfer_command))
    application.add_error_handler(error_handler)
    print('ZMHK iniciado. Detén con Ctrl+C. No ejecutes otra instancia con el mismo token.', flush=True)
    try:
        application.run_polling(drop_pending_updates=True, allowed_updates=['message'], bootstrap_retries=0)
    except Exception as error:
        raise SystemExit(f'No se pudo iniciar el bot ({type(error).__name__}). Comprueba token, red y otras instancias.') from None


if __name__ == '__main__':
    main()
