"""Independent, read-only AgencyKey recording pilot. Python 3.12+."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import random
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

RESOURCE_ROOT = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))
DEFAULT_DATA_ROOT = (Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
                     / 'AgencyKeyRecorderTests') if FROZEN else RESOURCE_ROOT
ROOT = Path(os.environ.get('AGENCYKEY_RECORDER_DATA_DIR', DEFAULT_DATA_ROOT)).expanduser().resolve()
if FROZEN:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(RESOURCE_ROOT / 'browser-tools')
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


def model_profile_url(creator_id) -> str:
    return f'https://app.agencykey.com/models/{int(creator_id)}'


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
    print(f'Configurados {len(ids)} posts. Video 854×480, recorrido continuo sin pausas fijas.')


def find_chrome() -> str | None:
    if sys.platform == 'win32':
        for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(variable)
            if base:
                path = Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'
                if path.is_file():
                    return str(path)
    return shutil.which('google-chrome') or shutil.which('google-chrome-stable')


async def launch_browser(playwright, *, headless: bool):
    try:
        return await playwright.chromium.launch(channel='chrome', headless=headless)
    except Exception as error:
        if not any(message in str(error) for message in ("Executable doesn't exist", "is not found", "not found at")):
            raise
    executable = find_chrome()
    if executable:
        return await playwright.chromium.launch(executable_path=executable, headless=headless)
    raise ValueError('No se encontró Google Chrome instalado. Instálalo o revisa su ubicación. No se descargó ningún navegador.')


async def check_chrome() -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await launch_browser(pw, headless=True)
        print(f'Chrome instalado disponible: {browser.version}')
        await browser.close()


async def save_login_session(page, context, profile_url: str, *, state_path: Path | None = None) -> None:
    state = state_path or STATE
    current, expected = urlparse(page.url), urlparse(profile_url)
    if (current.scheme != 'https' or current.netloc != 'app.agencykey.com'
            or current.path.rstrip('/') != expected.path.rstrip('/')):
        raise ValueError('Abre el perfil de la modelo configurada antes de guardar la sesión.')
    # The user has confirmed the profile is open. Virtual feeds may have no post nodes yet.
    state.parent.mkdir(parents=True, exist_ok=True)
    temporary = state.with_suffix('.tmp')
    try:
        await context.storage_state(path=str(temporary), indexed_db=True)
        temporary.chmod(0o600)
        temporary.replace(state)
    finally:
        temporary.unlink(missing_ok=True)


async def login() -> None:
    from playwright.async_api import async_playwright
    config = load_config()
    async with async_playwright() as pw:
        browser = await launch_browser(pw, headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        try:
            page = await context.new_page()
            await page.goto(config['profile_url'], wait_until='domcontentloaded', timeout=60000)
            await asyncio.to_thread(input, 'Inicia sesión y abre el feed de la modelo. Después pulsa Enter aquí: ')
            while True:
                try:
                    await save_login_session(page, context, config['profile_url'])
                    break
                except ValueError as error:
                    print(str(error))
                    choice = await asyncio.to_thread(input, 'Abre el perfil correcto y pulsa Enter, o escribe C para cancelar: ')
                    if choice.strip().lower() == 'c':
                        return
            print('Sesión guardada en esta PC. Los posts se comprobarán al elegir 3. Grabar prueba local.')
        finally:
            await browser.close()


# A recycled feed removes off-screen cards. Read only currently attached nodes.
SNAPSHOT = r'''() => [...document.querySelectorAll('[id^="postId_"]')].map(e => {
 const r=e.getBoundingClientRect();
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


async def frame_is_visible(page, frame) -> bool:
    """A card's local rectangle does not tell whether its iframe tab is visible."""
    while frame is not page.main_frame:
        if frame.is_detached() or frame.parent_frame is None:
            return False
        element = await frame.frame_element()
        visible = await element.evaluate(r'''e => {
            const r=e.getBoundingClientRect();
            if(!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) ||
               r.width<1 || r.height<1 || r.bottom<=0 || r.right<=0 ||
               r.top>=innerHeight || r.left>=innerWidth) return false;
            const x=(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2;
            const y=(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;
            return document.elementFromPoint(x,y)===e;
        }''')
        if not visible:
            return False
        frame = frame.parent_frame
    return not frame.is_detached()


