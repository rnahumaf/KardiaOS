"""One vector A4 page, explicit physical scales and contiguous DI row intervals."""
import io
import math
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from .signal import LEADS
from .orientation import evidence_summary,amplitude_label


def page_plan(recording, speed=25, gain=10, raw=False, offset=0, layout='auto', analysis=None):
    if analysis is not None and analysis.get("mode")!="normal":raise ValueError("Comparacao tecnica de inversoes nao pertence ao relatorio padrao.")
    r = recording
    if r is None or not r.n or r.meta.get('start') is None: raise ValueError('Não há trecho estabilizado para imprimir.')
    if speed not in (25,50) or gain not in (5,10,20): raise ValueError('Escala inválida.')
    if r.meta.get('sample_rate') != 300: raise ValueError('Frequência incompatível com a escala temporal de impressão.')
    if layout not in ('auto','di','six'): raise ValueError('Layout inválido.')
    times = r.times[:r.n]
    if not np.isfinite(times).all() or np.any(np.diff(times)<=0): raise ValueError('Base temporal inválida.')
    begin = float(r.meta['start'])
    end = min(float(r.meta.get('end') or r.last_time),r.last_time)+1/300
    if not np.isfinite(offset) or offset<0 or offset>=end-begin: raise ValueError('Início do trecho inválido.')
    t0=begin+offset
    selected='six' if (layout=='six' or layout=='auto' and r.mode_at(t0)==6) else 'di'
    values=r.lead_values(raw=raw)
    rows=[]
    available=95 if analysis is not None else 145
    if selected=='di':
        duration=250/speed
        # At most six rows, using the actual amplitude envelope. No vertical/horizontal compression.
        best=None
        for count in range(1,7):
            stop=min(end,t0+count*duration)
            first,last=np.searchsorted(times,[t0,stop])
            finite=values[first:last,0]; finite=finite[np.isfinite(finite)]
            low=min(0,float(finite.min())*gain) if len(finite) else 0
            high=max(gain,float(finite.max())*gain) if len(finite) else gain
            height=max(22,high-low+10)
            if count*height+(count-1)*2 > available: break
            best=(count,height,low,high)
            if stop>=end-1e-8: break
        if best is None: raise ValueError('Amplitude não cabe em uma faixa A4 nesse ganho. Reduza o ganho; nenhum traçado foi recortado.')
        count,height,low,high=best
        height=max(height,min(45,(available-(count-1)*2)/count))
        for i in range(count):
            start=t0+i*duration
            if start>=end-1e-8: break
            stop=min(start+duration,end)
            top=175-i*(height+2)
            bottom=top-height
            rows.append(dict(lead=0,x=10,top=top,w=277,h=height,baseline=bottom+3-low+max(0,height-(high-low+9))/2,
                             start=start,end=stop,data_x=27,duration=duration,
                             title=f'D1 | {start-begin:.1f}–{stop-begin:.1f} s'))
        stop=rows[-1]['end']
    else:
        if r.mode_at(t0)!=6: raise ValueError('Seis derivações indisponíveis no início; use DI em linhas.')
        band=24 if analysis is not None else 35
        for index,(left,right) in enumerate(((0,5),(1,4),(2,3))):
            for lead,xpos in [(left,10),(right,152)]:
                rows.append(dict(lead=lead,x=xpos,top=175-index*band,w=135,h=band,baseline=175-(index+1)*band+7 if analysis is not None else 155-index*35,
                    start=t0,end=min(t0+118/speed,end),data_x=xpos+17,duration=118/speed,title=LEADS[lead]))
        rows.append(dict(lead=1,x=10,top=103 if analysis is not None else 65,w=277,h=23 if analysis is not None else 40,baseline=87 if analysis is not None else 45,start=t0,end=min(t0+250/speed,end),data_x=27,
                         duration=250/speed,title='D2 contínua'))
        stop=rows[-1]['end']
    for row in rows:
        first,last=np.searchsorted(times,[row['start'],row['end']])
        row.update(first=int(first),last=int(last))
        v=values[first:last,row['lead']]
        y=row['baseline']+v*gain
        if np.any(np.isfinite(y)&((y<row['top']-row['h']+1)|(y>row['top']-6))):
            raise ValueError('Amplitude ultrapassa a faixa neste ganho. Reduza o ganho; nenhum traçado foi recortado.')
        if row['baseline']+gain>row['top']-6:
            raise ValueError('Pulso de calibração não cabe neste ganho. Reduza o ganho.')
    return dict(layout=selected,rows=rows,begin=begin,start=t0,end=stop,recording_end=end,
                speed=speed,gain=gain,remaining_seconds=max(0,end-stop),values=values)


