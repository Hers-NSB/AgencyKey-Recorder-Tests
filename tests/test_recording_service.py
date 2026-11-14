import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from agencykey import Creator
from bot import DropperBot
from core import Batch, Post
from recording_service import (
    AGENCYKEY_SIGN_IN, RecordingCoordinator, agencykey_login_complete,
    run_desktop_recording_job, session_path, verify_profile_route,
)
import recorder


class DesktopRecordingJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_uses_visible_chrome_and_returns_shared_state(self):
        state = {'cookies': [], 'origins': []}
        page = SimpleNamespace(url='https://app.agencykey.com/dashboard',
                               goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                               is_closed=lambda: False, locator=Mock())
        page.locator.side_effect = lambda selector: (
            SimpleNamespace(is_visible=AsyncMock(return_value=True)) if selector == 'body'
            else SimpleNamespace(first=SimpleNamespace(is_visible=AsyncMock(return_value=False)))
        )
        context = SimpleNamespace(new_page=AsyncMock(return_value=page),
                                  storage_state=AsyncMock(return_value=state))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        client = SimpleNamespace(update_recording_job=Mock(return_value={'active': False}))
        job = {'kind': 'connect'}
        with patch.object(recorder, 'launch_browser', new=AsyncMock(return_value=browser)) as launch:
            await run_desktop_recording_job(client, job, threading.Event())
        self.assertFalse(launch.call_args.kwargs['headless'])
        page.goto.assert_awaited_once_with(AGENCYKEY_SIGN_IN,
                                           wait_until='domcontentloaded', timeout=30000)
        context.storage_state.assert_awaited_once_with(indexed_db=True)
        browser.close.assert_awaited_once()
        client.update_recording_job.assert_called_once_with(job, status='ready', state=state)

    async def test_login_waits_during_sign_in_two_factor_and_external_redirects(self):
        for url in (AGENCYKEY_SIGN_IN, 'https://app.agencykey.com/auth/verify',
                    'https://app.agencykey.com/2fa', 'https://example.com/dashboard'):
            with self.subTest(url=url):
                page = SimpleNamespace(url=url, locator=Mock())
                self.assertFalse(await agencykey_login_complete(page))
                page.locator.assert_not_called()

    async def test_feed_check_uses_only_the_selected_model_route_and_saved_session(self):
        state = {'cookies': [], 'origins': []}
        url = 'https://app.agencykey.com/models/98'
        password = SimpleNamespace(is_visible=AsyncMock(return_value=False))
        page = SimpleNamespace(url=url, goto=AsyncMock(return_value=SimpleNamespace(status=200, ok=True)),
                               locator=Mock(return_value=SimpleNamespace(first=password)))
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        client = SimpleNamespace(recording_session=Mock(return_value={'state': state}),
                                 update_recording_job=Mock(return_value={'active': False}))
        job = {'kind': 'feed', 'creator_id': 98}
        with patch.object(recorder, 'launch_browser', new=AsyncMock(return_value=browser)) as launch, \
             patch.object(recorder, 'my_profile_visible', new=AsyncMock(return_value=True)), \
             patch.object(recorder, 'post_frame', new=AsyncMock(side_effect=AssertionError('Profile verification must not read posts'))):
            await run_desktop_recording_job(client, job, threading.Event())
        self.assertTrue(launch.call_args.kwargs['headless'])
        self.assertIs(browser.new_context.call_args.kwargs['storage_state'], state)
        page.goto.assert_awaited_once_with(url, wait_until='domcontentloaded', timeout=30000)
        client.update_recording_job.assert_called_once_with(job, status='ready', profile_checked=True)

    async def test_feed_check_rejects_login_access_errors_and_other_models(self):
        origin = 'https://app.agencykey.com'
        for path, status, password_visible, result in [
            ('/login', 200, False, 'login_required'),
            ('/models/98', 200, True, 'login_required'),
            ('/models/98', 401, False, 'login_required'),
            ('/models/98', 403, False, 'unavailable'),
            ('/models/98', 404, False, 'unavailable'),
            ('/models/98', 500, False, 'connection_error'),
            ('/models/52', 200, False, 'wrong_profile'),
        ]:
            with self.subTest(path=path, status=status, password_visible=password_visible), \
                 patch.object(recorder, 'monotonic', side_effect=[0, 36]), \
                 patch('recording_service.monotonic', return_value=0):
                password = SimpleNamespace(is_visible=AsyncMock(return_value=password_visible))
                response = SimpleNamespace(status=status, ok=status == 200)
                page = SimpleNamespace(url=origin + path, goto=AsyncMock(return_value=response),
                                       wait_for_timeout=AsyncMock(),
                                       locator=Mock(return_value=SimpleNamespace(first=password)))
                self.assertEqual(await verify_profile_route(page, origin + '/models/98'), result)


