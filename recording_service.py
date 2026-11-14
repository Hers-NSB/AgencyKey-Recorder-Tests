"""Publish-to-proof workflow. No credentials are persisted with recording jobs."""
import asyncio
import json
from pathlib import Path
import queue
from types import SimpleNamespace
from time import time, monotonic
from urllib.parse import urlparse

from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

import recorder
from config import log
from cloud_client import CloudError


AGENCYKEY_SIGN_IN = 'https://app.agencykey.com/auth/signin'
RECORDING_STEPS = {
    'preparando comprobante': 'Preparando el comprobante',
    'cargando sesión de AgencyKey': 'Abriendo la sesión guardada de AgencyKey',
    'iniciando Chrome': 'Iniciando Chrome',
    'abrir perfil': 'Abriendo el perfil de la modelo',
    'reintentando abrir el perfil por un fallo de conexión': 'La conexión se interrumpió. Intentando abrir el perfil otra vez',
    'cargando feed e imágenes': 'Buscando las publicaciones de la modelo y cargando sus fotos',
    'marcar inicio del video': 'Preparando el inicio del video',
    'recorrer posts / cargar imágenes': 'Grabando las publicaciones y sus fotos',
    'grabando': 'Grabando las publicaciones',
    'marcar fin del video': 'Terminando la grabación',
    'verificar límites del video': 'Comprobando que el video esté completo',
    'convertir video a MP4': 'Preparando el archivo de video',
    'video listo': 'Video listo',
    'enviando video': 'Enviando el video a Telegram',
    'enviado': 'Video enviado a Telegram',
}


def recording_step(stage):
    return RECORDING_STEPS.get(stage, stage)


def session_path(creator_id):
    return recorder.ROOT / 'private' / 'sessions' / f'{int(creator_id)}.json'


async def connect_session(creator_id, confirm, cancel, emit):
    from playwright.async_api import async_playwright
    url = recorder.model_profile_url(creator_id)
    state = session_path(creator_id)
    async with async_playwright() as pw:
        browser = await recorder.launch_browser(pw, headless=False)
        options = {'viewport': {'width': 1280, 'height': 720}}
        if state.is_file():
            options['storage_state'] = str(state)
            emit('INFO', 'Reutilizando la sesión guardada. No vuelvas a iniciar sesión si el perfil ya está abierto.')
        try:
            context = await browser.new_context(**options)
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            emit('INFO', 'La sesión se guardará automáticamente cuando el feed de esta modelo esté visible. '
                 'También puedes usar Guardar sesión en la ventana principal.')
            while not cancel.is_set() and not page.is_closed():
                automatic = await session_ready(page, url)
                if confirm.is_set() or automatic:
                    confirm.clear()
                    try:
                        await recorder.save_login_session(page, context, url, state_path=session_path(creator_id))
                    except ValueError as error:
                        emit('ERROR', str(error))
                    else:
                        emit('INFO', 'Sesión de AgencyKey guardada. Se reutilizará en las siguientes grabaciones mientras siga vigente.')
                        return True
                await asyncio.sleep(1)
        finally:
            await browser.close()
    return False


async def session_ready(page, expected_url):
    """Read the already loaded page; do not refresh, navigate or retry login."""
    current, expected = urlparse(page.url), urlparse(expected_url)
    if (current.scheme, current.netloc, current.path.rstrip('/')) != (
            expected.scheme, expected.netloc, expected.path.rstrip('/')):
        return False
    from playwright.async_api import Error as PlaywrightError
    try:
        frame = await recorder.post_frame(page)
        return bool(frame and await frame.evaluate(recorder.SNAPSHOT))
    except PlaywrightError:
        # Login redirects and iframe mounting can temporarily replace execution contexts.
        return False


async def agencykey_login_complete(page):
    from playwright.async_api import Error as PlaywrightError

    current = urlparse(page.url)
    if (current.scheme, current.netloc) != ('https', 'app.agencykey.com'):
        return False
    try:
        return not await recorder.agencykey_sign_in_visible(page) and await page.locator('body').is_visible()
    except PlaywrightError:
        return False


