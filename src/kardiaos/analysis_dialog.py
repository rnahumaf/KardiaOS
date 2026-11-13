"""Compact local research results. Technical assumptions live in an explicit detail view."""
import json
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox)
from .automatic_analysis import automatic_analysis,analysis_key,cache_analysis,cached_analysis
from .orientation import evidence_state
from .processing import profile_label,profile_info,snapshot


def label(text):
    w=QLabel(text);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText);return w


class AutomaticThread(QThread):
    update=Signal(dict);result_ready=Signal(dict)
    def __init__(self,recording,parent,technical_mode=False,offset=0.,duration=None):
        super().__init__(parent);self.recording=snapshot(recording);self.technical_mode=technical_mode
        self.offset=offset;self.duration=duration
        self.request_key=analysis_key(recording,offset=offset,duration=duration) if recording is not None else None
    def run(self):
        try:
            kwargs={'technical_mode':True} if self.technical_mode else {}
            if self.offset!=0 or self.duration is not None:kwargs.update(offset=self.offset,duration=self.duration)
            result=automatic_analysis(self.recording,self.update.emit,self.isInterruptionRequested,**kwargs)
        except Exception as exc:result=dict(status='failed',reason='Falha local: '+type(exc).__name__,scenarios=[])
        self.result_ready.emit(result)