async def post_frame(page, preferred_id=None):
    from playwright.async_api import Error as PlaywrightError

    first = None
    for frame in page.frames:
        try:
            if not await frame_is_visible(page, frame):
                continue
            visible_ids = await frame.locator('[id^="postId_"]').evaluate_all(
                """cards => cards.filter(e => e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})
                    && e.getBoundingClientRect().height>0).map(e => e.id.slice(7))""")
        except PlaywrightError as error:
            if frame.is_detached() or 'Execution context was destroyed' in str(error):
                continue
            raise
        if visible_ids:
            first = first or frame
            if preferred_id is None or preferred_id in visible_ids:
                return frame
    return first


async def scroll_frame(page, preferred_id=None):
    found = await post_frame(page, preferred_id)
    if found:
        return found
    # A profile header can fill a visible iframe before the recycled posts are mounted.
    largest, area = page.main_frame, 0
    for frame in page.frames:
        if frame is page.main_frame or not await frame_is_visible(page, frame):
            continue
        box = await (await frame.frame_element()).bounding_box()
        if box and box['width'] >= 400 and box['height'] >= 250:
            size = box['width'] * box['height']
            if size > area:
                largest, area = frame, size
    return largest


async def frame_geometry(page, frame):
    height = await frame.evaluate('innerHeight')
    if frame is page.main_frame:
        return 640, min(460, height - 30), height
    box = await (await frame.frame_element()).bounding_box()
    if not box:
        raise ValueError('El panel de publicaciones ya no está visible. Vuelve a abrir el perfil.')
    outer_height = await page.evaluate('innerHeight')
    visible_height = min(height, outer_height - box['y'])
    if visible_height < 150:
        raise ValueError('El panel de publicaciones no tiene espacio visible suficiente.')
    return box['x'] + box['width'] / 2, max(110, box['y'] + visible_height / 2), visible_height


IMAGE_TIMEOUT_MESSAGE = 'Las imágenes visibles del feed tardaron demasiado en cargar'


async def images_ready(page, timeout: int = 20000, *, frame=None) -> None:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    try:
        await (frame or page.main_frame).wait_for_function(IMAGES_READY, timeout=timeout)
    except PlaywrightTimeoutError as error:
        raise PlaywrightTimeoutError(IMAGE_TIMEOUT_MESSAGE) from error


async def confirm_start(page, frame, newest: str) -> dict:
    # Recheck after images settle: a recycled feed can replace the node while awaiting.
    await images_ready(page, frame=frame)
    if not await frame_is_visible(page, frame):
        raise ValueError('El primer post está en un panel oculto. No se inició el comprobante.')
    await frame.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    cards = await frame.evaluate(SNAPSHOT)
    target = next((card for card in cards if card['id'] == newest and not card['pinned']
                   and 95 <= card['top'] <= 145), None)
    if not target:
        raise ValueError(f'El post {newest} ya no está encuadrado en el panel visible. No se inició el comprobante.')
    return {'post_id': newest, 'frame_index': page.frames.index(frame),
            'top': round(target['top'], 2), 'images_ready': True, 'visible': True}


def wheel_steps(pixels: int, *, rng=None) -> list[tuple[int, int]]:
    """Continuous wheel events, without a rest between gestures."""
    rng = rng or random
    distance = abs(round(pixels))
    if not distance:
        return []
    count = min(distance, max(6, math.ceil(distance / 16)))
    weights = [(1 + .12 * math.sin(math.pi * (i + .5) / count)) * rng.uniform(.96, 1.04) for i in range(count)]
    total = sum(weights)
    sign = 1 if pixels > 0 else -1
    result = []
    accumulated = previous = 0
    for weight in weights:
        accumulated += weight
        position = round(distance * accumulated / total)
        delta = position - previous
        if delta:
            result.append((sign * delta, rng.randint(25, 31)))
        previous = position
    return result