async def verify_profile_route(page, url):
    response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    if response is None:
        return 'connection_error'
    if response.status == 401:
        return 'login_required'
    if response.status in (403, 404):
        return 'unavailable'
    if not response.ok:
        return 'connection_error'

    try:
        await recorder.wait_for_my_profile(page, url, deadline=monotonic() + 35)
    except recorder.FeedAccessError as error:
        return error.status
    return 'ready'


PROFILE_ERRORS = {
    'login_required': 'AgencyKey pide iniciar sesión desde el panel web.',
    'unavailable': 'AgencyKey denegó el acceso o el perfil no existe.',
    'wrong_profile': 'Chrome abrió otra ruta.',
    'profile_menu_missing': 'Chrome no encontró la opción Mi perfil.',
    'profile_not_visible': 'Mi perfil no terminó de cargar.',
    'connection_error': 'Chrome no pudo cargar AgencyKey.',
}


async def run_desktop_recording_job(client, job, stop_event):
    """Open AgencyKey on this PC, then return the result to the waiting admin page."""
    from playwright.async_api import async_playwright

    async def check_cancelled():
        while not stop_event.is_set():
            await asyncio.sleep(3)
            try:
                status = await asyncio.to_thread(client.update_recording_job, job)
            except CloudError:
                continue
            if not status.get('active'):
                return
        return

    async def open_agencykey():
        connect = job['kind'] == 'connect'
        options = {'viewport': {'width': 1280, 'height': 720}}
        if not connect:
            options['storage_state'] = (await asyncio.to_thread(client.recording_session))['state']
        async with async_playwright() as pw:
            browser = await recorder.launch_browser(pw, headless=not connect)
            try:
                context = await browser.new_context(**options)
                page = await context.new_page()
                if not connect:
                    url = recorder.model_profile_url(job['creator_id'])
                    status = await verify_profile_route(page, url)
                    if status != 'ready':
                        log.warning('Verificación de Mi perfil | Modelo %s · %s', job['creator_id'], PROFILE_ERRORS[status])
                    return {'status': status, 'profile_checked': True}
                response = await page.goto(AGENCYKEY_SIGN_IN, wait_until='domcontentloaded', timeout=30000)
                if response is not None and response.status >= 400:
                    return {'status': 'connection_error'}
                deadline = monotonic() + 240
                while not page.is_closed() and monotonic() < deadline:
                    if await agencykey_login_complete(page):
                        return {'status': 'ready', 'state': await context.storage_state(indexed_db=True)}
                    await asyncio.sleep(.7)
                return {'status': 'cancelled'}
            finally:
                await browser.close()

    running = asyncio.create_task(open_agencykey())
    cancelled = asyncio.create_task(check_cancelled())
    try:
        done, _ = await asyncio.wait((running, cancelled), return_when=asyncio.FIRST_COMPLETED)
        if running in done and not stop_event.is_set():
            try:
                result = running.result()
            except Exception as error:
                detail = recorder.recording_error_detail(error)
                log.error('Solicitud web de Chrome | %s', detail)
                result = {'status': 'connection_error'}
                if job['kind'] == 'feed':
                    result['profile_checked'] = True
            await asyncio.to_thread(client.update_recording_job, job, **result)
    finally:
        for task in (running, cancelled):
            if not task.done():
                task.cancel()
        await asyncio.gather(running, cancelled, return_exceptions=True)


