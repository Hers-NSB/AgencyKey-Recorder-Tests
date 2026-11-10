import base64

import httpx

from config import register_secrets
from connection import tls_context, system_proxy, network_message

DEFAULT_URL = 'https://agencykey-recorder-tests.datosenviados07.workers.dev'


class CloudError(Exception):
    pass


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

    def request(self, method, path, **kwargs):
        try:
            token = self.access_token
            authorization = f'Bearer {token}' if token.isascii() else 'Dropper ' + base64.urlsafe_b64encode(token.encode('utf-8')).decode('ascii').rstrip('=')
            options = {}
            if self.transport is None:
                options['verify'] = tls_context()
                proxy = system_proxy(self.base_url)
                if proxy:
                    options['proxy'] = proxy
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(45, connect=20), follow_redirects=False,
                              headers={'Authorization': authorization},
                              transport=self.transport, **options) as client:
                response = client.request(method, path, **kwargs)
            if response.status_code == 401:
                raise AccessDenied('Contraseña incorrecta o cambiada')
            if not response.is_success:
                try:
                    message = response.json().get('error', '')
                except ValueError:
                    message = ''
                if not isinstance(message, str) or len(message) > 180:
                    message = ''
                raise CloudError(message or f'Error al descargar configuraciones (HTTP {response.status_code})')
            return response.json()
        except httpx.RequestError as error:
            raise CloudError(network_message(error)) from None
        except ImportError:
            raise CloudError('No se pudo usar el proxy de esta red. Instala la versión actualizada de Dropper') from None
        except ValueError:
            raise CloudError('Respuesta de configuración inválida') from None

    def list_profiles(self):
        result = self.request('GET', '/v1/profiles').get('profiles')
        if not isinstance(result, list):
            raise CloudError('No se pudo leer la configuración')
        return result

    def credentials(self, profile_id):
        result = self.request('POST', f'/v1/profiles/{profile_id}/credentials')
        register_secrets(result.get('telegram_token'), result.get('api_key'))
        return result

