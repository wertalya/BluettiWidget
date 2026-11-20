"""Vector instruments and charts; no device commands in this module."""
import math
import time
from collections import deque
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QWidget
TEXT = '#f1f5fa'
MUTED = '#91a0b4'
INPUT = '#76d9ed'
OUTPUT = '#ffb57d'
GREEN = '#8ae0b4'
STYLE = '''
QWidget { color:#f1f5fa; font-family:'Segoe UI'; font-size:12px; }
QDialog { background:#121923; }
QLabel { background:transparent; border:none; }
QLabel#muted { color:#91a0b4; }
QLabel#eyebrow { color:#91a0b4; font-size:10px; font-weight:600; letter-spacing:1px; }
QPushButton { background:#202c3c; border:1px solid #3a495e; border-radius:8px; padding:7px 10px; font-weight:600; }
QPushButton:hover { background:#2c3c50; border-color:#6a809b; }
QPushButton:pressed { background:#172230; }
QPushButton:disabled { color:#7c899b; border-color:#334050; background:#19222e; }
QPushButton#quiet { background:transparent; border:none; padding:2px 5px; color:#b3c0d0; }
QPushButton#quiet:hover { background:#2c3c50; color:white; }
QPushButton#primary { background:#82d8c8; color:#102420; border:none; }
QPushButton#primary:hover { background:#a3eadc; }
QPushButton#primary:disabled { background:#27373d; color:#94a5ac; }
QComboBox { background:#202c3c; border:1px solid #3a495e; border-radius:7px; padding:7px; }
QComboBox QAbstractItemView { background:#202c3c; selection-background-color:#35516b; }
QMenu { background:#192330; border:1px solid #3a495e; padding:6px; }
QMenu::item { padding:8px 18px; }
QMenu::item:selected { background:#30445b; }
QToolTip { background:#253346; color:#f1f5fa; border:1px solid #51657f; padding:5px; }
QWidget#shell { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #182532,stop:1 #101820); border:1px solid #344355; border-radius:18px; }
QPushButton:checked { background:#153d36; color:#b4f5d7; border-color:#478e7d; }
QLineEdit,QPlainTextEdit { background:#0b121b; color:#f1f5fa; border:1px solid #3a495e; border-radius:7px; padding:8px; }
QLineEdit:focus,QPlainTextEdit:focus { border-color:#76d9ed; }
'''