async def scroll_down(page, pixels: int = 190, *, frame=None) -> None:
    frame = frame or page.main_frame
    x, y, _ = await frame_geometry(page, frame)
    await page.mouse.move(x, y)
    for delta, pause in wheel_steps(pixels):
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(pause)


async def seek_start(page, newest: str, timeout: float = 120) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        frame = await scroll_frame(page, newest)
        cards = await frame.evaluate(SNAPSHOT)
        target = next((p for p in cards if p['id'] == newest and not p['pinned']), None)
        if target:
            locator = frame.locator(f'[id="postId_{newest}"]:not(.m-pinned)').first
            await locator.evaluate('e => e.scrollIntoView({block:"start",behavior:"instant"})')
            x, y, _ = await frame_geometry(page, frame)
            await page.mouse.move(x, y)
            await page.mouse.wheel(0, -115)
            await page.wait_for_timeout(500)
            await images_ready(page, frame=frame)
            # A selector match is not sufficient: verify the requested post is actually framed.
            for _ in range(3):
                top = await locator.evaluate('e => e.getBoundingClientRect().top')
                if 95 <= top <= 145:
                    break
                await scroll_down(page, round(top - 115), frame=frame)
            else:
                raise ValueError(f'No se pudo encuadrar el post {newest}. No se inició el comprobante.')
            await confirm_start(page, frame, newest)
            target['_frame'] = frame
            return target
        await scroll_down(page, 260, frame=frame)
    raise ValueError('No se localizó el primer post. Revisa los IDs, la modelo y si la sesión sigue iniciada.')


async def prepare_feed(page, ids, *, timeout=600, on_progress=None, profile_url=None):
    """Warm the entire batch, including lazy images, before marking the video start.

    Virtual feeds remove off-screen cards, so waiting for all nodes at once never completes.
    """
    deadline = monotonic() + timeout
    feed_deadline = min(deadline, monotonic() + 35)
    expected = urlparse(profile_url) if profile_url else None
    from playwright.async_api import Error as PlaywrightError

    while monotonic() < feed_deadline:
        current = urlparse(page.url)
        path = current.path.lower().split('/')
        if current.netloc == 'app.agencykey.com' and any(
                part in {'login', 'sign-in', 'signin', 'auth', '2fa', 'mfa'} for part in path):
            raise ValueError('AgencyKey volvió a pedir inicio de sesión. Pulsa «Conectar AgencyKey» en el panel web.')
        if expected and (current.scheme, current.netloc, current.path.rstrip('/')) != (
                expected.scheme, expected.netloc, expected.path.rstrip('/')):
            await page.wait_for_timeout(500)
            continue
        if await post_frame(page, ids[0]):
            break
        # The profile header can occupy the full view before lazy cards are mounted.
        try:
            await scroll_down(page, 220, frame=await scroll_frame(page))
        except PlaywrightError as error:
            if page.is_closed():
                raise
            if not any(message in str(error) for message in
                       ('Execution context was destroyed', 'Frame was detached', 'Frame has been detached')):
                raise
        await page.wait_for_timeout(500)
    else:
        raise ValueError('No pudimos abrir las publicaciones de esta modelo. Comprueba su acceso con «Verificar feed» en el panel web.')
    first = await seek_start(page, ids[0], timeout=max(.1, min(30, deadline-monotonic())))
    def progress(value):
        if on_progress:
            on_progress(dict(value, stage='cargando feed e imágenes'))
    await capture_walk(page, ids, timeout=max(.1, deadline-monotonic()), frame=first['_frame'], on_progress=progress)
    # Reset every scrolling ancestor inside the active feed, without reloading the page.
    await first['_frame'].evaluate('''() => {
        const card=document.querySelector('[id^="postId_"]');
        for(let node=card?.parentElement;node;node=node.parentElement) node.scrollTop=0;
        window.scrollTo({top:0,behavior:'instant'});
    }''')
    await page.wait_for_timeout(500)
    return await seek_start(page, ids[0], timeout=max(.1, min(30, deadline-monotonic())))


