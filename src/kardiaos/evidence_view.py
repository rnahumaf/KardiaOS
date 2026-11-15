"""Visible rule evidence taken from the exact median/subset inputs; no redelineation."""
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QScrollArea,QFrame,QDoubleSpinBox)
from .rule_analysis import classify
from .analysis_presentation import criterion_group
from .paper import PAPER, MINOR, MAJOR, INK
from .review_signal import waveform_values
from .signal import FS

INTERVAL_RULES={'pr_long':('pr','pon','qon'),'pr_short':('pr','pon','qon'),
    'p_wide':('p_duration','pon','poff'),'qrs_wide':('qrs_duration','qon','qoff'),
    'qt_long':('qtc_f','qon','toff')}
RHYTHM_RULES=('irregular','brady','tachy')
POINT_NAMES=dict(pon='início P',poff='fim P',qon='início QRS',qoff='fim QRS',ton='início T',toff='fim T')
STATUS={'detected':'Presente','not_detected':'Não detectado','unavailable':'Indisponível'}


def evidence_data(recording,result,key,subset=-1):
    m=result.get('measurements',{});c=result.get('classification',{})
    row=next((r for r in c.get('rules',[]) if r['id']==key),{})
    points=m.get('global_fiducials',{});reps=result.get('representative',{});features=c.get('features',{})
    central_reps=reps;central_features=features;metrics=m.get('metrics',{});origin='Mediana completa'
    quality=m.get('technical_quality',{})
    rhythm=m.get('alignment',{}).get('rhythm',{})
    base=dict(row=row,key=key,subset=subset,classification=c,rhythm=rhythm)
    if key in RHYTHM_RULES or key == 'premature':
        rr = np.asarray(rhythm.get('rr_seconds', []))
        median = float(np.median(rr)) if len(rr) else None
        highlights = (abs(rr-median)/median > .15 if key == 'irregular' and median
                      and row.get('status') == 'detected' else np.zeros(len(rr), dtype=bool))
        return dict(base, traces=[], metrics=metrics, origin='Sequência original',
                    rr_median=median, rr_highlights=highlights)
    if subset>=0:
        replica=quality['replicates'][subset]
        points=dict(replica['analysis_points'],r=m['global_fiducials']['r'])
        reps=replica.get('curves',{});features=replica['features'];origin=quality['subsets'][subset]['name']
        metrics={k:dict(v,value=replica['values'].get(k,v['value'])) for k,v in metrics.items()}
        if m['metrics'].get('qtc_f',{}).get('value') is None:metrics['qtc_f']['value']=None
        if key != 'p_onset_review':
            variant=classify(recording,dict(m,metrics=metrics),{},feature_data=features,check_stability=False)
            row=next((r for r in variant['rules'] if r['id']==key),row)
    selected=list(dict.fromkeys(row.get('leads',[])+row.get('possible_morphology_leads',[])))
    if key=='sinus':selected=[l for l in ('I','II','aVR') if l in reps]
    reviews = {}
    if key == 'p_onset_review':
        reviews = {v['lead']: v for v in quality.get('p_onset_reviews', []) if v['source'].casefold() == origin.casefold()}
        selected = list(reviews)
        row = dict(status='unavailable', criterion='O candidato isolado foi descartado por falta de uma deflexão sustentada até a onda P.')
    if not selected:
        eligible={'p_tall':('II','III','aVF'),'q_prominent':('I','II','aVL','aVF')}
        if key in ('j_elevation','st_depression','t_inversion','t_tall'):eligible[key]=('I','II','III','aVL','aVF')
        selected=[lead for lead in eligible.get(key,reps) if lead in reps]
    traces=[]
    for lead in selected:
        if lead not in reps:continue
        f=features.get(lead,{});rep=reps[lead]
        pt=key.startswith('p_') or key.startswith('t_') or key=='sinus'
        wavekey='pt_values_mv' if pt else 'values_mv';basekey='pt_baseline_mv' if pt else 'baseline_mv'
        baseline=f.get(basekey)
        y=np.asarray(rep[wavekey],dtype=float)-(baseline if baseline is not None else 0)
        central=np.asarray(central_reps[lead][wavekey],dtype=float)-central_features.get(lead,{}).get(basekey,0)
        markers=[];bands=[];threshold=None;value='—';detail='';unit='mV'
        def mark(k,label,value=None):
            if k is not None and 0<=k<len(y):markers.append(dict(index=int(k),value=float(y[k] if value is None else value),label=label))
        def band(a,b,label):
            if a is not None and b is not None and 0<=a<=b<len(y):bands.append((int(a),int(b),label))
        def bounds(on,off,label):
            a,b=points.get(on),points.get(off);band(a,b,label);mark(a,on);mark(b,off)
        if key in INTERVAL_RULES:
            metric,on,off=INTERVAL_RULES[key];bounds(on,off,'Intervalo global')
            v=metrics.get(metric,{}).get('value');value=f'{v:g} ms' if v is not None else 'Indisponível'
            detail=metrics.get(metric,{}).get('reason','')
            detail+=(' · ' if detail else '')+{'pr_long':'Limiar >200 ms','pr_short':'Limiar <120 ms','p_wide':'Limiar ≥120 ms','qrs_wide':'Limiar ≥120 ms','qt_long':'Limiares: masculino ≥450 ms; feminino ≥460 ms'}[key]
            if key=='qt_long':detail='QTcF é QT corrigido pelo RR; faixa marcada representa QT, não QTcF. '+detail
        elif key in ('p_tall','t_tall','t_inversion'):
            on,off=('pon','poff') if key=='p_tall' else ('ton','toff');a,b=points.get(on),points.get(off)
            if a is not None and b is not None and b>=a and baseline is not None:
                peak=a+int(np.argmax(abs(y[a:b+1])));mark(peak,'P' if key=='p_tall' else 'T');band(a,b,'Onda')
                value=f'{y[peak]:.3f} mV';threshold={'p_tall':.25,'t_tall':.5,'t_inversion':-.1}[key]
        elif key in ('p_biphasic','t_biphasic','t_notched'):
            shape=f.get('morphology',{}).get(key,{});start=shape.get('start_index',0)
            for i,v in enumerate(shape.get('components',[])):mark(start+v['index'],('Vale' if key=='t_notched' and i==1 else 'Componente '+str(i+1)),v['amplitude_mv'])
            if markers:band(markers[0]['index'],markers[-1]['index'],'Componentes')
            value=' / '.join(f"{i+1}: {v['value']:.3f}" for i,v in enumerate(markers))+(' mV' if markers else '') or 'Não detectado'
            detail='Componente discreto · possível' if shape.get('status')=='possible' else 'Componentes definidos' if markers else 'Sem componentes suficientes'
            if 'depth_mv' in shape:detail+=f"; vale {shape['depth_mv']:.3f} mV"
            limits=shape.get('thresholds',{})
            if 'possible_mv' in limits:detail+=f"; limiares possível/definido {limits['possible_mv']:.3f}/{limits['defined_mv']:.3f} mV"
            if 'possible_depth_mv' in limits:detail+=f"; vale possível/definido ≥{limits['possible_depth_mv']:.3f}/{limits['defined_depth_mv']:.3f} mV; razão dos picos ≥0,15/0,30"
        elif key=='q_prominent':
            indices=f.get('q_indices',[])
            if indices:
                peak=min(indices,key=lambda i:y[i]);mark(peak,'Q');band(indices[0],indices[-1],'Q')
            value=f"Q {f.get('q_mv',0):.3f} mV / {f.get('q_ms',0):g} ms" if f.get('available') else 'Indisponível'
            detail=('QS' if f.get('qs') else 'Q inicial')+'; Q ≥30 ms e magnitude ≥0,10 mV, ou QS';threshold=-.1
        elif key in ('j_elevation','st_depression'):
            j=points.get('qoff');field='j_mv' if key=='j_elevation' else 'st60_mv';v=f.get(field)
            if j is not None and v is not None:
                center=j if key=='j_elevation' else j+18;mark(center,'J' if key=='j_elevation' else 'ST+60',v);band(center-1,center+1,'Média de 3 amostras')
                if key=='st_depression':mark(j+6,'ST+20',v-f['st_slope_mv']);band(j+5,j+7,'Referência de inclinação')
                value=f'{v:.3f} mV'
            threshold=.1 if key=='j_elevation' else -.05
            if key=='st_depression' and f.get('st_slope_mv') is not None:detail=f"ST+60 − ST+20: {f['st_slope_mv']:.3f} mV; limite ≤0,010"
        elif key=='sinus':
            bounds('pon','poff','P');bounds('qon','qoff','QRS');threshold=.02 if lead!='aVR' else -.02
            value=f"P {f.get('p_mv',0):.3f} mV" if f.get('available') else 'Indisponível'
            association = c.get('p_association')
            if association is None:
                detail=f"P consistente: {f.get('p_consistency',0):.0%} (≥90%); dispersão {f.get('p_peak_dispersion_ms',0):.1f} ms (≤20)"
            else:
                detail=f"Associação P–QRS em {association['matched']}/{association['evaluated']} batimentos predominantes"
                if association['dispersion_ms'] is not None:
                    detail += f" · variação de {association['dispersion_ms']:.1f} ms"
        elif key == 'p_onset_review' and lead in reviews:
            review = reviews[lead]
            mark(review['index'], 'candidato descartado')
            mark(points.get('pon'), 'pon')
            value = f"{review['time_ms']:g} ms"
            detail = 'Candidato descartado. O segundo marcador é o início sustentado.'
        focus=[v['index'] for v in markers]+[x for a,b,_ in bands for x in (a,b)]
        if not focus:focus=[points.get('pon',0),points.get('toff',len(y)-1)]
        lo=max(0,min(focus)-18);hi=min(len(y)-1,max(focus)+24)
        if key.startswith('p_'):hi=min(hi,points.get('qon',hi+3)-3)
        if key in ('pr_long','pr_short'):hi=min(hi,points.get('qon',hi)+3)
        hi=max(lo+1,hi)
        # Always include the PR reference window in the visible evidence.
        ref=(points.get('poff',0)+2,points.get('qon',0)-2)
        traces.append(dict(lead=lead,y=y,central=central,markers=markers,bands=bands,threshold=threshold,
            value=value,detail=detail,baseline=baseline,reference=ref,lo=lo,hi=hi,anchor=points.get('r',105)))
    return dict(base,traces=traces,row=row,origin=origin,points=points,metrics=metrics)


