"""Produce a standalone executable using the same dependency selection as the folder build."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
spec = (root / 'BluettiWidget.spec').read_text(encoding='utf-8')
analysis = spec.split('pyz = PYZ(a.pure)')[0]
tail = '''
# These DLLs are unnecessary for raster widgets; use Windows' own ICU API.
a.binaries = [item for item in a.binaries if item[0].replace('\\\\', '/').lower().split('/')[-1]
              not in {'icuuc.dll', 'icudt78.dll', 'opengl32sw.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='BluettiWidget',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, icon='assets/bluetti-widget.ico', disable_windowed_traceback=False)
'''
portable_spec = root / 'Portable.spec'
portable_spec.write_text(analysis + tail, encoding='utf-8')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                '--distpath', str(root / 'portable'), str(portable_spec)], cwd=root, check=True)
for name in ('README.md','LICENSE','THIRD_PARTY.md'):
    source = root / 'dist' / 'BluettiWidget' / name
    if source.exists():
        shutil.copy2(source, root / 'portable' / name)