class AutomaticAnalysisDialog(QDialog):
    def __init__(self,recording,parent=None,autostart=True):
        super().__init__(parent);self.recording=recording;self.thread=None;self.result=None;self.closing=False
        self.setWindowTitle('KardiaOS — resultados de pesquisa');self.resize(1120,760);self.setMinimumSize(850,650)
        box=QVBoxLayout(self);box.setContentsMargins(20,18,20,16)
        title=label('Medições e hipóteses dos modelos');title.setStyleSheet('font-size:18px;font-weight:600');box.addWidget(title)
        self.evidence_label=label(profile_label(recording));box.addWidget(self.evidence_label)
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        measure=QWidget();mb=QVBoxLayout(measure);self.measure_note=label('DI · trecho contínuo de até 30 s.');mb.addWidget(self.measure_note)
        self.measure_table=QTableWidget(0,3);self.measure_table.setHorizontalHeaderLabels(['Medição','Valor','Método / motivo de indisponibilidade'])
        self.measure_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col in (0,1):self.measure_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        mb.addWidget(self.measure_table);mb.addWidget(label('QTcF: fórmula de Fridericia, QT(ms) / RR(s)^(1/3).'))
        self.tabs.addTab(measure,'Medições')
        networks=QWidget();nb=QVBoxLayout(networks)
        nb.addWidget(label('Cinco maiores scores por modelo. A janela usada aparece em cada linha.'))
        self.score_table=QTableWidget(0,4);self.score_table.setHorizontalHeaderLabels(['Modelo / derivações','Trecho','Rótulo original','Score'])
        self.score_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col in (0,1,3):self.score_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        nb.addWidget(self.score_table);self.tabs.addTab(networks,'Hipóteses dos modelos')
        for table in (self.measure_table,self.score_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True)
        box.addWidget(label('Pesquisa local · scores não são probabilidades nem diagnósticos.'))
        self.status=label('Pronto.');box.addWidget(self.status)
        row=QHBoxLayout();details=QPushButton('Detalhes técnicos');details.clicked.connect(self.details);row.addWidget(details)
        self.reference_button=QPushButton('Referência');self.reference_button.clicked.connect(self.reference);row.addWidget(self.reference_button)
        row.addStretch();self.run_button=QPushButton('Reavaliar');self.cancel_button=QPushButton('Interromper');self.export_button=QPushButton('Exportar JSON');close=QPushButton('Fechar')
        for b in (self.run_button,self.cancel_button,self.export_button,close):row.addWidget(b)
        box.addLayout(row);self.cancel_button.setEnabled(False);self.export_button.setEnabled(False)
        self.run_button.clicked.connect(lambda:self.start(force=True));self.cancel_button.clicked.connect(self.cancel);self.export_button.clicked.connect(self.export);close.clicked.connect(self.reject)
        if autostart:QTimer.singleShot(0,self.start)
    def busy(self):return self.thread is not None and self.thread.isRunning()
    def start(self,force=False):
        if self.busy() or self.closing:return
        self.result=None;self.score_table.setRowCount(0);self.measure_table.setRowCount(0)
        self.evidence_label.setText(profile_label(self.recording))
        cached=cached_analysis(self.recording) if self.recording is not None and not force else None
        if cached:
            self.update_result(dict(kind='measurements',value=cached['measurements']))
            for item in cached.get('scenarios',[]):self.update_result(dict(kind='scenario',value=item))
            for item in cached.get('unavailable',[]):self.update_result(dict(kind='unavailable',value=item))
            self.on_result(cached);return
        self.reference_button.setEnabled(False);self.run_button.setEnabled(False);self.export_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.status.setText('Calculando medições e verificando entradas.')
        self.thread=AutomaticThread(self.recording,self);self.thread.update.connect(self.update_result);self.thread.result_ready.connect(self.on_result);self.thread.finished.connect(self.on_worker_finished);self.thread.start()
    def update_result(self,event):
        if self.closing:return
        kind,v=event['kind'],event['value']
        if kind=='progress':self.status.setText('Processamento local: '+v)
        elif kind=='measurements':
            self.measure_note.setText(f"DI · {v.get('offset_seconds',0):g}–{v.get('offset_seconds',0)+v.get('duration_seconds',0):g} s · 300 Hz nominais")
            metrics=list(v['metrics'].values());self.measure_table.setRowCount(len(metrics))
            for row,m in enumerate(metrics):
                values=[m['name'],f"{m['value']:g} {m['unit']}" if m['value'] is not None else 'Indisponível',m.get('reason') or m.get('formula') or v['method']]
                for col,text in enumerate(values):self.measure_table.setItem(row,col,QTableWidgetItem(text))
            self.measure_table.resizeRowsToContents()
        elif kind=='unavailable':self.add_row([v['model'],'—',v['reason'],'—'])
        elif kind=='scenario':
            interval=f"{v['offset_seconds']:g}–{v['offset_seconds']+v['duration_seconds']:g} s"
            scores=sorted(v['scores'],key=lambda s:s['score'],reverse=True)[:5]
            if not scores:self.add_row([v['name'],interval,v.get('reason','Indisponível'),'—'])
            for s in scores:self.add_row([v['name'],interval,s['name'],f"{s['score']:.4f}"])
    def add_row(self,values):
        row=self.score_table.rowCount();self.score_table.insertRow(row)
        for col,text in enumerate(values):
            item=QTableWidgetItem(text);item.setToolTip(text);self.score_table.setItem(row,col,item)
        self.score_table.resizeRowToContents(row)
    def on_result(self,result):
        self.result=result;self.export_button.setEnabled(True)
        if self.recording is not None:cache_analysis(self.recording,result)
        self.status.setText({'completed':f"Concluído · {sum(bool(v.get('scores')) for v in result.get('scenarios',[]))} modelos com scores.",'cancelled':'Análise interrompida; resultados parciais.'}.get(result['status'],result.get('reason','Falha local.')))
    def on_worker_finished(self):
        self.reference_button.setEnabled(True);self.run_button.setEnabled(True);self.cancel_button.setEnabled(False)
        if self.closing:super().reject()
    def cancel(self):
        if self.busy():self.thread.requestInterruption();self.status.setText('Interrompendo o processo local.')
    def reject(self):
        if self.busy():self.closing=True;self.cancel();return
        super().reject()
    def closeEvent(self,event):
        if self.busy():self.closing=True;self.cancel();event.ignore()
        else:event.accept()
    def details(self):
        info=dict(operational_profile=profile_info(self.recording),evidence=evidence_state(self.recording),
                  measurement_method='Limites relativos no template de DI; QTcF restrito a RR estável 0,6–1,5 s e QRS <120 ms.',
                  limitations='Perfil assumido não valida posição física, convenção elétrica ou mV. Consulte docs/research-profile.md.')
        dialog=QMessageBox(self);dialog.setWindowTitle('Pressupostos e proveniência');dialog.setText(profile_label(self.recording));dialog.setDetailedText(json.dumps(info,ensure_ascii=False,indent=2));dialog.exec()
    def reference(self):
        if self.busy() or self.recording is None:return
        from .evidence_dialog import EvidenceDialog
        if EvidenceDialog(self.recording,self).exec()==QDialog.DialogCode.Accepted:
            if self.parent() is not None and hasattr(self.parent(),'dirty'):self.parent().dirty=True
            self.start(force=True)
    def export(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar análise local','analise.research.json','JSON (*.json)')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f:json.dump(self.result,f,ensure_ascii=False,indent=2,allow_nan=False)
            except OSError:QMessageBox.warning(self,'Exportação','Não foi possível gravar no local escolhido.')