def text(value=''):
    w=QLabel(value);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText);return w


def capture_start(recording):
    start = recording.meta.get('start')
    return float(recording.times[0] if start is None else start)


def event_time(recording, event):
    return float(recording.times[event['sample']] - capture_start(recording))


class EvidencePanel(QWidget):
    overview=Signal()
    def __init__(self,recording,parent=None,display_config=None):
        super().__init__(parent);self.recording=recording;self.result={};self.key=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        bar=QHBoxLayout();self.back=QPushButton('Todas as curvas');self.back.clicked.connect(self.overview.emit);bar.addWidget(self.back)
        bar.addWidget(QLabel('Evidência'));self.rule_selector=QComboBox();self.rule_selector.setAccessibleName('Evidência selecionada');self.rule_selector.setMinimumContentsLength(12)
        self.rule_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);bar.addWidget(self.rule_selector,1);layout.addLayout(bar)
        self.origin_row=QWidget();ob=QHBoxLayout(self.origin_row);ob.setContentsMargins(0,0,0,0);ob.addWidget(QLabel('Curva destacada'))
        self.source_selector=QComboBox();self.source_selector.setAccessibleName('Origem da evidência');ob.addWidget(self.source_selector,1);layout.addWidget(self.origin_row)
        self.range_row=QWidget();rb=QHBoxLayout(self.range_row);rb.setContentsMargins(0,0,0,0);rb.addWidget(QLabel('Início do trecho de 10 s'))
        self.rhythm_offset=QDoubleSpinBox();self.rhythm_offset.setSuffix(' s');self.rhythm_offset.setDecimals(1);self.rhythm_offset.setSingleStep(5);rb.addWidget(self.rhythm_offset);rb.addStretch();layout.addWidget(self.range_row);self.range_row.hide()
        self.event_row = QWidget()
        event_layout = QHBoxLayout(self.event_row);event_layout.setContentsMargins(0,0,0,0)
        event_layout.addWidget(QLabel('Trecho'))
        self.event_selector = QComboBox()
        self.event_selector.setAccessibleName('Batimento prematuro exibido')
        event_layout.addWidget(self.event_selector, 1)
        layout.addWidget(self.event_row);self.event_row.hide()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);layout.addWidget(scroll,1)
        body=QWidget();self.body=QVBoxLayout(body);self.body.setContentsMargins(2,6,2,6);scroll.setWidget(body)
        self.caption=text();self.body.addWidget(self.caption)
        self.legend=text();self.legend.setObjectName('muted');self.body.addWidget(self.legend)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Derivação','Medição','Evidência / limiar'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide();self.table.setWordWrap(True);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True);self.body.addWidget(self.table)
        self.plot=EvidencePlot(recording, display_config);self.body.addWidget(self.plot);self.body.addStretch()
        self.rhythm_offset.valueChanged.connect(self.plot.set_offset);self.plot.focus_rr.connect(self.rhythm_offset.setValue)
        self.rule_selector.currentIndexChanged.connect(self.choose_rule);self.source_selector.currentIndexChanged.connect(self.refresh)
        self.event_selector.currentIndexChanged.connect(self.refresh)
    def set_result(self,result):
        self.result=result;self.key=None;self.rule_selector.blockSignals(True);self.rule_selector.clear()
        c=result.get('classification',{})
        if c.get('sinus_supported') is not None:self.rule_selector.addItem('Origem do ritmo de base','sinus')
        if result.get('measurements',{}).get('technical_quality',{}).get('p_onset_reviews'):
            self.rule_selector.addItem('Instabilidade no início de P', 'p_onset_review')
        ranks = {'detected': 0, 'review': 1, 'not_detected': 2}
        for r in sorted(c.get('rules', []), key=lambda row: ranks[criterion_group(row)]):
            group = criterion_group(r)
            prefix = 'Não detectado · ' if group == 'not_detected' else (
                'Indisponível · ' if r['status'] == 'unavailable' else 'Possível · ' if group == 'review' else '')
            self.rule_selector.addItem(prefix + r['label'], r['id'])
        self.rule_selector.blockSignals(False)
    def open(self,key):
        i=self.rule_selector.findData(key)
        if i<0:return
        self.rule_selector.blockSignals(True);self.rule_selector.setCurrentIndex(i);self.rule_selector.blockSignals(False);self.choose_rule()
    def choose_rule(self,*_):
        self.key=self.rule_selector.currentData()
        rhythm=self.key in RHYTHM_RULES;self.range_row.setVisible(rhythm)
        if self.recording is not None and self.recording.n:
            self.rhythm_offset.setMaximum(max(0, self.recording.last_time - capture_start(self.recording) - 10))
        row=next((r for r in self.result.get('classification',{}).get('rules',[]) if r['id']==self.key),{})
        quality=self.result.get('measurements',{}).get('technical_quality',{})
        self.source_selector.blockSignals(True);self.source_selector.clear();self.source_selector.addItem('Mediana completa',-1)
        names=row.get('possible',{}).get('subsets',[])
        if self.key == 'p_onset_review':
            names = {v['source'] for v in quality.get('p_onset_reviews', [])}
            if 'mediana completa' not in names:
                self.source_selector.clear()
        for i,s in enumerate(quality.get('subsets',[])):
            if s['name'] in names:self.source_selector.addItem(s['name'],i)
        self.source_selector.setCurrentIndex(1 if self.key != 'p_onset_review' and self.source_selector.count()>1 and not row.get('possible_morphology_leads') else 0)
        self.source_selector.blockSignals(False);self.origin_row.setVisible(self.source_selector.count()>1)
        events = self.result.get('measurements', {}).get('alignment', {}).get('rhythm', {}).get('premature', {}).get('events', [])
        self.event_selector.blockSignals(True)
        self.event_selector.clear()
        if self.key == 'premature' and len(events) > 2:
            self.event_selector.addItem('Primeiros dois batimentos', -1)
            for i, event in enumerate(events):
                self.event_selector.addItem(f"{event_time(self.recording, event):.2f} s", i)
        self.event_selector.blockSignals(False)
        self.event_row.setVisible(self.event_selector.count() > 1)
        self.refresh()
    def refresh(self,*_):
        if self.key is None:return
        self.data=evidence_data(self.recording,self.result,self.key,self.source_selector.currentData() if self.source_selector.currentData() is not None else -1)
        d=self.data;r=d['row'];rhythm=self.key in RHYTHM_RULES
        state=STATUS.get(r.get('status'),'Evidência de ritmo sinusal')
        if self.key=='sinus':state='Ritmo de base sinusal' if d['classification'].get('sinus_supported') else 'Origem do ritmo de base inconclusiva'
        if self.key == 'p_onset_review':
            state = 'Instabilidade técnica'
        elif d['subset']>=0:state='Possível na análise completa · '+state.lower()+' neste subconjunto'
        if r.get('possible_context'):state='Possível · depende do sexo de referência'
        if r.get('possible_morphology_leads'):state=('Possível · componentes discretos' if r.get('status')!='detected' and d['subset']<0 else state+' · componentes discretos possíveis')
        self.caption.setText(state+' · '+d['origin']+'\n'+r.get('criterion','P em I/II/aVR, associação P–QRS e qualidade dos batimentos alinhados.'))
        if r.get('reason'):self.caption.setText(self.caption.text()+'\n'+r['reason'])
        if r.get('interpretation'):self.caption.setText(self.caption.text()+'\n'+r['interpretation'])
        self.caption.setToolTip('\n'.join(r.get('limitations',[])))
        if self.key=='sinus' and d['classification'].get('sinus_reasons'):self.caption.setText(self.caption.text()+'\n'+'; '.join(d['classification']['sinus_reasons']))
        self.legend.setText('Traçado DI e RR da gravação completa. Clique em um RR para localizar seu trecho. Âmbar: RR fora da faixa de regularidade.' if rhythm else
            ('Verde: mediana completa · âmbar tracejado: subconjunto · círculos e faixas: evidência selecionada.' if d['subset']>=0 else 'Verde: mediana completa · círculos e faixas âmbar: evidência selecionada.')+' Escalas comuns; amplitudes relativas à base PR, quando disponível. Linha tracejada: limiar.')
        values=[]
        self.table.setHorizontalHeaderLabels(['Derivação','Medição','Evidência / limiar'])
        if rhythm:
            self.table.setHorizontalHeaderLabels(['Medida', 'Valor', 'Critério'])
            rr=np.asarray(d['rhythm'].get('rr_seconds',[]));c=d['classification'];hr=d['metrics'].get('heart_rate',{}).get('value')
            if self.key in ('brady', 'tachy'):
                self.legend.setText('A regra compara a FC calculada pelo RR mediano com o limiar. Os RR individuais aparecem como contexto.')
            values=[['FC da gravação',f'{hr:g} bpm' if hr is not None else 'Indisponível',r.get('criterion','')],
                ['RR mediano',f'{np.median(rr)*1000:.1f} ms' if len(rr) else 'Indisponível',f"CV: {c['rr_cv']*100:.1f}%" if c.get('rr_cv') is not None else 'RR insuficientes']]
        elif self.key == 'premature':
            events = d['rhythm'].get('premature', {}).get('events', [])
            index = self.event_selector.currentData()
            d['selected_events'] = events[index:index+1] if index is not None and index >= 0 else events[:2]
            self.table.setHorizontalHeaderLabels(['Trecho', 'QRS do grupo', 'Evidência'])
            self.legend.setText('40 ms por divisão horizontal, amplitude estimada em mV. Faixas: limites da mediana dos prematuros. Traçados com os filtros da prévia.')
            for event in d['selected_events']:
                width = event.get('qrs_ms')
                detail = f"RR antes {event['coupling_ms']:g} ms · referência {event['reference_rr_ms']:g} ms"
                if event['following_rr_ms'] is not None:
                    detail += f" · RR depois {event['following_rr_ms']:g} ms"
                if width is not None:
                    on, off = (event[k]*1000/FS for k in ('on','off'))
                    detail += f" · {on:+.1f} a {off:+.1f} ms na mediana de {event['group_size']} complexos"
                elif event.get('reason'):
                    detail += '. ' + event['reason']
                values.append([f'{event_time(self.recording, event):.2f} s',
                               f'{width:g} ms' if width is not None else 'Indisponível', detail])
        else:
            for t in d['traces']:
                extra=t['detail']
                if t['markers']:extra+=(' · ' if extra else '')+'; '.join(f"{i+1}: {POINT_NAMES.get(v['label'],v['label'])}" for i,v in enumerate(t['markers']))
                if t['threshold'] is not None:extra+=f" · limiar {t['threshold']:.3f} mV"
                if t['baseline'] is None:extra+=' · base PR indisponível'
                else:extra+=f" · base PR {t['baseline']:.3f} mV"
                values.append([t['lead'],t['value'],extra or r.get('criterion','')])
        self.table.setRowCount(len(values))
        for i,row in enumerate(values):
            for j,v in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(v))
        self.fit_table();self.plot.set_data(d)
    def fit_table(self):
        self.table.resizeRowsToContents();self.table.setFixedHeight(self.table.horizontalHeader().height()+sum(self.table.rowHeight(i) for i in range(self.table.rowCount()))+4)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_table()


