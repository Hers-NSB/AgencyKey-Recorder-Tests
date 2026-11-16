"""Diagnóstico independiente de Mi perfil (Python 3.12, Google Chrome y Playwright)."""

import asyncio
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import os
import re
import shutil
import sys
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from urllib.parse import urlparse

PROFILE_HEADER = 'main#content .js-compact-sticky-header'
SIGN_IN = 'https://app.agencykey.com/auth/signin'
VIEWPORT = {'width': 1280, 'height': 720}

# Funciones de verificación tomadas de recorder.py y recording_service.py.
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


def frame_matches_model(frame, profile_url):
    if not profile_url:
        return True
    model_id = urlparse(profile_url).path.rstrip('/').rsplit('/', 1)[-1]
    while frame.parent_frame is not None:
        host = urlparse(frame.url).hostname or ''
        if host.startswith('of-') and host.endswith('.agencykey.com') and host != f'of-{model_id}.agencykey.com':
            return False
        frame = frame.parent_frame
    return True


class FeedAccessError(ValueError):
    def __init__(self, status, message, *, observed=None):
        super().__init__(message)
        self.status = status
        self.observed = observed


async def agencykey_sign_in_visible(page):
    current = urlparse(page.url)
    if current.netloc != 'app.agencykey.com':
        return False
    return (any(part in {'login', 'sign-in', 'signin', 'auth', '2fa', 'mfa'}
                for part in current.path.lower().split('/'))
            or await page.locator('input[type="password"]:visible').first.is_visible())


async def agencykey_login_complete(page):
    from playwright.async_api import Error as BrowserError

    current = urlparse(page.url)
    if (current.scheme, current.netloc) != ('https', 'app.agencykey.com'):
        return False
    try:
        return not await agencykey_sign_in_visible(page) and await page.locator('body').is_visible()
    except BrowserError:
        return False


async def my_profile_visible(page):
    # Profile-specific controls also work when the sidebar has no ARIA selected state.
    edit = re.compile(r'^\s*(?:Editar perfil|Edit profile)\s*$', re.IGNORECASE)
    search = re.compile(r'Buscar (?:la publicación|publicaciones) del usuario|Search (?:user.?s? )?posts', re.IGNORECASE)
    for frame in page.frames:
        if await frame_is_visible(page, frame):
            if (await frame.locator(PROFILE_HEADER).first.is_visible()
                    or await frame.get_by_text(edit).first.is_visible()
                    or await frame.get_by_placeholder(search).first.is_visible()):
                return True
    return False


async def open_my_profile(page, *, profile_url=None):
    """Activate the model's profile from its navigation when available."""
    label = re.compile(r'^\s*(?:Mi perfil|My profile)\s*$', re.IGNORECASE)
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    for frame in page.frames:
        if (profile_url and not frame_matches_model(frame, profile_url)) or not await frame_is_visible(page, frame):
            continue
        matches = frame.get_by_text(label)
        navigation = frame.locator('nav, aside, [role="navigation"]').get_by_text(label)
        for control in [*await navigation.all(), *await matches.all()]:
            if not await control.is_visible():
                continue
            try:
                state = await control.evaluate("""element => {
                const item = element.closest('button, a, [role="button"], [role="tab"], [role="menuitem"]');
                if (!item && !element.closest('nav, aside, [role="navigation"]')
                    && getComputedStyle(element).cursor !== 'pointer') return 'text';
                return element.closest(
                    '[aria-current="page"], [aria-current="true"], [aria-selected="true"], [aria-pressed="true"]'
                ) ? 'selected' : 'available';
                }""", timeout=1500)
                if state == 'text':
                    continue
                if state == 'available':
                    await control.click(timeout=1500)
            except PlaywrightTimeout:
                if await my_profile_visible(page):
                    return True
                continue
            return True
    return False


def transient_frame_error(error):
    return any(message in str(error) for message in
               ('Execution context was destroyed', 'Frame was detached', 'Frame has been detached'))


def same_profile_route(current_url, expected_url):
    current, expected = urlparse(current_url), urlparse(expected_url)
    return (current.scheme, current.netloc, current.path.rstrip('/')) == (
        expected.scheme, expected.netloc, expected.path.rstrip('/'))


def profile_username(value):
    username = (value or '').strip().lstrip('@').casefold()
    return username if re.fullmatch(r'[a-z0-9_]{1,64}', username) else None


def profile_frame_identity(frame):
    url = urlparse(frame.url)
    identity = re.fullmatch(r'of-([0-9]+)\.agencykey\.com', url.hostname or '')
    username = profile_username(url.path.strip('/'))
    if url.scheme == 'https' and identity and username:
        return int(identity[1]), username
    return None


