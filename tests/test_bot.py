import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bot.config import Settings
from bot.downloads import TransferError, download_http, mirror_file, safe_name, validate_url
from bot.__main__ import restricted, transfer, transfer_command, cancel_command, post_stop


@pytest.fixture
def settings(tmp_path):
    with patch.dict(os.environ, {'BOT_TOKEN': '123:fake', 'OWNER_ID': '42'}, clear=True), patch('bot.config.load_dotenv'):
        result = Settings.from_env()
    return Settings(result.token, result.owner_id, result.authorized_users, tmp_path, 1024, 10)


def test_settings_secure_defaults(settings):
    assert settings.authorized_users == {42}
    assert 'fake' not in repr(settings)


@pytest.mark.parametrize('env', [
    {'BOT_TOKEN': ''}, {'OWNER_ID': '0'}, {'OWNER_ID': 'abc'},
    {'AUTHORIZED_USERS': '-3'}, {'MAX_DOWNLOAD_MB': '0'},
    {'TASK_TIMEOUT': '0'}, {'RCLONE_DESTINATION': '/tmp/test'},
])
def test_bad_settings(env):
    with patch.dict(os.environ, {'BOT_TOKEN': '123:fake', 'OWNER_ID': '42', **env}, clear=True), patch('bot.config.load_dotenv'):
        with pytest.raises(ValueError):
            Settings.from_env()


def test_safe_names():
    assert safe_name('../../secret.txt') == 'secret.txt'
    assert safe_name('..\\secret.txt') == 'secret.txt'
    assert safe_name('..') == 'archivo.bin'
    assert '/' not in safe_name('a/b')


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['file:///etc/passwd', 'ftp://example.com/file', 'http://a:b@example.com', 'http://localhost:9'])
async def test_reject_urls(url):
    with pytest.raises(TransferError):
        await validate_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize('ip', ['127.0.0.1', '10.1.1.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
async def test_reject_private_dns(ip):
    with patch.object(asyncio.get_running_loop(), 'getaddrinfo', AsyncMock(return_value=[(2, 1, 6, '', (ip, 80))])):
        with pytest.raises(TransferError):
            await validate_url('http://example.test')


class Stream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'hello'
        yield b' world'


def http_client(handler):
    real = httpx.AsyncClient
    return lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.asyncio
async def test_download(tmp_path):
    def handler(request):
        return httpx.Response(200, stream=Stream())
    with patch('bot.downloads.validate_url', AsyncMock()), patch('bot.downloads.httpx.AsyncClient', http_client(handler)):
        file = await download_http('https://example.test/a.txt', tmp_path, 100)
        assert file.read_bytes() == b'hello world'


@pytest.mark.asyncio
async def test_stream_limit(tmp_path):
    with patch('bot.downloads.validate_url', AsyncMock()), patch('bot.downloads.httpx.AsyncClient', http_client(lambda r: httpx.Response(200, stream=Stream()))):
        with pytest.raises(TransferError, match='supera'):
            await download_http('https://example.test/a', tmp_path, 4)


@pytest.mark.asyncio
async def test_redirect_revalidated(tmp_path):
    validate = AsyncMock(side_effect=[None, TransferError('private')])
    handler = lambda r: httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    with patch('bot.downloads.validate_url', validate), patch('bot.downloads.httpx.AsyncClient', http_client(handler)):
        with pytest.raises(TransferError):
            await download_http('https://example.test/a', tmp_path, 100)
    assert validate.await_count == 2


@pytest.mark.asyncio
async def test_mirror_no_shell(tmp_path):
    with patch('bot.downloads.run_tool', AsyncMock()) as run:
        await mirror_file(tmp_path / 'a;touch test.txt', 'drive:folder')
    assert run.call_args.args[:3] == ('rclone', 'copyto', str(tmp_path / 'a;touch test.txt'))


@pytest.mark.asyncio
async def test_authorization(settings):
    callback = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=999), effective_message=object())
    context = SimpleNamespace(application=SimpleNamespace(bot_data={'settings': settings}))
    await restricted(callback)(update, context)
    callback.assert_not_called()
    update.effective_user.id = 42
    await restricted(callback)(update, context)
    callback.assert_awaited_once()


