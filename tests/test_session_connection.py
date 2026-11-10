from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

import recorder
import recording_service as service


class SessionConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_existing_session_and_saves_automatically(self):
        page = SimpleNamespace(url='https://app.agencykey.com/models/52', goto=AsyncMock(), is_closed=Mock(return_value=False))
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        manager = Mock(__aenter__=AsyncMock(return_value=object()), __aexit__=AsyncMock(return_value=False))
        confirm, cancel = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder, 'ROOT', Path(folder)):
            state = service.session_path(52)
            state.parent.mkdir(parents=True)
            state.write_text('{"cookies":[],"origins":[]}')
            with patch('playwright.async_api.async_playwright', return_value=manager), \
                 patch.object(recorder,'launch_browser',new=AsyncMock(return_value=browser)), \
                 patch.object(service,'session_ready',new=AsyncMock(return_value=True)), \
                 patch.object(recorder,'save_login_session',new=AsyncMock()) as save:
                self.assertTrue(await service.connect_session(52,confirm,cancel,Mock()))
            self.assertEqual(browser.new_context.call_args.kwargs['storage_state'],str(state))
            save.assert_awaited_once_with(page,context,'https://app.agencykey.com/models/52',state_path=state)
            self.assertFalse(confirm.is_set())
            page.goto.assert_awaited_once()
            browser.close.assert_awaited_once()

    async def test_manual_save_is_available_when_profile_has_no_visible_posts(self):
        page=SimpleNamespace(goto=AsyncMock(),is_closed=Mock(return_value=False))
        context=SimpleNamespace(new_page=AsyncMock(return_value=page))
        browser=SimpleNamespace(new_context=AsyncMock(return_value=context),close=AsyncMock())
        manager=Mock(__aenter__=AsyncMock(return_value=object()),__aexit__=AsyncMock(return_value=False))
        confirm=threading.Event();confirm.set()
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)), \
             patch('playwright.async_api.async_playwright',return_value=manager), \
             patch.object(recorder,'launch_browser',new=AsyncMock(return_value=browser)), \
             patch.object(service,'session_ready',new=AsyncMock(return_value=False)), \
             patch.object(recorder,'save_login_session',new=AsyncMock()) as save:
            self.assertTrue(await service.connect_session(52,confirm,threading.Event(),Mock()))
            save.assert_awaited_once()
            self.assertNotIn('storage_state',browser.new_context.call_args.kwargs)

    async def test_does_not_auto_save_on_login_or_a_different_model(self):
        frame=SimpleNamespace(evaluate=AsyncMock(return_value=[{'id':'101'}]))
        for url in ['https://app.agencykey.com/login','https://app.agencykey.com/models/99','https://example.com/models/52']:
            with patch.object(recorder,'post_frame',new=AsyncMock(return_value=frame)) as frames:
                self.assertFalse(await service.session_ready(SimpleNamespace(url=url),'https://app.agencykey.com/models/52'))
                frames.assert_not_awaited()
        with patch.object(recorder,'post_frame',new=AsyncMock(return_value=None)):
            self.assertFalse(await service.session_ready(SimpleNamespace(url='https://app.agencykey.com/models/52'),
                                                         'https://app.agencykey.com/models/52'))

    async def test_browser_is_closed_even_when_saved_state_cannot_be_loaded(self):
        browser=SimpleNamespace(new_context=AsyncMock(side_effect=ValueError('bad state')),close=AsyncMock())
        manager=Mock(__aenter__=AsyncMock(return_value=object()),__aexit__=AsyncMock(return_value=False))
        with patch('playwright.async_api.async_playwright',return_value=manager), \
             patch.object(recorder,'launch_browser',new=AsyncMock(return_value=browser)):
            with self.assertRaisesRegex(ValueError,'bad state'):
                await service.connect_session(52,threading.Event(),threading.Event(),Mock())
        browser.close.assert_awaited_once()


class SessionButtonTests(unittest.TestCase):
    def test_desktop_has_no_login_workflow(self):
        from desktop import BotPanel
        self.assertFalse(hasattr(BotPanel, 'connect_recording'))

    def test_bot_starts_without_local_session_file(self):
        from desktop import BotPanel
        panel=BotPanel.__new__(BotPanel)
        panel.controller=SimpleNamespace(running=False,start=Mock())
        panel.manager=SimpleNamespace(closing=False,panels={})
        panel.set_mode=Mock()
        panel.start()
        panel.controller.start.assert_called_once()


if __name__=='__main__':
    unittest.main()

