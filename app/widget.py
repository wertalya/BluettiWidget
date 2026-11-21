"""BLUETTI desktop companion: compact instruments, details, tray and BLE handoff."""
import argparse
import logging
import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer, QLockFile, QPoint
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QActionGroup
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QGridLayout,
    QHBoxLayout, QMenu, QMessageBox, QPushButton, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget, QWidgetAction)
from .powerlink import BluetoothWorker
from .runtime_estimate import RuntimeEstimator, format_runtime
from .models import PROFILES, get_profile
from .feedback import FeedbackDialog, VERSION, open_model_report
from .updates import AutoUpdateMonitor, UpdateDialog
from .views import STYLE, INPUT, OUTPUT, GREEN, MUTED, InstrumentCluster, PowerHistory, label

APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
APP_ICON = Path(__file__).resolve().parent.parent / 'assets' / 'bluetti-widget.ico'
SIZES = {'S': (320, 204), 'M': (360, 220), 'L': (420, 246)}


def startup_hidden(settings, *, autostart=False, start_in_tray=False, demo=False, rendering=False, tray_available=True):
    if demo or rendering or not tray_available:
        return False
    return start_in_tray or (autostart and not settings.value('show_on_startup', True, type=bool))


def total(data, *fields):
    values = [data.get(f) for f in fields]
    return sum(values) if all(type(v) in (int, float) for v in values) else None


def describe_state(data):
    power_in = total(data, 'ac_input_power', 'dc_input_power')
    power_out = total(data, 'ac_output_power', 'dc_output_power')
    if power_in is None or power_out is None:
        return 'Дані неповні'
    if power_in > 0 and power_out > 0:
        return 'Вхід і навантаження'
    if power_in > 0:
        return 'Заряджається' if data.get('total_battery_percent', 0) < 100 else 'Заряд 100% · є вхід'
    if power_out > 0:
        return 'Живить пристрої'
    return 'Очікування'


def tray_icon(percent=None, stale=False):
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = MUTED if stale or percent is None else '#ff9b84' if percent <= 20 else GREEN
    painter.setPen(QColor(color))
    painter.setFont(QFont('Segoe UI', 28, QFont.Weight.Bold))
    painter.drawText(pix.rect().adjusted(0, -3, 0, -3), Qt.AlignmentFlag.AlignCenter,
                     '—' if percent is None else str(percent))
    painter.fillRect(12, 57, 40, 3, QColor(color))
    painter.end()
    return QIcon(pix)