def pdf_bytes(recording, speed=25.0, gain=10.0, raw=False, offset=0.0, layout='auto', analysis=None):
    plan=page_plan(recording,speed,gain,raw,offset,layout,analysis)
    stream=io.BytesIO(); c=canvas.Canvas(stream,pagesize=landscape(A4),pageCompression=1)
    c.setTitle('KardiaOS - ECG experimental')
    width,height=landscape(A4); cfg=recording.config; times=recording.times[:recording.n]
    gaps=np.r_[False,~np.isclose(np.diff(times),1/300,atol=1e-6,rtol=0)]
    c.setFillColor(HexColor('#fffcf1')); c.rect(0,0,width,height,fill=1,stroke=0)
    c.setFillColor(HexColor('#183e42')); c.setFont('Helvetica-Bold',17)
    c.drawString(10*mm,height-14*mm,'KardiaOS')
    c.setFont('Helvetica',9)
    c.drawString(10*mm,height-20*mm,'ECG experimental de pesquisa | '+('DADOS SINTÉTICOS' if recording.meta.get('synthetic') else 'Captura local'))
    c.drawRightString(width-10*mm,height-13*mm,f'{speed:g} mm/s | {gain:g} mm/mV | 300 Hz nominais')
    c.drawRightString(width-10*mm,height-19*mm,amplitude_label(recording))
    c.setFont('Helvetica',8)
    c.drawString(10*mm,height-27*mm,f"Trecho {offset:.1f} a {plan['end']-plan['begin']:.1f} s de {plan['recording_end']-plan['begin']:.1f} s | Página 1/1")
    filters='Bruto' if raw else f'Filtrado: base {cfg.baseline:g} Hz; passa-baixas {cfg.lowpass:g} Hz; rede {cfg.notch or "desligada"}'
    c.drawRightString(width-10*mm,height-27*mm,filters)
    c.setFont('Helvetica',6.5);c.drawString(10*mm,179*mm,evidence_summary(recording))
    for row in plan['rows']:
        x,top,w,h,baseline=[row[k] for k in ('x','top','w','h','baseline')]; bottom=top-h
        for j in range(int(w)+1):
            c.setStrokeColor(HexColor('#cfb89e' if j%5==0 else '#eedfcb'));c.setLineWidth(.35 if j%5==0 else .16)
            c.line((x+j)*mm,bottom*mm,(x+j)*mm,top*mm)
        for j in range(int(h)+1):
            c.setStrokeColor(HexColor('#cfb89e' if j%5==0 else '#eedfcb'));c.setLineWidth(.35 if j%5==0 else .16)
            c.line(x*mm,(bottom+j)*mm,(x+w)*mm,(bottom+j)*mm)
        c.setStrokeColor(HexColor('#153f43'));c.setLineWidth(.65)
        pulse=c.beginPath();pulse.moveTo((x+1)*mm,baseline*mm)
        for dx,dy in [(2,0),(2,gain),(2+.2*speed,gain),(2+.2*speed,0),(4+.2*speed,0)]: pulse.lineTo((x+dx)*mm,(baseline+dy)*mm)
        c.drawPath(pulse)
        path=c.beginPath();connected=False
        for k in range(row['first'],row['last']):
            v=plan['values'][k,row['lead']]
            if not np.isfinite(v) or k>row['first'] and gaps[k]: connected=False
            if not np.isfinite(v): continue
            px=(row['data_x']+(times[k]-row['start'])*speed)*mm;py=(baseline+v*gain)*mm
            if connected:path.lineTo(px,py)
            else:path.moveTo(px,py)
            connected=True
        c.drawPath(path)
        c.setFillColor(HexColor('#fffcf1'));c.rect((x+.5)*mm,(top-5)*mm,75*mm,4*mm,fill=1,stroke=0)
        c.setFillColor(HexColor('#183e42'));c.setFont('Helvetica-Bold',8);c.drawString((x+1)*mm,(top-4)*mm,row['title'])
    if analysis is not None: draw_analysis(c,analysis)
    c.setFillColor(HexColor('#53635e'));c.setFont('Helvetica',7)
    if plan['layout']=='di':
        message=f"Somente D1 em {len(plan['rows'])} linhas sucessivas; sem compressão temporal ou preenchimento."
    else:message=f'Seis derivações: faixas superiores de até {118/speed:g} s; D2 contínua de até {250/speed:g} s.'
    if analysis is not None:message+=' Resultados: janelas indicadas, podem diferir do trecho impresso.'
    c.drawString(10*mm,23*mm,message)
    c.drawString(10*mm,17*mm,'A4 paisagem a 100%. Grade: 1 mm / 5 mm. Pulso: 1 mV, 200 ms na escala indicada. Relógio físico não validado.')
    c.drawString(10*mm,12*mm,'Uso experimental. Lacunas preservadas. Amplitude/polaridade não são confirmadas pela aparência ou pelos escores.')
    c.drawString(10*mm,7*mm,f"Restante fora desta folha: {plan['remaining_seconds']:.1f} s. Mude o início para outro trecho; o bruto completo permanece preservado.")
    c.showPage();c.save();return stream.getvalue()


