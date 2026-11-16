from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import AsyncMock, Mock, patch

from diagnostico_perfil import app


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_accepts_model_id_or_link_and_removes_query_from_output(self):
        url = app.model_url('https://app.agencykey.com/models/52/')
        self.assertEqual(url, app.model_url('52'))
        self.assertEqual(app.safe_route(url + '?fixture=hidden#hidden'), 'app.agencykey.com/models/52')
        with self.assertRaises(ValueError):
            app.model_url('https://example.com/models/52')

    async def test_switch_reports_expected_and_detected_model_on_each_attempt(self):
        page = Mock()
        page.main_frame.locator.return_value.first.is_visible = AsyncMock(return_value=False)
        page.main_frame.get_by_text.return_value.all = AsyncMock(return_value=[])
        page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
        page.url = page.main_frame.url = 'about:blank'
        page.frames = [page.main_frame]

        async def navigate(url, **options):
            page.url = page.main_frame.url = url
            model_id = url.rsplit('/', 1)[-1]
            username = {'52': 'primera', '98': 'segunda'}[model_id]
            frame = Mock(url=f'https://of-{model_id}.agencykey.com/{username}?fixture=hidden')
            frame.locator.return_value.first.is_visible = AsyncMock(return_value=True)
            frame.get_by_text.return_value.all = AsyncMock(return_value=[])
            page.frames = [page.main_frame, frame]
            return Mock(status=200, ok=True)

        page.goto = AsyncMock(side_effect=navigate)
        with patch.object(app.recorder, 'frame_is_visible', new=AsyncMock(return_value=True)):
            for model_id, username in ((52, 'primera'), (98, 'segunda'), (52, 'primera')):
                output = StringIO()
                with redirect_stdout(output):
                    result = await app.check(page, app.model_url(str(model_id)), username)
                self.assertEqual(result, {'status': 'ready', 'observed_username': username})
                self.assertIn(f'{model_id} / @{username}', output.getvalue())
                self.assertNotIn('fixture=hidden', output.getvalue())