async def visible_model_profiles(page):
    """Read usernames from visible model iframes showing a profile header."""
    profiles = set()
    for frame in page.frames:
        identity = profile_frame_identity(frame)
        if identity and await frame_is_visible(page, frame) and await frame.locator(PROFILE_HEADER).first.is_visible():
            profiles.add(identity)
    return profiles


async def wait_for_model_identity(page, profile_url, username, *, deadline):
    from playwright.async_api import Error as PlaywrightError
    expected = profile_username(username)
    model_id = int(urlparse(profile_url).path.rstrip('/').rsplit('/', 1)[-1])
    on_route = opened = False
    observed = set()
    while monotonic() < deadline:
        try:
            if await agencykey_sign_in_visible(page):
                raise FeedAccessError('login_required', 'AgencyKey pide iniciar sesión · Reconecta desde el panel web')
            on_route = same_profile_route(page.url, profile_url)
            observed = await visible_model_profiles(page) if on_route else set()
            if expected and observed == {(model_id, expected)}:
                return expected
            if on_route and not opened:
                opened = await open_my_profile(page, profile_url=profile_url)
        except PlaywrightError as error:
            if page.is_closed() or not transient_frame_error(error):
                raise
        await page.wait_for_timeout(400)
    if len(observed) == 1 and expected:
        _, actual_username = next(iter(observed))
        detail = (f'Se esperaba @{expected} y se abrió @{actual_username}.'
                  if actual_username != expected else 'Chrome abrió el espacio de trabajo de otra modelo.')
        raise FeedAccessError('wrong_profile', detail, observed=actual_username)
    if not on_route:
        raise FeedAccessError('wrong_profile', 'Chrome no abrió la ruta de la modelo seleccionada')
    raise FeedAccessError('profile_unverified', 'No se pudo verificar el perfil de la modelo seleccionada')

recorder = SimpleNamespace(
    wait_for_model_identity=wait_for_model_identity,
    FeedAccessError=FeedAccessError,
)


async def verify_profile_route(page, url, username):
    response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    if response is None:
        return {'status': 'connection_error'}
    if response.status == 401:
        return {'status': 'login_required'}
    if response.status in (403, 404):
        return {'status': 'unavailable'}
    if not response.ok:
        return {'status': 'connection_error'}

    try:
        observed = await recorder.wait_for_model_identity(page, url, username, deadline=monotonic() + 35)
    except recorder.FeedAccessError as error:
        return {'status': error.status, 'observed_username': error.observed}
    return {'status': 'ready', 'observed_username': observed}


async def report_frames(page, expected_url, emit):
    from playwright.async_api import Error

    emit(f'Ruta de la modelo coincide: {same_profile_route(page.url, expected_url)}')
    for frame in page.frames:
        host = urlparse(frame.url).hostname or ''
        if frame is not page.main_frame and not re.fullmatch(r'of-[0-9]+\.agencykey\.com', host):
            continue
        try:
            identity = profile_frame_identity(frame)
            visible = await frame_is_visible(page, frame)
            header = await frame.locator(PROFILE_HEADER).first.is_visible()
            menu = await frame.get_by_text(
                re.compile(r'^\s*(Mi perfil|My profile)\s*$', re.IGNORECASE)
            ).first.is_visible()
            name = f'@{identity[1]}' if identity else '(sin usuario en la ruta)'
            matches = frame_matches_model(frame, expected_url)
            emit(f'{host or "(sin dominio)"} {name} | visible={visible} | '
                  f'cabecera={header} | menú={menu} | modelo esperado={matches}')
        except Error:
            emit(f'{host or "(sin dominio)"} | el frame cambió durante la lectura')



