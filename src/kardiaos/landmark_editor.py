"""Edit the common time coordinates directly on a displayed limb-lead median."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QVBoxLayout, QWidget)

from .landmark_review import LABELS, validate_points
from .signal import FS

KEYS = tuple(LABELS)


class MedianEditorPlot(QWidget):
    place = Signal(int)
    step = Signal(int)

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMinimumSize(340, 210)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName('Mediana editável. Clique para posicionar o marco. Use as setas para ajuste fino.')

    def domain(self):
        e = self.editor
        size, anchor = e.state['length'], e.state['anchor']
        if not e.zoom.isChecked():
            return 0, size-1
        group = e.key()[0]
        lo, hi = {'p': (0, max(12, e.points.get('qon', anchor-10)-4)), 'q': (anchor-44, anchor+45),
                  't': (min(size-12, e.points.get('qoff', anchor+10)+4), size-1)}[group]
        actual = [v for k, v in e.points.items() if k.startswith(group)]
        return max(0, min([lo]+[v-6 for v in actual])), min(size-1, max([hi]+[v+6 for v in actual]))

    def graph(self):
        return QRectF(18, 38, max(1, self.width()-36), max(1, self.height()-83))

    def set_from_mouse(self, event):
        box = self.graph()
        if not box.contains(event.position()):
            return
        lo, hi = self.domain()
        self.place.emit(round(lo+(hi-lo)*(event.position().x()-box.left())/box.width()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.set_from_mouse(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.set_from_mouse(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.step.emit(-1 if event.key() == Qt.Key.Key_Left else 1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        e = self.editor
        rep = e.reps[e.lead.currentData()]
        key = e.key()
        values = np.asarray(rep['values_mv' if key.startswith('q') else 'pt_values_mv'])
        lo, hi = self.domain()
        y = values[lo:hi+1]
        band = rep.get('aligned_quartiles_mv', {}).get('qrs' if key.startswith('q') else 'pt')
        show_band = e.dispersion.isChecked() and band is not None
        low, high = y.min(), y.max()
        if show_band:
            band = np.asarray(band)
            low = min(low, band[0, lo:hi+1].min())
            high = max(high, band[1, lo:hi+1].max())
        margin = .16*max(high-low, .01)
        low, high = low-margin, high+margin
        box = self.graph()
        def x(i): return box.left() + (i-lo)*box.width()/(hi-lo)
        def ypixel(v): return box.bottom() - (v-low)*box.height()/(high-low)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#ffffff'))
        anchor = rep['r_index']
        for sample in range(anchor % 12, hi+1, 12):
            if sample < lo: continue
            px = x(sample)
            painter.setPen(QPen(QColor('#e4ece8')))
            painter.drawLine(QPointF(px, box.top()), QPointF(px, box.bottom()))
            if (sample-anchor) % (24 if hi-lo < 160 else 48) == 0:
                painter.setPen(QColor('#4b6262'))
                painter.drawText(QRectF(px-24, box.bottom()+4, 48, 21), Qt.AlignmentFlag.AlignCenter,
                                 str(round((sample-anchor)*1000/FS)))
        if show_band:
            area = QPainterPath(QPointF(x(lo), ypixel(band[0, lo])))
            for i in range(lo+1, hi+1): area.lineTo(x(i), ypixel(band[0, i]))
            for i in range(hi, lo-1, -1): area.lineTo(x(i), ypixel(band[1, i]))
            area.closeSubpath()
            painter.fillPath(area, QColor(68, 134, 113, 56))
        path = QPainterPath(QPointF(x(lo), ypixel(y[0])))
        for i in range(lo+1, hi+1): path.lineTo(x(i), ypixel(values[i]))
        painter.setPen(QPen(QColor('#194f49'), 2))
        painter.drawPath(path)
        original = e.state['automatic_points'].get(key)
        if original is not None and original != e.points.get(key) and lo <= original <= hi:
            painter.setPen(QPen(QColor('#859695'), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x(original), box.top()), QPointF(x(original), box.bottom()))
        for k, position in e.points.items():
            if not lo <= position <= hi: continue
            selected = k == key
            painter.setPen(QPen(QColor('#98520b' if selected else '#6b9291'), 2 if selected else 1,
                                Qt.PenStyle.SolidLine if selected else Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x(position), box.top()), QPointF(x(position), box.bottom()))
            if selected:
                painter.drawEllipse(QPointF(x(position), ypixel(values[position])), 3.5, 3.5)
        painter.setPen(QColor('#314e4b'))
        painter.drawText(QRectF(18, 5, self.width()-36, 26), Qt.AlignmentFlag.AlignVCenter,
                         f"{e.lead.currentText()}   ·   {LABELS[key]}   ·   {rep['group_size']} batimentos   ·   ms em relação a R")


class LandmarkEditor(QDialog):
    def __init__(self, analysis, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Revisão dos marcos da mediana')
        self.resize(940, 540)
        self.setMinimumSize(740, 450)
        self.reps = analysis['representative']
        self.state = analysis['measurements']['landmark_review']
        self.boundaries = analysis['measurements'].get('technical_quality', {}).get('boundaries', {})
        saved = self.state.get('saved', {})
        self.resuming = bool(saved) and self.state['origin'] == 'automatic'
        self.points = dict(saved.get('points', self.state['automatic_points']))
        self.point_leads = dict(saved.get('point_leads', self.state['automatic_leads']))
        self.automatic_requested = False
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        toolbar = QHBoxLayout()
        self.lead = QComboBox()
        self.lead.setAccessibleName('Derivação da mediana')
        for lead in self.reps: self.lead.addItem('D'+lead if lead in ('I','II','III') else lead, lead)
        toolbar.addWidget(QLabel('Derivação')); toolbar.addWidget(self.lead)
        self.zoom = QCheckBox('Ampliar onda selecionada'); self.zoom.setChecked(True)
        toolbar.addSpacing(10); toolbar.addWidget(self.zoom)
        self.dispersion = QCheckBox('Dispersão dos batimentos')
        self.dispersion.setToolTip('Faixa entre os percentis 25 e 75 dos batimentos alinhados na banda da onda selecionada.')
        toolbar.addWidget(self.dispersion); toolbar.addStretch()
        box.addLayout(toolbar)
        middle = QHBoxLayout()
        self.table = QTableWidget(len(KEYS), 2)
        self.table.setAccessibleName('Marcos da mediana')
        self.table.setHorizontalHeaderLabels(['Marco', 'Tempo'])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.setStyleSheet('QTableWidget {selection-background-color:#dcece3;selection-color:#174d3f;}'
                                 'QTableWidget::item:selected {background:#dcece3;color:#174d3f;}')
        self.table.setFixedWidth(214)
        for i, key in enumerate(KEYS):
            quality = self.boundaries.get(key, {})
            warning = quality.get('reason') if quality.get('status') in ('review', 'unverified') else ''
            item = QTableWidgetItem(LABELS[key]+(' *' if warning else ''))
            if warning: item.setToolTip(warning)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem())
        self.table.selectRow(0); middle.addWidget(self.table)
        self.plot = MedianEditorPlot(self); middle.addWidget(self.plot, 1); box.addLayout(middle, 1)
        line = QHBoxLayout()
        self.back = QPushButton('−1 amostra'); self.forward = QPushButton('+1 amostra')
        self.clear = QPushButton('Sem marca'); self.reset = QPushButton('Repor automáticos')
        for button in (self.back, self.forward, self.clear, self.reset): line.addWidget(button)
        line.addStretch(); box.addLayout(line)
        self.intervals = QLabel(); self.intervals.setWordWrap(True); box.addWidget(self.intervals)
        self.message = QLabel(); self.message.setWordWrap(True); box.addWidget(self.message)
        actions = QHBoxLayout(); self.auto_button = QPushButton('Usar análise automática')
        self.auto_button.setVisible(self.state['origin'] == 'manual'); actions.addWidget(self.auto_button)
        actions.addStretch()
        self.cancel_button = QPushButton('Cancelar'); actions.addWidget(self.cancel_button)
        self.apply_button = QPushButton('Confirmar marcos e aplicar'); self.apply_button.setObjectName('primary')
        actions.addWidget(self.apply_button); box.addLayout(actions)
        self.plot.place.connect(self.place); self.plot.step.connect(self.nudge)
        self.back.clicked.connect(lambda: self.nudge(-1)); self.forward.clicked.connect(lambda: self.nudge(1))
        self.clear.clicked.connect(lambda: self.place(None)); self.reset.clicked.connect(self.reset_points)
        self.table.currentCellChanged.connect(self.select_landmark); self.zoom.toggled.connect(lambda _: self.plot.update())
        self.dispersion.toggled.connect(lambda _: self.plot.update())
        self.lead.currentIndexChanged.connect(lambda _: self.plot.update())
        self.cancel_button.clicked.connect(self.reject); self.apply_button.clicked.connect(self.confirm)
        self.auto_button.clicked.connect(self.use_automatic)
        for button in self.findChildren(QPushButton): button.setAutoDefault(False)
        self.select_landmark()

    def key(self):
        return KEYS[max(0, self.table.currentRow())]

    def select_landmark(self, *_):
        reference = self.point_leads.get(self.key())
        if reference: self.lead.setCurrentIndex(self.lead.findData(reference))
        self.refresh()

    def place(self, position):
        key = self.key()
        if position is None:
            self.points.pop(key, None); self.point_leads.pop(key, None)
        else:
            self.points[key] = min(self.state['length']-1, max(0, int(position)))
            self.point_leads[key] = self.lead.currentData()
        self.refresh()

    def nudge(self, delta):
        if self.key() in self.points: self.place(self.points[self.key()]+delta)

    def reset_points(self):
        self.points = dict(self.state['automatic_points'])
        self.point_leads = dict(self.state['automatic_leads'])
        self.resuming = False
        self.select_landmark()

    def refresh(self, *_):
        for i, key in enumerate(KEYS):
            value = self.points.get(key)
            text = 'Sem marca' if value is None else f"{(value-self.state['anchor'])*1000/FS:+.1f} ms".replace('.', ',')
            self.table.item(i, 1).setText(text)
        for button in (self.back, self.forward, self.clear): button.setEnabled(self.key() in self.points)
        labels = []
        for name, left, right in [('P','pon','poff'), ('PR','pon','qon'), ('QRS','qon','qoff'), ('QT','qon','toff')]:
            value = (self.points[right]-self.points[left])*1000/FS if left in self.points and right in self.points else None
            labels.append(name+' '+(f'{value:.1f} ms'.replace('.', ',') if value is not None and value > 0 else '—'))
        self.intervals.setText('     '.join(labels))
        try:
            validate_points(self.points, self.state['anchor'], self.state['length'])
            hint = 'Revisão salva carregada.' if self.resuming else 'Selecione um marco e clique na curva.'
            self.message.setText(hint+' Confirmar aplica todos os marcos exibidos, inclusive os deixados sem marca.')
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.message.setText(str(exc)); self.apply_button.setEnabled(False)
        self.plot.update()

    def confirm(self):
        self.accept()

    def use_automatic(self):
        self.automatic_requested = True
        self.accept()