def draw_analysis(c, analysis):
    """Compact research panel; all sign scenarios, never a favorable selection."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c.setFillColor(HexColor('#183e42'))
    def line(text, y, bold=False, size=7):
        font='Helvetica-Bold' if bold else 'Helvetica'
        text=str(text).replace('−','-').replace('≥','>=')
        while stringWidth(text,font,size)>277*mm: text=text[:-4]+'...'
        c.setFont(font,size);c.drawString(10*mm,y*mm,text)
    m=analysis['measurements'];metrics=m['metrics']
    line('MEDICOES EXPERIMENTAIS DE DI | 300 Hz nominais | nao validadas clinicamente',73,True)
    parts=[]
    for key,name in [('heart_rate','FC'),('p_duration','P'),('qrs_duration','QRS'),('qt','QT'),('qtc_f','QTcF')]:
        v=metrics[key];parts.append(name+': '+(f"{v['value']:g} {v['unit']}" if v['value'] is not None else 'indisponivel'))
    line(' | '.join(parts)+f" | trecho medido: {m.get('offset_seconds',0):g}-{m.get('offset_seconds',0)+m.get('duration_seconds',0):g} s",69,True)
    reasons=list(dict.fromkeys(v['reason'] for v in metrics.values() if v['value'] is None))
    line('Motivo: '+' / '.join(reasons) if reasons else 'QTcF = QT(ms)/RR(s)^(1/3). Limites relativos de onda; filtros podem alterar duracoes. Nao e medida global de 12 derivacoes.',65,size=6.8)
    line('QTcF = QT(ms)/RR(s)^(1/3), Fridericia; RR estavel 0,6-1,5 s e QRS <120 ms. Escala/polaridade nao verificadas por estas medidas.',61,size=6.8)
    line('HIPOTESES DAS REDES | 3 maiores scores por modelo; fluxo normal | nao sao probabilidades nem diagnosticos',57,True)
    entries=[]
    for item in analysis.get('scenarios',[]):
        prefix={'ecgfounder_1l':'ECGFounder 1L','deeppsp_2l':'DeepPSP 2L','deeppsp_6l':'DeepPSP 6L'}.get(item['model'],item['model'])
        prefix+=f" | {item['hypothesis']} | {item['offset_seconds']:g}-{item['offset_seconds']+10:g} s | "
        top=sorted(item['scores'],key=lambda v:v['score'],reverse=True)[:3]
        labels=[]
        for v in top:
            name=v['name'];name=name if len(name)<=43 else name[:40]+'...'
            labels.append(f"{name}: {v['score']:.4f}")
        entries.append(prefix+(' ; '.join(labels) if labels else 'Indisponivel: '+item.get('reason','sem saida valida')))
    entries.extend(v['model']+' | Indisponivel: '+v['reason'] for v in analysis.get('unavailable',[]))
    if not entries: entries=['Analise das redes em andamento.' if analysis.get('status')=='running' else 'Sem escores disponiveis. '+analysis.get('reason','')]
    for i,text in enumerate(entries[:10]):line(text,53-3*i,size=6.5)
    if analysis.get('status')!='completed':line('RESULTADO PARCIAL / '+analysis.get('status','indisponivel'),25,True,size=6.5)