class DirectAgencyKeyRequest(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def list_models(api_key, fetch=None):
    if fetch is None:
        fetch = build_opener(DirectAgencyKeyRequest()).open
    models = {}
    for page in range(1, 101):
        request = Request(
            f'https://app.agencykey.com/api/v1/onlyfans/creators?page={page}&limit=100',
            headers={'x-public-api-key': api_key, 'Accept': 'application/json'},
        )
        with fetch(request, timeout=20) as response:
            body = response.read(1048577)
        if len(body) > 1048576:
            raise ValueError('La respuesta de AgencyKey supera el límite de la prueba.')
        payload = json.loads(body)
        rows = payload.get('data')
        pages = payload.get('pagination', {}).get('pages', 1)
        if not isinstance(rows, list) or type(pages) is not int or pages < 1:
            raise ValueError('Formato inesperado en la lista de AgencyKey.')
        for item in rows:
            account = item.get('account') or {}
            username = profile_username(account.get('username'))
            external_id = str(account.get('externalId', ''))
            if username and re.fullmatch(r'[1-9][0-9]{0,15}', external_id):
                models[external_id] = username
        if page >= pages:
            return sorted((username, model_id) for model_id, username in models.items())
    raise ValueError('La lista supera el límite de páginas de la prueba.')


def model_input(value, username):
    match = re.fullmatch(
        r'(?:https://app\.agencykey\.com/models/)?([1-9][0-9]{0,15})/?',
        value.strip(),
    )
    username = profile_username(username)
    if not match or not username:
        raise ValueError('Introduce un ID o enlace de AgencyKey y un @usuario válido.')
    return username, match[1]


class DiagnosticWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.models = []
        self.session = None
        self.key = tk.StringVar()
        self.visible = tk.BooleanVar()
        self.model_id = tk.StringVar()
        self.username = tk.StringVar()
        self.busy = False

        root.title('AgencyKey · Diagnóstico de Mi perfil')
        root.geometry('700x600')
        root.minsize(570, 490)
        panel = ttk.Frame(root, padding=16)
        panel.pack(fill='both', expand=True)

        ttk.Label(panel, text='Clave API de AgencyKey (opcional)').grid(row=0, column=0, sticky='w')
        self.key_entry = ttk.Entry(panel, textvariable=self.key, show='*')
        self.key_entry.grid(row=1, column=0, sticky='ew', pady=(4, 12))
        self.load_button = ttk.Button(panel, text='Cargar modelos', command=self.load)
        self.load_button.grid(row=1, column=1, padx=(8, 0), pady=(4, 12))

        ttk.Label(panel, text='Modelos cargados').grid(row=2, column=0, sticky='w')
        self.model = ttk.Combobox(panel, state='readonly')
        self.model.grid(row=3, column=0, sticky='ew', pady=(4, 12))
        self.model.bind('<<ComboboxSelected>>', self.select_model)

        ttk.Label(panel, text='ID o enlace de AgencyKey').grid(row=4, column=0, sticky='w')
        self.model_entry = ttk.Entry(panel, textvariable=self.model_id)
        self.model_entry.grid(row=5, column=0, sticky='ew', pady=(4, 12))
        ttk.Label(panel, text='@usuario esperado').grid(row=6, column=0, sticky='w')
        self.username_entry = ttk.Entry(panel, textvariable=self.username)
        self.username_entry.grid(row=7, column=0, sticky='ew', pady=(4, 12))
        self.verify_button = ttk.Button(panel, text='Verificar perfil', command=self.verify)
        self.verify_button.grid(row=7, column=1, padx=(8, 0), pady=(4, 12))

        ttk.Checkbutton(panel, text='Mostrar Chrome durante la verificación', variable=self.visible).grid(
            row=8, column=0, sticky='w')
        self.reconnect_button = ttk.Button(panel, text='Cambiar sesión de Chrome', command=self.clear_session)
        self.reconnect_button.grid(row=9, column=0, sticky='w', pady=(8, 0))

        self.output = tk.Text(panel, state='disabled', wrap='word', height=12, pady=8, padx=8)
        self.output.grid(row=10, column=0, columnspan=2, sticky='nsew', pady=(12, 0))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(10, weight=1)
        root.after(100, self.update_ui)

    def emit(self, message):
        self.events.put(('message', message))

    def clear_session(self):
        self.session = None
        self.emit('La próxima comprobación abrirá Chrome para iniciar sesión.')

    def start(self, callback):
        if self.busy:
            return
        self.busy = True
        for entry in (self.key_entry, self.model_entry, self.username_entry):
            entry.config(state='disabled')
        self.model.config(state='disabled')
        for button in (self.load_button, self.verify_button, self.reconnect_button):
            button.config(state='disabled')

        def work():
            try:
                callback()
            except HTTPError as error:
                self.emit(f'La API de AgencyKey respondió HTTP {error.code}.')
            except (URLError, TimeoutError):
                self.emit('La API de AgencyKey no respondió. Comprueba la conexión.')
            except ValueError as error:
                self.emit(str(error))
            except Exception as error:
                self.emit(f'La operación se interrumpió en {type(error).__name__}.')
            finally:
                self.events.put(('done', None))

        threading.Thread(target=work, daemon=True).start()

    def load(self):
        api_key = self.key.get().strip()
        if not api_key:
            self.emit('Introduce tu clave API de AgencyKey.')
            return
        self.emit('Cargando modelos de AgencyKey…')
        self.start(lambda: self.events.put(('models', list_models(api_key))))

    def select_model(self, event=None):
        index = self.model.current()
        if index >= 0:
            username, model_id = self.models[index]
            self.model_id.set(model_id)
            self.username.set('@' + username)

    def verify(self):
        try:
            username, model_id = model_input(self.model_id.get(), self.username.get())
        except ValueError as error:
            self.emit(str(error))
            return
        headless = not self.visible.get()
        self.emit(f'Verificando modelo {model_id} / @{username}…')
        self.start(lambda: asyncio.run(self.check_profile(username, model_id, headless)))

    async def check_profile(self, username, model_id, headless):
        from playwright.async_api import TimeoutError as BrowserTimeout, async_playwright

        url = f'https://app.agencykey.com/models/{model_id}'
        async with async_playwright() as playwright:
            if self.session is None:
                browser = await launch_browser(playwright, headless=False)
                try:
                    context = await browser.new_context(viewport=VIEWPORT)
                    page = await context.new_page()
                    response = await page.goto(SIGN_IN, wait_until='domcontentloaded', timeout=30000)
                    if response and not response.ok:
                        self.emit(f'El inicio de sesión respondió HTTP {response.status}.')
                        return
                    self.emit('Inicia sesión en Chrome. La verificación continuará automáticamente.')
                    deadline = monotonic() + 240
                    while not page.is_closed() and monotonic() < deadline:
                        if await agencykey_login_complete(page):
                            self.session = await context.storage_state(indexed_db=True)
                            self.emit('Sesión de AgencyKey detectada.')
                            break
                        await asyncio.sleep(.7)
                    if self.session is None:
                        self.emit('Se cerró Chrome o venció el plazo para iniciar sesión.')
                        return
                finally:
                    await browser.close()

            browser = await launch_browser(playwright, headless=headless)
            try:
                context = await browser.new_context(viewport=VIEWPORT, storage_state=self.session)
                page = await context.new_page()

                def report_response(response):
                    request = response.request
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        self.emit(f'HTTP de navegación: {response.status}')

                page.on('response', report_response)
                self.emit(f'Abriendo el perfil de la modelo {model_id} en Chrome…')
                try:
                    result = await verify_profile_route(page, url, username)
                except BrowserTimeout:
                    self.emit('Chrome agotó el tiempo de espera al abrir la ruta de AgencyKey.')
                    return
                status = result['status']
                descriptions = {
                    'ready': 'El perfil coincide con la modelo seleccionada.',
                    'login_required': 'AgencyKey pidió iniciar sesión. Vuelve a verificar para reconectar.',
                    'unavailable': 'AgencyKey denegó el acceso o el perfil no existe.',
                    'wrong_profile': 'Chrome abrió un perfil o una ruta distintos a los esperados.',
                    'profile_unverified': 'Chrome no confirmó la identidad de Mi perfil.',
                    'connection_error': 'Chrome no pudo cargar el perfil de AgencyKey.',
                }
                self.emit(f'{descriptions.get(status, status)} ({status})')
                if result.get('observed_username'):
                    self.emit(f"Usuario detectado: @{result['observed_username']}")
                if status == 'login_required':
                    self.session = None
                if status != 'ready':
                    await report_frames(page, url, self.emit)
            finally:
                await browser.close()

    def update_ui(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'message':
                self.output.config(state='normal')
                self.output.insert('end', value + '\n')
                self.output.see('end')
                self.output.config(state='disabled')
            elif kind == 'models':
                self.models = value
                self.model.config(values=[f'@{username} · {model_id}' for username, model_id in value])
                self.model.set('')
                if value:
                    self.model.current(0)
                    self.select_model()
                    self.key.set('')
                self.emit(f'Modelos disponibles: {len(value)}.')
            elif kind == 'done':
                self.busy = False
                for entry in (self.key_entry, self.model_entry, self.username_entry):
                    entry.config(state='normal')
                self.model.config(state='readonly')
                self.load_button.config(state='normal')
                self.reconnect_button.config(state='normal')
                self.verify_button.config(state='normal')
        self.root.after(100, self.update_ui)


async def smoke_browser():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await launch_browser(playwright, headless=True)
        try:
            page = await browser.new_page()
            model_url = 'https://app.agencykey.com/models/52'
            frame_url = 'https://of-52.agencykey.com/modelo'
            await page.route(model_url, lambda route: route.fulfill(
                content_type='text/html',
                body=f'<iframe src="{frame_url}" width="900" height="620"></iframe>',
            ))
            await page.route(frame_url, lambda route: route.fulfill(
                content_type='text/html',
                body='<main id="content"><div class="js-compact-sticky-header">Modelo</div></main>',
            ))
            if await verify_profile_route(page, model_url, 'modelo') != {
                'status': 'ready', 'observed_username': 'modelo',
            }:
                raise RuntimeError('Chrome no verificó el perfil simulado.')
        finally:
            await browser.close()


if __name__ == '__main__':
    root = tk.Tk()
    DiagnosticWindow(root)
    if '--smoke-test' in sys.argv:
        root.update()
        root.destroy()
        asyncio.run(smoke_browser())
    else:
        root.mainloop()
