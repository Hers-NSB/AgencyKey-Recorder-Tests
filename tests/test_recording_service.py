import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from agencykey import Creator
from bot import DropperBot
from core import Batch, Post
from recording_service import RecordingCoordinator, session_path
import recorder


class ProofTests(unittest.IsolatedAsyncioTestCase):
    def batch(self):
        batch = Batch(Creator(52, 'Modelo', None))
        batch.order = [1, 2, 3]
        batch.published_ids = {1: '101', 2: '102', 3: '103'}
        batch.status = 'done'
        return batch

    async def test_background_proof_uses_newest_first_ids_and_sends_only_verified_mp4(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder, 'ROOT', Path(folder)):
            video, report_path = Path(folder)/'video.mp4', Path(folder)/'report.json'
            video.write_bytes(b'fixture')
            bot = SimpleNamespace(send_message=AsyncMock(), send_video=AsyncMock(return_value=SimpleNamespace(message_id=7)))
            coordinator = RecordingCoordinator(Creator(52, 'Modelo', None))
            with patch.object(recorder, 'record', new=AsyncMock(return_value=report_path)) as record, \
                 patch.object(recorder, 'verified_video', return_value=({'seen':['103','102','101']}, video)):
                await coordinator.run(self.batch(), bot, 42)
            self.assertEqual(record.call_args.args[0]['post_ids_newest_first'], ['103','102','101'])
            self.assertTrue(record.call_args.kwargs['headless'])
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
        bot=SimpleNamespace(send_message=AsyncMock())
        app=SimpleNamespace(create_task=lambda task:self.fail('missing ID must block recording'))
        await coordinator.start(batch,bot,42,app)
        self.assertIn('/id',bot.send_message.call_args.args[1])
        self.assertFalse(coordinator.busy)

    async def test_unknown_delivery_is_preserved_and_requires_explicit_resend(self):
        from telegram.error import TimedOut
        with tempfile.TemporaryDirectory() as folder, patch.object(recorder,'ROOT',Path(folder)):
            video=Path(folder)/'video.mp4';video.write_bytes(b'fixture')
            batch=self.batch();coordinator=RecordingCoordinator(batch.creator)
            bot=SimpleNamespace(send_message=AsyncMock(),send_video=AsyncMock(side_effect=TimedOut()))
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
            bot=SimpleNamespace(send_message=AsyncMock(),send_video=AsyncMock())
            with patch.object(recorder,'record',new=AsyncMock(side_effect=ValueError('fallo de imágenes'))):
                await coordinator.run(batch,bot,42)
            bot.send_video.assert_not_awaited()
            self.assertEqual(json.loads(coordinator.job_path(42).read_text())['status'],'error')

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


if __name__=='__main__':
    unittest.main()
