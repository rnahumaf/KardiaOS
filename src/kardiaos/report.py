"""One vector A4 page, explicit physical scales and contiguous DI row intervals."""
import io
import math
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from .signal import LEADS


def page_plan(recording, speed=25, gain=10, raw=False, offset=0, layout='auto'):
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
            if count*height+(count-1)*2 > 145: break
            best=(count,height,low,high)
            if stop>=end-1e-8: break
        if best is None: raise ValueError('Amplitude não cabe em uma faixa A4 nesse ganho. Reduza o ganho; nenhum traçado foi recortado.')
        count,height,low,high=best
        height=max(height,min(45,(145-(count-1)*2)/count))
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
        for index,(left,right) in enumerate(((0,5),(1,4),(2,3))):
            for lead,xpos in [(left,10),(right,152)]:
                rows.append(dict(lead=lead,x=xpos,top=175-index*35,w=135,h=35,baseline=155-index*35,
                    start=t0,end=min(t0+118/speed,end),data_x=xpos+17,duration=118/speed,title=LEADS[lead]))
        rows.append(dict(lead=1,x=10,top=65,w=277,h=40,baseline=45,start=t0,end=min(t0+250/speed,end),data_x=27,
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


def pdf_bytes(recording, speed=25.0, gain=10.0, raw=False, offset=0.0, layout='auto'):
    plan=page_plan(recording,speed,gain,raw,offset,layout)
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
    c.drawRightString(width-10*mm,height-19*mm,'amplitude declarada pelo usuário' if recording.meta.get('amplitude_verified') else 'amplitude estimada, não calibrada')
    c.setFont('Helvetica',8)
    c.drawString(10*mm,height-27*mm,f"Trecho {offset:.1f} a {plan['end']-plan['begin']:.1f} s de {plan['recording_end']-plan['begin']:.1f} s | Página 1/1")
    filters='Bruto' if raw else f'Filtrado: base {cfg.baseline:g} Hz; passa-baixas {cfg.lowpass:g} Hz; rede {cfg.notch or "desligada"}'
    c.drawRightString(width-10*mm,height-27*mm,filters)
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
    c.setFillColor(HexColor('#53635e'));c.setFont('Helvetica',7)
    if plan['layout']=='di':
        message=f"Somente D1 em {len(plan['rows'])} linhas sucessivas; sem compressão temporal ou preenchimento."
    else:message=f'Seis derivações: faixas superiores de até {118/speed:g} s; D2 contínua de até {250/speed:g} s.'
    c.drawString(10*mm,23*mm,message)
    c.drawString(10*mm,17*mm,'A4 paisagem a 100%. Grade: 1 mm / 5 mm. Pulso: 1 mV, 200 ms na escala indicada. Relógio físico não validado.')
    c.drawString(10*mm,12*mm,'Uso experimental. Lacunas preservadas. Amplitude/polaridade não são confirmadas pela aparência ou pelos escores.')
    c.drawString(10*mm,7*mm,f"Restante fora desta folha: {plan['remaining_seconds']:.1f} s. Mude o início para outro trecho; o bruto completo permanece preservado.")
    c.showPage();c.save();return stream.getvalue()