class Picker(QDialog):
    def __init__(self, worker, parent):
        super().__init__(parent)
        self.worker = worker
        self.scanning = False
        self.connecting = False
        self.setWindowTitle('Підключення BLUETTI')
        self.resize(380, 220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(label('Підключити станцію', size=22))
        hint = label('Увімкни Bluetooth на ПК і на станції. Якщо вона зайнята, закрий підключення в застосунку BLUETTI на телефоні.', 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.combo = QComboBox()
        self.combo.setAccessibleName('Знайдені станції BLUETTI')
        self.combo.setMinimumContentsLength(14)
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        layout.addWidget(self.combo)
        self.note = label('', 'muted')
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        layout.addWidget(self.note, 1)
        row = QHBoxLayout()
        self.scan = QPushButton('Шукати знову')
        self.connect = QPushButton('Підключити')
        self.connect.setObjectName('primary')
        self.connect.setEnabled(False)
        row.addWidget(self.scan)
        row.addWidget(self.connect)
        layout.addLayout(row)
        self.scan.clicked.connect(self.search)
        self.connect.clicked.connect(self.choose)
        worker.devices.connect(self.found)
        worker.scan_failed.connect(self.search_failed)
        worker.status.connect(self.connection_status)
        worker.failure.connect(self.connection_failed)
        worker.retrying.connect(self.connection_status)

    def search(self):
        if self.scanning:
            return
        self.scanning = True
        self.connecting = False
        self.combo.clear()
        self.combo.setEnabled(False)
        self.connect.setEnabled(False)
        self.scan.setEnabled(False)
        self.note.setText('Шукаю станції поблизу · приблизно 8 секунд')
        self.worker.submit('scan')

    def found(self, devices):
        self.scanning = False
        self.scan.setEnabled(True)
        self.combo.clear()
        for device in devices:
            self.combo.addItem(device['name'], device)
        self.combo.setEnabled(bool(devices))
        self.connect.setEnabled(bool(devices))
        self.note.setText('Вибери свою станцію зі списку.' if devices else
                          'Сумісних станцій поруч не видно. Перевір Bluetooth на станції та повтори пошук.')

    def search_failed(self, _message):
        self.scanning = False
        self.scan.setEnabled(True)
        self.note.setText('Пошук не вдався. Перевір Bluetooth у Windows і повтори спробу.')

    def connection_status(self, message):
        if self.connecting:
            self.note.setText(message)

    def connection_failed(self, message):
        if self.connecting:
            self.note.setText(message)
            self.combo.setEnabled(True)
            self.scan.setEnabled(True)
            self.connect.setEnabled(self.combo.currentData() is not None)

    def choose(self):
        device = self.combo.currentData()
        if device:
            self.connecting = True
            self.scan.setEnabled(False)
            self.combo.setEnabled(False)
            self.connect.setEnabled(False)
            self.note.setText('Підключаюся…')
            self.worker.submit('select', device)

    def connected(self):
        self.connecting = False
        self.accept()


class Panel(QWidget):
    def __init__(self, demo=False, start_worker=True, settings_path=None, auto_open_picker=True):
        super().__init__()
        self.demo = demo
        self.settings = QSettings(str(settings_path or APP_DIR / 'settings.ini'), QSettings.Format.IniFormat)
        self.auto_updates = AutoUpdateMonitor(self.settings, self)
        self.worker = BluetoothWorker()
        self.data = {}
        self.last_update = 0
        self.busy = False
        self.pending_field = None
        self.encrypted = False
        self.paused = False
        self.handoff_pending = False
        self.alerted = False
        self.stale = True
        self.drag_offset = None
        self.picker = None
        self.pending_station = None
        self.details = None
        self.update_dialog = None
        self.size_name = self.settings.value('size', 'M')
        self.position_locked = self.settings.value('position_locked', False, type=bool)
        self.always_on_top = self.settings.value('always_on_top', False, type=bool)
        self.show_in_taskbar = self.settings.value('show_in_taskbar', False, type=bool)
        self.opacity = min(100, max(65, self.settings.value('opacity', 100, type=int)))
        saved_model = self.settings.value('model', 'AC180P')
        saved_address = self.settings.value('address', '') if saved_model in PROFILES else ''
        self.profile = PROFILES.get(saved_model, PROFILES['AC180P'])
        self.has_station = bool(saved_address)
        self.setWindowTitle('BluettiWidget')
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.setWindowFlags(self.window_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.mini = QWidget()
        self.mini.setObjectName('shell')
        root.addWidget(self.mini)
        layout = QVBoxLayout(self.mini)
        layout.setContentsMargins(11, 9, 11, 10)
        layout.setSpacing(3)
        header = QHBoxLayout()
        self.connection_dot = label('●')
        self.connection_dot.setStyleSheet(f'color: {MUTED}; font-size: 10px;')
        header.addWidget(self.connection_dot)
        header.addWidget(label('BLUETTI', 'eyebrow'))
        self.model_label = label(self.profile.model if demo or saved_address else '', 'muted')
        header.addWidget(self.model_label)
        header.addStretch()
        self.connect_button = QPushButton('Станція')
        self.connect_button.setObjectName('quiet')
        self.connect_button.setToolTip('Знайти або змінити станцію BLUETTI')
        self.connect_button.clicked.connect(self.open_picker)
        self.connect_button.setEnabled(not demo)
        header.addWidget(self.connect_button)
        details_button = QPushButton('↗')
        details_button.setObjectName('quiet')
        details_button.setToolTip('Деталі та налаштування')
        details_button.setAccessibleName('Відкрити деталі та налаштування')
        details_button.clicked.connect(self.open_details)
        header.addWidget(details_button)
        self.menu_button = QPushButton('···')
        self.menu_button.setObjectName('quiet')
        self.menu_button.setToolTip('Розмір, прозорість і положення')
        self.menu_button.clicked.connect(self.show_menu)
        header.addWidget(self.menu_button)
        hide = QPushButton('×')
        hide.setObjectName('quiet')
        hide.setToolTip('Сховати в трей')
        hide.clicked.connect(self.hide)
        header.addWidget(hide)
        layout.addLayout(header)
        self.cluster = InstrumentCluster()
        layout.addWidget(self.cluster, 1)
        controls = QHBoxLayout()
        controls.setSpacing(7)
        self.switches = {}
        for field, title in [('ctrl_ac', 'AC'), ('ctrl_dc', 'DC')]:
            button = QPushButton(title + ' · —')
            button.setCheckable(True)
            button.setEnabled(False)
            button.setMinimumHeight(28)
            button.setStyleSheet('QPushButton { padding: 4px 6px; font-size: 11px; }')
            button.setToolTip('Розетки змінного струму' if field == 'ctrl_ac' else 'USB та виходи постійного струму')
            button.clicked.connect(lambda checked, f=field: self.toggle(f))
            self.switches[field] = button
            controls.addWidget(button, 1)
        self.bluetooth_button = QPushButton('Телефон')
        self.bluetooth_button.setStyleSheet('QPushButton { padding: 4px 8px; font-size: 11px; }')
        self.bluetooth_button.setMinimumHeight(28)
        self.bluetooth_button.setToolTip('Звільнити Bluetooth для застосунку на телефоні')
        self.bluetooth_button.clicked.connect(self.toggle_bluetooth)
        controls.addWidget(self.bluetooth_button)
        layout.addLayout(controls)
        self.status = label('Підключи станцію, щоб побачити заряд', 'muted')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setToolTip(self.status.text())
        self.status.setStyleSheet(f'font-size: 11px; color: {MUTED};')
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status.setFixedHeight(18)
        layout.addWidget(self.status)
        self.menu = self.make_menu()
        self.tray = QSystemTrayIcon(tray_icon(), self)
        self.tray.setToolTip('BLUETTI · немає з’єднання')
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()
        self.auto_updates.available.connect(lambda release: self.update_action.setText(f'Оновлення {release.version} доступне…'))
        self.auto_updates.notify.connect(self.notify_update)
        self.tray.messageClicked.connect(self.open_updates)
        self.worker.reading.connect(self.update_reading)
        self.worker.failure.connect(self.failed)
        self.worker.retrying.connect(self.set_status)
        self.worker.status.connect(self.worker_status)
        self.worker.selected.connect(self.on_selected)
        self.worker.command_done.connect(self.command_finished)
        self.worker.paused_changed.connect(self.on_paused)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.check_age)
        self.clock.start()
        self.history = PowerHistory()
        self.runtime_estimator = RuntimeEstimator(capacity_wh=self.station_capacity())
        self.apply_size(self.size_name)
        self.setWindowOpacity(self.opacity / 100)
        self.restore_position()
        if start_worker and not demo:
            self.auto_updates.start()
            self.worker.start()
            if saved_address:
                self.worker.submit('select', {'address': saved_address,
                    'model':self.profile.model,
                    'encrypted': self.settings.value('encrypted', False, type=bool)})
                self.set_status('Підключаюся…')
            elif auto_open_picker:
                QTimer.singleShot(0, self, self.open_picker)
        if demo:
            self.update_reading({'total_battery_percent': 81, 'ac_input_power': 1456,
                'dc_input_power': 0, 'ac_output_power': 329, 'dc_output_power': 12,
                'ctrl_ac': True, 'ctrl_dc': False, 'ctrl_charging_mode': 'TURBO'})
            self.set_status('Демонстрація · приклад показників')
            self.set_controls(False)

    def make_menu(self):
        menu = QMenu(self)
        header = QWidget(menu)
        header.setObjectName('trayHeader')
        summary = QVBoxLayout(header)
        summary.setContentsMargins(12, 9, 12, 9)
        summary.setSpacing(4)
        self.menu_title = label('BLUETTI', 'trayTitle')
        self.menu_status = label('', 'muted')
        summary.addWidget(self.menu_title)
        summary.addWidget(self.menu_status)
        summary_action = QWidgetAction(menu)
        summary_action.setDefaultWidget(header)
        menu.addAction(summary_action)

        choose_station = menu.addAction('Знайти станцію…', self.open_picker)
        choose_station.setEnabled(not self.demo)
        self.retry_action = menu.addAction('Спробувати підключитися зараз', self.retry_connection)
        self.handoff_action = menu.addAction('Звільнити Bluetooth для телефону', self.toggle_bluetooth)
        menu.addSeparator()
        menu.addAction('Деталі та історія', self.open_details)
        self.visibility_action = menu.addAction('Сховати віджет', self.toggle_visible)
        appearance = menu.addMenu('Вигляд і положення')
        sizes = appearance.addMenu('Розмір')
        group = QActionGroup(sizes)
        self.size_actions = {}
        for name, dimensions in SIZES.items():
            action = sizes.addAction(f'{name} · {dimensions[0]} × {dimensions[1]}')
            action.setCheckable(True)
            action.setChecked(name == self.size_name)
            action.triggered.connect(lambda checked, n=name: self.apply_size(n))
            group.addAction(action)
            self.size_actions[name] = action
        self.lock_action = appearance.addAction('Закріпити позицію')
        self.lock_action.setCheckable(True)
        self.lock_action.setChecked(self.position_locked)
        self.lock_action.toggled.connect(self.set_position_locked)
        self.top_action = appearance.addAction('Поверх інших вікон')
        self.top_action.setCheckable(True)
        self.top_action.setChecked(self.always_on_top)
        self.top_action.toggled.connect(self.set_on_top)
        self.taskbar_action = appearance.addAction('Показувати на панелі завдань')
        self.taskbar_action.setCheckable(True)
        self.taskbar_action.setChecked(self.show_in_taskbar)
        self.taskbar_action.toggled.connect(self.set_taskbar)
        opacity_menu = appearance.addMenu('Непрозорість')
        opacity_group = QActionGroup(opacity_menu)
        for value in (100, 90, 80, 70):
            action = opacity_menu.addAction(f'{value}%')
            action.setCheckable(True)
            action.setChecked(value == self.opacity)
            action.triggered.connect(lambda checked, v=value: self.set_opacity(v))
            opacity_group.addAction(action)
        appearance.addAction('Перемістити до правого краю', self.move_to_edge)
        self.startup_action = appearance.addAction('Показувати віджет після входу у Windows')
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(self.settings.value('show_on_startup', True, type=bool))
        self.startup_action.toggled.connect(lambda checked: self.save('show_on_startup', checked))
        menu.addSeparator()
        self.update_action = menu.addAction('Перевірити оновлення…', self.open_updates)
        self.auto_update_action = menu.addAction('Автоматично перевіряти оновлення')
        self.auto_update_action.setCheckable(True)
        self.auto_update_action.setChecked(self.auto_updates.enabled())
        self.auto_update_action.setEnabled(not self.demo)
        self.auto_update_action.toggled.connect(self.auto_updates.set_enabled)
        menu.addAction('Запропонувати модель…', open_model_report)
        menu.addAction('Написати автору…', self.open_feedback)
        menu.addAction('Закрити BluettiWidget', QApplication.instance().quit)
        menu.aboutToShow.connect(self.refresh_menu)
        return menu

    def refresh_menu(self):
        soc = self.data.get('total_battery_percent')
        title = f'BLUETTI  {self.profile.model}' if self.has_station or self.demo else 'BluettiWidget'
        self.menu_title.setText(f'{title}  ·  {soc}%' if soc is not None else title)
        fresh = self.fresh()
        if self.demo:
            status = 'Демонстраційний режим'
        elif self.handoff_pending:
            status = 'Змінюю стан Bluetooth…'
        elif self.paused:
            status = 'Bluetooth вільний для телефону'
        elif fresh:
            status = 'Підключено · живі показники'
        elif not self.has_station:
            status = 'Станцію ще не вибрано'
        elif soc is not None:
            status = 'Зв’язок втрачено · останній заряд'
        else:
            status = 'Очікую з’єднання зі станцією'
        self.menu_status.setText(status)
        self.retry_action.setVisible(self.can_retry_connection())
        self.handoff_action.setEnabled(self.has_station and not self.demo and not self.handoff_pending and not self.busy)
        self.visibility_action.setText('Сховати віджет' if self.isVisible() and not self.isMinimized() else 'Показати віджет')

    def can_retry_connection(self):
        return (self.has_station and not self.demo and not self.paused
                and not self.handoff_pending and not self.busy and not self.fresh())

    def retry_connection(self):
        if self.can_retry_connection():
            self.set_status('Підключаюся…')
            self.worker.submit('read')

    def save(self, key, value):
        if not self.demo:
            self.settings.setValue(key, value)

    def apply_size(self, name):
        self.size_name = name if name in SIZES else 'M'
        self.setFixedSize(*SIZES[self.size_name])
        if hasattr(self, 'size_actions'):
            self.size_actions[self.size_name].setChecked(True)
        self.save('size', self.size_name)
        self.keep_on_screen()
        QTimer.singleShot(0, self, lambda: self.set_status(self.status.toolTip()))

    def set_position_locked(self, locked):
        self.position_locked = locked
        self.save('position_locked', locked)

    def window_flags(self):
        window_type = Qt.WindowType.Window if self.show_in_taskbar else Qt.WindowType.Tool
        flags = Qt.WindowType.FramelessWindowHint | window_type
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        return flags

    def refresh_window_flags(self):
        visible, position = self.isVisible(), self.pos()
        self.setWindowFlags(self.window_flags())
        self.move(position)
        if visible:
            self.show()
            self.keep_on_screen()

    def set_on_top(self, enabled):
        self.always_on_top = enabled
        self.save('always_on_top', enabled)
        self.refresh_window_flags()

    def set_taskbar(self, enabled):
        self.show_in_taskbar = enabled
        self.save('show_in_taskbar', enabled)
        self.refresh_window_flags()

    def set_opacity(self, value):
        self.opacity = value
        self.setWindowOpacity(value / 100)
        self.save('opacity', value)

    def restore_position(self):
        point = self.settings.value('position')
        if isinstance(point, QPoint) and any(s.availableGeometry().contains(point) for s in QApplication.screens()):
            self.move(point)
            self.keep_on_screen()
        else:
            self.move_to_edge()

    def keep_on_screen(self):
        if self.screen():
            box = self.screen().availableGeometry()
            self.move(max(box.left(), min(self.x(), box.right() - self.width() + 1)),
                      max(box.top(), min(self.y(), box.bottom() - self.height() + 1)))

    def move_to_edge(self):
        box = self.screen().availableGeometry()
        self.move(box.right() - self.width() - 12, box.bottom() - self.height() - 12)
        self.save('position', self.pos())

    def show_menu(self):
        self.menu.popup(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def open_updates(self):
        if self.update_dialog is None:
            self.update_dialog = UpdateDialog(self)
        elif not self.update_dialog.isVisible():
            self.update_dialog.check()
        self.update_dialog.show()
        self.update_dialog.raise_()
        self.update_dialog.activateWindow()

    def notify_update(self, release):
        self.tray.showMessage('Доступне оновлення BluettiWidget',
            f'Версія {release.version}. Натисни, щоб переглянути та завантажити.',
            QSystemTrayIcon.MessageIcon.Information, 10000)

    def contextMenuEvent(self, event):
        self.menu.popup(event.globalPos())

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.keep_on_screen()
            self.raise_()
            self.activateWindow()
            if not self.has_station and self.picker is None:
                self.open_picker()

    def set_compact(self, compact):
        if compact:
            if self.details:
                self.details.hide()
            self.show()
        else:
            self.open_details()

    def open_picker(self):
        if self.demo:
            return
        if self.picker is None:
            self.picker = Picker(self.worker, self)
        if not self.picker.isVisible() and not self.picker.connecting:
            self.picker.search()
        self.picker.show()
        self.picker.raise_()
        self.picker.activateWindow()

    def open_details(self):
        if self.details is None:
            self.build_details()
        self.details.show()
        self.details.raise_()

    def open_feedback(self):
        dialog=FeedbackDialog(self.profile.model,self)
        dialog.exec()

    def build_details(self):
        self.details = QDialog(self)
        self.details.setWindowTitle('BLUETTI · '+self.profile.model+' · Деталі')
        self.details.resize(440, 440)
        layout = QVBoxLayout(self.details)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(13)
        row = QHBoxLayout()
        self.detail_model = label(self.profile.model,size=24)
        row.addWidget(self.detail_model)
        row.addStretch()
        self.soc_label = label('—%', size=28)
        row.addWidget(self.soc_label)
        layout.addLayout(row)
        self.detail_status = label('Очікую дані', 'muted')
        self.detail_status.setWordWrap(True)
        self.detail_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.detail_status)
        self.runtime_label = label('Орієнтовний час роботи: —', size=17)
        layout.addWidget(self.runtime_label)
        grid = QGridLayout()
        self.metrics = {}
        for index, (field, title, color) in enumerate([
            ('ac_input_power', 'Мережа', INPUT), ('dc_input_power', 'Сонячний вхід', INPUT),
            ('ac_output_power', 'AC · розетки', OUTPUT), ('dc_output_power', 'DC · USB / 12 В', OUTPUT)]):
            box = QVBoxLayout()
            box.addWidget(label(title, 'muted'))
            value = label('— Вт', size=23)
            value.setStyleSheet(f'color: {color}; font-size: 23px; font-weight: 600;')
            self.metrics[field] = value
            box.addWidget(value)
            grid.addLayout(box, index // 2, index % 2)
        layout.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(label('Історія · 10 хвилин', 'muted'))
        row.addStretch()
        row.addWidget(label(f'<span style="color:{INPUT}">● Вхід</span>　<span style="color:{OUTPUT}">● Вихід</span>'))
        layout.addLayout(row)
        layout.addWidget(self.history)
        self.detail_switches = {}
        row = QHBoxLayout()
        for field in ('ctrl_ac', 'ctrl_dc'):
            button = QPushButton()
            button.setCheckable(True)
            button.clicked.connect(lambda checked, f=field: self.toggle(f))
            row.addWidget(button)
            self.detail_switches[field] = button
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label('Режим заряджання', 'muted'))
        self.mode = QComboBox()
        for title, value in [('Тихий', 'SILENT'), ('Стандартний', 'STANDARD'), ('Турбо', 'TURBO')]:
            self.mode.addItem(title, value)
        self.mode.activated.connect(self.change_mode)
        row.addWidget(self.mode, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        connect = QPushButton('Вибрати станцію')
        connect.clicked.connect(self.open_picker)
        row.addWidget(connect)
        self.detail_bluetooth = QPushButton('Звільнити Bluetooth')
        self.detail_bluetooth.clicked.connect(self.toggle_bluetooth)
        row.addWidget(self.detail_bluetooth)
        layout.addLayout(row)
        note = label('Історія зберігається протягом цього запуску.\nРозмір і прозорість приборки — у меню ···.', 'muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        author_row=QHBoxLayout()
        author_row.addWidget(label('BluettiWidget '+VERSION,'muted'))
        author_row.addStretch()
        author_button=QPushButton('Написати автору')
        author_button.clicked.connect(self.open_feedback)
        author_row.addWidget(author_button)
        layout.addLayout(author_row)
        self.refresh_details()
        self.set_controls(self.fresh() and not self.busy)

    def set_status(self, message):
        width = self.status.width() if self.status.width() > 0 else self.width()
        self.status.setText(self.status.fontMetrics().elidedText(message, Qt.TextElideMode.ElideRight, width))
        self.status.setToolTip(message)
        if self.details:
            self.detail_status.setText(message)

    def worker_status(self, message):
        if self.stale or self.busy or self.paused or self.handoff_pending:
            self.set_status(message)

    def fresh(self):
        return bool(self.last_update) and not self.stale and not self.paused and not self.handoff_pending and time.monotonic() - self.last_update <= (45 if self.encrypted else 6)

    def on_selected(self, device):
        self.profile = get_profile(device.get('model','AC180P'))
        self.pending_station = device
        self.has_station = True
        self.model_label.setText(self.profile.model)
        if self.details:
            self.detail_model.setText(self.profile.model)
            self.details.setWindowTitle('BLUETTI · '+self.profile.model+' · Деталі')
        self.runtime_estimator.capacity_wh = self.station_capacity()
        self.encrypted = device.get('encrypted', False)
        self.alerted = False
        self.history.max_gap = 45 if self.encrypted else 6
        self.data = {}
        self.last_update = 0
        self.stale = True
        self.busy = False
        self.pending_field = None
        self.history.samples.clear()
        self.runtime_estimator.clear()
        self.cluster.runtime_text = '—'
        self.cluster.set_data(None, None, None)
        self.cluster.stale = True
        self.tray.setIcon(tray_icon())
        self.set_controls(False)
        self.refresh_details()
        self.set_status('Підключаюся…')

    def station_capacity(self):
        try:
            capacity = float(self.settings.value(f'capacity_wh/{self.profile.model}', 0))
        except (TypeError, ValueError):
            capacity = 0
        return capacity if math.isfinite(capacity) and capacity > 0 else self.profile.capacity_wh

    def set_controls(self, enabled):
        enabled = enabled and self.profile.controls and not self.encrypted and not self.paused and not self.handoff_pending and not self.demo
        for field, button in self.switches.items():
            value = self.data.get(field)
            state = 'Увімкн.' if value is True else 'Вимкн.' if value is False else '—'
            if self.busy and field == self.pending_field:
                state = 'Змінюю…'
            text = ('AC' if field == 'ctrl_ac' else 'DC') + ' · ' + state
            button.setText(text)
            button.setChecked(value is True)
            button.setEnabled(enabled and not self.busy and type(value) is bool)
            button.setVisible(self.profile.controls and not self.encrypted)
            if self.details:
                detail_button = self.detail_switches[field]
                detail_button.setText(text)
                detail_button.setChecked(value is True)
                detail_button.setEnabled(button.isEnabled())
        if self.details:
            self.mode.setCurrentIndex(self.mode.findData(self.data.get('ctrl_charging_mode')))
            self.mode.setEnabled(enabled and not self.busy and self.data.get('ctrl_charging_mode') in {'SILENT', 'STANDARD', 'TURBO'})
        self.bluetooth_button.setEnabled(not self.demo and not self.handoff_pending and not self.busy)
        self.bluetooth_button.setText('Повернути' if self.paused else 'Телефон')
        self.bluetooth_button.setToolTip('Повернути Bluetooth-з’єднання до ПК' if self.paused else 'Звільнити Bluetooth для телефону')
        self.handoff_action.setText('Повернути з’єднання до ПК' if self.paused else 'Звільнити Bluetooth для телефону')
        self.handoff_action.setEnabled(not self.demo and not self.handoff_pending and not self.busy)
        if self.details:
            self.detail_bluetooth.setText('Повернути до ПК' if self.paused else 'Звільнити Bluetooth')
            self.detail_bluetooth.setEnabled(self.bluetooth_button.isEnabled())

    def refresh_details(self):
        if not self.details:
            return
        soc = self.data.get('total_battery_percent')
        self.soc_label.setText('—%' if soc is None else f'{soc}%')
        for field, value in self.metrics.items():
            value.setText(f'{self.data[field]:g} Вт' if field in self.data else '— Вт')
        self.detail_status.setText(self.status.toolTip() or self.status.text())
        self.runtime_label.setText('Орієнтовний час роботи: ' + self.cluster.runtime_text)
        self.runtime_label.setToolTip(self.cluster.toolTip())

    def update_reading(self, data):
        if self.paused or self.handoff_pending:
            return
        if self.pending_station is not None:
            self.save('model', self.profile.model)
            self.save('address', self.pending_station['address'])
            self.save('encrypted', self.encrypted)
            self.settings.sync()
            self.pending_station = None
            if self.picker and self.picker.connecting:
                self.picker.connected()
        self.data = data
        self.last_update = time.monotonic()
        self.stale = False
        power_in = total(data, 'ac_input_power', 'dc_input_power')
        power_out = total(data, 'ac_output_power', 'dc_output_power')
        soc = data['total_battery_percent']
        hours = self.runtime_estimator.update(soc, power_in, power_out, self.last_update)
        self.cluster.runtime_text = format_runtime(hours)
        average = self.runtime_estimator.average_w
        self.cluster.setToolTip((
            f'Орієнтовно за середнім навантаженням {average:.0f} Вт за останні 20 с.\n'
            'Час залежить від навантаження, температури та стану батареї.'
            if hours is not None else 'Для оцінки потрібні ємність батареї, вхідна й вихідна потужність.'))
        self.cluster.set_data(soc, power_in, power_out)
        self.history.add(self.last_update, power_in, power_out)
        self.connection_dot.setStyleSheet(f'color: {GREEN}; font-size: 10px;')
        if not self.busy:
            self.set_status('● ' + describe_state(data) + (' · лише читання' if self.encrypted or not self.profile.controls else ' · наживо'))
        self.set_controls(True)
        self.refresh_details()
        self.tray.setIcon(tray_icon(soc))
        self.tray.setToolTip(f'BLUETTI {self.profile.model} · {soc}%\n{describe_state(data)}\nВхід {power_in if power_in is not None else "—"} Вт · Вихід {power_out if power_out is not None else "—"} Вт')
        if soc <= 20 and not self.alerted and not self.demo:
            self.tray.showMessage('BLUETTI · низький заряд', f'Залишилося {soc}% заряду')
            self.alerted = True
        elif soc > 25:
            self.alerted = False

    def check_age(self):
        if self.demo or self.paused or self.handoff_pending or not self.last_update:
            return
        age = int(time.monotonic() - self.last_update)
        if not self.stale and age > (45 if self.encrypted else 6):
            self.mark_stale()
            self.set_status(f'Зв’язок втрачено · даним {age} с')

    def mark_stale(self):
        if not self.stale:
            self.history.add(time.monotonic(), None, None)
        self.stale = True
        self.cluster.stale = True
        self.cluster.runtime_text = '—'
        self.runtime_estimator.clear()
        self.cluster.update()
        self.connection_dot.setStyleSheet(f'color: {MUTED}; font-size: 10px;')
        self.tray.setIcon(tray_icon(self.data.get('total_battery_percent'), True))
        self.tray.setToolTip('BLUETTI · останні дані, живого зв’язку немає')
        self.set_controls(False)
        self.refresh_details()

    def failed(self, message):
        if self.handoff_pending:
            self.handoff_pending = False
            self.paused = self.worker.paused
        self.mark_stale()
        self.set_status(message)

    def toggle_bluetooth(self):
        if self.demo or self.busy or self.handoff_pending:
            return
        self.handoff_pending = True
        self.mark_stale()
        self.set_status('Повертаю з’єднання…' if self.paused else 'Звільняю Bluetooth…')
        self.worker.submit('resume' if self.paused else 'pause')

    def on_paused(self, paused):
        self.paused = paused
        self.handoff_pending = False
        self.busy = False
        self.pending_field = None
        self.mark_stale()
        self.set_status('Bluetooth вільний для телефону' if paused else 'Підключаюся…')

    def toggle(self, field):
        self.set_controls(self.fresh())
        value = self.data.get(field)
        if not self.fresh() or self.busy or type(value) is not bool:
            return
        if value:
            title = 'AC-розетки' if field == 'ctrl_ac' else 'DC / USB-виходи'
            answer = QMessageBox.question(self, 'Вимкнути вихід?',
                f'Вимкнути {title}? Під’єднані пристрої втратять живлення.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.send_command(field, not value)

    def change_mode(self, index):
        value = self.mode.itemData(index)
        self.mode.setCurrentIndex(self.mode.findData(self.data.get('ctrl_charging_mode')))
        self.send_command('ctrl_charging_mode', value)

    def send_command(self, field, value):
        if self.demo or self.busy or self.encrypted or not self.profile.controls or not self.fresh():
            return
        self.busy = True
        self.pending_field = field
        self.set_controls(False)
        self.set_status('Змінюю налаштування · очікую підтвердження')
        self.worker.submit('write', (field, value))

    def command_finished(self, success, message):
        self.busy = False
        self.pending_field = None
        self.set_controls(success and self.fresh())
        self.set_status(message)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.position_locked:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            box = self.screen().availableGeometry()
            x, y = self.x(), self.y()
            for edge in (box.left() + 8, box.right() - self.width() - 7):
                if abs(x - edge) < 16:
                    x = edge
            for edge in (box.top() + 8, box.bottom() - self.height() - 7):
                if abs(y - edge) < 16:
                    y = edge
            self.move(x, y)
            self.keep_on_screen()
            self.save('position', self.pos())

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def shutdown(self):
        self.save('position', self.pos())
        self.clock.stop()
        self.cluster.animation.stop()
        self.worker.stop()
        self.tray.hide()
        self.auto_updates.stop()
        if self.update_dialog and self.update_dialog.worker.isRunning():
            self.update_dialog.worker.wait()
        if self.worker.isRunning():
            self.worker.wait(35000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--autostart', action='store_true', help='Використати збережені налаштування показу при автозапуску')
    parser.add_argument('--start-in-tray', action='store_true', help='Запустити лише в треї біля годинника')
    parser.add_argument('--render', type=Path)
    parser.add_argument('--render-details', type=Path)
    parser.add_argument('--size', choices=SIZES)
    parser.add_argument('--capture-live', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--capture-count', type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument('--keep-running', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('VitTools.BluettiWidget')
    app = QApplication(sys.argv)
    app.setApplicationName('BluettiWidget')
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    rendering = bool(args.render or args.render_details)
    mutex_handle = None
    if not rendering and sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        mutex_handle = kernel.CreateMutexW(None, False, 'Local\\VitToolsBluettiPowerCompanion')
        if not mutex_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            QMessageBox.information(None, 'BLUETTI', 'Віджет уже працює. Натисни значок біля годинника.')
            return 0
    lock = QLockFile(str(APP_DIR / 'widget.lock'))
    if not rendering and not lock.tryLock(100):
        QMessageBox.information(None, 'BLUETTI', 'Віджет уже працює. Натисни значок біля годинника.')
        return 0
    from logging.handlers import RotatingFileHandler
    log_dir = APP_DIR / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s', handlers=[RotatingFileHandler(
        log_dir / 'widget.log', maxBytes=500000, backupCount=2, encoding='utf-8')])
    settings = QSettings(str(APP_DIR / 'settings.ini'), QSettings.Format.IniFormat)
    start_in_tray = startup_hidden(settings, autostart=args.autostart,
        start_in_tray=args.start_in_tray, demo=args.demo, rendering=rendering,
        tray_available=QSystemTrayIcon.isSystemTrayAvailable())
    panel = Panel(demo=args.demo or rendering, start_worker=not rendering,
                  auto_open_picker=not start_in_tray)
    if args.size:
        panel.apply_size(args.size)
    app.aboutToQuit.connect(panel.shutdown)
    if not start_in_tray:
        panel.show()
    if rendering:
        if args.render_details:
            panel.open_details()
        def render():
            if args.render:
                panel.grab().save(str(args.render))
            if args.render_details:
                panel.details.grab().save(str(args.render_details))
            app.quit()
        QTimer.singleShot(800, render)
    if args.capture_live:
        captured = [False]
        read_times = []
        def save_capture():
            import json
            panel.grab().save(str(args.capture_live))
            args.capture_live.with_suffix('.json').write_text(json.dumps({
                'readings': len(read_times),
                'intervals': [round(b-a, 3) for a,b in zip(read_times,read_times[1:])],
                'last_success_unix': time.time(),
                'soc': panel.data.get('total_battery_percent'),
                'live': panel.fresh(),
                'gatt_ack': panel.worker.live.write_with_response if panel.worker.live else None,
                'runtime': panel.cluster.runtime_text,
            }), encoding='utf-8')
            if not args.keep_running:
                app.quit()
        def capture(data):
            read_times.append(time.monotonic())
            if captured[0]:
                return
            if len(read_times) < max(1, min(100, args.capture_count)):
                return
            captured[0] = True
            QTimer.singleShot(800, save_capture)
        panel.worker.reading.connect(capture)
        if not args.keep_running:
            QTimer.singleShot(60000, app.quit)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
