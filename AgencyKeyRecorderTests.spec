# Keep the Chrome driver and only the video encoders actually used by this app.
import json
import os
from pathlib import Path
import playwright

package = Path(playwright.__file__).parent / 'driver' / 'package'
browsers = json.loads((package / 'browsers.json').read_text())['browsers']
revision = next(b['revision'] for b in browsers if b['name'] == 'ffmpeg')
recorder_ffmpeg = Path(os.environ['LOCALAPPDATA']) / 'ms-playwright' / f'ffmpeg-{revision}' / 'ffmpeg-win64.exe'
encoder = Path('vendor/encoder/ffmpeg.exe')
if not recorder_ffmpeg.is_file() or not encoder.is_file():
    raise RuntimeError('Prepare Playwright ffmpeg and the minimal Windows encoder before building.')

a = Analysis(
    ['app.py'], pathex=[], binaries=[],
    datas=[('tests/feed.html', 'tests'), ('agencykey-perfiles.json', '.'), (str(encoder), 'encoder'),
           (str(recorder_ffmpeg), f'browser-tools/ffmpeg-{revision}')],
    hiddenimports=[], hookspath=[], runtime_hooks=[],
    excludes=['imageio_ffmpeg', 'playwright.sync_api', 'playwright.__main__'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='AgencyKeyRecorderTests',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True,
          hide_console='hide-early')