async def capture_walk(page, ids: list[str], dwell: float = 0, timeout: float = 600, *, frame=None, seen=None, on_progress=None) -> list[str]:
    frame = frame or await post_frame(page) or page.main_frame
    seen = [] if seen is None else seen
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if frame.is_detached():
            raise ValueError('El panel de publicaciones se recargó. Repite únicamente la grabación.')
        if not await frame_is_visible(page, frame):
            raise ValueError('El panel de publicaciones quedó oculto durante el recorrido. Repite la grabación.')
        await images_ready(page, frame=frame)
        _, _, height = await frame_geometry(page, frame)
        cards = await frame.evaluate(SNAPSHOT)
        for card in cards:
            if card['pinned'] or card['id'] not in ids or card['id'] in seen or not (100 <= card['top'] < height - 40):
                continue
            expected = ids[len(seen)]
            if card['id'] != expected:
                raise ValueError(f'Orden inesperado o post omitido: se esperaba {expected}, apareció {card["id"]}.')
            seen.append(card['id'])
            if on_progress:
                on_progress({'stage': 'grabando', 'completed': len(seen), 'total': len(ids), 'post_id': card['id']})
            print(f'Grabando {len(seen)}/{len(ids)} · ID {card["id"]}', flush=True)
            await page.wait_for_timeout(dwell * 1000)
        last = next((p for p in cards if p['id'] == ids[-1] and not p['pinned']), None)
        if last and 100 < last['bottom'] <= height - 20 and seen == ids:
            await page.wait_for_timeout(dwell * 1000)
            return seen
        await scroll_down(page, frame=frame)
    raise ValueError(f'Recorrido incompleto: {len(seen)}/{len(ids)} posts. No se enviará el video.')


def ffmpeg_path() -> str:
    if FROZEN:
        path = RESOURCE_ROOT / 'encoder' / 'ffmpeg.exe'
        if not path.is_file():
            raise ValueError('Falta el codificador incluido. Vuelve a descargar el EXE completo.')
        return str(path)
    found = shutil.which('ffmpeg') if not FROZEN else None
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


BOUNDARY_JS = r"""async (visible) => {
    document.getElementById('agencykey-recorder-boundary')?.remove();
    if (visible) {
        const marker=document.createElement('div'); marker.id='agencykey-recorder-boundary';
        marker.style.cssText='all:initial!important;position:fixed!important;left:0!important;top:0!important;width:96px!important;height:48px!important;z-index:2147483647!important;pointer-events:none!important;background:linear-gradient(to right,rgb(251,0,251) 50%,rgb(0,251,80) 50%)!important;';
        document.documentElement.appendChild(marker);
    }
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}"""


async def video_boundary(page) -> None:
    # These synchronization frames are excluded from the exported video.
    await page.evaluate(BOUNDARY_JS, True)
    await page.wait_for_timeout(550)
    await page.evaluate(BOUNDARY_JS, False)
    await page.wait_for_timeout(120)


