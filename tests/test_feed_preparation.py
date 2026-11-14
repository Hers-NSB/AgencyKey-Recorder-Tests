from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import recorder


class FeedPreparationTests(IsolatedAsyncioTestCase):
    async def test_profile_control_timeout_does_not_abort_feed_discovery(self):
        control = SimpleNamespace(
            is_visible=AsyncMock(return_value=True),
            evaluate=AsyncMock(return_value='available'),
            click=AsyncMock(side_effect=PlaywrightTimeoutError('intercepted')),
        )
        matches = SimpleNamespace(all=AsyncMock(return_value=[control]))
        frame = SimpleNamespace(
            get_by_text=lambda _: matches,
            locator=lambda _: SimpleNamespace(get_by_text=lambda _: matches),
        )
        page = SimpleNamespace(frames=[frame])
        with patch.object(recorder, 'frame_is_visible', new=AsyncMock(return_value=True)), \
             patch.object(recorder, 'my_profile_visible', new=AsyncMock(return_value=True)):
            self.assertTrue(await recorder.open_my_profile(page))
        control.click.assert_awaited_once()

    async def test_recording_can_exceed_initial_deadline_when_posts_keep_appearing(self):
        cards = [
            [{'id': '200', 'pinned': False, 'top': 115, 'bottom': 230}],
            [{'id': '100', 'pinned': False, 'top': 115, 'bottom': 230}],
        ]
        page = SimpleNamespace(wait_for_timeout=AsyncMock())
        frame = SimpleNamespace(is_detached=lambda: False, evaluate=AsyncMock(side_effect=cards))
        with patch.object(recorder, 'monotonic', side_effect=[0, 1, 9, 15, 16]), \
             patch.object(recorder, 'frame_is_visible', new=AsyncMock(return_value=True)), \
             patch.object(recorder, 'frame_geometry', new=AsyncMock(return_value=(0, 0, 720))), \
             patch.object(recorder, 'images_ready', new=AsyncMock()), \
             patch.object(recorder, 'scroll_down', new=AsyncMock()):
            seen = await recorder.capture_walk(page, ['200', '100'], timeout=10, frame=frame,
                                               reset_on_progress=True)
        self.assertEqual(seen, ['200', '100'])

    async def test_waits_for_delayed_feed_then_checks_all_posts_and_returns_to_start(self):
        page=SimpleNamespace(url='file:///test-feed.html',wait_for_timeout=AsyncMock())
        frame=SimpleNamespace(evaluate=AsyncMock())
        order=[]
        async def seek(*args,**kwargs):
            order.append('seek');return {'_frame':frame}
        async def walk(*args,**kwargs):
            order.append('preload');kwargs['on_progress']({'completed':2,'total':2,'stage':'grabando'})
        progress=[]
        with patch.object(recorder,'post_frame',new=AsyncMock(side_effect=[None,None,frame])), \
             patch.object(recorder,'scroll_frame',new=AsyncMock(return_value=frame)), \
             patch.object(recorder,'scroll_down',new=AsyncMock()) as scroll, \
             patch.object(recorder,'seek_start',new=AsyncMock(side_effect=seek)), \
             patch.object(recorder,'capture_walk',new=AsyncMock(side_effect=walk)) as capture:
            first=await recorder.prepare_feed(page,['200','100'],on_progress=progress.append)
        self.assertEqual(page.wait_for_timeout.await_count,3)
        self.assertEqual(scroll.await_count, 2)
        self.assertEqual(order,['seek','preload','seek'])
        self.assertEqual(capture.call_args.args[1],['200','100'])
        self.assertEqual(first['_frame'],frame)
        self.assertEqual(progress[0]['stage'],'cargando feed e imágenes')
        frame.evaluate.assert_awaited_once()

    async def test_expired_session_requests_reconnection_on_the_web(self):
        page=SimpleNamespace(url='https://app.agencykey.com/login')
        with self.assertRaisesRegex(ValueError,'panel web'):
            await recorder.prepare_feed(page,['200'])


    async def test_image_timeout_reports_the_stalled_stage(self):
        frame = SimpleNamespace(wait_for_function=AsyncMock(side_effect=PlaywrightTimeoutError('timeout')))
        with self.assertRaisesRegex(PlaywrightTimeoutError, 'imágenes visibles'):
            await recorder.images_ready(None, frame=frame)
        self.assertEqual(frame.wait_for_function.call_args.kwargs['timeout'], 20000)


    async def test_opens_my_profile_before_scrolling_for_posts(self):
        url = 'https://app.agencykey.com/models/52'
        frame = object()
        page = SimpleNamespace(url=url, wait_for_timeout=AsyncMock())
        with patch.object(recorder, 'agencykey_sign_in_visible', new=AsyncMock(return_value=False)), \
             patch.object(recorder, 'post_frame', new=AsyncMock(side_effect=[None, None, frame])), \
             patch.object(recorder, 'my_profile_visible', new=AsyncMock(return_value=False)), \
             patch.object(recorder, 'open_my_profile', new=AsyncMock(return_value=True)) as open_profile, \
             patch.object(recorder, 'scroll_frame', new=AsyncMock(return_value=frame)), \
             patch.object(recorder, 'scroll_down', new=AsyncMock()) as scroll:
            result = await recorder.wait_for_feed(page, url, deadline=recorder.monotonic() + 5)
        self.assertIs(result, frame)
        open_profile.assert_awaited_once_with(page)
        scroll.assert_awaited_once_with(page, 340, frame=frame, smooth=False)
        self.assertEqual([call.args for call in page.wait_for_timeout.await_args_list], [(700,), (500,)])
