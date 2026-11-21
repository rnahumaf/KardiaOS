"""One exact-scale A4 page containing the automatic report window."""
import io,math
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.units import mm
from .signal import LEADS
from .review_window import trace_window,recording_scope
from .review_signal import waveform_values
from .automatic_analysis import analysis_key,cached_analysis
from .measurement_quality import alerts
from .processing import profile_label,empirical

DEFAULT_IMAGEABLE=(3.,3.,291.,204.)
MIN_STRIP_HEIGHT = 24.  # mm
ROW_GAP = 2.
TEMPLATE_GAP = 3.


def analysis_for_page(recording,analysis,plan=None,raw=False):
    if analysis.get('mode')!='normal':raise ValueError('Comparação técnica não pertence ao laudo padrão.')
    if analysis.get('status')!='completed':raise ValueError('Aguarde a conclusão da análise local.')
    if analysis.get('source_key')!=analysis_key(recording):raise ValueError('Análise de outra captura ou processamento. Reavalie.')
    window=analysis.get('report_window')
    if not analysis.get('reportable') or not window:raise ValueError(analysis.get('reason') or 'Gravação insuficiente para laudo.')
    if plan:
        planned_window = plan.get('report_window', {})
        if (window['first_sample'] != planned_window.get('first_sample', plan['first'])
                or window['last_sample_exclusive'] != planned_window.get('last_sample_exclusive', plan['last'])
                or not plan['first'] <= window['first_sample'] < window['last_sample_exclusive'] <= plan['last']):
            raise ValueError('Resultados e traçado pertencem a janelas diferentes.')
    # Printing is never allowed to silently include a score from another window.
    for item in analysis.get('scenarios',[]):
        if item.get('scores') and (item.get('source_key')!=analysis['source_key'] or item.get('first_sample')!=window['first_sample'] or item.get('last_sample_exclusive')!=window['last_sample_exclusive']):
            raise ValueError('Hipótese de outra janela. Reavalie o registro.')
    return analysis


def _range(values,gain):
    finite=np.asarray(values)[np.isfinite(values)]
    return (min(0.,float(finite.min())*gain),max(0.,float(finite.max())*gain)) if len(finite) else (0.,0.)


def _strip(times, values, lead, start, end, gain):
    first, last = np.searchsorted(times, [start - 1e-7, end - 1e-7])
    low, high = _range(values[first:last, lead], gain)
    high = max(high, gain)  # The 1 mV calibration pulse shares the trace baseline.
    return dict(lead=lead, start=start, end=end, duration=end-start, first=int(first), last=int(last),
                h=max(MIN_STRIP_HEIGHT, high-low+4), center_mm=(high+low)/2)


def _di_edges(begin, end, window_end, count, narrow_rows, full_seconds, narrow_seconds):
    wide_rows = count - narrow_rows
    capacity = wide_rows * full_seconds + narrow_rows * narrow_seconds
    if capacity < 10 - 1e-7:
        return None
    span = min(end - begin, capacity)
    start = max(begin, min(window_end, end) - span)
    narrow_duration = min(span / count, narrow_seconds)
    wide_duration = (span - narrow_rows * narrow_duration) / wide_rows if wide_rows else 0.
    durations = [wide_duration] * wide_rows + [narrow_duration] * narrow_rows
    edges = start + np.r_[0., np.cumsum(durations)]
    edges[-1] = min(end, start + span)
    return edges


def _di_strips(times, values, begin, end, window_start, window_end, speed, gain, width, height, template_side):
    full_seconds = width / speed
    narrow_seconds = (width - template_side - TEMPLATE_GAP) / speed if template_side else full_seconds
    if narrow_seconds < 1:
        raise ValueError('A escala e as margens não comportam uma faixa legível.')
    if template_side > height:
        raise ValueError('A mediana excede a altura A4 nesta escala. Confira as margens e o ganho.')

    max_rows = math.floor((height + ROW_GAP) / (MIN_STRIP_HEIGHT + ROW_GAP))
    # A large median can sit beside the last two strips at 50 mm/s.
    beside_rows = math.ceil((template_side + ROW_GAP) / (MIN_STRIP_HEIGHT + ROW_GAP)) if template_side else 0
    # If an out-of-window amplitude cannot fit, the original 10 s may still be printable.
    for earliest, latest in ((begin, end), (window_start, min(window_end, end))):
        for count in range(max_rows, 0, -1):
            edges = _di_edges(earliest, latest, window_end, count, min(count, beside_rows),
                              full_seconds, narrow_seconds)
            if edges is None:
                continue
            rows = [_strip(times, values, 0, left, right, gain) for left, right in zip(edges, edges[1:])]
            spare = height - sum(row['h'] for row in rows) - ROW_GAP * (count - 1)
            if spare >= -1e-7:
                for row in rows:
                    row['h'] += spare / count
                return rows
    raise ValueError('A janela de 10 s não cabe na área imprimível nesta escala. Confira as margens ou reduza o ganho.')


