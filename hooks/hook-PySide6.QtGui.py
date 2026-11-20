"""This widget uses raster painting, PNG/ICO and Windows/offscreen platforms."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
allowed = {'qwindows.dll', 'qoffscreen.dll', 'qico.dll'}
binaries = [(source, target) for source, target in binaries
            if '/plugins/' not in source.replace('\\', '/').lower()
            or Path(source).name.lower() in allowed]
