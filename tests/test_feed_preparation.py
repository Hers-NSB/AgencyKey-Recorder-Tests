from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import recorder


class FeedPreparationTests(IsolatedAsyncioTestCase):
    async def test_waits_for_delayed_feed_then_checks_all_posts_and_returns_to_start(self):
        page=SimpleNamespace(url='https://app.agencykey.com/models/52',wait_for_timeout=AsyncMock())
        frame=SimpleNamespace(evaluate=AsyncMock())
        order=[]
        async def seek(*args,**kwargs):
            order.append('seek');return {'_frame':frame}
        async def walk(*args,**kwargs):
            order.append('preload');kwargs['on_progress']({'completed':2,'total':2,'stage':'grabando'})
        progress=[]
        with patch.object(recorder,'post_frame',new=AsyncMock(side_effect=[None,None,frame])), \
             patch.object(recorder,'seek_start',new=AsyncMock(side_effect=seek)), \
             patch.object(recorder,'capture_walk',new=AsyncMock(side_effect=walk)) as capture:
            first=await recorder.prepare_feed(page,['200','100'],on_progress=progress.append)
        self.assertEqual(page.wait_for_timeout.await_count,3)
        self.assertEqual(order,['seek','preload','seek'])
        self.assertEqual(capture.call_args.args[1],['200','100'])
        self.assertEqual(first['_frame'],frame)
        self.assertEqual(progress[0]['stage'],'cargando feed e imágenes')
        frame.evaluate.assert_awaited_once()

    async def test_expired_session_requests_reconnection_on_the_web(self):
        page=SimpleNamespace(url='https://app.agencykey.com/login')
        with self.assertRaisesRegex(ValueError,'desde la web'):
            await recorder.prepare_feed(page,['200'])


    async def test_image_timeout_reports_the_stalled_stage(self):
        frame = SimpleNamespace(wait_for_function=AsyncMock(side_effect=PlaywrightTimeoutError('timeout')))
        with self.assertRaisesRegex(ValueError, 'imágenes visibles'):
            await recorder.images_ready(None, frame=frame)
        self.assertEqual(frame.wait_for_function.call_args.kwargs['timeout'], 20000)
