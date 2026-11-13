"""Visible, opaque single-page preview, shared by PDF export and printing."""
from pathlib import Path
import math
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize, QRectF
from PySide6.QtGui import QImage, QPainter, QPixmap, QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDoubleSpinBox, QFileDialog, QMessageBox, QSizePolicy, QComboBox)
from .report import pdf_bytes, page_plan
from .automatic_analysis import analysis_key,cache_analysis,cached_analysis
from .orientation import evidence_state


def render_page(data, size=QSize(1404, 992)):
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    document = QPdfDocument()
    try:
        document.load(buffer)
        if document.status() != QPdfDocument.Status.Ready or document.pageCount() != 1:
            raise RuntimeError("O PDF não contém uma página pronta para impressão.")
        rendered = document.render(0, size)
        if rendered.isNull():
            raise RuntimeError("Não foi possível renderizar a prévia do ECG.")
        result = QImage(size, QImage.Format.Format_RGB32)
        result.fill(Qt.GlobalColor.white)
        painter = QPainter(result)
        painter.drawImage(0, 0, rendered)
        painter.end()
        return result
    finally:
        document.close()
        buffer.close()


def configure_printer(printer):
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setFullPage(True)
    printer.setCopyCount(1)
    printer.setFromTo(1, 1)
    printer.setDuplex(QPrinter.DuplexMode.DuplexNone)


def print_page(data, printer):
    layout = printer.pageLayout()
    if layout.pageSize().id() != QPageSize.PageSizeId.A4 or layout.orientation() != QPageLayout.Orientation.Landscape:
        raise ValueError("Escolha A4 paisagem para preservar os milímetros do quadriculado.")
    rendered = render_page(data, QSize(3508, 2480))
    printer.setFullPage(True)
    painter = QPainter(printer)
    if not painter.isActive():
        raise RuntimeError("A impressora não iniciou a página.")
    try:
        target = QRectF(0, 0, 297 / 25.4 * printer.resolution(), 210 / 25.4 * printer.resolution())
        painter.fillRect(target, Qt.GlobalColor.white)
        painter.drawImage(target, rendered)
    finally:
        if not painter.end():
            raise RuntimeError("A impressora não confirmou o envio da página.")