def page_plan(recording,speed=25,gain=10,raw=False,offset=0,layout='auto',analysis=None,imageable=DEFAULT_IMAGEABLE):
    r=recording;begin,end=recording_scope(r)
    if speed not in (25,50) or gain not in (5,10,20):raise ValueError('Escala inválida.')
    if layout not in ('auto','di','six'):raise ValueError('Layout inválido.')
    if offset!=0:raise ValueError('O laudo usa a janela automática comum de 10 s; não há seleção manual.')
    if r.meta.get('end') is None:raise ValueError('Conclua a gravação antes de gerar o laudo.')
    analysis=analysis if analysis is not None else cached_analysis(r)
    if analysis is not None:
        analysis=analysis_for_page(r,analysis);window=analysis['report_window']
    else:window=trace_window(r)
    selected=window['layout'] if layout=='auto' else layout
    if selected=='six' and window['layout']!='six':raise ValueError('Não há seis derivações reais nesta janela.')
    a,b=window['first_sample'],window['last_sample_exclusive'];t0=begin+window['offset_seconds'];stop=t0+10.
    times=r.times[:r.n]
    if not 0<=a<b<=r.n or abs(times[a]-t0)>1/300+1e-7:raise ValueError('Janela inconsistente com as amostras.')
    inferred=bool(analysis and not analysis.get('trace_only') and window['analysis_eligible'])
    reps=analysis.get('representative',{}) if inferred else {}
    values=waveform_values(r,0,r.n,raw=raw,mask_contact=inferred)
    x0,y0,w,h=map(float,imageable)
    if not all(np.isfinite([x0,y0,w,h])) or x0<0 or y0<0 or w<=0 or h<=0 or x0+w>297.01 or y0+h>210.01:
        raise ValueError('Área imprimível inválida.')
    gutter=max(9.,4+.2*speed);left=x0+gutter;right=x0+w-3.;top=y0+h-24
    names=['I','II','III','aVR','aVL','aVF'] if selected=='six' else ['I']
    side=max(24.,.96*speed)
    for name in names:
        template=reps.get(name)
        if template:
            lo,hi=_range(template['raw_values_mv' if raw else 'values_mv'],gain)
            side=max(side,hi-lo+4.,(template['time_seconds'][-1]-template['time_seconds'][0]+1/300)*speed)
    if selected=='six':
        rows = [_strip(times, values, lead, t0, stop, gain) for lead in range(len(names))]
        for row, name in zip(rows, names):
            row['template'] = reps.get(name)
            if row['template']:
                row['h'] = max(row['h'], side)
    else:
        template = reps.get('I')
        footer_height = 24. if analysis and alerts(analysis.get('measurements', {})) else 20.
        rows = _di_strips(times, values, begin, end, t0, stop, speed, gain,
                          right-left, top-(y0+footer_height), side if template else 0.)
        rows[-1]['template'] = template
    for row in rows:
        lead, start, finish = row['lead'], row['start'], row['end']
        template = row.get('template')
        trace_width=row['duration']*speed;template_x=left+trace_width+TEMPLATE_GAP
        if left+trace_width>right+1e-7 or template and template_x+side>right+1e-7:
            raise ValueError('10 s e o template não cabem nas margens nesta escala. Nenhum traçado foi comprimido.')
        height = row['h']
        baseline = top - height/2 - row['center_mm']
        title=LEADS[lead] if selected=='six' else f'DI | {start-begin:.3f}–{finish-begin:.3f} s'
        row.update(x=x0, top=top, w=trace_width+gutter, baseline=baseline, data_x=left, title=title,
                   template=template, template_x=template_x, template_side=side if template else 0.)
        if template:
            tl,th=_range(template['raw_values_mv' if raw else 'values_mv'],gain)
            row['template_bottom']=top-height+max(0., (height-side)/2)
            row['template_baseline']=row['template_bottom']+side/2-(tl+th)/2
        top -= height + ROW_GAP
    if rows[-1]['top']-rows[-1]['h']<y0+20-1e-7:
        raise ValueError('Amplitude e quadrados excedem a altura A4 nesta escala. Reduza o ganho; nada foi recortado.')
    if not rows[0]['first'] <= a < b <= rows[-1]['last']:
        raise ValueError('A janela automática não está contida no trecho impresso.')
    start, finish = rows[0]['start'], rows[-1]['end']
    return dict(layout=selected,rows=rows,begin=begin,start=start,end=finish,recording_end=end,
        first=rows[0]['first'],last=rows[-1]['last'],report_window=window.copy(),
        speed=speed,gain=gain,raw=raw,remaining_seconds=max(0,(end-begin)-(finish-start)),values=values,
        analysis=analysis,inferred=inferred,imageable=(x0,y0,w,h),content_bounds=(x0,y0,x0+w,y0+h))


