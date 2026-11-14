"""Automatic-window, opaque one-page preview. No time or scale fitting."""
from pathlib import Path
from PySide6.QtCore import Qt,QByteArray,QBuffer,QIODevice,QSize,QRectF
from PySide6.QtGui import QImage,QPainter,QPixmap,QPageLayout,QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter,QPrinterInfo
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox,QSizePolicy,QComboBox
from .report import pdf_bytes,page_plan,DEFAULT_IMAGEABLE
from .review_window import recording_scope
from .automatic_analysis import analysis_key,cache_analysis,cached_analysis


def render_page(data,size=QSize(1404,992)):
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly);document=QPdfDocument()
    try:
        document.load(buffer)
        if document.status()!=QPdfDocument.Status.Ready or document.pageCount()!=1:raise RuntimeError('PDF sem uma página pronta.')
        rendered=document.render(0,size)
        if rendered.isNull():raise RuntimeError('Não foi possível renderizar o ECG.')
        result=QImage(size,QImage.Format.Format_RGB32);result.fill(Qt.GlobalColor.white)
        painter=QPainter(result);painter.drawImage(0,0,rendered);painter.end();return result
    finally:document.close();buffer.close()


def configure_printer(printer):
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4));printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setFullPage(True);printer.setCopyCount(1);printer.setFromTo(1,1);printer.setDuplex(QPrinter.DuplexMode.DuplexNone)


def printer_imageable(printer):
    layout=printer.pageLayout();layout.setUnits(QPageLayout.Unit.Millimeter);m=layout.minimumMargins()
    # Qt may report zero for a virtual printer. A deliberate 3mm document margin remains.
    left,right,top,bottom=[max(3.,float(v)) for v in (m.left(),m.right(),m.top(),m.bottom())]
    return left,bottom,297-left-right,210-top-bottom


def print_page(data,printer,bounds=None):
    layout=printer.pageLayout()
    if layout.pageSize().id()!=QPageSize.PageSizeId.A4 or layout.orientation()!=QPageLayout.Orientation.Landscape:
        raise ValueError('Escolha A4 paisagem para preservar os milímetros da grade.')
    if bounds:
        x,y,w,h=printer_imageable(printer);l,b,r,t=bounds
        if l<x-.01 or b<y-.01 or r>x+w+.01 or t>y+h+.01:raise ValueError('As margens físicas mudaram. Gere novamente a prévia.')
    rendered=render_page(data,QSize(3508,2480));printer.setFullPage(True);painter=QPainter(printer)
    if not painter.isActive():raise RuntimeError('A impressora não iniciou a página.')
    try:
        target=QRectF(0,0,297/25.4*printer.resolution(),210/25.4*printer.resolution())
        painter.fillRect(target,Qt.GlobalColor.white);painter.drawImage(target,rendered)
    finally:
        if not painter.end():raise RuntimeError('A impressora não confirmou o envio.')


