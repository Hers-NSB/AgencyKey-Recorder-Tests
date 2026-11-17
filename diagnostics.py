"""Local, shareable failure reports. Never export browser storage or raw HTML."""
import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import traceback
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from config import ConsoleFormatter, log


def redact(text):
    record = logging.LogRecord('diagnostic', logging.ERROR, '', 0, str(text), (), None)
    text = ConsoleFormatter('%(message)s').format(record)
    text = re.sub(r'https?://[^\s<>\"\']+', lambda m: safe_url(m[0]), text)
    text = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [oculto]', text)
    text = re.sub(r'\b\d{6,}:[A-Za-z0-9_-]{20,}\b', '[oculto]', text)
    return re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[oculto]', text)


def safe_url(value):
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        if url.scheme == 'https' and (host == 'app.agencykey.com'
                or re.fullmatch(r'of-\d+\.agencykey\.com', host)):
            path = url.path if (re.fullmatch(r'/models/\d+/?', url.path)
                                or re.fullmatch(r'/[a-zA-Z0-9_]{1,64}/?', url.path)) else '/[ruta omitida]'
            return 'https://' + host + path
    except ValueError:
        pass
    return '[URL omitida]'


async def capture_failure(page, *, kind, profile_url, username=None, error=None, status=None, post_ids=(), stage=None,
                          http_status=None):
    """Bounded best-effort capture; a broken browser must not hide the original error."""
    import recorder
    folder = recorder.ROOT / 'diagnostics' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '-' + uuid4().hex[:8])
    try:
        folder.mkdir(parents=True)
        report = dict(kind=kind, created_at_utc=datetime.now(timezone.utc).isoformat(),
                      expected_url=safe_url(profile_url), expected_username=username,
                      stage=stage, status=status, http_status=http_status, post_ids=list(post_ids), frames=[])
        report['observed_username'] = getattr(error, 'observed', None)
        if error is not None:
            report.update(error_type=type(error).__name__, error=redact(error),
                          traceback=redact(''.join(traceback.format_exception(error))))
        def save_report():
            temporary = folder / 'diagnostic.tmp'
            recorder.save_json(temporary, report)
            temporary.replace(folder / 'diagnostic.json')
        save_report()
        try:
            async with asyncio.timeout(6):
                report['opened_url'] = safe_url(page.url)
                report['browser_closed'] = page.is_closed()
                if not report['browser_closed']:
                    report['frames'] = await recorder.failure_diagnostics(page)
                    for entry in report['frames']:
                        frame = page.frames[entry['frame_index']]
                        entry['url'] = safe_url(frame.url)
                        identity = recorder.profile_frame_identity(frame)
                        entry['identity'] = list(identity) if identity else None
                        entry['profile_header'] = await frame.locator(recorder.PROFILE_HEADER).first.is_visible()
                        entry['profile_menu'] = await frame.get_by_text(
                            re.compile(r'^\s*(?:Mi perfil|My profile)\s*$', re.IGNORECASE)).first.is_visible()
                        entry['viewport'] = await frame.evaluate('''() => ({width:innerWidth,height:innerHeight,
                            scrollTop:document.scrollingElement?.scrollTop,
                            scrollHeight:document.scrollingElement?.scrollHeight})''')
        except Exception as exc:
            report['inspection_error'] = type(exc).__name__
        try:
            async with asyncio.timeout(4):
                if not page.is_closed() and not await recorder.agencykey_sign_in_visible(page):
                    mask = [frame.locator('input, textarea, [contenteditable], pre, code, [data-sensitive]')
                            for frame in page.frames if not frame.is_detached()]
                    await page.screenshot(path=str(folder / 'chrome.tmp.png'), timeout=3000, mask=mask)
                    (folder / 'chrome.tmp.png').replace(folder / 'chrome.png')
                    report['screenshot'] = 'chrome.png'
                else:
                    report['screenshot_omitted'] = 'login_or_closed'
        except Exception as exc:
            report['screenshot_error'] = type(exc).__name__
        save_report()
        log.error('Diagnóstico de %s guardado · Usa Guardar registro para exportarlo · %s', kind, folder.name)
        return folder
    except Exception as exc:
        log.warning('No se pudo guardar el diagnóstico (%s)', type(exc).__name__)
        return None


def export_diagnostics(destination, activity):
    import recorder
    root = recorder.ROOT / 'diagnostics'
    folders = sorted((p for p in root.glob('*') if p.is_dir() and not p.is_symlink()), reverse=True)[:20]
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('recorder-registro.txt', redact(activity))
        archive.writestr('LEEME.txt', 'Registro y últimos 20 diagnósticos locales de verificación y grabación.\n'
                          'Las capturas muestran la página en el momento del fallo.\n'
                          'No se incluyen archivos de sesión, cookies, configuración ni HTML.\n')
        for folder in folders:
            # Whitelist generated artifacts; never traverse session/output directories.
            for name in ('diagnostic.json', 'chrome.png'):
                source = folder / name
                if source.is_file() and not source.is_symlink():
                    target = f'diagnosticos/{folder.name}/{name}'
                    if name.endswith('.json'):
                        def clean(value):
                            if isinstance(value, str):
                                return redact(value)
                            if isinstance(value, dict):
                                return {key: clean(item) for key, item in value.items()}
                            if isinstance(value, list):
                                return [clean(item) for item in value]
                            return value
                        report = clean(json.loads(source.read_text(encoding='utf-8')))
                        archive.writestr(target, json.dumps(report, ensure_ascii=False, indent=2))
                    else:
                        archive.write(source, target)
    return len(folders)