def _grid(c,x,bottom,w,h):
    for vertical,length in [(True,w),(False,h)]:
        for j in range(int(length)+1):
            c.setStrokeColor(HexColor('#cfb89e' if j%5==0 else '#eedfcb'));c.setLineWidth(.35 if j%5==0 else .16)
            if vertical:c.line((x+j)*mm,bottom*mm,(x+j)*mm,(bottom+h)*mm)
            else:c.line(x*mm,(bottom+j)*mm,(x+w)*mm,(bottom+j)*mm)


def _text(c,text,x,y,size=8,bold=False,*,right=False,max_width=None):
    c.setFillColor(HexColor('#183e42'));c.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
    text = str(text).replace('≥','>=')
    if max_width is not None and c.stringWidth(text) > max_width*mm:
        available = max_width*mm - c.stringWidth('…')
        length = 0
        for character in text:
            available -= c.stringWidth(character)
            if available < 0:
                break
            length += 1
        text = text[:length].rstrip() + '…'
    draw = c.drawRightString if right else c.drawString
    draw(x*mm,y*mm,text)


def measurement_line(analysis):
    if not analysis:return ''
    root=analysis.get('measurements',{});items=[root]+root.get('additional_leads',[])
    selected=analysis.get('selected_lead');item=next((v for v in items if v.get('lead')==selected),root)
    parts=[]
    for key,name in [('heart_rate','FC'),('p_duration','P'),('qrs_duration','QRS'),('qtc_f','QTcF')]:
        metric=item.get('metrics',{}).get(key,{})
        value=metric.get('value');text=f'{value:g} {metric["unit"]}' if value is not None else 'indisponível'
        if metric.get('quality',{}).get('reason'):text+=' *'
        if key!='heart_rate':
            scope = 'global' if item.get('global_intervals') else f'D{item["lead"]}' if item.get('lead') else ''
            if scope:
                suffix = ', Fridericia' if key == 'qtc_f' else ''
                text += f' ({scope}{suffix})'
        parts.append(name+': '+text)
    return ' | '.join(parts)


