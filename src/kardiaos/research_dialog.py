"""Experimental model results, kept separate from the ECG print/report flow."""
import json
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QFileDialog, QMessageBox, QDialogButtonBox)
from .research import analyze, inspect_window, catalog
from .processing import snapshot


def text_label(text):
    item = QLabel(text)
    item.setWordWrap(True)
    item.setTextFormat(Qt.TextFormat.PlainText)
    return item


class AnalysisThread(QThread):
    result_ready = Signal(dict)

    def __init__(self, recording, key, offset, parent):
        super().__init__(parent)
        self.recording, self.key, self.offset = recording, key, offset

    def run(self):
        try:
            result = analyze(self.recording, self.key, self.offset)
        except Exception:
            result = dict(status='inconclusive', scores=[], reasons=['Falha na análise local. Nenhum resultado foi aceito.'])
        self.result_ready.emit(result)


class ModelPane(QWidget):
    def __init__(self, owner, key):
        super().__init__(owner)
        self.owner, self.thread, self.result = owner, None, None
        self.key = key
        self.spec = catalog()['models'][key]
        box = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(text_label(self.spec['name']), 1)
        self.run_button = QPushButton('Reavaliar modelo')
        self.run_button.clicked.connect(lambda: self.owner.start_models([self]))
        controls.addWidget(self.run_button)
        box.addLayout(controls)
        self.description = text_label('')
        box.addWidget(self.description)
        self.state = text_label('')
        self.state.setObjectName('status')
        box.addWidget(self.state)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filtrar rótulos originais ou códigos')
        self.search.textChanged.connect(self.filter_rows)
        box.addWidget(self.search)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Rótulo original do modelo', 'Código', 'Score'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        box.addWidget(self.table, 1)
        self.provenance = text_label('')
        self.provenance.setObjectName('muted')
        box.addWidget(self.provenance)
        self.export_button = QPushButton('Exportar resultado JSON')
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_result)
        box.addWidget(self.export_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.reset()

    def busy(self):
        # Keep the UI busy until the queued finished slot has restored controls.
        return self.thread is not None

    def reset(self, *_):
        self.result = None
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        spec = self.spec
        self.description.setText(spec['summary'])
        result = inspect_window(self.owner.recording, self.key, self.owner.offset.value(), require_calibration=False)
        self.state.setText('Pronto para avaliação experimental de 10 s.' if result['status'] == 'ready'
                           else 'Não executado — ' + ' '.join(result['reasons']))
        self.provenance.setText('Fonte: ' + spec['source'] + '\nSHA-256: ' + spec['sha256'])

    def start(self):
        if self.busy():
            return
        self.result = None
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        self.state.setText('Avaliando localmente em CPU…')
        self.run_button.setEnabled(False)
        self.thread = AnalysisThread(self.owner.recording, self.key, self.owner.offset.value(), self)
        self.thread.result_ready.connect(self.show_result)
        self.thread.finished.connect(self.finished)
        self.thread.start()

    def show_result(self, result):
        self.result = result
        rows = sorted(result.get('scores', []), key=lambda r: r['score'], reverse=True)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for col, value in enumerate((row['name'], row['code'], f"{row['score']:.4f}")):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, col, item)
        self.table.resizeRowsToContents()
        self.filter_rows()
        if result['status'] == 'inconclusive':
            self.state.setText('Sem resultado — ' + ' '.join(result['reasons']))
        else:
            prefix = 'TESTE SINTÉTICO' if result['synthetic'] else 'AVALIAÇÃO EXPERIMENTAL'
            self.state.setText(f"{prefix} — {len(rows)} scores não calibrados. Nenhum diagnóstico foi confirmado.")
            self.provenance.setText(f"{result['runtime']} · {result['elapsed_seconds']:.2f} s · janela de 10 s\n"
                                    + result['preprocessing'] + '\nSHA-256: ' + result['checkpoint_sha256'])
        self.export_button.setEnabled(True)

    def finished(self):
        self.thread.deleteLater()
        self.thread = None
        self.owner.start_next()

    def filter_rows(self, *_):
        query = self.search.text().casefold()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, query not in ' '.join(self.table.item(row, col).text().casefold() for col in (0, 1)))

    def export_result(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar avaliação experimental', 'avaliacao.research.json', 'JSON (*.json)')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as file:
                    json.dump(self.result, file, ensure_ascii=False, indent=2, allow_nan=False)
            except OSError:
                QMessageBox.warning(self, 'Exportação', 'Não foi possível gravar o resultado no local escolhido.')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.table.resizeRowsToContents()


class ResearchDialog(QDialog):
    def __init__(self, recording, parent=None, *, autostart=True):
        super().__init__(parent)
        self.recording = snapshot(recording)
        self.pending = []
        self.running = False
        self.closing = False
        self.batch = []
        self.setWindowTitle('KardiaOS — avaliação experimental')
        self.resize(1020, 760)
        self.setMinimumSize(820, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(text_label('Análise neural exploratória · processamento local'))
        layout.addWidget(text_label('Sinal bruto · escala configurada · polaridade registrada · filtros próprios de cada modelo.'))
        layout.addWidget(text_label('Scores sigmoid não são probabilidades calibradas nem diagnósticos. '
            'Não há validação clínica no KardiaMobile. Rótulos temporais do ECGFounder não demonstram mudança entre exames; '
            'Q anormal não determina área inativa ou infarto.'))
        row = QHBoxLayout()
        row.addWidget(QLabel('Início após estabilização'))
        self.offset = QDoubleSpinBox()
        duration = max(0, recording.last_time - float(recording.meta.get('start') or 0) - 10 + 1/300) if recording else 0
        self.offset.setRange(0, duration)
        self.offset.setDecimals(2)
        self.offset.setSuffix(' s')
        row.addWidget(self.offset)
        row.addStretch()
        self.calibrate_button = QPushButton('Evidências independentes')
        self.calibrate_button.setEnabled(bool(recording and not recording.meta.get('synthetic')))
        self.calibrate_button.clicked.connect(self.calibrate)
        row.addWidget(self.calibrate_button)
        layout.addLayout(row)
        self.calibration = text_label('')
        layout.addWidget(self.calibration)
        self.tabs = QTabWidget()
        self.panes = [ModelPane(self, key) for key in ('ecgfounder_1l', 'deeppsp_2l', 'deeppsp_6l')]
        for pane, title in zip(self.panes, ('ECGFounder · I', 'DeepPSP · I–II', 'DeepPSP · 6L')):
            self.tabs.addTab(pane, title)
        layout.addWidget(self.tabs, 1)
        self.offset.valueChanged.connect(self.invalidate)
        self.progress = text_label('Pronto para avaliar os modelos compatíveis.')
        layout.addWidget(self.progress)
        self.run_all = QPushButton('Reavaliar todos')
        self.run_all.clicked.connect(self.start_all)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText('Fechar')
        close.addButton(self.run_all, QDialogButtonBox.ButtonRole.ActionRole)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.update_calibration()
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        if autostart:
            QTimer.singleShot(0, self.start_all)

    def busy(self):
        return self.running

    def set_busy(self, busy):
        self.running = busy
        self.offset.setEnabled(not busy)
        self.run_all.setEnabled(not busy)
        self.calibrate_button.setEnabled(not busy and bool(self.recording and not self.recording.meta.get('synthetic')))
        for pane in self.panes:
            pane.run_button.setEnabled(not busy)

    def start_all(self):
        self.start_models(self.panes)

    def start_models(self, panes):
        if self.busy() or self.closing:
            return
        self.batch = list(panes)
        self.pending = []
        for pane in self.batch:
            pane.reset()
            check = inspect_window(self.recording, pane.key, self.offset.value(), require_calibration=False)
            if check['status'] == 'ready':
                pane.state.setText('Aguardando avaliação local…')
                self.pending.append(pane)
            else:
                check.update(mode='exploratory', clinical_validation=False, calibration_verified=False)
                pane.show_result(check)
                pane.state.setText('Não executado — ' + ' '.join(check['reasons']))
        self.set_busy(True)
        self.start_next()

    def start_next(self):
        if self.pending:
            pane = self.pending.pop(0)
            self.progress.setText(f'Avaliando {self.batch.index(pane)+1} de {len(self.batch)} · {pane.spec["name"]}')
            pane.start()
            return
        self.set_busy(False)
        completed = sum(bool(p.result and p.result.get('scores')) for p in self.batch)
        self.progress.setText(f'Avaliação concluída · {completed} de {len(self.batch)} modelos com resultado.'
                              + (' Consulte o motivo nas abas sem resultado.' if completed < len(self.batch) else ''))

    def update_calibration(self):
        from .orientation import evidence_summary
        self.calibration.setText(evidence_summary(self.recording))

    def invalidate(self, *_):
        for pane in self.panes:
            pane.reset()
        self.update_calibration()
        self.progress.setText('Trecho alterado. Selecione Reavaliar todos para atualizar os resultados.')

    def calibrate(self):
        from .evidence_dialog import EvidenceDialog
        if EvidenceDialog(self.recording,self).exec()==QDialog.DialogCode.Accepted:
            if self.parent() is not None and hasattr(self.parent(),'dirty'):self.parent().dirty=True
            self.invalidate()

    def reject(self):
        if self.busy():
            return
        self.closing = True
        super().reject()

    def closeEvent(self, event):
        if self.busy():
            event.ignore()
        else:
            self.closing = True
            event.accept()
