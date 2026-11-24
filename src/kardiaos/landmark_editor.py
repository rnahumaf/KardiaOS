"""Edit the common time coordinates directly on a displayed limb-lead median."""
import math
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QVBoxLayout, QWidget)

from .landmark_review import LABELS, save_review, set_review_active, validate_points
from .paper import MAJOR, MINOR, PAPER, screen_geometry
from .signal import FS

KEYS = tuple(LABELS)


class MedianEditorPlot(QWidget):
    place = Signal(int)
    step = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.zoom = 1.
        self.center = QPointF((editor.state['length']-1)/2, 0.)
        self.setMinimumSize(340, 210)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName('Mediana editável. Clique para marcar, role para ajustar o zoom e use as setas para ajuste fino.')

    def view_transform(self):
        e = self.editor
        ppmx, ppmy = screen_geometry(self.screen(), e.settings)
        sx = e.speed * ppmx * self.zoom / FS
        sy = e.gain * ppmy * self.zoom
        origin = self.graph().center()
        return QTransform(sx, 0, 0, -sy, origin.x()-self.center.x()*sx, origin.y()+self.center.y()*sy)

    def reset_view(self):
        e = self.editor
        rep = e.reps[e.lead.currentData()]
        waves = np.asarray([rep['values_mv'], rep['pt_values_mv']])
        self.center = QPointF((e.state['length']-1)/2, float((waves.min()+waves.max())/2))
        self.zoom = 1.
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event):
        pos = event.position()
        steps = event.angleDelta().y()/120 or event.pixelDelta().y()/60
        if not steps or not self.graph().contains(pos):
            event.ignore()
            return
        anchor = self.view_transform().inverted()[0].map(pos)
        factor = 1.3 ** max(-24., min(24., steps))
        self.zoom = max(.25, min(32., self.zoom*factor))
        self.center += anchor - self.view_transform().inverted()[0].map(pos)
        self.zoom_changed.emit(self.zoom)
        self.update()
        event.accept()

    def graph(self):
        return QRectF(18, 38, max(1, self.width()-36), max(1, self.height()-83))

    def set_from_mouse(self, event):
        box = self.graph()
        if not box.contains(event.position()):
            return
        index = round(self.view_transform().inverted()[0].map(event.position()).x())
        if 0 <= index < self.editor.state['length']:
            self.place.emit(index)

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

    def draw_grid(self, painter, transform, box, anchor):
        origin = transform.map(QPointF(anchor, 0))
        dx = transform.m11()*FS/self.editor.speed
        dy = -transform.m22()/self.editor.gain
        minor, major = QPainterPath(), QPainterPath()
        for axis, (start, end, zero, spacing) in enumerate((
                (box.left(), box.right(), origin.x(), dx), (box.top(), box.bottom(), origin.y(), dy))):
            step = 5 if spacing < 3 else 1
            for i in range(math.ceil((start-zero)/(spacing*step)), math.floor((end-zero)/(spacing*step))+1):
                line = i*step
                position = zero + line*spacing
                grid = major if line % 5 == 0 else minor
                if axis == 0:
                    grid.moveTo(position, box.top()); grid.lineTo(position, box.bottom())
                else:
                    grid.moveTo(box.left(), position); grid.lineTo(box.right(), position)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for grid, color, width in ((minor, MINOR, .35), (major, MAJOR, .7)):
            painter.setPen(QPen(color, width))
            painter.drawPath(grid)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    def paintEvent(self, event):
        e = self.editor
        rep = e.reps[e.lead.currentData()]
        key = e.key()
        values = np.asarray(rep['values_mv' if key.startswith('q') else 'pt_values_mv'])
        transform = self.view_transform()
        box = self.graph()
        inverse = transform.inverted()[0]
        lo = max(0, math.floor(inverse.map(box.topLeft()).x()))
        hi = min(len(values)-1, math.ceil(inverse.map(box.bottomRight()).x()))
        def point(i, v): return transform.map(QPointF(i, v))
        band = rep.get('aligned_quartiles_mv', {}).get('qrs' if key.startswith('q') else 'pt')
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#ffffff'))
        anchor = rep['r_index']
        painter.save()
        painter.setClipRect(box)
        painter.fillRect(box, PAPER)
        self.draw_grid(painter, transform, box, anchor)
        if lo <= hi and e.dispersion.isChecked() and band is not None:
            band = np.asarray(band)
            area = QPainterPath(point(lo, band[0, lo]))
            for i in range(lo+1, hi+1): area.lineTo(point(i, band[0, i]))
            for i in range(hi, lo-1, -1): area.lineTo(point(i, band[1, i]))
            area.closeSubpath()
            painter.fillPath(area, QColor(68, 134, 113, 56))
        if lo <= hi:
            path = QPainterPath(point(lo, values[lo]))
            for i in range(lo+1, hi+1): path.lineTo(point(i, values[i]))
            painter.setPen(QPen(QColor('#194f49'), 1.5))
            painter.drawPath(path)
        original = e.state['automatic_points'].get(key)
        if original is not None and original != e.points.get(key) and lo <= original <= hi:
            painter.setPen(QPen(QColor('#859695'), 1, Qt.PenStyle.DotLine))
            px = point(original, 0).x()
            painter.drawLine(QPointF(px, box.top()), QPointF(px, box.bottom()))
        for k, position in e.points.items():
            if not lo <= position <= hi: continue
            selected = k == key
            painter.setPen(QPen(QColor('#98520b' if selected else '#6b9291'), 2 if selected else 1,
                                Qt.PenStyle.SolidLine if selected else Qt.PenStyle.DashLine))
            marker = point(position, values[position])
            painter.drawLine(QPointF(marker.x(), box.top()), QPointF(marker.x(), box.bottom()))
            if selected:
                painter.drawEllipse(marker, 3.5, 3.5)
        painter.restore()
        painter.setPen(QColor('#4b6262'))
        stride = next((n for n in (3, 6, 15, 30, 60, 150, 300, 600, 1500) if n*transform.m11() >= 44), 3000)
        for sample in range(anchor + math.ceil((lo-anchor)/stride)*stride, hi+1, stride):
            px = point(sample, 0).x()
            painter.drawText(QRectF(px-24, box.bottom()+4, 48, 21), Qt.AlignmentFlag.AlignCenter,
                             str(round((sample-anchor)*1000/FS)))
        painter.setPen(QColor('#314e4b'))
        painter.drawText(QRectF(18, 5, self.width()-36, 26), Qt.AlignmentFlag.AlignVCenter,
                         f"{e.lead.currentText()}   ·   {LABELS[key]}   ·   {rep['group_size']} batimentos   ·   ms em relação a R")


