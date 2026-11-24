"""Compact local research results. Technical assumptions live in an explicit detail view."""
import json
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,QWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox,QComboBox,QScrollArea,QFrame)
from .automatic_analysis import automatic_analysis,analysis_key,cache_analysis,cached_analysis
from .measurement_quality import warning as quality_warning, detail as quality_detail
from .analysis_presentation import criterion_group
from .orientation import evidence_state
from .timing_plot import TimingPlot
from .evidence_view import EvidencePanel
from html import escape
from .processing import profile_label,profile_info,snapshot
from .landmark_review import origin_label, save_review, set_review_active


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
        self.review_changed = False
        self.setObjectName('analysisDetails')
        self.setWindowTitle('KardiaOS — detalhes da análise');self.resize(1120,760);self.setMinimumSize(850,650)
        box=QVBoxLayout(self);box.setContentsMargins(18,16,18,14);box.setSpacing(8)
        heading=QHBoxLayout();heading.setSpacing(18)
        title=label('Detalhes da análise');title.setStyleSheet('font-size:18px;font-weight:600');heading.addWidget(title)
        self.evidence_label=label(profile_label(recording));self.evidence_label.setObjectName('muted');self.evidence_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);heading.addWidget(self.evidence_label,1);box.addLayout(heading)
        self.review_button = QPushButton('Revisar marcos…')
        self.review_button.setEnabled(False); self.review_button.clicked.connect(self.edit_landmarks)
        heading.addWidget(self.review_button)
        self.save_review_button = QPushButton('Salvar captura…')
        self.save_review_button.hide(); self.save_review_button.clicked.connect(self.save_review_file)
        heading.addWidget(self.save_review_button)
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        def page(title):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
            widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(4,12,4,8);layout.setSpacing(8)
            scroll.setWidget(widget);self.tabs.addTab(scroll,title);return layout
        nb=page('Resumo');self.network_tab=0
        self.classification_summary=label('Aguardando análise.');self.classification_summary.setStyleSheet('font-size:16px;font-weight:600');nb.addWidget(self.classification_summary)
        self.findings_label=label('');nb.addWidget(self.findings_label)
        self.pending_label=label('');nb.addWidget(self.pending_label)
        self.qtc_summary=label('');self.qtc_summary.setObjectName('muted');nb.addWidget(self.qtc_summary)
        self.morphology_label=label('');self.morphology_label.hide();nb.addWidget(self.morphology_label)
        self.possibilities_label=label('');self.possibilities_label.hide();nb.addWidget(self.possibilities_label)
        self.limitations_label=label('');self.limitations_label.setObjectName('muted');self.limitations_label.hide();nb.addWidget(self.limitations_label)
        self.quality_summary=label('');self.quality_summary.setStyleSheet('color:#855b11;');self.quality_summary.hide();nb.addWidget(self.quality_summary)
        note=label('Análise automática exploratória · amplitudes estimadas · derivações de membros, sem precordiais.');note.setObjectName('muted');nb.addWidget(note)
        self.criteria_toggle=QPushButton('Mostrar critérios técnicos');self.criteria_toggle.setCheckable(True);nb.addWidget(self.criteria_toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.technical_body=QWidget();tb=QVBoxLayout(self.technical_body);tb.setContentsMargins(0,0,0,0)
        self.rule_tables = {}
        self.rule_toggles = {}
        for key, title in (('detected', 'Detectados'), ('review', 'Possíveis ou inconclusivos'), ('not_detected', 'Não detectados')):
            toggle = QPushButton();toggle.setCheckable(True);toggle.setChecked(key != 'not_detected')
            toggle.setAccessibleName(title)
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(['Critério avaliado', 'Resultado / fundamento'])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tb.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
            tb.addWidget(table)
            self.rule_tables[key] = table
            self.rule_toggles[key] = (title, toggle)
            toggle.toggled.connect(self.update_rule_groups)
            table.cellClicked.connect(lambda row, col, table=table: self.open_table_evidence(table, row))
            table.cellActivated.connect(lambda row, col, table=table: self.open_table_evidence(table, row))
        self.update_rule_groups()
        self.criteria_table=QTableWidget(0,2);self.criteria_table.setHorizontalHeaderLabels(['Medição e qualidade','Método / limite'])
        self.criteria_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        method_toggle = QPushButton('Medição e qualidade')
        method_toggle.setCheckable(True)
        tb.addWidget(method_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        tb.addWidget(self.criteria_table)
        self.criteria_table.hide()
        method_toggle.toggled.connect(self.criteria_table.setVisible)
        nb.addWidget(self.technical_body);self.technical_body.hide();nb.addStretch()
        self.criteria_toggle.toggled.connect(self.toggle_criteria)
        mb=page('Medidas');self.measure_note=label('Medianas da gravação completa; intervalos globais.');mb.addWidget(self.measure_note)
        self.measure_table=QTableWidget(0,3);self.measure_table.setHorizontalHeaderLabels(['Medição','Valor','Método / indisponibilidade'])
        self.measure_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        for col in (0,1):self.measure_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        mb.addWidget(self.measure_table);mb.addWidget(label('Amplitude por derivação · mV estimados'))
        self.feature_table=QTableWidget(0,7);self.feature_table.setHorizontalHeaderLabels(['Derivação','P (mV)','Q (mV)','Q (ms)','T (mV)','J (mV)','ST+60 (mV)'])
        self.feature_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);mb.addWidget(self.feature_table)
        mb.addWidget(label('QTcF por Fridericia, calculado com o QT e o RR mediano elegíveis.'));mb.addStretch()
        limits=QWidget();outer=QVBoxLayout(limits);outer.setContentsMargins(0,0,0,0)
        self.curve_overview=QWidget();outer.addWidget(self.curve_overview);lb=QVBoxLayout(self.curve_overview);lb.setContentsMargins(4,12,4,8);lb.setSpacing(8)
        selection=QHBoxLayout();selection.setSpacing(8);caption=label('Derivação');selection.addWidget(caption)
        self.lead_selector=QComboBox();self.lead_selector.setAccessibleName('Derivação');self.lead_selector.setFixedWidth(108);self.lead_selector.setEnabled(False);caption.setBuddy(self.lead_selector);selection.addWidget(self.lead_selector)
        hint=label('Medianas alinhadas · limites globais compartilhados');hint.setObjectName('muted');selection.addSpacing(8);selection.addWidget(hint,1);lb.addLayout(selection)
        self.measurements_by_lead=[];self.lead_selector.currentIndexChanged.connect(self.show_measurement)
        self.beat_selector=QComboBox();self.beat_selector.setAccessibleName('Batimento');self.beat_selector.setEnabled(False);self.beat_selector.hide();lb.addWidget(self.beat_selector)
        self.timing_plot=TimingPlot(recording);lb.addWidget(self.timing_plot,1)
        self.beat_selector.currentIndexChanged.connect(self.timing_plot.set_beat);self.tabs.addTab(limits,'Curvas e marcos')
        display_config = getattr(getattr(parent, 'paper', None), 'display_config', None)
        self.evidence_panel=EvidencePanel(recording, display_config=display_config);outer.addWidget(self.evidence_panel);self.evidence_panel.hide()
        self.evidence_panel.overview.connect(self.show_all_curves)
        for widget in (self.findings_label,self.morphology_label,self.possibilities_label):
            widget.setTextFormat(Qt.TextFormat.RichText);widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction);widget.setOpenExternalLinks(False)
            widget.linkActivated.connect(self.open_evidence)
        for table in (self.measure_table, *self.rule_tables.values(), self.criteria_table, self.feature_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.verticalHeader().hide();table.setWordWrap(True)
            table.setAlternatingRowColors(True);table.setShowGrid(False);table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setFrameShape(QFrame.Shape.NoFrame)
            table.setStyleSheet('QTableWidget {background:white;alternate-background-color:#f1f6f3;selection-background-color:#dcece3;selection-color:#174d3f;} QTableWidget::item {padding:4px;border-bottom:1px solid #e1e9e4;} QHeaderView::section {background:#e7efea;color:#345848;font-weight:600;padding:5px;border:0;text-align:left;}')
        self.status=label('Pronto.');self.status.setObjectName('muted');box.addWidget(self.status)
        row=QHBoxLayout();details=QPushButton('Proveniência');details.clicked.connect(self.details);row.addWidget(details)
        self.reference_button=QPushButton('Referência');self.reference_button.clicked.connect(self.reference);row.addWidget(self.reference_button)
        self.neural_button=QPushButton('Análise neural…');self.neural_button.clicked.connect(self.neural_analysis);row.addWidget(self.neural_button)
        row.addStretch();self.run_button=QPushButton('Reavaliar');self.cancel_button=QPushButton('Interromper');self.export_button=QPushButton('Exportar JSON');close=QPushButton('Fechar')
        row.setSpacing(6);self.run_button.setObjectName('primary');self.cancel_button.setObjectName('interrupt')
        for button in (self.run_button,self.cancel_button,self.export_button,close):row.addWidget(button)
        box.addLayout(row);self.cancel_button.setVisible(False);self.export_button.setEnabled(False)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.run_button.clicked.connect(lambda:self.start(force=True));self.cancel_button.clicked.connect(self.cancel);self.export_button.clicked.connect(self.export);close.clicked.connect(self.reject)
        self.tabs.currentChanged.connect(lambda _:QTimer.singleShot(0,self.fit_tables))
        if autostart:QTimer.singleShot(0,self.start)

    def open_evidence(self,key):
        if not self.result or self.busy():return
        self.curve_overview.hide();self.evidence_panel.show();self.evidence_panel.open(key);self.tabs.setCurrentIndex(2)

    def show_all_curves(self):
        self.evidence_panel.hide();self.curve_overview.show()

    def open_table_evidence(self,table,row):
        item=table.item(row,0)
        if item and item.data(Qt.ItemDataRole.UserRole):self.open_evidence(item.data(Qt.ItemDataRole.UserRole))

    def update_rule_groups(self):
        for key, table in self.rule_tables.items():
            title, toggle = self.rule_toggles[key]
            count = table.rowCount()
            toggle.setText(f'{title} ({count}) · ' + ('Recolher' if toggle.isChecked() and count else 'Expandir' if count else 'Sem critérios'))
            toggle.setEnabled(bool(count))
            table.setVisible(toggle.isChecked() and count > 0)
        QTimer.singleShot(0, self.fit_tables)

    def toggle_criteria(self,shown):
        self.technical_body.setVisible(shown);self.criteria_toggle.setText('Ocultar critérios técnicos' if shown else 'Mostrar critérios técnicos')
        self.fit_tables()

    def fit_tables(self):
        for table in (self.measure_table, *self.rule_tables.values(), self.criteria_table, self.feature_table):
            table.resizeRowsToContents()
            table.setFixedHeight(table.horizontalHeader().height()+sum(table.rowHeight(i) for i in range(table.rowCount()))+4)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'feature_table'):QTimer.singleShot(0,self.fit_tables)

    def busy(self):return self.thread is not None and self.thread.isRunning()
    def save_review_file(self):
        parent = self.parent()
        if parent is not None and parent.save():
            self.review_changed = False
            self.status.setText('Captura e revisão dos marcos salvas no arquivo .kardia.')

    def edit_landmarks(self):
        if self.busy() or not self.result or not self.recording:
            return
        from .landmark_editor import LandmarkEditor
        result = self.result
        editor = LandmarkEditor(result, self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        if result.get('source_key') != analysis_key(self.recording):
            QMessageBox.warning(self, 'Revisão dos marcos', 'A captura mudou. Confira a mediana atualizada.')
            self.start(force=True)
            return
        state = result['measurements']['landmark_review']
        if editor.automatic_requested:
            set_review_active(self.recording, state, False)
        else:
            save_review(self.recording, state, editor.points, editor.point_leads)
        self.review_changed = True
        parent = self.parent()
        if parent is not None and hasattr(parent, 'dirty'): parent.dirty = True
        self.start(force=True)

    def neural_analysis(self):
        if self.busy() or self.recording is None:return
        from .research_dialog import ResearchDialog
        dialog=ResearchDialog(snapshot(self.recording),self)
        if self.result and self.result.get('report_window'):dialog.offset.setValue(self.result['report_window']['offset_seconds'])
        dialog.exec()
    def start(self,force=False):
        if self.busy() or self.closing:return
        self.review_button.setEnabled(False)
        self.save_review_button.hide()
        self.show_all_curves();self.evidence_panel.set_result({})
        self.result=None;self.clear_rule_tables();self.measure_table.setRowCount(0)
        self.classification_summary.setText('Atualizando a análise…');self.findings_label.clear();self.pending_label.clear();self.feature_table.setRowCount(0)
        self.quality_summary.clear();self.quality_summary.hide();self.qtc_summary.clear()
        for widget in (self.morphology_label,self.possibilities_label,self.limitations_label):widget.clear();widget.hide()
        self.measurements_by_lead=[];self.lead_selector.clear();self.criteria_table.setRowCount(0);self.beat_selector.clear();self.timing_plot.set_measurement(None)
        self.lead_selector.setEnabled(False);self.beat_selector.setEnabled(False)
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
            self.lead_selector.blockSignals(False);self.lead_selector.setEnabled(bool(self.measurements_by_lead));self.show_measurement(0)
        # Network outputs are published once, after exact-window validation and merging.
    def show_measurement(self,index):
        if not 0<=index<len(self.measurements_by_lead):return
        v=self.measurements_by_lead[index]
        self.measure_note.setText(f"D{v['lead']} · {v.get('offset_seconds',0):g}–{v.get('offset_seconds',0)+v.get('duration_seconds',0):g} s · tempos experimentais; 300 Hz nominais")
        if v.get('global_intervals'):
            self.measure_note.setText(f"Gravação completa · {v.get('duration_seconds',0):.1f} s · intervalos globais · {origin_label(v)}")
        metrics=list(v['metrics'].values());self.measure_table.setRowCount(len(metrics))
        for row,m in enumerate(metrics):
            method=m.get('reason') or m.get('formula') or m.get('method') or f"Mediana de {m.get('accepted_beats',0)}/{m.get('candidate_beats',0)} batimentos delimitados."
            if quality_detail(m):method+=' · '+quality_detail(m)
            values=[m['name'],(f"{m['value']:g} {m['unit']}"+(' · revisar' if quality_warning(m) else '')) if m['value'] is not None else 'Indisponível',method]
            for col,text in enumerate(values):
                item=QTableWidgetItem(text);item.setToolTip(text);self.measure_table.setItem(row,col,item)
        self.measure_table.resizeRowsToContents();self.timing_plot.set_measurement(v)
        self.beat_selector.blockSignals(True);self.beat_selector.clear()
        self.beat_selector.addItems([f"Batimento {i+1} · amostra {p['r']}" for i,p in enumerate(v.get('fiducials',[]))])
        self.beat_selector.blockSignals(False)
        self.beat_selector.setEnabled(self.beat_selector.count()>0)
        self.beat_selector.setVisible(not v.get('global_intervals'))
        items=v.get('descriptions',[]);self.criteria_table.setRowCount(len(items))
        for row,item in enumerate(items):
            for col,text in enumerate([item['text'],item.get('reason') or item.get('criterion','')]):
                cell=QTableWidgetItem(text);cell.setToolTip(text);self.criteria_table.setItem(row,col,cell)
        self.criteria_table.resizeRowsToContents()
    def clear_rule_tables(self):
        for table in self.rule_tables.values():
            table.setRowCount(0)
        self.update_rule_groups()

    def add_row(self,group,values,key=None):
        table = self.rule_tables[group]
        row=table.rowCount();table.insertRow(row)
        for col,text in enumerate(values):
            item=QTableWidgetItem(text);item.setToolTip(text);table.setItem(row,col,item)
        if key:
            table.item(row,0).setData(Qt.ItemDataRole.UserRole,key)
            table.item(row,0).setToolTip('Abrir evidência nas curvas')
        table.resizeRowToContents(row)
    def on_result(self,result):
        if result.get('source_key') and result['source_key']!=analysis_key(self.recording):return
        self.result=result;self.evidence_panel.set_result(result);self.show_all_curves();self.export_button.setEnabled(True)
        self.qtc_summary.setText(result.get('qtc_label','QTc: erro na estimativa'))
        from .measurement_quality import alerts
        messages=alerts(result.get('measurements',{}))
        self.quality_summary.setText('Revisar medidas\n'+'\n'.join(messages) if messages else '');self.quality_summary.setVisible(bool(messages))
        self.clear_rule_tables()
        classification=result.get('classification',{})
        self.classification_summary.setText(classification.get('summary',result.get('reason') or 'Análise automática inconclusiva'))
        findings=classification.get('findings',[])
        self.findings_label.setText('Achados\n'+'\n'.join('• '+v['label'] for v in findings) if findings else 'Nenhuma alteração detectada nos critérios avaliados.' if classification.get('status')=='no_findings' else 'Consulte as pendências antes de interpretar o resultado.')
        from .analysis_presentation import pending_messages
        reasons=pending_messages(classification)
        self.pending_label.setText('Pendências\n'+'\n'.join('• '+v for v in reasons) if reasons else '')
        self.pending_label.setVisible(bool(reasons))
        from .analysis_presentation import descriptive_messages
        morphology,possibilities,limitations=descriptive_messages(classification)
        for widget,title,items in [(self.morphology_label,'Descrições morfológicas · sem efeito isolado na conclusão',morphology),
                (self.possibilities_label,'Possibilidades entre subconjuntos · somente nos detalhes',possibilities),
                (self.limitations_label,'Limitações das comparações exploratórias',limitations)]:
            widget.setText(title+'\n'+'\n'.join('• '+v for v in items) if items else '');widget.setVisible(bool(items))
        sinus_label = classification.get('sinus_label', 'Ritmo de base sinusal')
        if classification.get('sinus_supported'):
            self.add_row('detected', [sinus_label, 'Polaridade de P e associação P–QRS nos batimentos predominantes.'], 'sinus')
        elif classification.get('sinus_supported') is not None:
            self.add_row('review', ['Origem do ritmo de base', '. '.join(classification.get('sinus_reasons', []))], 'sinus')
        quality = result.get('measurements', {}).get('technical_quality', {})
        if quality.get('p_onset_reviews'):
            self.add_row('review', ['Instabilidade no início de P', quality['boundaries']['pon']['reason']], 'p_onset_review')
        for item in classification.get('rules',[]):
            prefix='Indeterminado: ' if item.get('technical_status')=='indeterminate' else {'detected':'','not_detected':'Não detectado: ','unavailable':'Indisponível: '}[item['status']]
            if item.get('presentation')=='description' and item['status']=='detected':prefix='Descrição: '
            if item.get('possible') and item['status']!='detected':prefix='Possível nos subconjuntos: '
            elif item.get('possible_morphology_leads') and item['status']!='detected':prefix='Possível: '
            detail=item['reason'] or item['criterion']
            if item['id'] == 'irregular' and classification.get('rr_cv') is not None:
                detail = f"CV dos RR originais: {classification['rr_cv']*100:.1f}%. " + detail
            if item.get('interpretation'):detail=item['interpretation']+' '+detail
            if item.get('leads'):detail+=' Derivações: '+', '.join(item['leads'])+'.'
            if item.get('amplitude_estimated'):detail+=' Amplitude estimada.'
            if item.get('possible'):detail+=' '+item['possible']['reason']+' Subconjuntos: '+', '.join(item['possible']['subsets'])+'.'
            if item.get('possible_morphology_leads'):detail+=' Componentes discretos em '+', '.join(item['possible_morphology_leads'])+'.'
            if item['status'] == 'detected' and item.get('limitations'):
                detail+=' '+' '.join(item['limitations'])
            if item.get('possible_context'):
                if item['id'] == 'pr_short':
                    prefix = ''
                    detail = item['possible_context']
                else:
                    prefix = 'Possível: '
                    detail += ' ' + item['possible_context']
            self.add_row(criterion_group(item),[prefix+item['label'],detail],item['id'])
        self.update_rule_groups()
        def link(key,value):return '<a style="color:#176b55" href="'+escape(key,quote=True)+'">'+escape(value)+'</a>'
        links=[link(v['id'],v['label'] + (' · '+v['interpretation'] if v.get('interpretation') else '')) for v in findings]
        if classification.get('sinus_supported') is not None:links.append(link('sinus',(sinus_label if classification['sinus_supported'] else 'Verificar origem do ritmo')+' · ver evidências'))
        if classification.get('regular'):links.append(link('irregular','Ritmo regular · ver evidências'))
        if links:self.findings_label.setText('<br>'.join(links))
        descriptions=[];possible_links=[]
        for item in classification.get('rules',[]):
            if item.get('presentation')=='description' and (item['status']=='detected' or item.get('possible_morphology_leads') or item.get('possible')):
                prefix='Possível ' if item['status']!='detected' else ''
                names=list(dict.fromkeys(item.get('leads',[])+item.get('possible_morphology_leads',[])+item.get('possible',{}).get('leads',[])))
                descriptions.append(link(item['id'],prefix+item['label']+' — '+', '.join(names)))
            elif item.get('possible') or item.get('possible_context'):
                possible_links.append(link(item['id'],item.get('possible_context') or 'Possível '+item['label']+' · '+', '.join(item.get('possible',{}).get('subsets',[]))))
        for widget,title,values in [(self.morphology_label,'Descrições morfológicas · sem efeito isolado na conclusão',descriptions),
                (self.possibilities_label,'Possibilidades · somente nos detalhes',possible_links)]:
            widget.setText(escape(title)+'<br>'+'<br>'.join(values) if values else '');widget.setVisible(bool(values))
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
        state = result.get('measurements', {}).get('landmark_review', {})
        self.review_button.setEnabled(bool(state and result.get('representative')))
        self.save_review_button.setVisible(bool(state.get('saved') and callable(getattr(self.parent(), 'save', None))))
        status = state.get('notice') or origin_label(result.get('measurements', {}))
        if self.review_changed: status += ' · Salve a captura para gravar a revisão no arquivo .kardia.'
        self.status.setText({'completed':status,'cancelled':'Análise interrompida; resultados parciais.'}.get(result['status'],result.get('reason','Falha local.')))
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