class EvidencePlot(QWidget):
    focus_rr=Signal(float)
    def __init__(self,recording,display_config=None):
        super().__init__();self.recording=recording;self.data=None;self.offset=0.;self.rr_targets=[];self.setMinimumWidth(400)
        self.display_config = display_config
        self.event_curves = []
    def set_offset(self,value):self.offset=value;self.update()
    def mousePressEvent(self,event):
        if self.data and self.data['key'] in RHYTHM_RULES and self.rr_targets:
            target=min(self.rr_targets,key=lambda v:(v[0]-event.position().x())**2+(v[1]-event.position().y())**2)
            if (target[0]-event.position().x())**2+(target[1]-event.position().y())**2<400:self.focus_rr.emit(max(0,target[2]-5))
        super().mousePressEvent(event)
    def set_data(self,data):
        self.data = data
        self.event_curves = []
        if data['key'] == 'premature':
            self.event_curves = self.premature_curves(data.get('selected_events', []))
            height = max(210, 185*max((len(curves) for _, curves in self.event_curves), default=0))
        else:
            height = 500 if data['key'] in RHYTHM_RULES else max(230, 195*len(data['traces']))
        self.setMinimumHeight(height)
        self.update()

    def premature_curves(self, events):
        r = self.recording
        curves = []
        if r is None or not events:
            return curves
        for event in events:
            center = event['center']
            left, right = max(0, center-48), min(r.n, center+97)
            values = waveform_values(r, left, right, display_config=self.display_config)
            times = (r.times[left:right]-r.times[center])*1000
            leads = [('DIII', 2), ('aVF', 5)] if r.lead_modes[center] == 6 else [('DI', 0)]
            data = {}
            for lead, ch in leads:
                y = values[:, ch]
                baseline = y[(times < -85) & np.isfinite(y)]
                if len(baseline) and np.isfinite(y).any():
                    data[lead] = (times, y-np.median(baseline))
            if data:
                curves.append((event, data))
        return curves
    @staticmethod
    def path(p,xx,yy,xs,ys,color,width=1.6,dashed=False):
        path=QPainterPath();active=False
        for x,y in zip(xs,ys):
            if not np.isfinite(y):active=False;continue
            if active:path.lineTo(xx(x),yy(y))
            else:path.moveTo(xx(x),yy(y));active=True
        p.setPen(QPen(QColor(color),width,Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine));p.drawPath(path)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('white'))
        d=self.data
        if not d:return
        if d['key'] in RHYTHM_RULES:self.paint_rhythm(p);return
        if d['key'] == 'premature':
            self.paint_premature(p)
            return
        traces=d['traces']
        if not traces:
            p.setPen(QColor('#345848'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Sem curva disponível para este critério.');return
        lo=min(t['lo'] for t in traces);hi=max(t['hi'] for t in traces)
        all_y=np.concatenate([np.r_[t['y'][lo:hi+1],t['central'][lo:hi+1],0] for t in traces])
        low=float(all_y.min());high=float(all_y.max());span=max(high-low,.05);low-=span*.18;high+=span*.18
        for n,t in enumerate(traces):
            area=QRectF(62,n*195+30,max(1,self.width()-88),122)
            xx=lambda i:area.left()+(i-lo)/max(1,hi-lo)*area.width()
            yy=lambda v:area.bottom()-(v-low)/(high-low)*area.height()
            p.setPen(QColor('#345848'));p.drawText(8,n*195+23,t['lead'])
            ticks=[0]+[v for v in (low+(high-low)*.2,low+(high-low)*.8) if abs(v)>(high-low)*.15]
            for val in ticks:
                p.setPen(QPen(QColor('#e2ebe7'),1));p.drawLine(QPointF(area.left(),yy(val)),QPointF(area.right(),yy(val)))
                p.setPen(QColor('#61776c'));p.drawText(QRectF(1,yy(val)-9,57,18),Qt.AlignmentFlag.AlignRight,f'{val:.2f}')
            if t['baseline'] is not None:
                p.setPen(QPen(QColor('#657d9c'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(area.left(),yy(0)),QPointF(area.right(),yy(0)))
                p.drawText(QRectF(area.left(),area.top()-23,100,20),'Base PR = 0')
            for a,b,label in t['bands']:
                p.fillRect(QRectF(xx(a),area.top(),max(2,xx(b)-xx(a)),area.height()),QColor(187,130,25,30))
            for ms in range(-400,701,50):
                i=t['anchor']+ms*.3
                if lo<=i<=hi:
                    p.setPen(QPen(QColor('#e2ebe7'),1));p.drawLine(QPointF(xx(i),area.top()),QPointF(xx(i),area.bottom()))
                    p.setPen(QColor('#61776c'));p.drawText(QRectF(xx(i)-23,area.bottom()+4,46,20),Qt.AlignmentFlag.AlignCenter,str(ms))
            indices=np.arange(lo,hi+1)
            self.path(p,xx,yy,indices,t['central'][lo:hi+1],'#246b58',1.8)
            if d['subset']>=0:self.path(p,xx,yy,indices,t['y'][lo:hi+1],'#99650f',1.8,True)
            threshold=t['threshold']
            if threshold is not None:
                p.setPen(QPen(QColor('#886b42'),1,Qt.PenStyle.DashLine))
                if low<=threshold<=high:p.drawLine(QPointF(area.left(),yy(threshold)),QPointF(area.right(),yy(threshold)))
                else:p.drawText(QRectF(area.left(),area.top()-23,area.width(),20),Qt.AlignmentFlag.AlignRight,f'Limiar {threshold:g} mV fora da faixa visível')
            for number,marker in enumerate(t['markers'],1):
                p.setPen(QPen(QColor('#98610a'),2));p.setBrush(QColor('white'));p.drawEllipse(QPointF(xx(marker['index']),yy(marker['value'])),3.5,3.5);p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawText(QPointF(xx(marker['index'])+5,yy(marker['value'])-6),str(number))
            p.setPen(QColor('#61776c'));p.drawText(QRectF(area.left(),area.bottom()+23,area.width(),20),Qt.AlignmentFlag.AlignRight,'ms relativos ao QRS · mV estimados')

    def paint_premature(self, p):
        if not self.event_curves:
            p.setPen(INK)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Sem complexo prematuro destacado.')
            return
        y_values = np.concatenate([y[np.isfinite(y)] for _, curves in self.event_curves for _, y in curves.values()])
        low = min(float(y_values.min()), -.1)
        high = max(float(y_values.max()), .1)
        grid_step = .1 if high-low <= 1.5 else .2 if high-low <= 3. else .5
        low = np.floor(low/grid_step)*grid_step
        high = np.ceil(high/grid_step)*grid_step
        column_width = self.width()/len(self.event_curves)
        for col, (event, curves) in enumerate(self.event_curves):
            for row, (lead, (times, values)) in enumerate(curves.items()):
                area = QRectF(col*column_width+50, row*185+25, column_width-66, 132)
                xx = lambda ms: area.left()+(ms+160)/480*area.width()
                yy = lambda v: area.bottom()-(v-low)/(high-low)*area.height()
                p.setPen(INK)
                p.drawText(QPointF(area.left(), area.top()-8), f'{lead} · {event_time(self.recording, event):.2f} s')
                p.fillRect(area, PAPER)
                if 'on' in event and 'off' in event:
                    left = xx(event['on']*1000/FS)
                    right = xx(event['off']*1000/FS)
                    p.fillRect(QRectF(left, area.top(), right-left, area.height()), QColor(187,130,25,46))
                for ms in range(-160, 321, 40):
                    p.setPen(QPen(MAJOR if ms == 0 else MINOR, 1))
                    p.drawLine(QPointF(xx(ms), area.top()), QPointF(xx(ms), area.bottom()))
                    if ms % 80 == 0:
                        p.setPen(INK)
                        p.drawText(QRectF(xx(ms)-24, area.bottom()+3, 48, 18), Qt.AlignmentFlag.AlignCenter, str(ms))
                for val in np.arange(low, high+.1*grid_step, grid_step):
                    p.setPen(QPen(MAJOR if abs(val) < 1e-8 else MINOR, 1))
                    p.drawLine(QPointF(area.left(), yy(val)), QPointF(area.right(), yy(val)))
                for val in (low, 0., high):
                    p.setPen(INK)
                    p.drawText(QRectF(area.left()-47, yy(val)-8, 42, 17), Qt.AlignmentFlag.AlignRight, f'{val:g}')
                p.save()
                p.setClipRect(area)
                self.path(p, xx, yy, times, values, INK, 1.7)
                if 'on' in event and 'off' in event:
                    p.setPen(QPen(QColor('#966c2e'), 1, Qt.PenStyle.DashLine))
                    for sample in (event['on'], event['off']):
                        x = xx(sample*1000/FS)
                        p.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
                p.restore()

    def paint_rhythm(self,p):
        d=self.data;r=self.recording;rhythm=d['rhythm'];rr=np.asarray(rhythm.get('rr_seconds',[]));pairs=rhythm.get('rr_pairs',[])
        p.setPen(QColor('#345848'))
        if r is None or not r.n or not len(rr):p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Sem sequência RR disponível.');return
        vals=waveform_values(r,0,r.n,display_config=self.display_config)[:,0].copy()
        times=r.times[:r.n]-capture_start(r);duration=max(float(times[-1]),1)
        vals[times < 0] = np.nan
        low=float(np.nanmin(vals));high=float(np.nanmax(vals));span=max(high-low,.05)
        area=QRectF(62,30,self.width()-88,200);start=min(self.offset,max(0,duration-10));end=min(duration,start+10);xx=lambda t:area.left()+(t-start)/max(1,end-start)*area.width();yy=lambda v:area.bottom()-(v-low+span*.1)/(span*1.2)*area.height()
        med=d['rr_median'];key=d['key'];bad=d['rr_highlights']
        p.save();p.setClipRect(area)
        for i,(a,b) in enumerate(pairs):
            if i<len(bad) and bad[i]:p.fillRect(QRectF(xx(times[a]),area.top(),max(2,xx(times[b])-xx(times[a])),area.height()),QColor(187,130,25,40))
        # Break the line at transport gaps as well as rejected contacts.
        gaps=np.flatnonzero(np.diff(times)>.006)+1;vals[gaps]=np.nan
        self.path(p,xx,yy,times,vals,'#246b58',1.1)
        for k in rhythm.get('detected_peaks',[]):
            if k<r.n and np.isfinite(vals[k]):
                p.setPen(QPen(QColor('#306454'),1.5));p.drawEllipse(QPointF(xx(times[k]),yy(vals[k])),2.5,2.5)
        p.restore()
        for sec in np.linspace(start,end,6):
            p.setPen(QColor('#61776c'));p.drawText(QRectF(xx(sec)-20,234,40,20),Qt.AlignmentFlag.AlignCenter,f'{sec:g}')
        p.setPen(QColor('#345848'));p.drawText(62,20,'DI · trecho de 10 s · batimentos originais, inclusive excluídos da mediana')
        area2=QRectF(62,290,self.width()-88,160);levels=(med,1.) if key=='brady' else (med,.6) if key=='tachy' else (med*.85,med,med*1.15)
        xx=lambda t:area2.left()+t/duration*area2.width();rlo=min(float(rr.min()),min(levels));rhi=max(float(rr.max()),max(levels));rspan=max(rhi-rlo,.1)
        ry=lambda v:area2.bottom()-(v-rlo+rspan*.1)/(rspan*1.2)*area2.height()
        last_label = -100
        for v in sorted(set(levels), reverse=True):
            rate_finding = key in ('brady', 'tachy') and v == med and d['row'].get('status') == 'detected'
            color = '#98610a' if rate_finding else '#306454' if v == med else '#a7b9b1'
            p.setPen(QPen(QColor(color),1.5,Qt.PenStyle.DashLine));p.drawLine(QPointF(area2.left(),ry(v)),QPointF(area2.right(),ry(v)))
            label_y = max(ry(v)-9, last_label+17)
            p.setPen(QColor('#61776c'));p.drawText(QRectF(0,label_y,58,18),Qt.AlignmentFlag.AlignRight,f'{v*1000:.0f}')
            last_label = label_y
        self.rr_targets=[]
        p.fillRect(QRectF(xx(start),area2.top(),xx(end)-xx(start),area2.height()),QColor(36,107,88,18))
        for i,(a,b) in enumerate(pairs):
            if i>=len(rr):break
            self.rr_targets.append((xx(times[b]),ry(rr[i]),float(times[b])))
            p.setPen(QPen(QColor('#98610a' if bad[i] else '#246b58'),2));p.drawEllipse(QPointF(xx(times[b]),ry(rr[i])),3,3)
        p.setPen(QColor('#345848'));p.drawText(62,277,'RR (ms) · mediana e '+('limiar equivalente de FC' if key in ('brady','tachy') else 'faixa ±15%; CV utiliza a sequência inteira'))
        for sec in range(0,int(duration)+1,5):
            p.setPen(QColor('#61776c'));p.drawText(QRectF(xx(sec)-20,455,40,20),Qt.AlignmentFlag.AlignCenter,str(sec))
        p.drawText(QRectF(62,477,self.width()-88,20),Qt.AlignmentFlag.AlignRight,'Tempo da gravação (s) · nenhuma ligação RR atravessa lacunas')
