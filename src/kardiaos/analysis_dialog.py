"""Compact local research results. Technical assumptions live in an explicit detail view."""
import json
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox,QComboBox,QScrollArea,QFrame)
from .automatic_analysis import automatic_analysis,analysis_key,cache_analysis,cached_analysis
from .orientation import evidence_state
from .timing_plot import TimingPlot
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
        self.setWindowTitle('KardiaOS — detalhes da análise');self.resize(1120,760);self.setMinimumSize(850,650)
        box=QVBoxLayout(self);box.setContentsMargins(20,18,20,16);box.setSpacing(10)
        title=label('Detalhes da análise');title.setStyleSheet('font-size:18px;font-weight:600');box.addWidget(title)
        self.evidence_label=label(profile_label(recording));self.evidence_label.setObjectName('muted');box.addWidget(self.evidence_label)
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        def page(title):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
            widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(10,12,10,10);layout.setSpacing(10)
            scroll.setWidget(widget);self.tabs.addTab(scroll,title);return layout
        nb=page('Resumo');self.network_tab=0
        self.classification_summary=label('Aguardando análise.');self.classification_summary.setStyleSheet('font-size:17px;font-weight:600');nb.addWidget(self.classification_summary)
        self.findings_label=label('');nb.addWidget(self.findings_label)
        self.pending_label=label('');nb.addWidget(self.pending_label)
        self.qtc_summary=label('');self.qtc_summary.setObjectName('muted');nb.addWidget(self.qtc_summary)
        note=label('Análise automática exploratória · amplitudes estimadas · derivações de membros, sem precordiais.');note.setObjectName('muted');nb.addWidget(note)
        self.criteria_toggle=QPushButton('Mostrar critérios técnicos');self.criteria_toggle.setCheckable(True);nb.addWidget(self.criteria_toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.technical_body=QWidget();tb=QVBoxLayout(self.technical_body);tb.setContentsMargins(0,0,0,0)
        self.score_table=QTableWidget(0,2);self.score_table.setHorizontalHeaderLabels(['Critério avaliado','Resultado / fundamento'])
        self.score_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);tb.addWidget(self.score_table)
        self.criteria_table=QTableWidget(0,2);self.criteria_table.setHorizontalHeaderLabels(['Medição e qualidade','Método / limite'])
        self.criteria_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);tb.addWidget(self.criteria_table)
        nb.addWidget(self.technical_body);self.technical_body.hide();nb.addStretch()
        self.criteria_toggle.toggled.connect(self.toggle_criteria)
        mb=page('Medidas');self.measure_note=label('Medianas da gravação completa; intervalos globais.');mb.addWidget(self.measure_note)
        self.measure_table=QTableWidget(0,3);self.measure_table.setHorizontalHeaderLabels(['Medição','Valor','Método / indisponibilidade'])
        self.measure_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col in (0,1):self.measure_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        mb.addWidget(self.measure_table);mb.addWidget(label('Amplitude por derivação · mV estimados'))
        self.feature_table=QTableWidget(0,7);self.feature_table.setHorizontalHeaderLabels(['Derivação','P (mV)','Q (mV)','Q (ms)','T (mV)','J (mV)','ST+60 (mV)'])
        self.feature_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);mb.addWidget(self.feature_table)
        mb.addWidget(label('QTcF: Fridericia, QT(ms) / RR(s)^(1/3). Valores automáticos, sem revisão clínica.'));mb.addStretch()
        limits=QWidget();lb=QVBoxLayout(limits);lb.addWidget(label('Medianas e batimentos alinhados. Limites globais compartilhados entre derivações.'))
        selection=QHBoxLayout();selection.addWidget(label('Derivação:'));self.lead_selector=QComboBox();selection.addWidget(self.lead_selector);selection.addStretch();lb.addLayout(selection)
        self.measurements_by_lead=[];self.lead_selector.currentIndexChanged.connect(self.show_measurement)
        self.beat_selector=QComboBox();lb.addWidget(self.beat_selector)
        self.timing_plot=TimingPlot(recording);lb.addWidget(self.timing_plot,1)
        self.beat_selector.currentIndexChanged.connect(self.timing_plot.set_beat);self.tabs.addTab(limits,'Curvas e marcos')
        for table in (self.measure_table,self.score_table,self.criteria_table,self.feature_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True)
            table.setStyleSheet('QTableWidget {background:white;gridline-color:#e0e7e4;} QHeaderView::section {background:#eef3f1;padding:6px;border:0;text-align:left;}')
        self.status=label('Pronto.');self.status.setObjectName('muted');box.addWidget(self.status)
        row=QHBoxLayout();details=QPushButton('Proveniência');details.clicked.connect(self.details);row.addWidget(details)
        self.reference_button=QPushButton('Referência');self.reference_button.clicked.connect(self.reference);row.addWidget(self.reference_button)
        self.neural_button=QPushButton('Análise neural…');self.neural_button.clicked.connect(self.neural_analysis);row.addWidget(self.neural_button)
        row.addStretch();self.run_button=QPushButton('Reavaliar');self.cancel_button=QPushButton('Interromper');self.export_button=QPushButton('Exportar JSON');close=QPushButton('Fechar')
        for button in (self.run_button,self.cancel_button,self.export_button,close):row.addWidget(button)
        box.addLayout(row);self.cancel_button.setVisible(False);self.export_button.setEnabled(False)
        self.run_button.clicked.connect(lambda:self.start(force=True));self.cancel_button.clicked.connect(self.cancel);self.export_button.clicked.connect(self.export);close.clicked.connect(self.reject)
        self.tabs.currentChanged.connect(lambda _:QTimer.singleShot(0,self.fit_tables))
        if autostart:QTimer.singleShot(0,self.start)

    def toggle_criteria(self,shown):
        self.technical_body.setVisible(shown);self.criteria_toggle.setText('Ocultar critérios técnicos' if shown else 'Mostrar critérios técnicos')
        self.fit_tables()

    def fit_tables(self):
        for table in (self.measure_table,self.score_table,self.criteria_table,self.feature_table):
            table.resizeRowsToContents()
            table.setFixedHeight(table.horizontalHeader().height()+sum(table.rowHeight(i) for i in range(table.rowCount()))+4)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'feature_table'):QTimer.singleShot(0,self.fit_tables)

    def busy(self):return self.thread is not None and self.thread.isRunning()
    def neural_analysis(self):
        if self.busy() or self.recording is None:return
        from .research_dialog import ResearchDialog
        dialog=ResearchDialog(snapshot(self.recording),self)
        if self.result and self.result.get('report_window'):dialog.offset.setValue(self.result['report_window']['offset_seconds'])
        dialog.exec()
    def start(self,force=False):
        if self.busy() or self.closing:return
        self.result=None;self.score_table.setRowCount(0);self.measure_table.setRowCount(0)
        self.classification_summary.setText('Atualizando a análise…');self.findings_label.clear();self.pending_label.clear();self.feature_table.setRowCount(0)
        self.measurements_by_lead=[];self.lead_selector.clear();self.criteria_table.setRowCount(0);self.beat_selector.clear();self.timing_plot.set_measurement(None)
        self.evidence_label.setText(profile_label(self.recording))
        cached=cached_analysis(self.recording) if self.recording is not None and not force else None
        if cached:
            self.update_result(dict(kind='measurements',value=cached['measurements']))
            for item in cached.get('scenarios',[]):self.update_result(dict(kind='scenario',value=item))
            for item in cached.get('unavailable',[]):self.update_result(dict(kind='unavailable',value=item))
            self.on_result(cached);return
        self.reference_button.setEnabled(False);self.run_button.setEnabled(False);self.export_button.setEnabled(False);self.cancel_button.setVisible(True);self.cancel_button.setEnabled(True)
        self.neural_button.setEnabled(False)
        self.status.setText('Calculando medições e verificando entradas.')
        self.thread=AutomaticThread(self.recording,self);self.thread.update.connect(self.update_result);self.thread.result_ready.connect(self.on_result);self.thread.finished.connect(self.on_worker_finished);self.thread.start()
    def update_result(self,event):
        if self.closing:return
        kind,v=event['kind'],event['value']
        if kind=='progress':self.status.setText('Processamento local: '+v)
        elif kind=='measurements':
            self.measurements_by_lead=[v]+v.get('additional_leads',[])
            self.lead_selector.blockSignals(True);self.lead_selector.clear()
            self.lead_selector.addItems([('D'+item['lead'] if item['lead'] in ('I','II','III') else item['lead']) for item in self.measurements_by_lead])
            self.lead_selector.blockSignals(False);self.show_measurement(0)
        # Network outputs are published once, after exact-window validation and merging.
    def show_measurement(self,index):
        if not 0<=index<len(self.measurements_by_lead):return
        v=self.measurements_by_lead[index]
        self.measure_note.setText(f"D{v['lead']} · {v.get('offset_seconds',0):g}–{v.get('offset_seconds',0)+v.get('duration_seconds',0):g} s · tempos experimentais; 300 Hz nominais")
        if v.get('global_intervals'):
            self.measure_note.setText(f"Gravação completa · {v.get('duration_seconds',0):.1f} s · intervalos globais das derivações disponíveis")
        metrics=list(v['metrics'].values());self.measure_table.setRowCount(len(metrics))
        for row,m in enumerate(metrics):
            method=m.get('reason') or m.get('formula') or m.get('method') or f"Mediana de {m.get('accepted_beats',0)}/{m.get('candidate_beats',0)} batimentos delimitados."
            values=[m['name'],(f"{m['value']:g} {m['unit']}"+(' (baixa confiança)' if m.get('status')=='exploratory_low_confidence' else '')) if m['value'] is not None else 'Indisponível',method]
            for col,text in enumerate(values):
                item=QTableWidgetItem(text);item.setToolTip(text);self.measure_table.setItem(row,col,item)
        self.measure_table.resizeRowsToContents();self.timing_plot.set_measurement(v)
        self.beat_selector.blockSignals(True);self.beat_selector.clear()
        self.beat_selector.addItems([f"Batimento {i+1} · amostra {p['r']}" for i,p in enumerate(v.get('fiducials',[]))])
        self.beat_selector.blockSignals(False)
        self.beat_selector.setVisible(not v.get('global_intervals'))
        items=v.get('descriptions',[]);self.criteria_table.setRowCount(len(items))
        for row,item in enumerate(items):
            for col,text in enumerate([item['text'],item.get('reason') or item.get('criterion','')]):
                cell=QTableWidgetItem(text);cell.setToolTip(text);self.criteria_table.setItem(row,col,cell)
        self.criteria_table.resizeRowsToContents()
    def add_row(self,values):
        row=self.score_table.rowCount();self.score_table.insertRow(row)
        for col,text in enumerate(values):
            item=QTableWidgetItem(text);item.setToolTip(text);self.score_table.setItem(row,col,item)
        self.score_table.resizeRowToContents(row)
    def on_result(self,result):
        if result.get('source_key') and result['source_key']!=analysis_key(self.recording):return
        self.result=result;self.export_button.setEnabled(True)
        self.qtc_summary.setText(result.get('qtc_label','QTc: erro na estimativa'))
        self.score_table.setRowCount(0)
        classification=result.get('classification',{})
        self.classification_summary.setText(classification.get('summary',result.get('reason') or 'Análise automática inconclusiva'))
        findings=classification.get('findings',[])
        self.findings_label.setText('Achados\n'+'\n'.join('• '+v['label'] for v in findings) if findings else 'Nenhuma alteração detectada nos critérios avaliados.' if classification.get('status')=='no_findings' else 'Consulte as pendências antes de interpretar o resultado.')
        from .analysis_presentation import pending_messages
        reasons=pending_messages(classification)
        self.pending_label.setText('Pendências\n'+'\n'.join('• '+v for v in reasons) if reasons else '')
        self.pending_label.setVisible(bool(reasons))
        if classification.get('sinus_supported'):self.add_row(['Ritmo compatível com origem sinusal','P positiva em I/II, negativa em aVR e associação P–QRS consistente nos batimentos alinhados. Estimativa automática.'])
        if classification.get('regular') is not None:self.add_row(['Ritmo regular' if classification['regular'] else 'Ritmo irregular',f"Variação dos RR originais: {classification['rr_cv']*100:.1f}%."])
        for item in sorted(classification.get('rules',[]),key=lambda v:{'detected':0,'unavailable':1,'not_detected':2}[v['status']]):
            prefix={'detected':'','not_detected':'Não detectado: ','unavailable':'Indisponível: '}[item['status']]
            detail=item['reason'] or item['criterion']
            if item.get('leads'):detail+=' Derivações: '+', '.join(item['leads'])+'.'
            if item.get('amplitude_estimated'):detail+=' Amplitude estimada.'
            self.add_row([prefix+item['label'],detail])
        features=classification.get('features',{});self.feature_table.setRowCount(len(features))
        for row,(lead,f) in enumerate(features.items()):
            values=[lead]+[f"{f[key]:.3f}" if f.get(key) is not None else '—' for key in ('p_mv','q_mv','q_ms','t_mv','j_mv','st60_mv')]
            for col,text in enumerate(values):
                item=QTableWidgetItem(text);item.setToolTip(f.get('reason','') if text=='—' else 'Amplitude estimada.' if col not in (0,3) else '')
                self.feature_table.setItem(row,col,item)
        QTimer.singleShot(0,self.fit_tables)
        self.tabs.setTabVisible(self.network_tab,True)
        if result.get('selected_lead'):
            index=next((i for i,v in enumerate(self.measurements_by_lead) if v['lead']==result['selected_lead']),0)
            self.lead_selector.setCurrentIndex(index)
        if self.recording is not None and cache_analysis(self.recording,result):
            parent=self.parent()
            if parent is not None and hasattr(parent,'background_result'):parent.background_result(self.recording,result)
        self.status.setText({'completed':f"Regras concluídas em {result.get('elapsed_seconds',0):.2f} s · redes somente sob solicitação.",'cancelled':'Análise interrompida; resultados parciais.'}.get(result['status'],result.get('reason','Falha local.')))
    def on_worker_finished(self):
        self.reference_button.setEnabled(True);self.run_button.setEnabled(True);self.cancel_button.setEnabled(False)
        self.neural_button.setEnabled(True);self.cancel_button.hide()
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
                  measurement_method=[dict(lead=m['lead'],method=m['method'],pipeline=m['pipeline']) for m in self.measurements_by_lead],
                  limitations='Perfil assumido não valida posição física, convenção elétrica ou mV. Consulte docs/measurement-validation.md e docs/research-profile.md.')
        dialog=QMessageBox(self);dialog.setWindowTitle('Pressupostos e proveniência');dialog.setText(profile_label(self.recording));info['analysis']=self.result;dialog.setDetailedText(json.dumps(info,ensure_ascii=False,indent=2));dialog.exec()
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
