"""Visible, opaque single-page preview, shared by PDF export and printing."""
from pathlib import Path
import math
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize, QRectF
from PySide6.QtGui import QImage, QPainter, QPixmap, QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDoubleSpinBox, QFileDialog, QMessageBox, QSizePolicy, QComboBox)
from .report import pdf_bytes


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
    def __init__(self, recording, speed=25, gain=10, raw=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KardiaOS — Prévia de impressão")
        self.resize(1120, 850)
        self.setMinimumSize(800, 600)
        self.recording, self.speed, self.gain, self.raw = recording, speed, gain, raw
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
        top.addStretch()
        top.addWidget(QLabel(f"1 folha · A4 paisagem · {speed:g} mm/s · {gain:g} mm/mV"))
        layout.addLayout(top)
        layout.addWidget(QLabel(f"Faixa contínua: até {250 / speed:g} s. O arquivo bruto mantém toda a gravação."))
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
        save = QPushButton("Salvar PDF")
        save.clicked.connect(self.save_pdf)
        self.print_button = QPushButton("Imprimir 1 folha")
        self.print_button.setEnabled(self.printers.count() > 0)
        self.print_button.setObjectName("primary")
        self.print_button.clicked.connect(self.print_current)
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        for button in (save, self.print_button, close):
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.status = QLabel("" if self.printers.count() else "Nenhuma impressora instalada. Você pode salvar o PDF.")
        layout.addWidget(self.status)
        self.offset.valueChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.data = pdf_bytes(self.recording, self.speed, self.gain, self.raw, self.offset.value())
        self.page_image = render_page(self.data)
        self.fit_page()

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
        filename, _ = QFileDialog.getSaveFileName(self, "Salvar uma folha A4", "ecg.kardiaos.pdf", "PDF (*.pdf)")
        if filename:
            try:
                Path(filename).write_bytes(self.data)
            except Exception as exc:
                QMessageBox.warning(self, "Falha ao salvar PDF", str(exc))

    def print_current(self):
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
            self.print_button.setEnabled(self.printers.count() > 0)
