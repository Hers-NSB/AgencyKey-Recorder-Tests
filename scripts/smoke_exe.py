"""Exercise the frozen app, installed Chrome, and its bundled encoder."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def check_token_paste(exe, environment, cwd):
    if sys.platform != 'win32':
        return
    powershell = shutil.which('powershell.exe')
    fake = '12345:RECORDER_QA_PASTE_ONLY'
    process = subprocess.Popen([str(exe), '--check-token-input'], env=environment, cwd=cwd,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        script = r"""
Add-Type -AssemblyName System.Windows.Forms
$shell = New-Object -ComObject WScript.Shell
$found = $false
for ($i=0; $i -lt 120; $i++) {
    if ($shell.AppActivate('AgencyKey Recorder Tests - Telegram')) { $found=$true; break }
    Start-Sleep -Milliseconds 250
}
if (-not $found) { throw 'Token test dialog did not open' }
$previous = [System.Windows.Forms.Clipboard]::GetText()
try {
    [System.Windows.Forms.Clipboard]::SetText('12345:RECORDER_QA_PASTE_ONLY')
    Start-Sleep -Milliseconds 350
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds 250
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
} finally {
    Start-Sleep -Milliseconds 350
    if ($previous) { [System.Windows.Forms.Clipboard]::SetText($previous) }
    else { [System.Windows.Forms.Clipboard]::Clear() }
}
"""
        subprocess.run([powershell, '-NoProfile', '-STA', '-Command', script], check=True, timeout=45,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, f'Token input test failed: {stderr}'
        assert 'Token recibido correctamente' in stdout
        assert fake not in stdout + stderr, 'A token must not be printed'
        print('Pegado Ctrl+V del token verificado en el campo oculto.')
    finally:
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)


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
        assert report['status'] == 'complete' and report['seen'] == ['200', '100'], report
        assert report['resolution'] == '854x480'
        assert report['headless'] is True and report['post_hold_seconds'] == 0
        assert report['first_post_id'] == '200'
        assert report['duration_seconds'] < 8, 'Unexpected pauses in a two-post recording'
        video = reports[0].parent / 'comprobante.mp4'
        assert hashlib.sha256(video.read_bytes()).hexdigest() == report['sha256']
        assert video.stat().st_size > 1000
        # The blue post 300 is above the chosen start. The first frame must show green post 200.
        import imageio_ffmpeg
        decoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                                  '-i', str(video), '-frames:v', '1', '-threads', '1', '-pix_fmt', 'rgb24',
                                  '-f', 'rawvideo', 'pipe:1'], check=True, capture_output=True).stdout
        offset = (250 * 854 + 400) * 3
        red, green, blue = decoded[offset:offset+3]
        assert green > red + 40 and green > blue + 12, f'Wrong first post color: {(red,green,blue)}'
        assert not (data / 'browsers').exists(), 'The app must not download a browser'
        assert exe.stat().st_size < 87_121_379, 'The executable must be smaller than the original release'
        check_token_paste(exe, environment, root)
        # Open the actual default menu, then exit; this also checks restart persistence.
        subprocess.run([str(exe)], input='0\n', text=True, encoding='utf-8',
                       env=environment, cwd=root, check=True, timeout=180)
        assert (data / 'config.local.json').exists() and video.exists()
        if destination := os.environ.get('AGENCYKEY_RECORDER_DEMO_EXPORT'):
            exported = Path(destination).resolve()
            exported.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video, exported)
        print('EXE verificado: menú, configuración persistente, Chrome instalado sin descargas y MP4 480p completos.')


if __name__ == '__main__':
    main()

