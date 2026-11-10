"""Publish-to-proof workflow. No credentials are persisted with recording jobs."""
import asyncio
import json
from pathlib import Path
import queue
from types import SimpleNamespace

from telegram.error import BadRequest, Forbidden, TelegramError

import recorder
from config import log


def session_path(creator_id):
    return recorder.ROOT / 'private' / 'sessions' / f'{int(creator_id)}.json'


async def connect_session(creator_id, confirm, cancel, emit):
    from playwright.async_api import async_playwright
    url = f'https://app.agencykey.com/models/{int(creator_id)}'
    async with async_playwright() as pw:
        browser = await recorder.launch_browser(pw, headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        try:
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            emit('INFO', 'Abre el perfil en Chrome y pulsa Guardar sesión en la app.')
            while not cancel.is_set() and not page.is_closed():
                if confirm.is_set():
                    confirm.clear()
                    try:
                        await recorder.save_login_session(page, context, url, state_path=session_path(creator_id))
                    except ValueError as error:
                        emit('ERROR', str(error))
                    else:
                        emit('INFO', 'Sesión de AgencyKey guardada para esta modelo.')
                        return
                await asyncio.sleep(.2)
        finally:
            await browser.close()


class RecordingCoordinator:
    def __init__(self, creator, *, events=None, stop_event=None):
        self.creator, self.events, self.stop_event = creator, events, stop_event
        self.busy = False

    def emit(self, event, value):
        if self.events is not None:
            try:
                self.events.put_nowait((event, value))
            except queue.Full:
                pass

    def progress(self, value):
        self.emit('recording', value)
        log.info('Comprobante | %s | %s/%s | ID %s', value['stage'], value['completed'], value['total'], value.get('post_id', ''))

    def job_path(self, chat_id):
        return recorder.ROOT / 'jobs' / f'{int(self.creator.external_id)}-{int(chat_id)}.json'

    @staticmethod
    def missing_ids(batch):
        return [number for number in range(1, len(batch.order) + 1) if number not in batch.published_ids]

    async def start(self, batch, bot, chat_id, application, *, resend=False):
        if self.busy:
            await bot.send_message(chat_id, '🎥 Ya hay un comprobante en proceso. Mira el progreso en la app.')
            return
        missing = self.missing_ids(batch)
        if missing:
            await bot.send_message(chat_id, 'Para grabar también los posts manuales, indica sus IDs: '
                                   + ', '.join(map(str, missing)) + '\nUsa /id NUMERO ID_O_ENLACE y después /video.')
            return
        path = self.job_path(chat_id)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if previous.get('batch_id') == batch.id:
            if previous.get('status') == 'sent':
                await bot.send_message(chat_id, '✅ Este comprobante ya fue enviado.')
                return
            if previous.get('status') in {'sending', 'delivery_unknown'} and not resend:
                await bot.send_message(chat_id, 'La entrega anterior no está confirmada. Revisa el chat; '
                                       'si no llegó, usa /video reenviar.')
                return
        self.busy = True
        async def work():
            try:
                await self.run(batch, bot, chat_id, previous if previous.get('batch_id') == batch.id else {})
            finally:
                self.busy = False
        application.create_task(work())

    def restore_batch(self, chat_id):
        path = self.job_path(chat_id)
        if not path.exists():
            return None
        job = json.loads(path.read_text())
        ids = job.get('post_ids_oldest_first')
        if not isinstance(ids, list) or not ids:
            return None
        return SimpleNamespace(id=job['batch_id'], status='done', creator=self.creator,
                               order=list(range(len(ids))), published_ids={i+1: value for i, value in enumerate(ids)})

    async def run(self, batch, bot, chat_id, previous=None):
        job = dict(previous or {})
        job.update(batch_id=batch.id, chat_id=chat_id, creator_id=int(self.creator.external_id))
        job['post_ids_oldest_first'] = [batch.published_ids[n] for n in range(1, len(batch.order)+1)]
        path = self.job_path(chat_id)
        try:
            report_path = Path(job['report']) if job.get('report') else None
            if report_path is None:
                job['status'] = 'recording'
                recorder.save_json(path, job)
                await bot.send_message(chat_id, '🎥 Drop finalizado. Grabando el comprobante en segundo plano; '
                                       'puedes ver la vista previa y el progreso en la app.')
                ids = [recorder.post_id(batch.published_ids[n]) for n in range(len(batch.order), 0, -1)]
                config = recorder.validate_config({'profile_url': f'https://app.agencykey.com/models/{self.creator.external_id}',
                                                   'post_ids_newest_first': ids})
                report_path = await recorder.record(config, headless=True, session_path=session_path(self.creator.external_id),
                    on_progress=self.progress, on_preview=lambda png: self.emit('preview', png), stop_event=self.stop_event)
                job['report'] = str(report_path)
            report, video = recorder.verified_video(report_path)
            self.progress({'stage': 'enviando video', 'completed': len(report['seen']), 'total': len(report['seen'])})
            job['status'] = 'sending'
            recorder.save_json(path, job)
            with video.open('rb') as stream:
                message = await bot.send_video(chat_id=chat_id, video=stream,
                    caption=f'✅ Comprobante · {len(report["seen"])} posts · {self.creator.name}',
                    supports_streaming=True, read_timeout=180, write_timeout=180, connect_timeout=30, pool_timeout=30)
            job.update(status='sent', message_id=message.message_id)
            self.progress({'stage': 'enviado', 'completed': len(report['seen']), 'total': len(report['seen'])})
        except TelegramError as error:
            uncertain = job.get('status') == 'sending' and not isinstance(error, (BadRequest, Forbidden))
            job.update(status='delivery_unknown' if uncertain else 'error', error_type=type(error).__name__)
            self.emit('recording', {'stage': 'error de Telegram' + (' · entrega incierta' if uncertain else ''), 'completed': 0, 'total': len(batch.order)})
            log.error('Comprobante | Telegram | %s | Entrega incierta: %s', type(error).__name__, uncertain)
            try:
                await bot.send_message(chat_id, '⚠️ No se confirmó el envío del comprobante. '
                                       'Revisa la app y el chat antes de usar /video reenviar.')
            except TelegramError:
                pass
        except Exception as error:
            job.update(status='error', error_type=type(error).__name__)
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__
            self.emit('recording', {'stage': 'error · ' + detail, 'completed': 0, 'total': len(batch.order)})
            log.error('Comprobante | %s', detail)
            try:
                await bot.send_message(chat_id, '⚠️ No se completó el comprobante. Revisa el error en la app; '
                                       'las publicaciones no se volverán a enviar. Usa /video para repetir el comprobante.')
            except TelegramError:
                pass
        finally:
            recorder.save_json(path, job)
