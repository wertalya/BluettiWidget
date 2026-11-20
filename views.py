"""Vector instruments and charts; no device commands in this module."""
import math
import time
from collections import deque
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QWidget
TEXT = '#f1f5fa'
MUTED = '#91a0b4'
INPUT = '#76d9ed'
OUTPUT = '#ffb57d'
GREEN = '#8ae0b4'
STYLE_ACCENT = '''
QWidget#shell { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #192b3a,stop:1 #0b121b); border:1px solid #426078; border-radius:18px; }
QPushButton:checked { background:#153d36; color:#b4f5d7; border-color:#478e7d; }
QLineEdit,QPlainTextEdit { background:#0b121b; color:#f1f5fa; border:1px solid #3a495e; border-radius:7px; padding:8px; }
QLineEdit:focus,QPlainTextEdit:focus { border-color:#76d9ed; }
'''
STYLE = "\nQWidget { color:#f1f5fa; font-family:'Segoe UI'; font-size:12px; }\nQWidget#shell { background:#121923; border:1px solid #344152; border-radius:17px; }\nQDialog { background:#121923; }\nQLabel { background:transparent; border:none; }\nQLabel#muted { color:#91a0b4; }\nQLabel#eyebrow { color:#91a0b4; font-size:10px; font-weight:600; letter-spacing:1px; }\nQPushButton { background:#202c3c; border:1px solid #3a495e; border-radius:8px; padding:7px 10px; font-weight:600; }\nQPushButton:hover { background:#2c3c50; border-color:#6a809b; }\nQPushButton:pressed { background:#172230; }\nQPushButton:checked { background:#1c3c34; color:#a3edc5; border-color:#477b66; }\nQPushButton:disabled { color:#7c899b; border-color:#334050; background:#19222e; }\nQPushButton#quiet { background:transparent; border:none; padding:2px 5px; color:#b3c0d0; }\nQPushButton#quiet:hover { background:#2c3c50; color:white; }\nQPushButton#primary { background:#82d8c8; color:#102420; border:none; }\nQPushButton#primary:hover { background:#a3eadc; }\nQComboBox { background:#202c3c; border:1px solid #3a495e; border-radius:7px; padding:7px; }\nQComboBox QAbstractItemView { background:#202c3c; selection-background-color:#35516b; }\nQMenu { background:#192330; border:1px solid #3a495e; padding:6px; }\nQMenu::item { padding:8px 18px; }\nQMenu::item:selected { background:#30445b; }\nQToolTip { background:#253346; color:#f1f5fa; border:1px solid #51657f; padding:5px; }\n"

STYLE += STYLE_ACCENT

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
        self.runtime_caption = 'ДО РОЗРЯДУ'
        self.setAccessibleName('Заряд станції та вхідна і вихідна потужність')
        self.setToolTip('Шкала 0–2 кВт. Цифри показують повне значення, зокрема понад шкалу.')
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
        p.scale(self.width() / 338, self.height() / 132)
        for i, (cx, title, color) in enumerate([(58, 'ВХІД', INPUT), (280, 'ВИХІД', OUTPUT)]):
            color = MUTED if self.stale else color
            cy, radius = (51, 46)
            p.setPen(Qt.PenStyle.NoPen)
            face = QRadialGradient(cx,cy,54)
            face.setColorAt(0,QColor('#1a2b3c'))
            face.setColorAt(1,QColor('#09111b'))
            p.setBrush(face)
            p.drawEllipse(QRectF(cx - 51, cy - 51, 102, 102))
            arc = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
            p.setPen(QPen(QColor('#2e3c4f'), 3))
            p.drawArc(arc, 210 * 16, -240 * 16)
            ratio = min(max(self.values[i] / 2000, 0), 1)
            p.setPen(QPen(QColor(color), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(arc, 210 * 16, -int(240 * 16 * ratio))
            for tick in range(13):
                angle = math.radians(150 + tick * 20)
                major = tick % 3 == 0
                r = radius - (9 if major else 5)
                p.setPen(QPen(QColor('#8797ac' if major else '#4d5e75'), 1))
                p.drawLine(int(cx + math.cos(angle) * r), int(cy + math.sin(angle) * r), int(cx + math.cos(angle) * (radius - 2)), int(cy + math.sin(angle) * (radius - 2)))
            font(p, 10)
            p.setPen(QColor(MUTED))
            for text, angle in [('0', 150), ('1', 270), ('2', 390)]:
                a = math.radians(angle)
                x, y = (cx + math.cos(a) * 29, cy + math.sin(a) * 29)
                p.drawText(QRectF(x - 7, y - 7, 14, 14), Qt.AlignmentFlag.AlignCenter, text)
            a = math.radians(150 + 240 * ratio)
            p.setPen(QPen(QColor(color), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(cx, cy, int(cx + math.cos(a) * 34), int(cy + math.sin(a) * 34))
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))
            font(p, 10)
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(cx - 20, 63, 40, 14), Qt.AlignmentFlag.AlignCenter, 'кВт')
            p.setPen(QColor(MUTED if self.stale else TEXT))
            font(p, 24, True)
            value = '—' if self.targets[i] is None else f'{self.values[i]:.0f}'
            p.drawText(QRectF(cx - 55, 78, 110, 30), Qt.AlignmentFlag.AlignCenter, value)
            font(p, 11, True)
            p.setPen(QColor(color))
            p.drawText(QRectF(cx - 58, 111, 116, 17), Qt.AlignmentFlag.AlignCenter, title + ' · Вт')
        battery = QColor(MUTED if self.stale else GREEN if self.soc is None or self.soc > 20 else '#ff9b84')
        p.setPen(QPen(battery, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(155, 16, 27, 10), 2, 2)
        p.fillRect(QRectF(183, 19, 2, 4), battery)
        if self.soc is not None:
            p.fillRect(QRectF(158, 19, 21 * self.soc / 100, 4), battery)
        p.setPen(battery)
        font(p, 35, True)
        p.drawText(QRectF(116, 35, 106, 46), Qt.AlignmentFlag.AlignCenter, '—' if self.soc is None else f'{self.soc}%')
        p.setPen(QColor(MUTED))
        font(p, 13, True)
        p.drawText(QRectF(110, 83, 118, 22), Qt.AlignmentFlag.AlignCenter, self.runtime_text)
        font(p, 10)
        p.drawText(QRectF(108, 107, 122, 17), Qt.AlignmentFlag.AlignCenter, 'останні дані' if self.stale and self.soc is not None else self.runtime_caption)
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
