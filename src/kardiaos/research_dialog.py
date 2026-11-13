"""Experimental model results, kept separate from the ECG print/report flow."""
import json
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QComboBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QFileDialog, QMessageBox, QFormLayout,
    QCheckBox, QDialogButtonBox)
from .research import analyze, inspect_window, calibration_valid, catalog


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
    def __init__(self, owner, keys):
        super().__init__(owner)
        self.owner, self.thread, self.result = owner, None, None
        self.specs = catalog()['models']
        box = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.models = QComboBox()
        for key in keys:
            self.models.addItem(self.specs[key]['name'], key)
        controls.addWidget(self.models, 1)
        self.run_button = QPushButton('Avaliar trecho')
        self.run_button.clicked.connect(self.start)
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
        self.models.currentIndexChanged.connect(self.reset)
        self.reset()

    def busy(self):
        return self.thread is not None and self.thread.isRunning()

    def reset(self, *_):
        self.result = None
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        spec = self.specs[self.models.currentData()]
        self.description.setText(spec['summary'])
        result = inspect_window(self.owner.recording, self.models.currentData(), self.owner.offset.value())
        self.state.setText('Pronto para avaliação experimental de 10 s.' if result['status'] == 'ready'
                           else 'Inconclusivo — ' + ' '.join(result['reasons']))
        self.provenance.setText('Fonte: ' + spec['source'] + '\nSHA-256: ' + spec['sha256'])

    def start(self):
        if self.busy():
            return
        self.result = None
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        self.state.setText('Avaliando localmente em CPU…')
        self.run_button.setEnabled(False)
        self.models.setEnabled(False)
        self.owner.offset.setEnabled(False)
        self.owner.calibrate_button.setEnabled(False)
        self.thread = AnalysisThread(self.owner.recording, self.models.currentData(), self.owner.offset.value(), self)
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
            self.state.setText('Inconclusivo — ' + ' '.join(result['reasons']))
        else:
            prefix = 'TESTE SINTÉTICO' if result['synthetic'] else 'AVALIAÇÃO EXPERIMENTAL'
            self.state.setText(f"{prefix} — {len(rows)} scores não calibrados. Nenhum diagnóstico foi confirmado.")
            self.provenance.setText(f"{result['runtime']} · {result['elapsed_seconds']:.2f} s · janela de 10 s\n"
                                    + result['preprocessing'] + '\nSHA-256: ' + result['checkpoint_sha256'])
        self.export_button.setEnabled(True)

    def finished(self):
        self.run_button.setEnabled(True)
        self.models.setEnabled(True)
        if not any(p.busy() for p in self.owner.panes):
            self.owner.offset.setEnabled(True)
            self.owner.calibrate_button.setEnabled(bool(self.owner.recording and not self.owner.recording.meta.get('synthetic')))

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
    def __init__(self, recording, parent=None):
        super().__init__(parent)
        self.recording = recording
        self.setWindowTitle('KardiaOS — avaliação experimental')
        self.resize(1020, 760)
        self.setMinimumSize(820, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(text_label('Dois modelos independentes · processamento local'))
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
        self.calibrate_button = QPushButton('Registrar referência de escala')
        self.calibrate_button.setEnabled(bool(recording and not recording.meta.get('synthetic')))
        self.calibrate_button.clicked.connect(self.calibrate)
        row.addWidget(self.calibrate_button)
        layout.addLayout(row)
        self.calibration = text_label('')
        layout.addWidget(self.calibration)
        tabs = QTabWidget()
        self.panes = [ModelPane(self, ['ecgfounder_1l']), ModelPane(self, ['deeppsp_2l', 'deeppsp_6l'])]
        tabs.addTab(self.panes[0], 'ECGFounder · I')
        tabs.addTab(self.panes[1], 'DeepPSP / CinC2021 · I–II ou 6L')
        layout.addWidget(tabs, 1)
        self.offset.valueChanged.connect(self.invalidate)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.update_calibration()

    def update_calibration(self):
        if self.recording and self.recording.meta.get('synthetic'):
            text = 'Dados sintéticos: apenas teste técnico do pipeline.'
        elif self.recording and calibration_valid(self.recording):
            text = 'Referência de escala e polaridade declarada para esta captura. O programa não verifica a referência.'
        else:
            text = 'Escala/polaridade sem referência verificada: análise inconclusiva, sem emissão de scores.'
        self.calibration.setText(text)

    def invalidate(self, *_):
        for pane in self.panes:
            pane.reset()
        self.update_calibration()

    def calibrate(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Referência externa para esta captura')
        box = QVBoxLayout(dialog)
        box.addWidget(text_label('Use uma referência conhecida de amplitude e polaridade. '
            'O traçado e os scores não permitem deduzir a calibração. Não informe dados pessoais nesta descrição.'))
        form = QFormLayout()
        factor = QDoubleSpinBox()
        factor.setDecimals(10)
        factor.setRange(0.00000001, 1)
        factor.setValue(self.recording.meta['mv_per_count'])
        reference = QLineEdit()
        reference.setPlaceholderText('Instrumento/referência, método e data da conferência')
        reference.setMaxLength(300)
        verified = QCheckBox('Conferi amplitude e polaridade das entradas utilizadas com essa referência')
        form.addRow('mV por contagem', factor)
        form.addRow('Referência', reference)
        box.addLayout(form)
        box.addWidget(verified)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        def update():
            buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(verified.isChecked() and len(reference.text().strip()) >= 8)
        verified.toggled.connect(update)
        reference.textChanged.connect(update)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.recording.meta.update(mv_per_count=factor.value(), amplitude_verified=True,
                research_calibration=dict(mv_per_count=factor.value(), polarity_verified=True, reference=reference.text().strip()))
            if self.parent() is not None:
                self.parent().dirty = True
                self.parent().paper.update()
            self.invalidate()

    def reject(self):
        if any(p.busy() for p in self.panes):
            return
        super().reject()

    def closeEvent(self, event):
        if any(p.busy() for p in self.panes):
            event.ignore()
        else:
            event.accept()