def pdf_bytes(recording,speed=25.,gain=10.,raw=False,offset=0.,layout='auto',analysis=None,imageable=DEFAULT_IMAGEABLE):
    plan=page_plan(recording,speed,gain,raw,offset,layout,analysis,imageable)
    analysis=plan['analysis'];x0,y0,w,h=plan['imageable'];top=y0+h;right=x0+w
    stream=io.BytesIO();c=canvas.Canvas(stream,pagesize=landscape(A4),pageCompression=1)
    c.setTitle('KardiaOS - ECG exploratório');width,height=landscape(A4)
    c.setFillColor(HexColor('#fffcf1'));c.rect(0,0,width,height,fill=1,stroke=0)
    _text(c,'KardiaOS',x0,top-5,14,True)
    if recording.meta.get('synthetic'):_text(c,'DADOS SINTÉTICOS',x0+35,top-5,8,True)
    _text(c,f'{speed:g} mm/s | {gain:g} mm/mV estimados | 300 Hz nominais',right,top-5,right=True)
    cfg=recording.config
    filters='Bruto' if raw else f'Fase zero | {cfg.baseline:g}–{cfg.lowpass:g} Hz | rede {cfg.notch or "desligada"}'
    _text(c,filters,right,top-11,right=True)
    if recording.patient_name:
        name = ' '.join(recording.patient_name.split())
        name_width = w - c.stringWidth(filters, 'Helvetica', 8)/mm - 5
        _text(c,f'Paciente: {name}',x0,top-11,10,True,max_width=name_width)
    timestamp = recording.recorded_time_text
    _text(c,f'Gravado em {timestamp}' if timestamp else 'Data e hora da gravação indisponíveis',x0,top-17)
    metrics = measurement_line(analysis) if plan['inferred'] else 'Somente traçado'
    _text(c,metrics,right,top-17,right=True)
    window = plan['report_window']
    window_start = window['offset_seconds']
    window_label = f'Janela automática {window_start:.3f}–{window_start + window["duration_seconds"]:.3f} s'
    span = f'{plan["start"]-plan["begin"]:.3f}–{plan["end"]-plan["begin"]:.3f} s'
    if plan['layout'] == 'di':
        scope = f'DI {span}'
        if plan['inferred']:
            scope += f' | {window_label}'
    else:
        scope = window_label
    _text(c,f'{scope} | gravação {plan["recording_end"]-plan["begin"]:.3f} s',x0,top-21)
    times=recording.times[:recording.n];gaps=np.r_[False,~np.isclose(np.diff(times),1/300,atol=1e-6,rtol=0)]
    for row in plan['rows']:
        left=row['data_x'];bottom=row['top']-row['h'];baseline=row['baseline']
        _grid(c,left,bottom,row['duration']*speed,row['h'])
        c.setStrokeColor(HexColor('#153f43'));c.setLineWidth(.65)
        pulse=c.beginPath();pulse.moveTo((x0+.5)*mm,baseline*mm)
        for dx,dy in [(1,0),(1,gain),(1+.2*speed,gain),(1+.2*speed,0),(2+.2*speed,0)]:
            pulse.lineTo((x0+dx)*mm,(baseline+dy)*mm)
        c.drawPath(pulse)
        path=c.beginPath();connected=False
        for k in range(row['first'],row['last']):
            value=plan['values'][k,row['lead']]
            if not np.isfinite(value) or k>row['first'] and gaps[k]:connected=False
            if not np.isfinite(value):continue
            px=(left+(times[k]-row['start'])*speed)*mm;py=(baseline+value*gain)*mm
            if connected:path.lineTo(px,py)
            else:path.moveTo(px,py)
            connected=True
        c.drawPath(path)
        from .timing_markers import p_intervals
        for mark in p_intervals(analysis,['I','II','III','aVR','aVL','aVF'][row['lead']],row['first'],row['last']):
            c.setStrokeColor(HexColor('#8c6e39'));c.setLineWidth(.4)
            for k in (mark['on'],mark['off']):
                value=plan['values'][k,row['lead']]
                if np.isfinite(value):
                    xx=left+(times[k]-row['start'])*speed;yy=baseline+value*gain
                    c.line(xx*mm,(yy-.7)*mm,xx*mm,(yy+.7)*mm)
            k=mark['on'];value=plan['values'][k,row['lead']]
            if np.isfinite(value):_text(c,'P',left+(times[k]-row['start'])*speed,baseline+value*gain+1.1,4)
        _text(c,row['title'],left,row['top']+.35,5.5,True)
        template=row['template']
        if template:
            bx,by,side=row['template_x'],row['template_bottom'],row['template_side'];_grid(c,bx,by,side,side)
            c.setStrokeColor(HexColor('#899c96'));c.setLineWidth(.5);c.rect(bx*mm,by*mm,side*mm,side*mm)
            _text(c,'Mediana',bx,by+side+.35,5.5)
            tx=np.asarray(template['time_seconds']);tv=np.asarray(template['raw_values_mv' if raw else 'values_mv']);px=bx+(side-(tx[-1]-tx[0])*speed)/2+(tx-tx[0])*speed
            py=row['template_baseline']+tv*gain;path=c.beginPath();path.moveTo(px[0]*mm,py[0]*mm)
            for xx,yy in zip(px[1:],py[1:]):path.lineTo(xx*mm,yy*mm)
            c.setStrokeColor(HexColor('#153f43'));c.setLineWidth(.65);c.drawPath(path)
            for marker in template.get('markers',[]):
                k=marker['index']
                if 0<=k<len(px):
                    c.setStrokeColor(HexColor('#6e817d'));c.setLineWidth(.5);c.line(px[k]*mm,(py[k]-.8)*mm,px[k]*mm,(py[k]+.8)*mm)
    if plan['inferred'] and analysis.get('classification'):
        summary=analysis['classification']['summary']
        _text(c,summary,x0,y0+17,7,True)
        items=analysis.get('hypotheses',[])
        for index,item in enumerate(items[:2]):_text(c,item['label'],x0,y0+12-index*4,7)
        if len(items)>2:_text(c,f"Mais {len(items)-2} achados nos detalhes da análise.",x0,y0+4,6.5)
    elif plan['inferred'] and analysis.get('hypotheses'):
        _text(c,'Hipóteses dos modelos',x0,y0+16,7,True)
        for index,item in enumerate(analysis['hypotheses'][:3]):_text(c,item['label']+' · '+item['model'],x0,y0+12-index*4,7.5)
    profile='perfil empírico' if empirical(recording) else profile_label(recording)
    if analysis and alerts(analysis.get('measurements',{})):
        _text(c,'* Estabilidade técnica limitada em algumas medidas; motivos e faixas nos detalhes da análise.',x0,y0+21,6.5)
    _text(c,'Pesquisa exploratória | '+profile+' | A4 a 100% | medianas: QRS 0,5–80 Hz; P/T 0,5–30 Hz | gravação completa preservada',x0,y0+1,6.5)
    c.showPage();c.save();return stream.getvalue()
