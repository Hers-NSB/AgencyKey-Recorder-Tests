"""Atiende una solicitud de Chrome del panel web, sin iniciar los bots."""

import argparse
import asyncio
from getpass import getpass
from threading import Event
from time import sleep


def main():
    parser = argparse.ArgumentParser(
        description='Atiende la siguiente solicitud de conexión o verificación del panel web.'
    )
    parser.parse_args()

    from cloud_client import CloudClient, CloudError
    from config import log
    from recording_service import run_desktop_recording_job

    password = getpass('Contraseña de las apps del panel: ').strip()
    if not password:
        log.error('Introduce la contraseña de las apps para continuar.')
        return 1

    client = CloudClient(password)
    stop_event = Event()
    log.info('Esperando una solicitud. Pulsa «Verificar Mi perfil» en el panel.')
    try:
        while True:
            job = client.claim_recording_job()
            if job:
                break
            sleep(2)

        log.info('Solicitud recibida. Abriendo AgencyKey en Chrome.')
        asyncio.run(run_desktop_recording_job(client, job, stop_event))
    except KeyboardInterrupt:
        log.info('Verificador detenido.')
        return 130
    except CloudError as error:
        log.error('%s', error)
        return 1
    finally:
        stop_event.set()

    log.info('Consulta el resultado de la solicitud en el panel.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