class ProofTests(unittest.IsolatedAsyncioTestCase):
    def batch(self):
        batch = Batch(Creator(52, 'Modelo', None))
        batch.order = [1, 2, 3]
        batch.published_ids = {1: '101', 2: '102', 3: '103'}
        batch.status = 'done'
        return batch

    async def test_visible_recording_uses_desktop_failure_callback(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder, 'ROOT', Path(folder)):
            coordinator = RecordingCoordinator(Creator(52, 'Modelo', None))
            bot = SimpleNamespace(send_message=AsyncMock())
            with patch.object(recorder, 'record', new=AsyncMock(side_effect=ValueError('No se encontró el perfil'))) as record:
                await coordinator.run(self.batch(), bot, 42)
            self.assertFalse(record.call_args.kwargs['headless'])
            self.assertEqual(record.call_args.kwargs['on_browser_failure'], coordinator.inspect_browser_failure)

    async def test_visible_failure_explains_what_to_do_and_waits_for_chrome_to_close(self):
        coordinator = RecordingCoordinator(Creator(52, 'Modelo', None))
        page = SimpleNamespace(is_closed=Mock(side_effect=[False, True]))
        with patch.object(coordinator, 'emit') as emit, patch('recording_service.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await coordinator.inspect_browser_failure(page, 'abrir perfil', 'Se agotó la espera.')
        sleep.assert_awaited_once()
        self.assertIn('Chrome queda abierto', emit.call_args.args[1]['stage'])
        self.assertTrue(emit.call_args.args[1]['error'])

    async def test_visible_proof_uses_newest_first_ids_and_sends_only_verified_mp4(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder, 'ROOT', Path(folder)):
            video, report_path = Path(folder)/'video.mp4', Path(folder)/'report.json'
            video.write_bytes(b'fixture')
            bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)), send_video=AsyncMock(return_value=SimpleNamespace(message_id=7)))
            coordinator = RecordingCoordinator(Creator(52, 'Modelo', None))
            with patch.object(recorder, 'record', new=AsyncMock(return_value=report_path)) as record, \
                 patch.object(recorder, 'verified_video', return_value=({'seen':['103','102','101']}, video)):
                await coordinator.run(self.batch(), bot, 42)
            self.assertEqual(record.call_args.args[0]['post_ids_newest_first'], ['103','102','101'])
            self.assertFalse(record.call_args.kwargs['headless'])
            self.assertEqual(record.call_args.kwargs['session_path'], session_path(52))
            bot.send_video.assert_awaited_once()
            job = json.loads(coordinator.job_path(42).read_text())
            self.assertEqual((job['status'],job['message_id']),('sent',7))
            self.assertEqual(coordinator.restore_batch(42).published_ids,{1:'101',2:'102',3:'103'})
            app=SimpleNamespace(create_task=lambda task: self.fail('confirmed proof must not be scheduled'))
            await coordinator.start(self.batch_with_id(job['batch_id']), bot,42,app)
            bot.send_video.assert_awaited_once()

    def batch_with_id(self, value):
        batch=self.batch();batch.id=value;return batch

    async def test_missing_manual_id_does_not_record_or_publish_again(self):
        coordinator=RecordingCoordinator(Creator(52,'Modelo',None))
        batch=self.batch();batch.published_ids.pop(2);batch.manual=[2]
        bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)))
        app=SimpleNamespace(create_task=lambda task:self.fail('missing ID must block recording'))
        await coordinator.start(batch,bot,42,app)
        self.assertIn('/id',bot.send_message.call_args.args[1])
        self.assertFalse(coordinator.busy)

    async def test_unknown_delivery_is_preserved_and_requires_explicit_resend(self):
        from telegram.error import TimedOut
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            batch=self.batch();coordinator=RecordingCoordinator(batch.creator)
            bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)),send_video=AsyncMock(side_effect=TimedOut()))
            with patch.object(recorder,'record',new=AsyncMock(return_value=Path(folder)/'report.json')), \
                 patch.object(recorder,'verified_video',return_value=({'seen':['103','102','101']},video)):
                await coordinator.run(batch,bot,42)
            self.assertEqual(json.loads(coordinator.job_path(42).read_text())['status'],'delivery_unknown')
            app=SimpleNamespace(create_task=lambda task:self.fail('unknown delivery must not retry itself'))
            await coordinator.start(batch,bot,42,app)
            bot.send_video.assert_awaited_once()
            self.assertIn('/video reenviar',bot.send_message.call_args.args[1])

    async def test_recording_error_never_sends_incomplete_video(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            batch=self.batch();coordinator=RecordingCoordinator(batch.creator)
            bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)),send_video=AsyncMock())
            with patch.object(recorder,'record',new=AsyncMock(side_effect=ValueError('fallo de imágenes'))):
                await coordinator.run(batch,bot,42)
            bot.send_video.assert_not_awaited()
            self.assertEqual(json.loads(coordinator.job_path(42).read_text())['status'],'error')
            button = bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard[0][0]
            self.assertIn('Repetir grabación', button.text)
            query = SimpleNamespace(data=button.callback_data, answer=AsyncMock())
            update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=42))
            context = SimpleNamespace(user_data={}, bot=bot, application=object())
            publisher = DropperBot(SimpleNamespace(), batch.creator, coordinator)
            with patch.object(coordinator, 'start', new_callable=AsyncMock) as retry:
                await publisher.retry_recording(update, context)
                self.assertEqual(retry.call_args.args[0].published_ids, batch.published_ids)
                retry.assert_awaited_once()
                query.data = 'proof-retry:' + '0' * 32
                await publisher.retry_recording(update, context)
                retry.assert_awaited_once()
                self.assertTrue(query.answer.call_args.kwargs['show_alert'])

    async def test_integrated_telegram_error_uses_safe_network_diagnosis(self):
        import httpx
        from telegram.error import NetworkError
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            batch=self.batch();coordinator=RecordingCoordinator(batch.creator)
            video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            failure=NetworkError('private details')
            failure.__cause__=httpx.ConnectTimeout('PRIVATE_TOKEN')
            bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)),send_video=AsyncMock(side_effect=failure))
            with patch.object(recorder,'record',new=AsyncMock(return_value=Path(folder)/'report.json')), \
                 patch.object(recorder,'verified_video',return_value=({'seen':['103','102','101']},video)), \
                 patch.object(coordinator,'emit') as emit:
                await coordinator.run(batch,bot,42)
            self.assertEqual(json.loads(coordinator.job_path(42).read_text())['status'],'error')
            self.assertIn('no se pudo establecer',str(emit.call_args_list))
            self.assertNotIn('PRIVATE_TOKEN',str(emit.call_args_list))

    async def test_batch_retains_ids_across_pause_and_manual_recovery(self):
        from agencykey import AgencyKeyError
        batch=Batch(Creator(52,'Modelo',None));batch.order=[1,2]
        batch.received={1:Post('one',None),2:Post('two',None)}
        api=SimpleNamespace(publish_text=AsyncMock(side_effect=[101,AgencyKeyError('fail')]))
        await batch.publish(api,AsyncMock())
        self.assertEqual(batch.published_ids,{1:'101'})
        batch.confirm_manual()
        self.assertEqual(batch.published_ids,{1:'101'})
        self.assertEqual(RecordingCoordinator.missing_ids(batch),[2])

    async def test_completed_drop_schedules_proof_with_original_chat(self):
        batch=Batch(Creator(52,'Modelo',None));batch.order=[1];batch.received={1:Post('text',None)}
        recording=SimpleNamespace(busy=False,start=AsyncMock())
        bot=DropperBot(SimpleNamespace(publish_text=AsyncMock(return_value=101)),batch.creator,recording)
        from test_publisher_flow import context,update
        ctx=context();ctx.application=object();ctx.user_data['batch']=batch
        await bot.publish_batch(batch,update(),ctx)
        recording.start.assert_awaited_once_with(batch,ctx.bot,123,ctx.application)
        self.assertFalse(any('Drop finalizado' in str(call) for call in ctx.bot.send_message.call_args_list))

    async def test_final_summary_follows_video_and_includes_the_entire_process(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            batch=self.batch();batch.started_wall_at=1000;batch.session_total=11
            video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            sequence=[]
            async def send_video(**kwargs):
                sequence.append('video delivered')
                return SimpleNamespace(message_id=7)
            async def send_message(chat_id,text,**kwargs):
                if 'Drop finalizado' in text:
                    sequence.append('summary')
                    self.assertIn('Tiempo total: 0 min 49 s',text)
                    self.assertIn('Total del Drop: 3',text)
                    self.assertIn('Total de post: 11 posts',text)
                return SimpleNamespace(message_id=8)
            bot=SimpleNamespace(send_message=AsyncMock(side_effect=send_message),send_video=AsyncMock(side_effect=send_video))
            coordinator=RecordingCoordinator(batch.creator)
            with patch.object(recorder,'record',new=AsyncMock(return_value=Path(folder)/'report.json')), \
                 patch.object(recorder,'verified_video',return_value=({'seen':['103','102','101']},video)), \
                 patch('recording_service.time',return_value=1049):
                await coordinator.run(batch,bot,42)
            self.assertEqual(sequence,['video delivered','summary'])
            job=json.loads(coordinator.job_path(42).read_text())
            self.assertEqual(job['summary_status'],'sent')
            await coordinator.start(batch,bot,42,SimpleNamespace(create_task=lambda task:self.fail('must not resend')))
            self.assertEqual(sequence,['video delivered','summary'])

    async def test_summary_failure_keeps_confirmed_video_and_does_not_duplicate_it(self):
        from telegram.error import TimedOut
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            batch=self.batch();video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            async def notify(chat_id,text,**kwargs):
                if 'Drop finalizado' in text: raise TimedOut()
                return SimpleNamespace(message_id=8)
            bot=SimpleNamespace(send_message=AsyncMock(side_effect=notify),send_video=AsyncMock(return_value=SimpleNamespace(message_id=7)))
            coordinator=RecordingCoordinator(batch.creator)
            with patch.object(recorder,'record',new=AsyncMock(return_value=Path(folder)/'report.json')), \
                 patch.object(recorder,'verified_video',return_value=({'seen':['103','102','101']},video)):
                await coordinator.run(batch,bot,42)
            job=json.loads(coordinator.job_path(42).read_text())
            self.assertEqual((job['status'],job['summary_status']),('sent','delivery_unknown'))
            await coordinator.start(batch,bot,42,SimpleNamespace(create_task=lambda task:self.fail('must not resend')))
            bot.send_video.assert_awaited_once()

    async def test_new_model_uses_shared_web_session_in_memory_and_refreshes_by_revision(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            batch=self.batch();video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            state={'cookies':[],'origins':[]}
            client=SimpleNamespace(recording_session=lambda:{'state':state,'revision':'original'},refresh_recording_session=lambda value,revision:None)
            coordinator=RecordingCoordinator(batch.creator,session_client=client)
            bot=SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)),send_video=AsyncMock(return_value=SimpleNamespace(message_id=7)))
            with patch.object(recorder,'record',new=AsyncMock(return_value=Path(folder)/'report.json')) as record, \
                 patch.object(recorder,'verified_video',return_value=({'seen':['103','102','101']},video)):
                await coordinator.run(batch,bot,42)
            self.assertEqual(record.call_args.kwargs['session_state'],state)
            self.assertNotIn('on_preview',record.call_args.kwargs)
            self.assertFalse(session_path(52).exists())


if __name__=='__main__':
    unittest.main()