def label(text, name='', size=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    if size:
        item.setStyleSheet(f'font-size:{size}px; font-weight:600;')
    return item

def font(p, pixels, bold=False):
    f = QFont('Segoe UI')
    f.setPixelSize(pixels)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    p.setFont(f)

class InstrumentCluster(QWidget):

    def __init__(self):
        super().__init__()
        self.values = [0.0, 0.0]
        self.targets = [None, None]
        self.soc = None
        self.stale = True
        self.runtime_text = '—'
        self.setAccessibleName('Заряд станції та вхідна і вихідна потужність')
        self.animation = QTimer(self)
        self.animation.setInterval(16)
        self.animation.setTimerType(Qt.TimerType.PreciseTimer)
        self.last_frame = time.perf_counter()
        self.animation.timeout.connect(self.step)

    def set_data(self, soc, input_w, output_w):
        self.soc = soc
        self.targets = [input_w, output_w]
        self.stale = False
        self.setAccessibleDescription(f'Заряд {soc} відсотків. Вхід {input_w} ват. Вихід {output_w} ват.')
        if self.isVisible() and any((abs(v - (t or 0)) > 0.5 for v, t in zip(self.values, self.targets))):
            if not self.animation.isActive():
                self.last_frame = time.perf_counter()
                self.animation.start()
        else:
            self.values = [t or 0 for t in self.targets]
        self.update()

    def step(self):
        now = time.perf_counter()
        alpha = 1-math.exp(-min(.25,now-self.last_frame)/.11)
        self.last_frame = now
        for i in range(2):
            self.values[i] += ((self.targets[i] or 0) - self.values[i]) * alpha
        if not self.isVisible() or all((abs(v - (t or 0)) < 0.5 for v, t in zip(self.values, self.targets))):
            self.values = [t or 0 for t in self.targets]
            self.animation.stop()
        self.update()

    def hideEvent(self, event):
        self.animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        battery = QColor(MUTED if self.stale else '#ff9b84' if self.soc is not None and self.soc <= 20 else GREEN)
        p.setPen(battery)
        font(p, min(40, int(height * .34)), True)
        soc = '—' if self.soc is None else f'{self.soc}%'
        p.drawText(QRectF(3, 0, width * .47, height * .49),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, soc)

        bar = QRectF(4, height * .51, width - 8, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#344355'))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if self.soc:
            bar.setWidth(bar.width() * self.soc / 100)
            p.setBrush(battery)
            p.drawRoundedRect(bar, 2.5, 2.5)

        font(p, 12)
        p.setPen(QColor(MUTED))
        hint = ('Останні дані' if self.stale and self.soc is not None else
                f'До розряду {self.runtime_text}' if self.runtime_text != '—' else 'Заряд батареї')
        p.drawText(QRectF(width * .43, 0, width * .57 - 4, height * .49),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, hint)
        for index, (title, color) in enumerate((('Вхід', INPUT), ('Вихід', OUTPUT))):
            left = index * width / 2 + 4
            p.setPen(QColor(MUTED if self.stale else color))
            font(p, 11, True)
            p.drawText(QRectF(left, height * .64, width / 2 - 8, height * .14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
            p.setPen(QColor(MUTED if self.stale else TEXT))
            font(p, min(22, int(height * .2)), True)
            value = '—' if self.targets[index] is None else f'{self.values[index]:.0f} Вт'
            p.drawText(QRectF(left, height * .78, width / 2 - 8, height * .22),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        p.end()


class PowerHistory(QWidget):

    def __init__(self):
        super().__init__()
        self.samples = deque(maxlen=900)
        self.max_gap = 6
        self.setMinimumHeight(145)
        self.setAccessibleName('Графік вхідної та вихідної потужності за останні 10 хвилин')

    def add(self, timestamp, input_w, output_w):
        self.samples.append((timestamp, input_w, output_w))
        while self.samples and timestamp - self.samples[0][0] > 600:
            self.samples.popleft()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0, 0, self.width(), self.height())
        p.setBrush(QColor('#0d141e'))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(box, 10, 10)
        valid = [s for s in self.samples if s[1] is not None and s[2] is not None]
        if len(valid) < 2:
            font(p, 12)
            p.setPen(QColor(MUTED))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, 'Збираю історію потужності…')
            p.end()
            return
        end = self.samples[-1][0]
        ceiling = max(500, math.ceil(max((max(s[1], s[2]) for s in valid)) / 500) * 500)
        plot = box.adjusted(42, 17, -15, -29)
        font(p, 10)
        for fraction in (0, 0.5, 1):
            y = plot.bottom() - fraction * plot.height()
            p.setPen(QPen(QColor('#263448'), 1, Qt.PenStyle.DotLine))
            p.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(1, y - 8, 35, 16), Qt.AlignmentFlag.AlignRight, f'{ceiling * fraction:g}')
        p.drawText(QRectF(plot.left(), plot.bottom() + 7, 90, 18), '−10 хв')
        p.drawText(QRectF(plot.right() - 70, plot.bottom() + 7, 70, 18), Qt.AlignmentFlag.AlignRight, 'зараз · Вт')
        for index, color in [(1, INPUT), (2, OUTPUT)]:
            path = QPainterPath()
            previous = None
            for sample in self.samples:
                stamp, value = (sample[0], sample[index])
                if value is None:
                    previous = None
                    continue
                x = plot.right() - (end - stamp) / 600 * plot.width()
                y = plot.bottom() - value / ceiling * plot.height()
                if previous is None or stamp - previous > self.max_gap:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
                previous = stamp
            p.setPen(QPen(QColor(color), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.end()
