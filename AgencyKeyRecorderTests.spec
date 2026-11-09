# Build a single Windows executable; browsers are downloaded into the user's data folder.
from PyInstaller.utils.hooks import collect_all

pw_datas, pw_binaries, pw_hidden = collect_all('playwright')
ff_datas, ff_binaries, ff_hidden = collect_all('imageio_ffmpeg')

a = Analysis(
    ['recorder.py'],
    pathex=[],
    binaries=pw_binaries + ff_binaries,
    datas=pw_datas + ff_datas + [('tests/feed.html', 'tests')],
    hiddenimports=pw_hidden + ff_hidden + ['playwright.__main__'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='AgencyKeyRecorderTests',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
