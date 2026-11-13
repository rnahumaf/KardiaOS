"""Physical paper geometry in Qt logical pixels, independent of Windows scaling."""
import math
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QWidget
from .signal import LEADS

PAPER = QColor("#fffcf1")
MINOR = QColor("#eedfcb")
MAJOR = QColor("#cfb89e")
INK = QColor("#164e50")


def screen_geometry(screen):
    size = screen.physicalSize()
    rect = screen.geometry()
    if size.width() > 10 and size.height() > 10:
        return rect.width() / size.width(), rect.height() / size.height()
    fallback = screen.logicalDotsPerInch() / 25.4
    return fallback, fallback


def screen_key(screen):
    return f"{screen.name()}_{screen.size().width()}x{screen.size().height()}_{screen.devicePixelRatio()}"


class ECGPaper(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 500)
        self.recording = None
        self.cursor = 0.0
        self.ppmx = self.ppmy = 4.0
        self.speed = 25.0
        self.gain = 10.0
        self.raw_mode = False
        self.overlay = "Pronto para uma nova captura"
        self.overlay_detail = "Toque os dois eletrodos superiores e apoie o inferior na perna esquerda."
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), PAPER)
        width, height = self.width(), self.height()
        margin, gutter = 18.0, 18.0
        r = self.recording
        mode = r.mode_at(self.cursor) if r is not None and r.n else 1
        displayed = (0, 5, 1, 4, 2, 3) if mode == 6 else (0,)
        columns, rows = (2, 3) if mode == 6 else (1, 1)
        cw = (width - margin * 2 - gutter * (columns - 1)) / columns
        rh = (height - 24) / rows
        visible = r is not None and r.n and r.meta.get("start") is not None
        times = r.times[:r.n] if visible else np.empty(0)
        available_seconds = max(0.5, (cw - 25 * self.ppmx) / (self.ppmx * self.speed))
        start = float(r.meta["start"]) if visible else 0
        right = max(start + available_seconds, self.cursor)
        left = right - available_seconds
        first = int(np.searchsorted(times, max(start, left)))
        last = int(np.searchsorted(times, min(self.cursor, right), side="right"))
        last = max(first, last)
        leads = r.lead_values(first, last, raw=self.raw_mode) if visible else None
        p.setFont(QFont("Segoe UI", 9))
        for position, lead in enumerate(displayed):
            col, row = position % columns, position // columns
            rect = QRectF(margin + col * (cw + gutter), 10 + row * rh, cw, rh - 8)
            p.save()
            p.setClipRect(rect)
            for j in range(math.ceil(rect.width() / self.ppmx) + 1):
                x = rect.left() + j * self.ppmx
                p.setPen(QPen(MAJOR if j % 5 == 0 else MINOR, 0.7 if j % 5 == 0 else 0.35))
                p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            for j in range(math.ceil(rect.height() / self.ppmy) + 1):
                y = rect.top() + j * self.ppmy
                p.setPen(QPen(MAJOR if j % 5 == 0 else MINOR, 0.7 if j % 5 == 0 else 0.35))
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            baseline = rect.top() + round(rect.height() / 2 / (5 * self.ppmy)) * 5 * self.ppmy
            p.setPen(QPen(QColor("#b69a7c"), 0.9))
            p.drawLine(QPointF(rect.left(), baseline), QPointF(rect.right(), baseline))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(INK, 1.25))
            pulse = QPainterPath(QPointF(rect.left() + 13 * self.ppmx, baseline))
            for x, y in ((14, 0), (14, -self.gain), (19, -self.gain), (19, 0), (21, 0)):
                pulse.lineTo(rect.left() + x * self.ppmx, baseline + y * self.ppmy)
            p.drawPath(pulse)
            if visible and last > first:
                x0 = rect.left() + 24 * self.ppmx
                path = QPainterPath()
                connected = False
                for k in range(first, last):
                    value = leads[k - first, lead]
                    if not np.isfinite(value) or (k > first and times[k] - times[k - 1] > 0.12):
                        connected = False
                    if not np.isfinite(value):
                        continue
                    x = x0 + (times[k] - left) * self.speed * self.ppmx
                    y = baseline - value * self.gain * self.ppmy
                    if connected:
                        path.lineTo(x, y)
                    else:
                        path.moveTo(x, y)
                    connected = True
                p.setPen(QPen(INK, 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            label_rect = QRectF(rect.left() + 3, rect.top() + 3, 38, 22)
            p.fillRect(label_rect, PAPER)
            p.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            p.setPen(INK)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, LEADS[lead])
            p.restore()
        if self.overlay:
            panel = QRectF(width / 2 - min(310, width / 2 - 20), height / 2 - 48, min(620, width - 40), 96)
            p.setPen(QPen(QColor("#dfd3bd"), 1))
            p.setBrush(QColor("#fffcf1"))
            p.drawRoundedRect(panel, 10, 10)
            p.setPen(INK)
            p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            p.drawText(panel.adjusted(10, 8, -10, -40), Qt.AlignmentFlag.AlignCenter, self.overlay)
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor("#6a6e64"))
            p.drawText(panel.adjusted(18, 43, -18, -6), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.overlay_detail)
        p.end()


class Ruler(QWidget):
    def __init__(self, px, py):
        super().__init__()
        self.px, self.py = px, py
        self.setMinimumSize(int(100 * px + 60), int(50 * py + 60))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), PAPER)
        p.setPen(QPen(INK, 1))
        p.drawLine(QPointF(30, 30), QPointF(30 + 100 * self.px, 30))
        p.drawLine(QPointF(30, 30), QPointF(30, 30 + 50 * self.py))
        for i in range(101):
            h = 10 if i % 10 == 0 else 6 if i % 5 == 0 else 3
            p.drawLine(QPointF(30 + i * self.px, 30), QPointF(30 + i * self.px, 30 + h))
        for i in range(51):
            h = 10 if i % 10 == 0 else 6 if i % 5 == 0 else 3
            p.drawLine(QPointF(30, 30 + i * self.py), QPointF(30 + h, 30 + i * self.py))
        p.drawText(QRectF(70, 60, self.width() - 90, 80), Qt.TextFlag.TextWordWrap,
                   "Referências: 100 mm na horizontal e 50 mm na vertical.\nMeça entre os extremos das linhas.")
        p.end()