class RecordingCoordinator:
    def __init__(self, creator, *, events=None, stop_event=None, session_client=None):
        self.creator, self.events, self.stop_event = creator, events, stop_event
        self.busy = False
        self.session_client = session_client
        self.completion_markup = None
        self.last_recording_step = None

    def emit(self, event, value):
        if self.events is not None:
            try:
                self.events.put_nowait((event, value))
            except queue.Full:
                pass

    def progress(self, value):
        stage = recording_step(value['stage'])
        self.emit('recording', dict(value, stage=stage))
        if stage != self.last_recording_step:
            log.info('%s', stage)
            self.last_recording_step = stage

    async def inspect_browser_failure(self, page, stage, reason):
        detail = f'{recording_step(stage)}. {reason} Chrome queda abierto. Ciérralo cuando termines de revisar.'
        self.emit('recording', {'stage': detail, 'error': True, 'completed': 0, 'total': 0})
        log.error('%s', detail)
        while not page.is_closed() and not (self.stop_event and self.stop_event.is_set()):
            await asyncio.sleep(0.25)

    def job_path(self, chat_id):
        return recorder.ROOT / 'jobs' / f'{int(self.creator.external_id)}-{int(chat_id)}.json'

    @staticmethod
    def missing_ids(batch):
        return [number for number in range(1, len(batch.order) + 1) if number not in batch.published_ids]

    async def start(self, batch, bot, chat_id, application, *, resend=False):
        if self.busy:
            await bot.send_message(chat_id, '🎥 Video en proceso…')
            return
        missing = self.missing_ids(batch)
        if missing:
            await bot.send_message(chat_id, 'Para grabar también los posts manuales, indica sus IDs: '
                                   + ', '.join(map(str, missing)) + '\nUsa /id NUMERO ID_O_ENLACE y después /video')
            return
        path = self.job_path(chat_id)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if previous.get('batch_id') == batch.id:
            if previous.get('status') == 'sent':
                if previous.get('delivered_wall_at') and not previous.get('summary_status'):
                    await self.send_summary(previous, bot, chat_id, path)
                await bot.send_message(chat_id, '✅ Este comprobante ya fue enviado')
                return
            if previous.get('status') in {'sending', 'delivery_unknown'} and not resend:
                await bot.send_message(chat_id, 'Entrega anterior sin confirmar · Revisa el chat y, '
                                       'si no llegó, usa /video reenviar')
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
                               order=list(range(len(ids))), published_ids={i+1: value for i, value in enumerate(ids)},
                               started_wall_at=job.get('started_wall_at'), session_total=job.get('session_total', len(ids)),
                               rejected=job.get('rejected', []))

    async def run(self, batch, bot, chat_id, previous=None):
        self.last_recording_step = None
        job = dict(previous or {})
        job.update(batch_id=batch.id, chat_id=chat_id, creator_id=int(self.creator.external_id))
        job['post_ids_oldest_first'] = [batch.published_ids[n] for n in range(1, len(batch.order)+1)]
        job.setdefault('started_wall_at', getattr(batch, 'started_wall_at', None) or time())
        job.setdefault('session_total', getattr(batch, 'session_total', 0) or len(batch.order))
        job.setdefault('rejected', list(getattr(batch, 'rejected', [])))
        path = self.job_path(chat_id)
        try:
            report_path = Path(job['report']) if job.get('report') else None
            if report_path is None:
                self.progress({'stage': 'preparando comprobante', 'completed': 0, 'total': len(batch.order)})
                job['status'] = 'recording'
                recorder.save_json(path, job)
                try:
                    await bot.send_message(chat_id, '🎥 Preparando video…')
                except TelegramError:
                    log.warning('Comprobante | No se pudo entregar el aviso inicial; la grabación continúa.')
                ids = [recorder.post_id(batch.published_ids[n]) for n in range(len(batch.order), 0, -1)]
                config = recorder.validate_config({'profile_url': recorder.model_profile_url(self.creator.external_id),
                                                   'post_ids_newest_first': ids})
                options = {}
                if self.session_client:
                    self.progress({'stage': 'cargando sesión de AgencyKey', 'completed': 0, 'total': len(batch.order)})
                    shared = await asyncio.to_thread(self.session_client.recording_session)
                    options['session_state'] = shared['state']
                    async def refresh(state):
                        await asyncio.to_thread(self.session_client.refresh_recording_session, state, shared['revision'])
                    options['on_session_saved'] = refresh
                report_path = await recorder.record(config, headless=False,
                    on_browser_failure=self.inspect_browser_failure, session_path=session_path(self.creator.external_id),
                    on_progress=self.progress, stop_event=self.stop_event, **options)
                job['report'] = str(report_path)
            report, video = recorder.verified_video(report_path)
            self.progress({'stage': 'enviando video', 'completed': len(report['seen']), 'total': len(report['seen'])})
            job['status'] = 'sending'
            recorder.save_json(path, job)
            with video.open('rb') as stream:
                message = await bot.send_video(chat_id=chat_id, video=stream,
                    caption=f'✅ Comprobante · {len(report["seen"])} posts · {self.creator.name}',
                    supports_streaming=True, read_timeout=180, write_timeout=180, connect_timeout=30, pool_timeout=30)
            job.update(status='sent', message_id=message.message_id, delivered_wall_at=time())
            recorder.save_json(path, job)
            if hasattr(batch, 'finished_at'):
                batch.finished_at = monotonic()
            self.progress({'stage': 'enviado', 'completed': len(report['seen']), 'total': len(report['seen'])})
            await self.send_summary(job, bot, chat_id, path)
        except TelegramError as error:
            uncertain = job.get('status') == 'sending' and not isinstance(error, (BadRequest, Forbidden, RetryAfter))
            detail = 'No se pudo enviar el video a Telegram.'
            import httpx
            from recorder_network import network_failure
            current = error
            for _ in range(8):
                if isinstance(current, httpx.RequestError):
                    diagnosed = network_failure('sendVideo', current)
                    detail = str(diagnosed)
                    uncertain = job.get('status') == 'sending' and diagnosed.uncertain
                    break
                current = current.__cause__ or current.__context__ if current is not None else None
                if current is None:
                    break
            job.update(status='delivery_unknown' if uncertain else 'error', error_type=type(error).__name__)
            if uncertain and 'La entrega no está confirmada' not in detail:
                detail += ' Comprueba si el video llegó antes de reenviarlo.'
            message = detail if uncertain else f'{detail} Usa /video para reintentar.'
            self.emit('recording', {'stage': message, 'error': True, 'completed': 0, 'total': len(batch.order)})
            log.error('Comprobante | %s | Entrega incierta: %s', detail, uncertain)
            try:
                await bot.send_message(chat_id, '⚠️ Envío sin confirmar · Revisa el chat antes de usar /video reenviar'
                                       if uncertain else '❌ No se pudo enviar el video · Usa /video para reintentar')
            except TelegramError:
                pass
        except Exception as error:
            job.update(status='error', error_type=type(error).__name__)
            detail = str(error) if isinstance(error, (ValueError, CloudError)) else type(error).__name__
            if detail.startswith('Etapa: '):
                stage, _, reason = detail.removeprefix('Etapa: ').partition('. ')
                message = f'{recording_step(stage)}. {reason}'
            elif isinstance(error, (ValueError, CloudError)):
                message = detail
            else:
                step = self.last_recording_step or 'Preparando el comprobante'
                message = f'{step}. {recorder.recording_error_detail(error)}'
            self.emit('recording', {'stage': message, 'error': True, 'completed': 0, 'total': len(batch.order)})
            log.error('%s', message)
            try:
                await bot.send_message(chat_id, '❌ ' + message.removesuffix('.'))
            except TelegramError:
                pass
        finally:
            recorder.save_json(path, job)

    async def send_summary(self, job, bot, chat_id, path):
        if job.get('summary_status') in {'sent', 'delivery_unknown'}:
            return
        seconds = max(0, int(job['delivered_wall_at'] - job['started_wall_at']))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        elapsed = (f'{hours} h ' if hours else '') + f'{minutes} min {seconds:02d} s'
        text = (f'✅ Drop finalizado · {self.creator.name}\n\n'
                f'📦 Total del Drop: {len(job["post_ids_oldest_first"])}\n\n'
                f'⏱ Tiempo total: {elapsed}\n\n'
                f'🔄 Bot · {self.creator.name}\n\n'
                f'🗂 Total de post: {job["session_total"]} posts')
        if job['rejected']:
            text += f'\n\n⚠️ Mensajes rechazados: {len(job["rejected"])}'
        job['summary_status'] = 'delivery_unknown'
        recorder.save_json(path, job)
        try:
            message = await bot.send_message(chat_id, text, reply_markup=self.completion_markup)
            job.update(summary_status='sent', summary_message_id=message.message_id)
            self.emit('publication_summary', job.get('batch_id'))
        except TelegramError:
            log.warning('Comprobante entregado; no se confirmó el resumen final. No se duplicará el video.')
        recorder.save_json(path, job)

