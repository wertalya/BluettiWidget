"""Check public Windows releases without sending station data or installing code."""
import json
import re
from dataclasses import dataclass
from urllib.parse import quote
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from feedback import REPOSITORY, VERSION
from views import label

API_URL = 'https://api.github.com/repos/wertalya/BluettiWidget/releases?per_page=100'


def version_key(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-(preview)(?:\.(\d+))?)?', version)
    if not match:
        raise ValueError('Unsupported release version')
    major, minor, patch, preview, number = match.groups()
    return int(major), int(minor), int(patch), not bool(preview), int(number or 0)


@dataclass(frozen=True)
class WindowsRelease:
    version: str
    download_url: str
    notes_url: str


def newer_release(releases, current=VERSION):
    current_key = version_key(current)
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft', True):
            continue
        tag = release.get('tag_name', '')
        try:
            key = version_key(tag)
        except (ValueError, TypeError):
            continue
        if key <= current_key or (current_key[3] and not key[3]):
            continue
        download = f'{REPOSITORY}/releases/download/{quote(tag, safe="")}/BluettiWidget-Setup.exe'
        assets = release.get('assets') or []
        if not isinstance(assets, list):
            continue
        if any(isinstance(a, dict) and a.get('name') == 'BluettiWidget-Setup.exe'
               and a.get('state') == 'uploaded' and a.get('browser_download_url') == download
               for a in assets):
            candidates.append((key, WindowsRelease(tag.removeprefix('v'), download,
                f'{REPOSITORY}/releases/tag/{quote(tag, safe="")}')))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check_releases():
    request = Request(API_URL, headers={'Accept': 'application/vnd.github+json',
                                      'User-Agent': 'BluettiWidget-update-check'})
    with urlopen(request, timeout=10) as response:
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError('Release response is too large')
    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError('Unexpected release response')
    return newer_release(releases)


class ReleaseCheck(QThread):
    checked = Signal(object)
    failed = Signal()

    def run(self):
        try:
            result = check_releases()
        except Exception:
            self.failed.emit()
        else:
            self.checked.emit(result)


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Оновлення · BluettiWidget')
        self.setMinimumWidth(420)
        self.release = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(label('Оновлення BluettiWidget', size=21))
        layout.addWidget(label(f'Поточна версія: {VERSION}', 'muted'))
        self.status = label('Перевіряю випуски на GitHub…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        hint = label('Оновлення встановлюється поверх програми. Перед запуском інсталятора закрий BluettiWidget через меню в треї. Налаштування станції та вигляду збережуться.', 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.retry = QPushButton('Перевірити знову')
        self.retry.clicked.connect(self.check)
        self.download = QPushButton('Завантажити оновлення')
        self.download.setObjectName('primary')
        self.download.clicked.connect(self.open_download)
        row.addWidget(self.retry)
        row.addWidget(self.download)
        layout.addLayout(row)
        self.worker = ReleaseCheck(self)
        self.worker.checked.connect(self.on_checked)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(lambda: self.retry.setEnabled(True))
        self.check()

    def check(self):
        if self.worker.isRunning():
            return
        self.release = None
        self.download.setEnabled(False)
        self.retry.setEnabled(False)
        self.status.setText('Перевіряю випуски на GitHub…')
        self.worker.start()

    def on_checked(self, release):
        self.release = release
        self.download.setEnabled(release is not None)
        self.status.setText(f'Доступна версія {release.version}.' if release else
                            'Новіших готових випусків для Windows немає.')

    def on_failed(self):
        self.status.setText('Не вдалося перевірити оновлення. Перевір інтернет і повтори спробу. Програма продовжує працювати.')

    def open_download(self):
        if self.release and not QDesktopServices.openUrl(QUrl(self.release.download_url)):
            self.status.setText('Не вдалося відкрити браузер. Випуски: github.com/wertalya/BluettiWidget/releases')
