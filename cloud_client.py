import base64

import httpx

from config import register_secrets
from connection import tls_context, system_proxy, network_message

DEFAULT_URL = 'https://agencykey-recorder-tests.datosenviados07.workers.dev'


class CloudError(Exception):
    def __init__(self, message, *, retryable=False, status=None, uncertain=None, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.uncertain = uncertain
        self.retry_after = retry_after


class AccessDenied(CloudError):
    pass


class CloudClient:
    def __init__(self, access_token, base_url=DEFAULT_URL, transport=None):
        self.access_token = access_token.strip()
        if not base_url.startswith('https://'):
            raise ValueError('La conexión requiere HTTPS')
        self.base_url = base_url.rstrip('/')
        self.transport = transport
        register_secrets(self.access_token)

    def request(self, method, path, *, timeout=45, **kwargs):
        try:
            token = self.access_token
            authorization = f'Bearer {token}' if token.isascii() else 'Dropper ' + base64.urlsafe_b64encode(token.encode('utf-8')).decode('ascii').rstrip('=')
            options = {}
            if self.transport is None:
                options['verify'] = tls_context()
                proxy = system_proxy(self.base_url)
                if proxy:
                    options['proxy'] = proxy
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=20), follow_redirects=False,
                              headers={'Authorization': authorization, 'X-Recorder-Protocol': '3'},
                              transport=self.transport, **options) as client:
                response = client.request(method, path, **kwargs)
            if response.status_code == 401:
                raise AccessDenied('Contraseña incorrecta o cambiada')
            if not response.is_success:
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                message = data.get('error', '')
                if not isinstance(message, str) or len(message) > 180:
                    message = ''
                uncertain = data.get('uncertain')
                raise CloudError(message or f'Error de Cloudflare (HTTP {response.status_code})',
                                 retryable=response.status_code in (408, 429) or response.status_code >= 500,
                                 status=response.status_code, uncertain=uncertain if isinstance(uncertain, bool) else None,
                                 retry_after=response.headers.get('Retry-After'))
            return response.json()
        except httpx.RequestError as error:
            raise CloudError(network_message(error), retryable=True) from None
        except ImportError:
            raise CloudError('No se pudo usar el proxy de esta red. Instala la versión actualizada de Dropper') from None
        except ValueError:
            raise CloudError('Respuesta de configuración inválida', retryable=True) from None

    def list_profiles(self):
        data = self.request('GET', '/v1/profiles')
        result = data.get('profiles')
        if not isinstance(result, list):
            raise CloudError('No se pudo leer la configuración')
        self.recording_configured = data.get('recording_session', {}).get('configured')
        return result

    def profile_revisions(self):
        profiles = self.request('GET', '/v1/profile-revisions').get('profiles')
        if not isinstance(profiles, list):
            raise CloudError('No se pudo verificar si hay cambios')
        return profiles

    def credentials(self, profile_id):
        result = self.request('POST', f'/v1/profiles/{profile_id}/credentials')
        register_secrets(result.get('telegram_token'))
        return result

    def publish_post(self, profile_id, revision, request_id, text, photo=None, *, slow=False):
        payload = {'revision': revision, 'request_id': request_id, 'text': text, 'slow': slow}
        if photo is not None:
            if len(photo) > 10 * 1024 * 1024:
                raise CloudError('La foto supera 10 MiB', status=413)
            payload['photo'] = base64.b64encode(photo).decode('ascii')
        return self.request('POST', f'/v1/profiles/{profile_id}/publish', timeout=330, json=payload)

    def claim_recording_job(self):
        return self.request('POST', '/v1/recording-desktop-job').get('job')

    def update_recording_job(self, job, **result):
        return self.request('PUT', '/v1/recording-desktop-job',
                            json={'id': job['id'], 'claim': job['claim'], **result})

    def recording_session(self):
        result = self.request('GET', '/v1/recording-session')
        state = result.get('state')
        if not isinstance(state, dict) or not isinstance(state.get('cookies'), list) or not isinstance(state.get('origins'), list):
            raise CloudError('Conecta la sesión compartida de AgencyKey desde la web')
        return result

    def refresh_recording_session(self, state, revision):
        return self.request('PUT', '/v1/recording-session', json={'state': state, 'revision': revision})