class LandmarkEditor(QDialog):
    def __init__(self, analysis, parent=None, paper=None):
        super().__init__(parent)
        self.setWindowTitle('Revisão dos marcos da mediana')
        self.resize(940, 540)
        self.setMinimumSize(740, 450)
        self.reps = analysis['representative']
        self.state = analysis['measurements']['landmark_review']
        self.speed = paper.speed if paper is not None else 25.
        self.gain = paper.gain if paper is not None else 10.
        self.settings = getattr(paper.window(), 'settings', None) if paper is not None else None
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
        toolbar.addSpacing(10)
        self.dispersion = QCheckBox('Dispersão dos batimentos')
        self.dispersion.setToolTip('Faixa entre os percentis 25 e 75 dos batimentos alinhados na banda da onda selecionada.')
        toolbar.addWidget(self.dispersion); toolbar.addStretch()
        self.zoom_label = QLabel('100%')
        self.zoom_label.setAccessibleName('Zoom da mediana')
        self.zoom_label.setToolTip(f'Escala a 100%: {self.speed:g} mm/s e {self.gain:g} mm/mV estimados.')
        toolbar.addWidget(self.zoom_label)
        self.original_size = QPushButton('Tamanho original')
        self.original_size.setToolTip('Centralizar a mediana e voltar para 100%.')
        toolbar.addWidget(self.original_size)
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
        self.table.currentCellChanged.connect(self.select_landmark)
        self.original_size.clicked.connect(self.plot.reset_view)
        self.plot.zoom_changed.connect(lambda factor: self.zoom_label.setText(f'{factor*100:.0f}%'))
        self.dispersion.toggled.connect(lambda _: self.plot.update())
        self.lead.currentIndexChanged.connect(lambda _: self.plot.update())
        self.cancel_button.clicked.connect(self.reject); self.apply_button.clicked.connect(self.confirm)
        self.auto_button.clicked.connect(self.use_automatic)
        for button in self.findChildren(QPushButton): button.setAutoDefault(False)
        self.select_landmark()
        self.plot.reset_view()

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
            hint = 'Revisão salva carregada. ' if self.resuming else ''
            self.message.setText(hint+'Role sobre a curva para ajustar o zoom. Clique para marcar. Confirmar aplica também os limites deixados sem marca.')
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.message.setText(str(exc)); self.apply_button.setEnabled(False)
        self.plot.update()

    def confirm(self):
        self.accept()

    def use_automatic(self):
        self.automatic_requested = True
        self.accept()


def review_landmarks(recording, analysis, parent, paper):
    from .automatic_analysis import analysis_key
    editor = LandmarkEditor(analysis, parent, paper)
    try:
        if editor.exec() != QDialog.DialogCode.Accepted:
            return False
        if analysis.get('source_key') != analysis_key(recording):
            raise ValueError('A captura mudou. Confira a mediana atualizada.')
        if editor.automatic_requested:
            set_review_active(recording, editor.state, False)
        else:
            save_review(recording, editor.state, editor.points, editor.point_leads)
        return True
    finally:
        editor.deleteLater()