def context_for(settings):
    message = SimpleNamespace(reply_text=AsyncMock(), reply_document=AsyncMock(), text='/leech https://example.test/a', reply_to_message=None)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=message)
    context = SimpleNamespace(args=['https://example.test/a'], application=SimpleNamespace(bot_data={'settings': settings}))
    return update, context


@pytest.mark.asyncio
async def test_failure_cleans_files(settings):
    update, context = context_for(settings)
    async def fail(url, directory, limit):
        (directory / 'partial').write_bytes(b'partial')
        raise TransferError('fallo seguro')
    with patch('bot.__main__.download_http', fail):
        await transfer(update, context, 'leech', 'https://example.test', None)
    assert not list(settings.download_dir.iterdir())
    update.effective_message.reply_text.assert_awaited_with('fallo seguro')


@pytest.mark.asyncio
async def test_success_upload_and_cleanup(settings):
    update, context = context_for(settings)
    async def download(url, directory, limit):
        file = directory / 'ok.txt'
        file.write_text('hello')
        return file
    with patch('bot.__main__.download_http', download):
        await transfer(update, context, 'leech', 'https://example.test', None)
    update.effective_message.reply_document.assert_awaited_once()
    assert not list(settings.download_dir.iterdir())


@pytest.mark.asyncio
async def test_cancel_and_stop(settings):
    update, context = context_for(settings)
    started = asyncio.Event()
    async def download(url, directory, limit):
        (directory / 'partial').write_bytes(b'partial')
        started.set()
        await asyncio.Event().wait()
    with patch('bot.__main__.download_http', download):
        await transfer_command(update, context)
        await started.wait()
        await cancel_command(update, context)
        await post_stop(context.application)
    assert context.application.bot_data['task'].cancelled()
    assert not list(settings.download_dir.iterdir())


@pytest.mark.asyncio
async def test_prevent_second_task(settings):
    update, context = context_for(settings)
    task = asyncio.create_task(asyncio.sleep(60))
    context.application.bot_data['task'] = task
    try:
        await transfer_command(update, context)
        assert context.application.bot_data['task'] is task
        update.effective_message.reply_text.assert_awaited_with('Hay una tarea en curso. Usa /status o /cancel.')
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_content_length_limit(tmp_path):
    handler = lambda r: httpx.Response(200, headers={'content-length': '9000'}, stream=Stream())
    with patch('bot.downloads.validate_url', AsyncMock()), patch('bot.downloads.httpx.AsyncClient', http_client(handler)):
        with pytest.raises(TransferError, match='supera'):
            await download_http('https://example.test/a', tmp_path, 100)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_video_output_and_limits(tmp_path):
    from bot.downloads import download_video
    async def fake_tool(*args):
        (tmp_path / 'video.mp4').write_bytes(b'video')
    with patch('bot.downloads.validate_url', AsyncMock()), patch('bot.downloads.run_tool', fake_tool):
        result = await download_video('https://example.test/video', tmp_path, 100)
    assert result.name == 'video.mp4'


@pytest.mark.asyncio
async def test_video_cancels_oversized_download(tmp_path):
    from bot.downloads import download_video
    stopped = asyncio.Event()
    async def fake_tool(*args):
        try:
            (tmp_path / 'large.part').write_bytes(b'x' * 200)
            await asyncio.Event().wait()
        finally:
            stopped.set()
    with patch('bot.downloads.validate_url', AsyncMock()), patch('bot.downloads.run_tool', fake_tool):
        with pytest.raises(TransferError, match='supera'):
            await download_video('https://example.test/video', tmp_path, 100)
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_subprocess_cancel_kills_group():
    import signal
    from bot.downloads import run_tool
    started = asyncio.Event()
    calls = 0
    async def wait():
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.Event().wait()
        return 0
    process = SimpleNamespace(pid=123, wait=AsyncMock(side_effect=wait))
    with patch('bot.downloads.asyncio.create_subprocess_exec', AsyncMock(return_value=process)), patch('bot.downloads.os.killpg') as kill:
        task = asyncio.create_task(run_tool('fake'))
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        kill.assert_called_once_with(123, signal.SIGKILL)
        assert task.cancelled()
        assert calls == 2
