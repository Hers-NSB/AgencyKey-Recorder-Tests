"""Independent, read-only AgencyKey recording pilot. Python 3.12+."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.local.json'
STATE = ROOT / 'private' / 'session.json'


def post_id(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r'[1-9][0-9]*', value):
        return value
    match = re.fullmatch(r'https://onlyfans\.com/([1-9][0-9]*)/[^/?#]+/?(?:[?#].*)?', value)
    if not match:
        raise ValueError('Usa un ID numérico o un enlace individual de OnlyFans.')
    return match[1]


def validate_config(data: dict) -> dict:
    url = urlparse(data.get('profile_url', ''))
    if url.scheme != 'https' or url.netloc != 'app.agencykey.com' or not re.fullmatch(r'/models/[0-9]+/?', url.path) or url.query or url.fragment:
        raise ValueError('El perfil debe ser https://app.agencykey.com/models/ID')
    ids = [post_id(str(value)) for value in data.get('post_ids_newest_first', [])]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Añade los IDs sin duplicados, del más reciente al más antiguo.')
    data = dict(data)
    data['post_ids_newest_first'] = ids
    return data


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def load_config() -> dict:
    if not CONFIG.exists():
        raise ValueError('Ejecuta primero la opción Configurar prueba.')
    return validate_config(json.loads(CONFIG.read_text(encoding='utf-8')))


def configure() -> None:
    print('Se usarán publicaciones existentes. No se enviará contenido a AgencyKey.')
    url = input('Perfil AgencyKey [https://app.agencykey.com/models/600912674]: ').strip()
    url = url or 'https://app.agencykey.com/models/600912674'
    print('Pega un enlace o ID por línea, del más reciente al más antiguo. Línea vacía para terminar.')
    ids = []
    while value := input('Post: ').strip():
        ids.append(post_id(value))
    config = validate_config({'profile_url': url, 'post_ids_newest_first': ids})
    save_json(CONFIG, config)
    print(f'Configurados {len(ids)} posts. Resolución 854×480, mínimo 3 segundos por post.')


async def login() -> None:
    from playwright.async_api import async_playwright
    config = load_config()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        try:
            page = await context.new_page()
            await page.goto(config['profile_url'], wait_until='domcontentloaded', timeout=60000)
            await asyncio.to_thread(input, 'Inicia sesión y abre el feed de la modelo. Después pulsa Enter aquí: ')
            if urlparse(page.url).netloc != 'app.agencykey.com' or not await page.locator('[id^="postId_"]').count():
                raise ValueError('No se encontró un feed de posts. Abre el perfil y vuelve a conectar.')
            STATE.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(STATE))
            STATE.chmod(0o600)
            print('Sesión guardada solo en esta PC. No se ha grabado el inicio de sesión.')
        finally:
            await browser.close()


# A recycled feed removes off-screen cards. Read only currently attached nodes.
SNAPSHOT = r'''() => [...document.querySelectorAll('[id^="postId_"]')].map(e => {
 const r=e.getBoundingClientRect();
 const p=e.closest('.b-post__wrapper');
 return {id:e.id.slice(7),top:r.top,bottom:r.bottom,height:r.height,
 pinned:e.classList.contains('m-pinned'),
 visible:r.bottom>100 && r.top<innerHeight && r.width>0 && r.height>0};
}).filter(p=>p.visible).sort((a,b)=>a.top-b.top)'''

IMAGES_READY = r'''() => {
 const cards=[...document.querySelectorAll('[id^="postId_"]')];
 return cards.every(card => {
  const c=card.getBoundingClientRect();
  if(c.bottom<=100 || c.top>=innerHeight) return true;
  return [...card.querySelectorAll('img')].every(img => {
   const r=img.getBoundingClientRect();
   if(!r.width || !r.height || r.bottom<=100 || r.top>=innerHeight) return true;
   return img.complete && img.naturalWidth>0;
  });
 });
}'''


async def images_ready(page, timeout: int = 30000) -> None:
    await page.wait_for_function(IMAGES_READY, timeout=timeout)


async def scroll_down(page, pixels: int = 190) -> None:
    # Mouse wheel targets the scrollable feed under the pointer, including nested containers.
    await page.mouse.move(640, 460)
    await page.mouse.wheel(0, pixels)
    await page.wait_for_timeout(500)


async def seek_start(page, newest: str, timeout: float = 120) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        cards = await page.evaluate(SNAPSHOT)
        target = next((p for p in cards if p['id'] == newest and not p['pinned']), None)
        if target:
            locator = page.locator(f'[id="postId_{newest}"]:not(.m-pinned)').first
            await locator.evaluate('e => e.scrollIntoView({block:"start",behavior:"instant"})')
            # Leave room for the fixed profile header.
            await page.mouse.wheel(0, -115)
            await page.wait_for_timeout(500)
            await images_ready(page)
            return target
        await scroll_down(page, 260)
    raise ValueError('No se localizó el primer post normal. Revisa IDs, modelo, sesión y posts fijados.')


async def capture_walk(page, ids: list[str], dwell: float = 3, timeout: float = 600) -> list[str]:
    seen: list[str] = []
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        await images_ready(page)
        cards = await page.evaluate(SNAPSHOT)
        for card in cards:
            # Begin the dwell only when the beginning of the post is below the header.
            if card['pinned'] or card['id'] not in ids or card['id'] in seen or not (100 <= card['top'] < 680):
                continue
            expected = ids[len(seen)]
            if card['id'] != expected:
                raise ValueError(f'Orden inesperado o post omitido: se esperaba {expected}, apareció {card["id"]}.')
            seen.append(card['id'])
            print(f'Grabando {len(seen)}/{len(ids)} · ID {card["id"]}', flush=True)
            await page.wait_for_timeout(dwell * 1000)
        last = next((p for p in cards if p['id'] == ids[-1] and not p['pinned']), None)
        if last and 100 < last['bottom'] <= 700 and seen == ids:
            await page.wait_for_timeout(dwell * 1000)
            return seen
        await scroll_down(page)
    raise ValueError(f'Recorrido incompleto: {len(seen)}/{len(ids)} posts. No se enviará el video.')


def ffmpeg_path() -> str:
    found = shutil.which('ffmpeg')
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def encode(source: Path, target: Path, start: float, duration: float) -> None:
    command = [ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
               '-ss', str(max(0, start)), '-t', str(duration), '-an', '-vf', 'scale=854:480',
               '-r', '20', '-c:v', 'libx264', '-preset', 'fast', '-crf', '24',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
    subprocess.run(command, check=True, capture_output=True)
    if not target.exists() or target.stat().st_size < 1000:
        raise ValueError('No se pudo generar un video válido.')


async def record(config: dict, *, fixture: Path | None = None, headless: bool = False, dwell: float = 3) -> Path:
    from playwright.async_api import async_playwright
    if not fixture and not STATE.exists():
        raise ValueError('Ejecuta primero Conectar AgencyKey.')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + __import__('uuid').uuid4().hex[:6]
    output = ROOT / 'output' / run_id
    output.mkdir(parents=True)
    report_path = output / 'report.json'
    report = {'status': 'incomplete', 'simulation': bool(fixture), 'post_ids': config['post_ids_newest_first'],
              'profile_url': config['profile_url'], 'resolution': '854x480', 'seen': [], 'created_at_utc': run_id}
    save_json(report_path, report)
    started = ended = epoch = 0.0
    raw = None
    error = None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        options = {'viewport': {'width': 1280, 'height': 720},
                   'record_video_dir': str(output / 'raw'), 'record_video_size': {'width': 854, 'height': 480}}
        if not fixture:
            options['storage_state'] = str(STATE)
        context = await browser.new_context(**options)
        # Browser video starts as the page is created. Trim setup/search from the exported MP4.
        epoch = monotonic()
        page = await context.new_page()
        try:
            url = fixture.resolve().as_uri() if fixture else config['profile_url']
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await seek_start(page, config['post_ids_newest_first'][0], timeout=10 if fixture else 120)
            started = max(0, monotonic() - epoch - .5)
            report['seen'] = await capture_walk(page, config['post_ids_newest_first'], dwell=dwell,
                                                 timeout=15 if fixture else 600)
            ended = monotonic() - epoch
        except Exception as exc:
            error = exc
            report['error'] = 'No se completó el recorrido. Revisa sesión, IDs, orden y carga de imágenes.'
        finally:
            await context.close()
            if page.video:
                raw = Path(await page.video.path())
            await browser.close()
    try:
        if error:
            raise ValueError(report['error']) from error
        video = output / 'comprobante.mp4'
        await asyncio.to_thread(encode, raw, video, started, ended - started)
        report.update(status='complete', duration_seconds=round(ended-started, 2),
                      bytes=video.stat().st_size, sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
                      video='comprobante.mp4')
        print(f'Video completo: {video}\nTamaño: {video.stat().st_size / 1_000_000:.2f} MB')
        return report_path
    finally:
        save_json(report_path, report)
        # Never retain setup/login navigation or incomplete captures.
        if raw and raw.exists():
            raw.unlink()
        if (output / 'raw').exists():
            shutil.rmtree(output / 'raw')


def verified_video(report_path: Path) -> tuple[dict, Path]:
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('status') != 'complete' or report.get('seen') != report.get('post_ids'):
        raise ValueError('El comprobante no está completo.')
    video = report_path.parent / 'comprobante.mp4'
    if hashlib.sha256(video.read_bytes()).hexdigest() != report.get('sha256'):
        raise ValueError('El video cambió después de la grabación.')
    if video.stat().st_size > 49_000_000:
        raise ValueError('El video supera el límite conservador de 49 MB; no se enviará.')
    return report, video


async def send(report_path: Path) -> None:
    from getpass import getpass
    import httpx
    report, video = verified_video(report_path)
    token = getpass('Token de tu BOT DE PRUEBAS (no se guarda): ').strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Formato de token inválido.')
    async with httpx.AsyncClient(base_url=f'https://api.telegram.org/bot{token}/', timeout=180) as client:
        async def api(method, **kwargs):
            try:
                response = await client.post(method, **kwargs)
                body = response.json()
                if not response.is_success or not body.get('ok'):
                    raise ValueError('Telegram rechazó la operación. Revisa token, permisos y chat.')
                return body['result']
            except httpx.HTTPError:
                raise ValueError('Error de red con Telegram. Comprueba el chat antes de reintentar.') from None
        me = await api('getMe')
        username = me.get('username', '')
        print(f'Bot de destino: @{username}')
        if input('Confirma que es tu bot de pruebas escribiendo su usuario sin @: ').strip() != username:
            raise ValueError('Envío cancelado.')
        webhook = await api('getWebhookInfo')
        if webhook.get('url'):
            raise ValueError('Este bot tiene un webhook activo. Usa uno de pruebas sin otro proceso activo.')
        code = 'recorder-' + __import__('secrets').token_hex(4)
        print(f'Envía este texto exacto al bot, en tu chat privado: {code}')
        input('Después pulsa Enter aquí: ')
        updates = await api('getUpdates', json={'timeout': 0, 'limit': 100})
        chats = {u['message']['chat']['id'] for u in updates if u.get('message', {}).get('text') == code
                 and u['message']['chat']['type'] == 'private'}
        if len(chats) != 1:
            raise ValueError('No se encontró un único chat con el código. No se envió nada.')
        chat_id = chats.pop()
        caption = ('SIMULACIÓN · ' if report.get('simulation') else '') + f'Comprobante de prueba · {len(report["seen"])} posts · 480p'
        with video.open('rb') as stream:
            result = await api('sendVideo', data={'chat_id': str(chat_id), 'caption': caption,
                                                  'supports_streaming': 'true'},
                               files={'video': ('comprobante.mp4', stream, 'video/mp4')})
        report['telegram'] = {'chat_id': chat_id, 'message_id': result['message_id']}
        save_json(report_path, report)
        print('Video enviado al chat del bot de pruebas.')


def latest_report() -> Path:
    reports = sorted((ROOT / 'output').glob('*/report.json'))
    if not reports:
        raise ValueError('Todavía no hay grabaciones.')
    return reports[-1]


def menu() -> None:
    while True:
        print('\nAgencyKey Recorder Tests — independiente de Dropper\n'
              '1. Configurar posts existentes\n2. Conectar AgencyKey\n3. Grabar prueba local\n'
              '4. Enviar último video al bot de pruebas\n5. Generar demo sin AgencyKey\n0. Salir')
        choice = input('Opción: ').strip()
        try:
            if choice == '0':
                return
            if choice == '1':
                configure()
            elif choice == '2':
                asyncio.run(login())
            elif choice == '3':
                asyncio.run(record(load_config()))
            elif choice == '4':
                asyncio.run(send(latest_report()))
            elif choice == '5':
                asyncio.run(record({'profile_url': 'SIMULACIÓN', 'post_ids_newest_first': ['300', '200', '100']},
                                   fixture=ROOT / 'tests' / 'feed.html'))
        except KeyboardInterrupt:
            print('\nOperación interrumpida.')
        except Exception as exc:
            # Third-party exceptions can contain request URLs; never echo them.
            detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            print(f'No se completó la operación: {detail}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='menu', choices=['menu', 'configure', 'login', 'record', 'send', 'demo'])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()
    if args.command == 'menu':
        menu()
    elif args.command == 'configure':
        configure()
    elif args.command == 'login':
        asyncio.run(login())
    elif args.command == 'record':
        asyncio.run(record(load_config(), headless=args.headless))
    elif args.command == 'send':
        asyncio.run(send(args.report or latest_report()))
    elif args.command == 'demo':
        asyncio.run(record({'profile_url': 'SIMULACIÓN', 'post_ids_newest_first': ['300', '200', '100']},
                           fixture=ROOT / 'tests' / 'feed.html', headless=args.headless))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrumpido.')
        sys.exit(130)
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f'Error: {detail}', file=sys.stderr)
        sys.exit(1)
