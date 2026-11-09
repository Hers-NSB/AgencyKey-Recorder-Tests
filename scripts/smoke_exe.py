"""Exercise the frozen app, installed Chrome, and its bundled encoder."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    source = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='recorder-exe-') as directory:
        root = Path(directory)
        folder = root / 'Aplicación con espacios ñ'
        folder.mkdir()
        exe = folder / source.name
        shutil.copy2(source, exe)
        data = root / 'Datos persistentes ñ'
        environment = dict(os.environ, AGENCYKEY_RECORDER_DATA_DIR=str(data), PYTHONUTF8='1')
        # Avoid relying on a separately installed FFmpeg in the runner's PATH.
        # Frozen mode always chooses the bundled imageio-ffmpeg encoder.
        configured = subprocess.run([str(exe), 'configure'], input='https://app.agencykey.com/models/123\n300\n200\n100\n\n',
                                    text=True, encoding='utf-8', env=environment, cwd=root, timeout=180)
        configured.check_returncode()
        subprocess.run([str(exe), 'check-chrome'], env=environment, cwd=root, check=True, timeout=180)
        assert (data / 'config.local.json').exists(), 'Frozen app did not persist its configuration'
        subprocess.run([str(exe), 'demo', '--headless'], env=environment, cwd=root, check=True, timeout=900)
        reports = list((data / 'output').glob('*/report.json'))
        assert len(reports) == 1, 'Expected one standalone demo'
        report = json.loads(reports[0].read_text(encoding='utf-8'))
        assert report['status'] == 'complete' and report['seen'] == ['300', '200', '100'], report
        assert report['resolution'] == '854x480'
        video = reports[0].parent / 'comprobante.mp4'
        assert hashlib.sha256(video.read_bytes()).hexdigest() == report['sha256']
        assert video.stat().st_size > 1000
        assert not (data / 'browsers').exists(), 'The app must not download a browser'
        assert exe.stat().st_size < 87_121_379, 'The executable must be smaller than the original release'
        # Open the actual default menu, then exit; this also checks restart persistence.
        subprocess.run([str(exe)], input='0\n', text=True, encoding='utf-8',
                       env=environment, cwd=root, check=True, timeout=180)
        assert (data / 'config.local.json').exists() and video.exists()
        print('EXE verificado: menú, configuración persistente, Chrome instalado sin descargas y MP4 480p completos.')


if __name__ == '__main__':
    main()
