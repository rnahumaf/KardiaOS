"""Automatic research workflow; distinct measurements, network hypotheses and file facts."""
import json
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QWidget,
    QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox)
from .automatic_analysis import automatic_analysis,analysis_key
from .orientation import evidence_summary


def label(text):
    w=QLabel(text);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText);return w


class AutomaticThread(QThread):
    update=Signal(dict);result_ready=Signal(dict)
    def __init__(self,recording,parent,technical_mode=False):super().__init__(parent);self.recording=recording;self.technical_mode=technical_mode
    def run(self):
        try:
            kwargs={'technical_mode':True} if self.technical_mode else {}
            result=automatic_analysis(self.recording,self.update.emit,self.isInterruptionRequested,**kwargs)
        except Exception as exc: result=dict(status='failed',reason='Falha local: '+type(exc).__name__,scenarios=[])
        self.result_ready.emit(result)


class AutomaticAnalysisDialog(QDialog):
    def __init__(self,recording,parent=None,autostart=True):
        super().__init__(parent);self.recording=recording;self.thread=None;self.result=None;self.closing=False
        self.setWindowTitle('KardiaOS — análise automática experimental');self.resize(1120,780);self.setMinimumSize(850,650)
        box=QVBoxLayout(self)
        box.addWidget(label('Medições experimentais e hipóteses das redes — processamento local'))
        box.addWidget(label('Escores nao sao probabilidades ou diagnosticos. Posicao fisica nao comprova decoder ou mV. Sem referencia pareada do decoder, morfologia fica indisponivel no fluxo normal. Q anormal nao estabelece area inativa.'))
        self.facts=label('Confirmado pelo arquivo: sem captura.' if not recording else
            f"Informação do arquivo: {recording.n} pares; {recording.meta.get('sample_rate')} Hz nominais; "
            +('sinal sintético.' if recording.meta.get('synthetic') else 'captura local. Relógio físico, mV e orientação não são confirmados por esta tela.'))
        box.addWidget(self.facts)
        self.evidence_label=label(evidence_summary(recording));box.addWidget(self.evidence_label)
        self.technical=QCheckBox("Modo tecnico: comparar multiplicadores +/- (fora da impressao)");box.addWidget(self.technical)
        box.addWidget(label("I+ preserva o bruto; I- multiplica por -1. Nao significam onda R positiva/negativa. Nenhum sinal e escolhido pelo maior score."))
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        measure=QWidget();mb=QVBoxLayout(measure)
        self.measure_note=label('Escolha automática do trecho contínuo mais longo de DI, limitado a 30 s.');mb.addWidget(self.measure_note)
        self.measure_table=QTableWidget(0,3);self.measure_table.setHorizontalHeaderLabels(['Medição experimental','Valor','Método / indisponibilidade'])
        self.measure_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.measure_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        mb.addWidget(self.measure_table)
        mb.addWidget(label('QTcF = QT(ms) / RR(s)^(1/3). Não aplicado a limites incertos, RR muito variável, QRS ≥120 ms ou RR fora de 0,6–1,5 s. P/QRS/QT usam limites relativos no template, não delineação clínica validada.'))
        self.tabs.addTab(measure,'Medições')
        networks=QWidget();nb=QVBoxLayout(networks)
        nb.addWidget(label('Cinco maiores saídas de cada cenário, sem comparar “confiança” entre modelos. Janela: primeiro trecho de 10 s que passa nas verificações técnicas; não selecionado pelo resultado. Todos os escores ficam na exportação local.'))
        self.score_table=QTableWidget(0,5);self.score_table.setHorizontalHeaderLabels(['Modelo / derivações','Janela / hipótese','Rótulo original','Score','Estado'])
        self.score_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col in (0,1,3,4):self.score_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        nb.addWidget(self.score_table);self.tabs.addTab(networks,'Hipóteses das redes')
        for table in (self.measure_table,self.score_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True)
        self.status=label('Pronto.');box.addWidget(self.status)
        row=QHBoxLayout();self.reference_button=QPushButton('Referência');self.reference_button.clicked.connect(self.reference);row.addWidget(self.reference_button);self.run_button=QPushButton('Reavaliar');self.cancel_button=QPushButton('Interromper');self.export_button=QPushButton('Exportar análise JSON');close=QPushButton('Fechar')
        self.cancel_button.setEnabled(False);self.export_button.setEnabled(False)
        for b in (self.run_button,self.cancel_button,self.export_button,close):row.addWidget(b)
        box.addLayout(row);self.run_button.clicked.connect(self.start);self.cancel_button.clicked.connect(self.cancel);self.export_button.clicked.connect(self.export);close.clicked.connect(self.reject)
        self.technical.toggled.connect(self.start)
        if autostart:QTimer.singleShot(0,self.start)
    def busy(self):return self.thread is not None and self.thread.isRunning()
    def start(self):
        if self.busy() or self.closing:return
        self.result=None;self.score_table.setRowCount(0);self.measure_table.setRowCount(0)
        if self.recording is not None:self.recording._automatic_analysis=None
        self.technical.setEnabled(False);self.evidence_label.setText(evidence_summary(self.recording))
        self.reference_button.setEnabled(False);self.run_button.setEnabled(False);self.export_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.status.setText('Calculando medições e verificando entradas…')
        self.thread=AutomaticThread(self.recording,self,self.technical.isChecked());self.thread.update.connect(self.update_result);self.thread.result_ready.connect(self.on_result);self.thread.finished.connect(self.on_worker_finished);self.thread.start()
    def update_result(self,event):
        if self.closing:return
        kind,v=event['kind'],event['value']
        if kind=='progress':self.status.setText('Avaliando em CPU: '+v)
        elif kind=='measurements':
            self.measure_note.setText(v.get('timebase','')+f" · DI · início {v.get('offset_seconds',0):.1f} s · trecho {v.get('duration_seconds',0):.1f} s. Ganho/polaridade não validados por medidas de tempo.")
            metrics=list(v['metrics'].values());self.measure_table.setRowCount(len(metrics))
            for row,m in enumerate(metrics):
                values=[m['name'],f"{m['value']:g} {m['unit']}" if m['value'] is not None else 'Indisponível',m.get('reason') or m.get('formula') or v['method']]
                for col,text in enumerate(values):self.measure_table.setItem(row,col,QTableWidgetItem(text))
            self.measure_table.resizeRowsToContents()
        elif kind=='unavailable':self.add_row([v['model'],'—','Indisponível: '+v['reason'],'—','Indisponível'])
        elif kind=='scenario':
            scores=sorted(v['scores'],key=lambda s:s['score'],reverse=True)[:5]
            if not scores:self.add_row([v['name'],v['hypothesis'],v.get('reason','Indisponível'),'—','Indisponível'])
            for s in scores:self.add_row([v['name'],f"{v['offset_seconds']:g}–{v['offset_seconds']+10:g} s · {v['hypothesis']}",s['name'],f"{s['score']:.4f}",'Sintético' if v['status']=='synthetic' else 'Não validado'])
    def add_row(self,values):
        row=self.score_table.rowCount();self.score_table.insertRow(row)
        for col,text in enumerate(values):
            item=QTableWidgetItem(text);item.setToolTip(text);self.score_table.setItem(row,col,item)
        self.score_table.resizeRowToContents(row)
    def on_result(self,result):
        self.result=result;self.export_button.setEnabled(True)
        if self.recording is not None and result['status']=='completed' and result.get('mode')=='normal':
            self.recording._automatic_analysis=result;self.recording._automatic_analysis_key=analysis_key(self.recording)
        self.status.setText({'completed':f"Concluído: {sum(bool(v.get('scores')) for v in result.get('scenarios',[]))} cenários com escores. Resultados experimentais, sem confirmação clínica.",'cancelled':'Interrompido. Resultados parciais identificados; nenhuma captura alterada.'}.get(result['status'],result.get('reason','Falha local.')))
    def on_worker_finished(self):
        self.technical.setEnabled(True)
        self.reference_button.setEnabled(True);self.run_button.setEnabled(True);self.cancel_button.setEnabled(False)
        if self.closing:super().reject()
    def cancel(self):
        if self.busy():self.thread.requestInterruption();self.status.setText('Interrompendo o processo local…')
    def reject(self):
        if self.busy():self.closing=True;self.cancel();return
        super().reject()
    def closeEvent(self,event):
        if self.busy():self.closing=True;self.cancel();event.ignore()
        else:event.accept()
    def reference(self):
        if self.busy() or self.recording is None:return
        from .evidence_dialog import EvidenceDialog
        if EvidenceDialog(self.recording,self).exec()==QDialog.DialogCode.Accepted:
            if self.parent() is not None and hasattr(self.parent(),'dirty'):self.parent().dirty=True
            self.evidence_label.setText(evidence_summary(self.recording));self.start()
    def export(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar análise local','analise.research.json','JSON (*.json)')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f:json.dump(self.result,f,ensure_ascii=False,indent=2,allow_nan=False)
            except OSError:QMessageBox.warning(self,'Exportação','Não foi possível gravar no local escolhido.')