class PrintPreview(QDialog):
    def __init__(self,recording,speed=25,gain=10,raw=False,parent=None,autostart=True,analysis=None):
        super().__init__(parent);self.setWindowTitle('KardiaOS — Prévia de impressão');self.resize(1120,850);self.setMinimumSize(800,600)
        self.recording,self.speed,self.gain,self.raw=recording,speed,gain,raw
        self.analysis=analysis or cached_analysis(recording) or dict(status='running')
        self.thread=None;self.closing=False;self.autostart=autostart;self._desired_key=analysis_key(recording)
        self.data=b'';self.page_image=None;self.plan=None
        box=QVBoxLayout(self);box.setContentsMargins(20,16,20,16)
        box.addWidget(QLabel(f'Janela automática de 10 s · 1 folha · A4 paisagem · {speed:g} mm/s · {gain:g} mm/mV'))
        self.span_note=QLabel('A gravação completa permanece disponível na tela.');self.span_note.setWordWrap(True);box.addWidget(self.span_note)
        row=QHBoxLayout();row.addWidget(QLabel('Impressora'));self.printers=QComboBox();self.printers.addItems(QPrinterInfo.availablePrinterNames())
        default=QPrinterInfo.defaultPrinterName()
        if self.printers.findText(default)>=0:self.printers.setCurrentText(default)
        row.addWidget(self.printers,1);row.addWidget(QLabel('1 página · 1 cópia'));box.addLayout(row)
        self.page=QLabel();self.page.setMinimumSize(400,280);self.page.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        self.page.setAlignment(Qt.AlignmentFlag.AlignCenter);self.page.setStyleSheet('background:#dce3df;border:1px solid #c7d3cc;');box.addWidget(self.page,1)
        bottom=QHBoxLayout();bottom.addWidget(QLabel('Tamanho real (100%), sem ajustar à página.'));bottom.addStretch()
        self.save_button=QPushButton('Salvar PDF');self.save_button.clicked.connect(self.save_pdf)
        self.print_button=QPushButton('Imprimir 1 folha');self.print_button.setObjectName('primary');self.print_button.clicked.connect(self.print_current)
        close=QPushButton('Fechar');close.clicked.connect(self.reject)
        for button in (self.save_button,self.print_button,close):bottom.addWidget(button)
        box.addLayout(bottom);self.status=QLabel();self.status.setWordWrap(True);box.addWidget(self.status)
        self.printers.currentIndexChanged.connect(self.refresh);self.request_analysis()

    def request_analysis(self,*_):
        if self.closing:return
        try:recording_scope(self.recording)
        except ValueError as exc:self.analysis=dict(status='unavailable',reason=str(exc));self.refresh();return
        self.refresh()
        if self.analysis.get('status')=='completed' or not self.autostart or self.thread and self.thread.isRunning():return
        from .analysis_dialog import AutomaticThread
        self.thread=AutomaticThread(self.recording,self);self.thread.result_ready.connect(self.analysis_done);self.thread.finished.connect(self.worker_finished);self.thread.start()

    def analysis_done(self,result):
        if self._desired_key!=analysis_key(self.recording):
            self.analysis=dict(status='unavailable',reason='O registro mudou durante a análise. Feche e reabra a prévia.')
        else:self.analysis=result;cache_analysis(self.recording,result)
        if not self.closing:self.refresh()

    def worker_finished(self):
        if self.closing:super().reject()

    def reject(self):
        self.closing=True
        if self.thread is not None and self.thread.isRunning():self.thread.requestInterruption();return
        super().reject()

    def closeEvent(self,event):
        self.closing=True
        if self.thread is not None and self.thread.isRunning():self.thread.requestInterruption();event.ignore()
        else:super().closeEvent(event)

    def imageable(self):
        info=QPrinterInfo.printerInfo(self.printers.currentText())
        if info.isNull():return DEFAULT_IMAGEABLE
        printer=QPrinter(info,QPrinter.PrinterMode.HighResolution);configure_printer(printer);return printer_imageable(printer)

    def refresh(self,*_):
        self.data=b'';self.page_image=None;self.plan=None;self.page.clear();self.save_button.setEnabled(False);self.print_button.setEnabled(False)
        state=self.analysis.get('status')
        if state!='completed':
            self.status.setText(self.analysis.get('reason') or ('Calculando análise local; fechar interrompe o processo.' if state=='running' else 'Análise interrompida.'))
            return
        try:
            region=self.imageable();self.plan=page_plan(self.recording,self.speed,self.gain,self.raw,analysis=self.analysis,imageable=region)
            self.data=pdf_bytes(self.recording,self.speed,self.gain,self.raw,analysis=self.analysis,imageable=region);self.page_image=render_page(self.data)
            p=self.plan;self.span_note.setText(f'{len(p["rows"])} faixas · {p["start"]-p["begin"]:.3f}–{p["end"]-p["begin"]:.3f} s · sem compressão de tempo ou amplitude.')
            self.save_button.setEnabled(True);self.print_button.setEnabled(self.printers.count()>0)
            self.status.setText('Somente traçado: a janela não sustentou análise.' if not p['inferred'] else '');self.fit_page()
        except (ValueError,RuntimeError) as exc:self.status.setText(str(exc));self.data=b''

    def fit_page(self):
        if self.page_image is not None:
            self.page.setPixmap(QPixmap.fromImage(self.page_image).scaled(self.page.size()-QSize(24,24),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):super().resizeEvent(event);self.fit_page()

    def ready(self):return bool(self.data and self.analysis.get('status')=='completed' and self._desired_key==analysis_key(self.recording))

    def save_pdf(self):
        if not self.ready():return
        filename,_=QFileDialog.getSaveFileName(self,'Salvar uma folha A4','ecg.kardiaos.pdf','PDF (*.pdf)')
        if filename:
            try:Path(filename).write_bytes(self.data)
            except OSError as exc:QMessageBox.warning(self,'Falha ao salvar PDF',str(exc))

    def print_current(self):
        if not self.ready():return
        self.print_button.setEnabled(False)
        try:
            info=QPrinterInfo.printerInfo(self.printers.currentText())
            if info.isNull():raise RuntimeError('A impressora selecionada não está disponível.')
            printer=QPrinter(info,QPrinter.PrinterMode.HighResolution);configure_printer(printer)
            print_page(self.data,printer,self.plan['content_bounds']);self.status.setText('Uma página enviada para '+info.printerName()+'.')
        except Exception as exc:QMessageBox.warning(self,'Falha na impressão',str(exc))
        finally:self.print_button.setEnabled(self.printers.count()>0 and self.ready())