class PrintPreview(QDialog):
    def __init__(self, recording, speed=25, gain=10, raw=False, parent=None, autostart=True):
        super().__init__(parent)
        self.setWindowTitle("KardiaOS — Prévia de impressão")
        self.resize(1120, 850)
        self.setMinimumSize(800, 600)
        self.recording, self.speed, self.gain, self.raw = recording, speed, gain, raw
        from .measurements import measure_recording
        self.analysis=dict(status='running',mode='normal',source_key=analysis_key(recording),measurements=measure_recording(recording),scenarios=[],unavailable=[])
        self.thread=None;self.closing=False;self.autostart=autostart
        self._desired_key=None;self._worker_key=None
        self.data = b""
        self.page_image = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        top.addWidget(QLabel("Início do trecho"))
        self.offset = QDoubleSpinBox()
        self.offset.setDecimals(1)
        self.offset.setSuffix(" s")
        end = min(float(recording.meta.get("end") or recording.last_time), recording.last_time)
        max_offset = math.floor(max(0, end - float(recording.meta["start"]) - 1 / 300) * 10) / 10
        self.offset.setRange(0, max_offset)
        top.addWidget(self.offset)
        self.layout_choice = QComboBox()
        self.layout_choice.addItem("Automático", "auto")
        self.layout_choice.addItem("DI em linhas", "di")
        self.layout_choice.addItem("Seis derivações", "six")
        top.addWidget(self.layout_choice)
        top.addStretch()
        top.addWidget(QLabel(f"1 folha · A4 paisagem · {speed:g} mm/s · {gain:g} mm/mV"))
        layout.addLayout(top)
        self.span_note = QLabel("O bruto completo é preservado.")
        self.span_note.setWordWrap(True)
        layout.addWidget(self.span_note)
        destinations = QHBoxLayout()
        destinations.addWidget(QLabel("Impressora"))
        self.printers = QComboBox()
        self.printers.addItems(QPrinterInfo.availablePrinterNames())
        default = QPrinterInfo.defaultPrinterName()
        if self.printers.findText(default) >= 0:
            self.printers.setCurrentText(default)
        destinations.addWidget(self.printers, 1)
        destinations.addWidget(QLabel("1 página · 1 cópia"))
        layout.addLayout(destinations)
        self.page = QLabel()
        self.page.setMinimumSize(400, 280)
        self.page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page.setStyleSheet("background: #dce3df; border: 1px solid #c7d3cc;")
        layout.addWidget(self.page, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Tamanho real (100%), sem ajustar à página."))
        bottom.addStretch()
        save = self.save_button = QPushButton("Salvar PDF")
        save.clicked.connect(self.save_pdf)
        self.print_button = QPushButton("Imprimir 1 folha")
        self.print_button.setEnabled(self.printers.count() > 0 and self.analysis is not None and self.analysis["status"]!="running")
        self.print_button.setObjectName("primary")
        self.print_button.clicked.connect(self.print_current)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        for button in (save, self.print_button, close):
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.status = QLabel("" if self.printers.count() else "Nenhuma impressora instalada. Você pode salvar o PDF.")
        layout.addWidget(self.status)
        self.offset.valueChanged.connect(self.request_analysis)
        self.layout_choice.currentIndexChanged.connect(self.request_analysis)
        self.request_analysis()

    def request_analysis(self,*_):
        from .measurements import measure_recording,empty
        if self.closing:return
        try:
            plan=page_plan(self.recording,self.speed,self.gain,self.raw,self.offset.value(),self.layout_choice.currentData(),dict(mode='normal'))
        except ValueError as exc:
            self.data=b'';self.page_image=None;self.page.clear();self.status.setText(str(exc));self.save_button.setEnabled(False);self.print_button.setEnabled(False);return
        offset=self.offset.value();duration=plan['end']-plan['start']
        self._desired_key=analysis_key(self.recording,offset=offset,duration=duration)
        cached=cached_analysis(self.recording,offset,duration)
        self.analysis=cached or dict(status='completed' if self.raw else 'running',mode='normal',source_key=analysis_key(self.recording),
            scope=dict(offset_seconds=offset,duration_seconds=duration),
            measurements=empty('Vista bruta.') if self.raw else measure_recording(self.recording,offset,duration),scenarios=[],unavailable=[])
        self.refresh()
        if self.thread is not None and self.thread.isRunning():
            if self._worker_key!=self._desired_key or self.raw:self.thread.requestInterruption()
            return
        if self.raw or cached is not None or not self.autostart:return
        from .analysis_dialog import AutomaticThread
        self._worker_key=self._desired_key
        self.thread=AutomaticThread(self.recording,self,offset=offset,duration=duration)
        self.thread.result_ready.connect(self.analysis_done);self.thread.finished.connect(self.worker_finished);self.thread.start()

    def analysis_done(self,result):
        if self._worker_key!=self._desired_key:return
        if 'measurements' not in result:result['measurements']=self.analysis['measurements']
        if 'source_key' not in result:result['source_key']=self.analysis['source_key']
        self.analysis=result;cache_analysis(self.recording,result)
        if not self.closing:self.refresh()

    def worker_finished(self):
        if self.closing:super().reject()
        elif self._worker_key!=self._desired_key:self.request_analysis()

    def reject(self):
        self.closing=True
        if self.thread is not None and self.thread.isRunning():self.thread.requestInterruption();return
        super().reject()

    def closeEvent(self,event):
        self.closing=True
        if self.thread is not None and self.thread.isRunning():self.thread.requestInterruption();event.ignore()
        else:event.accept()

    def refresh(self):
        try:
            choice = self.layout_choice.currentData()
            plan = page_plan(self.recording, self.speed, self.gain, self.raw, self.offset.value(), choice, self.analysis)
            self.data = pdf_bytes(self.recording, self.speed, self.gain, self.raw, self.offset.value(), choice, self.analysis)
            self.page_image = render_page(self.data)
            self.span_note.setText(f"{len(plan['rows'])} faixas · até {plan['end']-plan['start']:.1f} s nesta folha · restante {plan['remaining_seconds']:.1f} s. Sem comprimir o tempo ou mudar o ganho.")
            self.save_button.setEnabled(self.analysis is not None and self.analysis["status"]!="running")
            self.print_button.setEnabled(self.printers.count() > 0 and self.analysis is not None and self.analysis["status"]!="running")
            self.status.setText("Calculando analise local para a folha; aguarde. Fechar interrompe o processamento." if self.analysis["status"]=="running" else ("" if self.printers.count() else "Nenhuma impressora instalada. Você pode salvar o PDF."))
            self.fit_page()
        except ValueError as exc:
            self.data = b""
            self.page_image = None
            self.page.clear()
            self.status.setText(str(exc))
            self.save_button.setEnabled(False)
            self.print_button.setEnabled(False)

    def fit_page(self):
        if self.page_image is not None:
            pixmap = QPixmap.fromImage(self.page_image).scaled(
                self.page.size() - QSize(24, 24), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.page.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_page()

    def save_pdf(self):
        if not self.data or self.analysis["status"]=="running":
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Salvar uma folha A4", "ecg.kardiaos.pdf", "PDF (*.pdf)")
        if filename:
            try:
                Path(filename).write_bytes(self.data)
            except Exception as exc:
                QMessageBox.warning(self, "Falha ao salvar PDF", str(exc))

    def print_current(self):
        if not self.data or self.analysis["status"]=="running":
            return
        self.print_button.setEnabled(False)
        try:
            info = QPrinterInfo.printerInfo(self.printers.currentText())
            if info.isNull():
                raise RuntimeError("A impressora selecionada não está disponível.")
            printer = QPrinter(info, QPrinter.PrinterMode.HighResolution)
            configure_printer(printer)
            print_page(self.data, printer)
            self.status.setText("Uma página enviada para " + info.printerName() + ".")
        except Exception as exc:
            QMessageBox.warning(self, "Falha na impressão", str(exc))
        finally:
            self.print_button.setEnabled(self.printers.count() > 0 and self.analysis is not None and self.analysis["status"]!="running")
