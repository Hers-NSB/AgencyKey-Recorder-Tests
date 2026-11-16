"""Diagnóstico interactivo de Mi perfil. La sesión de prueba vive en memoria."""
import asyncio
from pathlib import Path
import re
import sys
from time import monotonic
from urllib.parse import urlsplit

from playwright.async_api import Error as BrowserError, async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import recorder
from recording_service import (
    AGENCYKEY_SIGN_IN,
    agencykey_login_complete,
    verify_profile_route,
)


def model_url(value):
    match = re.fullmatch(
        r'(?:https://app\.agencykey\.com/models/)?([1-9][0-9]{0,19})/?',
        value.strip(),
    )
    if not match:
        raise ValueError('Escribe el ID numérico o el enlace de AgencyKey de la modelo.')
    return recorder.model_profile_url(match[1])


def safe_route(url):
    parts = urlsplit(url)
    host = parts.hostname or ''
    if host == 'app.agencykey.com':
        if re.fullmatch(r'/models/[0-9]+/?', parts.path):
            return host + parts.path
        if re.fullmatch(r'/(?:auth(?:/signin)?|login|sign-in|signin|2fa|mfa)/?', parts.path):
            return host + ' [inicio de sesión]'
        return host + ' [otra ruta]'
    if re.fullmatch(r'of-[0-9]+\.agencykey\.com', host):
        username = recorder.profile_username(parts.path.strip('/'))
        return host + (f'/@{username}' if username else ' [sin usuario en la ruta]')
    return '[otra página]'


async def observe(page, expected_url):
    frames = []
    for frame in page.frames:
        route = safe_route(frame.url)
        if frame is not page.main_frame and route == '[otra página]':
            continue
        try:
            visible = await recorder.frame_is_visible(page, frame)
            header = await frame.locator(recorder.PROFILE_HEADER).first.is_visible()
            profile_controls = await frame.get_by_text(
                re.compile(r'^\s*(?:Mi perfil|My profile)\s*$', re.IGNORECASE)
            ).all()
            profile = any([await control.is_visible() for control in profile_controls])
        except BrowserError:
            if frame.is_detached():
                frames.append(f'{route} · marco reemplazado')
            continue
        kind = 'Página principal' if frame is page.main_frame else 'Iframe'
        flags = (
            f"visible={'sí' if visible else 'no'}",
            f"encabezado={'sí' if header else 'no'}",
            f"Mi perfil={'sí' if profile else 'no'}",
        )
        frames.append(f"{kind} {route} · {' · '.join(flags)}")
    try:
        identities = await recorder.visible_model_profiles(page)
    except BrowserError:
        identities = None
    on_route = recorder.same_profile_route(page.url, expected_url)
    return safe_route(page.url), on_route, tuple(frames), (
        tuple(sorted(identities)) if identities is not None else None
    )


def show_observation(observation, elapsed):
    route, on_route, frames, identities = observation
    print(f'  +{elapsed:.1f} s · {route} · ruta esperada: {"sí" if on_route else "no"}')
    for frame in frames:
        print(f'    {frame}')
    if identities is None:
        matched = 'observación interrumpida por el navegador'
    else:
        matched = ', '.join(f'{model_id} / @{username}' for model_id, username in identities) or 'ninguno'
    print(f'    Perfiles visibles que reconoce el código: {matched}', flush=True)


async def check(page, url, username):
    start = monotonic()
    verification = asyncio.create_task(verify_profile_route(page, url, username))
    last = None
    try:
        while not verification.done():
            observation = await observe(page, url)
            if observation != last:
                show_observation(observation, monotonic() - start)
                last = observation
            await asyncio.wait({verification}, timeout=0.4)
        result = await verification
        observation = await observe(page, url)
        if observation != last:
            show_observation(observation, monotonic() - start)
        return result
    finally:
        if not verification.done():
            verification.cancel()
            await asyncio.gather(verification, return_exceptions=True)


async def login(playwright):
    browser = await recorder.launch_browser(playwright, headless=False)
    try:
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        await page.goto(AGENCYKEY_SIGN_IN, wait_until='domcontentloaded', timeout=30000)
        print('Inicia sesión en AgencyKey en la ventana de Chrome.')
        await asyncio.to_thread(input, 'Cuando veas el panel de AgencyKey, pulsa Enter aquí. ')
        if page.is_closed() or not await agencykey_login_complete(page):
            raise ValueError('AgencyKey todavía no muestra una sesión iniciada. Abre el diagnóstico de nuevo.')
        return await context.storage_state(indexed_db=True)
    finally:
        await browser.close()


async def main():
    print('Diagnóstico de Mi perfil de AgencyKey')
    print('Usa el ID y el @usuario asignados al bot. Prueba una modelo, otra y vuelve a la primera.')
    async with async_playwright() as playwright:
        state = await login(playwright)
        browser = await recorder.launch_browser(playwright, headless=True)
        try:
            attempt = 0
            while True:
                value = input('\nID o enlace de la modelo (Enter para salir): ').strip()
                if not value:
                    return
                try:
                    url = model_url(value)
                    username = recorder.profile_username(input('@usuario esperado: '))
                    if not username:
                        raise ValueError('Escribe un @usuario de OnlyFans válido.')
                except ValueError as error:
                    print(error)
                    continue
                attempt += 1
                print(f'\nPrueba {attempt} · esperado {safe_route(url)} / @{username}')
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720}, storage_state=state,
                )
                try:
                    result = await check(await context.new_page(), url, username)
                    print(f"Resultado del verificador: {result['status']}")
                    if result.get('observed_username'):
                        print(f"Usuario devuelto: @{result['observed_username']}")
                except BrowserError as error:
                    print(f'Error de Chrome: {type(error).__name__}')
                finally:
                    await context.close()
        finally:
            await browser.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (EOFError, KeyboardInterrupt):
        pass
    except ValueError as error:
        print(error)
        sys.exit(1)
    except BrowserError as error:
        print(f'Chrome no pudo iniciar el diagnóstico: {type(error).__name__}')
        sys.exit(1)
