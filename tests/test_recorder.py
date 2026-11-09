import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, Mock

import recorder


class ValidationTests(unittest.TestCase):
    def test_extract_real_link(self):
        self.assertEqual(recorder.post_id('https://onlyfans.com/2872688165/your_goddess_lilith'), '2872688165')

    def test_invalid_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            recorder.post_id('https://example.com/123/user')
        with self.assertRaises(ValueError):
            recorder.validate_config({'profile_url': 'https://app.agencykey.com/models/123', 'post_ids_newest_first': ['1', '1']})

    def test_order_preserved_not_sorted_numerically(self):
        data = recorder.validate_config({'profile_url': 'https://app.agencykey.com/models/123', 'post_ids_newest_first': ['1', '3', '2']})
        self.assertEqual(data['post_ids_newest_first'], ['1', '3', '2'])

    def test_refuse_incomplete_or_tampered_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            recorder.save_json(path, {'status': 'incomplete'})
            with self.assertRaises(ValueError):
                recorder.verified_video(path)
            video = path.parent / 'comprobante.mp4'
            video.write_bytes(b'original')
            recorder.save_json(path, {'status': 'complete', 'seen': ['1'], 'post_ids': ['1'], 'sha256': hashlib.sha256(b'original').hexdigest()})
            self.assertEqual(recorder.verified_video(path)[1], video)
            video.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                recorder.verified_video(path)


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch()
        self.page = await self.browser.new_page(viewport={'width': 1280, 'height': 720})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def test_virtual_feed_with_delayed_images_and_tall_posts(self):
        await self.page.goto((recorder.RESOURCE_ROOT / 'tests/feed.html').as_uri())
        await recorder.seek_start(self.page, '300', timeout=3)
        seen = await recorder.capture_walk(self.page, ['300', '200', '100'], dwell=.05, timeout=15)
        self.assertEqual(seen, ['300', '200', '100'])
        last = await self.page.locator('#postId_100').bounding_box()
        self.assertLessEqual(last['y'] + last['height'], 700)

    async def test_out_of_order_fails(self):
        await self.page.goto((recorder.RESOURCE_ROOT / 'tests/feed.html').as_uri())
        await recorder.seek_start(self.page, '300', timeout=3)
        with self.assertRaisesRegex(ValueError, 'Orden inesperado'):
            await recorder.capture_walk(self.page, ['300', '100', '200'], dwell=.01, timeout=10)

    async def test_missing_post_and_failed_image(self):
        await self.page.set_content('<div id="postId_1" style="height:500px;margin-top:120px"><img src="http://127.0.0.1:1/missing" style="width:100px;height:100px"></div>')
        from playwright.async_api import TimeoutError
        with self.assertRaises(TimeoutError):
            await recorder.images_ready(self.page, timeout=300)
        await self.page.set_content('<p>Sesión vencida o feed vacío</p>')
        with self.assertRaises(ValueError):
            await recorder.seek_start(self.page, '999', timeout=.1)

    async def test_pinned_post_does_not_define_start(self):
        await self.page.set_content('<div id="postId_1" class="m-pinned" style="height:200px;margin-top:120px">fijado</div>')
        with self.assertRaises(ValueError):
            await recorder.seek_start(self.page, '1', timeout=.1)


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_uses_challenge_chat_and_keeps_token_out_of_report(self):
        import httpx
        token = '12345:TEST_TOKEN'
        sent = []
        code = []
        def fake_print(message, *args, **kwargs):
            if 'recorder-' in str(message):
                code.append(str(message).split()[-1])
        def handler(request):
            method = request.url.path.rsplit('/', 1)[-1]
            if method == 'getMe':
                result = {'username': 'test_recorder_bot'}
            elif method == 'getWebhookInfo':
                result = {'url': ''}
            elif method == 'getUpdates':
                result = [{'message': {'text': code[-1], 'chat': {'id': 42, 'type': 'private'}}}]
            elif method == 'sendVideo':
                sent.append(request)
                result = {'message_id': 7}
            else:
                raise AssertionError(method)
            return httpx.Response(200, json={'ok': True, 'result': result})
        actual_client = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            video = path.parent / 'comprobante.mp4'
            video.write_bytes(b'test video')
            recorder.save_json(path, {'status': 'complete', 'seen': ['1'], 'post_ids': ['1'],
                                     'sha256': hashlib.sha256(video.read_bytes()).hexdigest()})
            with patch('getpass.getpass', return_value=token), patch('builtins.input', side_effect=['test_recorder_bot', '']), \
                 patch('builtins.print', side_effect=fake_print), \
                 patch.object(httpx, 'AsyncClient', side_effect=lambda **kw: actual_client(transport=httpx.MockTransport(handler), **kw)):
                await recorder.send(path)
            self.assertEqual(len(sent), 1)
            self.assertIn(b'42', sent[0].content)
            self.assertNotIn(token, path.read_text())
            self.assertEqual(json.loads(path.read_text())['telegram']['chat_id'], 42)

    async def test_incomplete_report_never_requests_token_or_sends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            recorder.save_json(path, {'status': 'incomplete'})
            with patch('getpass.getpass') as prompt:
                with self.assertRaises(ValueError):
                    await recorder.send(path)
                prompt.assert_not_called()


class BrowserSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_browser_installs_and_retries(self):
        browser = object()
        playwright = Mock()
        playwright.chromium.launch = AsyncMock(side_effect=[RuntimeError("Executable doesn't exist"), browser])
        with patch.object(recorder, 'install_browser') as install:
            result = await recorder.launch_browser(playwright, headless=True)
        self.assertIs(result, browser)
        self.assertEqual(playwright.chromium.launch.await_count, 2)
        install.assert_called_once()

    async def test_other_launch_errors_do_not_download(self):
        playwright = Mock()
        playwright.chromium.launch = AsyncMock(side_effect=RuntimeError('Operating system failure'))
        with patch.object(recorder, 'install_browser') as install:
            with self.assertRaisesRegex(RuntimeError, 'Operating system failure'):
                await recorder.launch_browser(playwright, headless=True)
        install.assert_not_called()

    async def test_existing_browser_does_not_download(self):
        browser = object()
        playwright = Mock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        with patch.object(recorder, 'install_browser') as install:
            self.assertIs(await recorder.launch_browser(playwright, headless=False), browser)
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