def boundary_intervals(samples: bytes) -> tuple[float, float]:
    if len(samples) % 6:
        raise ValueError('No se pudo comprobar el inicio y fin del video.')
    runs = []
    first = None
    for index in range(len(samples) // 6 + 1):
        pixel = samples[index*6:index*6+6]
        marker = (len(pixel) == 6 and pixel[0] > 210 and pixel[1] < 45 and pixel[2] > 210
                  and pixel[3] < 45 and pixel[4] > 210 and 35 < pixel[5] < 135)
        if marker and first is None:
            first = index
        elif not marker and first is not None:
            if index - first >= 4:
                runs.append((first, index))
            first = None
    if len(runs) != 2:
        raise ValueError(f'No se verificaron los límites de grabación ({len(runs)}/2). No se enviará un video incompleto.')
    start = (runs[0][1] + 1) / 25
    end = (runs[1][0] - 1) / 25
    if end <= start:
        raise ValueError('El recorrido grabado no tiene una duración válida.')
    return start, end


def video_bounds(source: Path) -> tuple[float, float]:
    result = subprocess.run([ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-i', str(source),
                             '-an', '-vf', 'fps=25,crop=64:4:0:8,format=rgb24',
                             '-pix_fmt', 'rgb24', '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo', 'pipe:1'],
                            check=True, capture_output=True)
    raw = result.stdout
    frame_bytes = 64 * 4 * 3
    if len(raw) % frame_bytes:
        raise ValueError('No se pudieron leer los límites del video.')
    samples = b''.join(raw[i + (64+8)*3:i + (64+8)*3+3] + raw[i + (64+48)*3:i + (64+48)*3+3]
                       for i in range(0, len(raw), frame_bytes))
    return boundary_intervals(samples)


def encode(source: Path, target: Path, start: float, duration: float) -> None:
    command = [ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
               '-ss', str(max(0, start)), '-t', str(duration), '-an', '-vf', 'scale=854:480',
               '-r', '20', '-c:v', 'libx264', '-preset', 'fast', '-crf', '24',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
    subprocess.run(command, check=True, capture_output=True)
    if not target.exists() or target.stat().st_size < 1000:
        raise ValueError('No se pudo generar un video válido.')


async def failure_diagnostics(page) -> list[dict]:
    """Only collect geometry and load state; omit URLs, text and session data."""
    result = []
    for index, frame in enumerate(page.frames):
        if frame.is_detached():
            continue
        try:
            cards = await frame.evaluate(SNAPSHOT)
            images = await frame.evaluate(r'''() => [...document.querySelectorAll('[id^="postId_"] img')]
                .filter(img => { const r=img.getBoundingClientRect();
                    return r.width>0 && r.height>0 && r.bottom>100 && r.top<innerHeight; })
                .map(img => ({post_id:img.closest('[id^="postId_"]').id.slice(7),
                    complete:img.complete, loaded:img.naturalWidth>0}))''')
            result.append({'frame_index': index, 'visible': await frame_is_visible(page, frame),
                           'cards': cards, 'images': images})
        except Exception:
            result.append({'frame_index': index, 'unavailable': True})
    return result


async def pause_failed_test(page) -> None:
    if page.is_closed():
        return
    print('Chrome queda abierto en el punto del fallo para revisarlo.', flush=True)
    try:
        await asyncio.to_thread(input, 'Pulsa Enter en esta consola para cerrar Chrome: ')
    except EOFError:
        pass


async def record(config: dict, *, fixture: Path | None = None, headless: bool = False, dwell: float = 0,
                 session_path: Path | None = None, on_progress=None, on_preview=None, stop_event=None,
                 session_state=None, on_session_saved=None, on_browser_failure=None) -> Path:
    from playwright.async_api import async_playwright
    state = session_path or STATE
    if not fixture and session_state is None and not state.exists():
        raise ValueError('Conecta la sesión compartida de AgencyKey desde la web.')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + __import__('uuid').uuid4().hex[:6]
    output = ROOT / 'output' / run_id
    output.mkdir(parents=True)
    report_path = output / 'report.json'
    report = {'status': 'incomplete', 'simulation': bool(fixture), 'post_ids': config['post_ids_newest_first'],
              'profile_url': config['profile_url'], 'resolution': '854x480', 'seen': [], 'created_at_utc': run_id,
              'first_post_id': config['post_ids_newest_first'][0], 'headless': headless, 'post_hold_seconds': dwell}
    save_json(report_path, report)
    started = ended = 0.0
    raw = None
    error = None
    def stage(value):
        report['stage'] = value
        if on_progress:
            on_progress({'stage': value, 'completed': len(report['seen']), 'total': len(report['post_ids'])})

    async with async_playwright() as pw:
        stage('iniciando Chrome')
        browser = await launch_browser(pw, headless=headless)
        options = {'viewport': {'width': 1280, 'height': 720},
                   'record_video_dir': str(output / 'raw'), 'record_video_size': {'width': 854, 'height': 480}}
        if not fixture:
            options['storage_state'] = session_state if session_state is not None else str(state)
        context = await browser.new_context(**options)
        page = await context.new_page()
        async def monitor():
            while not page.is_closed():
                if stop_event and stop_event.is_set():
                    await page.close()
                    return
                if on_preview:
                    try:
                        on_preview(await page.screenshot(type='png', timeout=2000))
                    except Exception:
                        pass
                await asyncio.sleep(1.5)
        monitor_task = asyncio.create_task(monitor())
        try:
            stage('abrir perfil')
            print('Etapa: abrir perfil', flush=True)
            url = fixture.resolve().as_uri() if fixture else config['profile_url']
            from playwright.async_api import Error as BrowserError
            try:
                response = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            except BrowserError as error:
                transient = ('ERR_NETWORK_CHANGED', 'ERR_INTERNET_DISCONNECTED', 'ERR_CONNECTION_RESET',
                             'ERR_TIMED_OUT', 'ERR_CONNECTION_CLOSED')
                if fixture or (stop_event and stop_event.is_set()) or not any(code in str(error) for code in transient):
                    raise
                stage('reintentando abrir el perfil por un fallo de conexión')
                await asyncio.sleep(2)
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

            if not fixture and response is not None:
                if response.status == 401:
                    raise ValueError('AgencyKey pide iniciar sesión · Reconecta desde la web')
                if response.status in (403, 404):
                    raise ValueError('AgencyKey no permite abrir las publicaciones de esta modelo. Revisa sus permisos en el panel web.')
                if response.status >= 500:
                    raise ValueError('AgencyKey no pudo cargar el perfil. Usa /video para intentarlo de nuevo.')
            stage('cargando feed e imágenes')
            print(f'Etapa: {report["stage"]} · ID {report["first_post_id"]}', flush=True)
            preload_limit = 45 if fixture else min(180, 55 + 4 * len(report['post_ids']))
            try:
                async with asyncio.timeout(preload_limit):
                    first = await prepare_feed(page, config['post_ids_newest_first'], timeout=preload_limit,
                                               on_progress=on_progress, profile_url=None if fixture else url)
            except TimeoutError as exc:
                raise ValueError('Se agotó la espera del feed. Usa /video para reintentar el comprobante') from exc
            report['feed_preloaded'] = True
            print(f'Inicio del comprobante: post {config["post_ids_newest_first"][0]} · segundo plano: {headless}', flush=True)
            stage('marcar inicio del video')
            report['start_verified'] = await confirm_start(page, first['_frame'], report['first_post_id'])
            await video_boundary(page)
            stage('recorrer posts / cargar imágenes')
            walk_limit = 30 if fixture else max(preload_limit, 30 + len(report['post_ids']) * (dwell + 4))
            try:
                async with asyncio.timeout(walk_limit):
                    await capture_walk(page, config['post_ids_newest_first'], dwell=dwell, timeout=walk_limit,
                                       frame=first['_frame'], seen=report['seen'], on_progress=on_progress)
            except TimeoutError as exc:
                raise ValueError('Se agotó el tiempo de grabación · Usa /video para reintentar el comprobante') from exc
            await page.wait_for_timeout(120)
            stage('marcar fin del video')
            await video_boundary(page)
        except Exception as exc:
            error = exc
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            report['error_type'] = type(exc).__name__
            if stop_event and stop_event.is_set():
                exc = ValueError('Grabación detenida · Usa /video para reintentar el comprobante')
                error = exc
                report['error_type'] = 'RecordingStopped'
            reason = str(exc) if isinstance(exc, ValueError) or (
                isinstance(exc, PlaywrightTimeoutError) and str(exc) == IMAGE_TIMEOUT_MESSAGE
            ) else (
                'Se agotó el tiempo de espera del navegador.' if isinstance(exc, PlaywrightTimeoutError)
                else 'Chrome se cerró durante la grabación.' if page.is_closed()
                else 'Chrome no pudo completar este paso. Usa /video para intentarlo de nuevo.')
            report['error'] = f'Etapa: {report["stage"]}. {reason}'
            report['next_post_id'] = next((pid for pid in report['post_ids'] if pid not in report['seen']), None)
            try:
                async with asyncio.timeout(5):
                    report['diagnostics'] = await failure_diagnostics(page)
            except TimeoutError:
                report['diagnostics'] = []
            save_json(report_path, report)
            print(f'{report["error"]}\nPosts comprobados: {len(report["seen"])}/{len(report["post_ids"])}'
                  f' · siguiente ID: {report["next_post_id"]}\nInforme: {report_path}', flush=True)
            if not headless and not fixture and not page.is_closed() and not (stop_event and stop_event.is_set()):
                if on_browser_failure:
                    await on_browser_failure(page, report['stage'], reason)
                else:
                    await pause_failed_test(page)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            try:
                if not fixture and error is None:
                    try:
                        if session_state is not None:
                            if on_session_saved:
                                await on_session_saved(await context.storage_state(indexed_db=True))
                        else:
                            await save_login_session(page, context, config['profile_url'], state_path=state)
                        report['session_refreshed'] = True
                    except Exception as refresh_error:
                        report['session_refresh_error'] = type(refresh_error).__name__
                        if on_progress:
                            on_progress({'stage': 'Aviso: no se pudo actualizar la sesión guardada',
                                         'completed': len(report['seen']), 'total': len(report['post_ids'])})
                await context.close()
                # Failed runs discard raw capture; asking for its path can itself
                # fail when Chrome closed before the video artifact was created.
                if not error and page.video:
                    raw = Path(await page.video.path())
            finally:
                await browser.close()
    try:
        if error:
            raise ValueError(report['error']) from error
        stage('verificar límites del video')
        started, ended = await asyncio.to_thread(video_bounds, raw)
        stage('convertir video a MP4')
        video = output / 'comprobante.mp4'
        await asyncio.to_thread(encode, raw, video, started, ended - started)
        report.update(status='complete', stage='completo', duration_seconds=round(ended-started, 2),
                      bytes=video.stat().st_size, sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
                      video='comprobante.mp4')
        if on_progress:
            on_progress({'stage': 'video listo', 'completed': len(report['seen']), 'total': len(report['post_ids'])})
        print(f'Video completo: {video}\nTamaño: {video.stat().st_size / 1_000_000:.2f} MB')
        return report_path
    except Exception as exc:
        report.setdefault('error_type', type(exc).__name__)
        raise
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


TOKEN_DIALOG_SCRIPT = r"""
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = 'AgencyKey Recorder Tests - Telegram'
$form.ClientSize = New-Object System.Drawing.Size(470,155)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$label = New-Object System.Windows.Forms.Label
$label.Text = 'Pega el token del BOT DE PRUEBAS con Ctrl+V. No se guarda.'
$label.SetBounds(15,15,440,30)
$entry = New-Object System.Windows.Forms.TextBox
$entry.SetBounds(15,50,440,26)
$entry.UseSystemPasswordChar = $true
$entry.ShortcutsEnabled = $true
$ok = New-Object System.Windows.Forms.Button
$ok.Text = 'Usar token'
$ok.SetBounds(235,100,105,30)
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancelar'
$cancel.SetBounds(350,100,105,30)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.AddRange(@($label,$entry,$ok,$cancel))
$form.AcceptButton = $ok
$form.CancelButton = $cancel
$form.Add_Shown({[void]$entry.Focus()})
try {
    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Out.Write($entry.Text.Trim())
    } else { exit 2 }
} finally { $entry.Clear(); $form.Dispose() }
"""


def read_bot_token() -> str:
    if sys.platform != 'win32':
        from getpass import getpass
        return getpass('Token del BOT DE PRUEBAS (oculto, no se guarda): ').strip()
    powershell = shutil.which('powershell.exe')
    if not powershell:
        raise ValueError('No se encontró Windows PowerShell para abrir el campo de token.')
    result = subprocess.run([powershell, '-NoProfile', '-STA', '-Command', TOKEN_DIALOG_SCRIPT],
                            capture_output=True, text=True, encoding='utf-8',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode == 2:
        raise ValueError('Envío cancelado.')
    if result.returncode:
        raise ValueError('No se pudo abrir el campo de token de Telegram.')
    return result.stdout.strip()


async def send(report_path: Path) -> None:
    import httpx
    from recorder_network import TelegramFailure, telegram_connection_options, telegram_request
    report, video = verified_video(report_path)
    if report.get('telegram', {}).get('message_id'):
        raise ValueError('Este comprobante ya tiene un envío confirmado en Telegram.')
    previous = report.get('telegram_attempt', {}).get('status')
    if previous in {'sending', 'delivery_unknown'}:
        if input('El envío anterior no está confirmado. Revisa el chat; escribe REENVIAR solo si no llegó: ').strip() != 'REENVIAR':
            raise ValueError('Reenvío cancelado.')
    token = read_bot_token()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Formato de token inválido.')
    options = telegram_connection_options()
    async with httpx.AsyncClient(base_url=f'https://api.telegram.org/bot{token}/',
                                 timeout=httpx.Timeout(180, connect=30, pool=30),
                                 follow_redirects=False, **options) as client:
        async def api(method, **kwargs):
            print(f'Telegram · {method}', flush=True)
            try:
                return await telegram_request(client, method, **kwargs)
            except TelegramFailure as error:
                report['telegram_attempt'] = {'status': 'delivery_unknown' if error.uncertain else 'failed',
                                              'method': error.method, 'category': error.category}
                save_json(report_path, report)
                raise
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
        report['telegram_attempt'] = {'status': 'sending', 'method': 'sendVideo', 'chat_id': chat_id}
        save_json(report_path, report)
        with video.open('rb') as stream:
            result = await api('sendVideo', data={'chat_id': str(chat_id), 'caption': caption,
                                                  'supports_streaming': 'true'},
                               files={'video': ('comprobante.mp4', stream, 'video/mp4')})
        report['telegram'] = {'chat_id': chat_id, 'message_id': result['message_id']}
        report['telegram_attempt'] = {'status': 'sent', 'method': 'sendVideo'}
        save_json(report_path, report)
        print('Video enviado al chat del bot de pruebas.')


def latest_report() -> Path:
    reports = sorted((ROOT / 'output').glob('*/report.json'))
    if not reports:
        raise ValueError('Todavía no hay grabaciones.')
    return reports[-1]


def menu(*, headless: bool = False) -> None:
    print(f'Chrome instalado · navegador {"oculto" if headless else "visible"} · movimiento continuo.')
    print(f'Carpeta de datos y videos: {ROOT}')
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
                asyncio.run(record(load_config(), headless=headless))
            elif choice == '4':
                asyncio.run(send(latest_report()))
            elif choice == '5':
                asyncio.run(record({'profile_url': 'SIMULACIÓN', 'post_ids_newest_first': ['200', '100']},
                                   fixture=RESOURCE_ROOT / 'tests' / 'feed.html', headless=headless))
        except KeyboardInterrupt:
            print('\nOperación interrumpida.')
        except Exception as exc:
            # Third-party exceptions can contain request URLs; never echo them.
            detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            print(f'No se completó la operación: {detail}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='menu', choices=['menu', 'configure', 'login', 'record', 'send', 'demo', 'check-chrome'])
    parser.add_argument('--report', type=Path)
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument('--headless', action='store_true', help='Grabar sin ventana explícitamente.')
    visibility.add_argument('--show-browser', action='store_true', help='Mostrar Chrome durante una prueba (predeterminado).')
    parser.add_argument('--check-token-input', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--check-telegram-support', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_telegram_support:
        from recorder_network import check_telegram_support
        asyncio.run(check_telegram_support())
        return
    if args.check_token_input:
        token = read_bot_token()
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
            raise ValueError('Formato de token inválido.')
        print('Token recibido correctamente (oculto).')
        return
    if args.command == 'check-chrome':
        asyncio.run(check_chrome())
    elif args.command == 'menu':
        menu(headless=args.headless)
    elif args.command == 'configure':
        configure()
    elif args.command == 'login':
        asyncio.run(login())
    elif args.command == 'record':
        asyncio.run(record(load_config(), headless=args.headless))
    elif args.command == 'send':
        asyncio.run(send(args.report or latest_report()))
    elif args.command == 'demo':
        asyncio.run(record({'profile_url': 'SIMULACIÓN', 'post_ids_newest_first': ['200', '100']},
                           fixture=RESOURCE_ROOT / 'tests' / 'feed.html', headless=args.headless))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrumpido.')
        sys.exit(130)
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f'Error: {detail}', file=sys.stderr)
        if FROZEN and len(sys.argv) == 1:
            input('Pulsa Enter para cerrar: ')
        sys.exit(1)


