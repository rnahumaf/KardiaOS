"""Inspectable timing fiducials on the dedicated measurement pipeline."""
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import QWidget
from .delineation import preprocess,FS
from .processing import scale_and_signs

class TimingPlot(QWidget):
    def __init__(self,recording,parent=None):
        super().__init__(parent);self.recording=recording;self.measurement=None;self.beat=0;self.values=None
        self.setMinimumSize(400,230)
    def set_measurement(self,value):
        self.measurement=value;self.beat=0;self.values=None
        if value and value.get('global_intervals'):
            if value.get('median'):
                self.values=np.asarray(value['median']['values_mv'])
        elif value and value.get('fiducials'):
            a=value['first_sample'];b=value['last_sample_exclusive'];channel=0 if value['lead']=='I' else 1
            factor,signs=scale_and_signs(self.recording)
            self.values=preprocess(self.recording.raw[a:b,channel].astype(float))*factor*signs[channel]
        self.update()
    def set_beat(self,index):self.beat=max(0,index);self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#ffffff'))
        p.setPen(QColor('#21474b'))
        m=self.measurement
        if m and m.get('global_intervals'):
            self.paint_median(p,m);return
        if self.values is None or not m or self.beat>=len(m['fiducials']):
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Sem limites disponíveis neste trecho.');return
        point=m['fiducials'][self.beat];a=m['first_sample'];r=point['r']-a
        lo=max(0,r-120);hi=min(len(self.values),r+190);y=self.values[lo:hi]
        if len(y)<2:return
        area=QRectF(48,44,max(1,self.width()-70),max(1,self.height()-102))
        low=float(y.min());high=float(y.max());span=max(high-low,.05);low-=span*.15;high+=span*.15
        def px(index):return area.left()+(index-lo)/(hi-lo-1)*area.width()
        def py(value):return area.bottom()-(value-low)/(high-low)*area.height()
        p.setPen(QPen(QColor('#e5edef'),1))
        for ms in range(-400,651,100):
            sample=r+ms*FS/1000
            if lo<=sample<hi:
                p.setPen(QPen(QColor('#e5edef'),1))
                xx=px(sample);p.drawLine(QPointF(xx,area.top()),QPointF(xx,area.bottom()))
                p.setPen(QColor('#526a6e'))
                p.drawText(QRectF(xx-25,area.bottom()+6,50,20),Qt.AlignmentFlag.AlignCenter,str(ms))
        p.setPen(QColor('#526a6e'));p.drawText(QRectF(48,8,self.width()-70,26),
            f"D{m['lead']} · amostra {point['r']} · tempo relativo ao QRS (ms) · amplitude estimada")
        path=QPainterPath();path.moveTo(px(lo),py(y[0]))
        for index,value in enumerate(y[1:],lo+1):path.lineTo(px(index),py(value))
        p.setPen(QPen(QColor('#183e42'),1.7));p.drawPath(path)
        for metric,on,off,color,name in [('p_duration','pon','poff','#996800','P'),('qrs_duration','qon','qoff','#295eab','QRS'),('qt','ton','toff','#187963','T')]:
            if m['metrics'][metric]['value'] is None:continue
            indices=[point[k]-a for k in (on,off) if k in point]
            p.setPen(QPen(QColor(color),1.5,Qt.PenStyle.DashLine))
            for value in indices:
                if lo<=value<hi:p.drawLine(QPointF(px(value),area.top()),QPointF(px(value),area.bottom()))
            if len(indices)==2:
                p.setPen(QColor(color));p.drawText(QRectF(px(np.mean(indices))-30,area.top()-23,60,20),Qt.AlignmentFlag.AlignCenter,name)
        p.setPen(QColor('#526a6e'));p.drawText(QRectF(48,self.height()-30,self.width()-60,22),'Filtro de medição: 0,5–80 Hz, fase zero. Pontos aceitos; não são marcações clínicas revisadas.')

    def paint_median(self,p,m):
        median=m.get('median')
        if not median:
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Sem batimentos completos para formar a mediana.');return
        y=np.asarray(median['values_mv']);curves=np.asarray(median['aligned_beats_mv'])
        pt=np.asarray(median['pt_values_mv']);time=np.asarray(median['time_seconds'])*1000
        area=QRectF(48,66,max(1,self.width()-70),max(1,self.height()-120))
        low=float(min(curves.min(),pt.min()));high=float(max(curves.max(),pt.max()));span=max(high-low,.05)
        low-=span*.12;high+=span*.12
        def px(index):return area.left()+index/(len(y)-1)*area.width()
        def py(value):return area.bottom()-(value-low)/(high-low)*area.height()
        for ms in range(-400,651,100):
            if time[0]<=ms<=time[-1]:
                xx=area.left()+(ms-time[0])/(time[-1]-time[0])*area.width()
                p.setPen(QPen(QColor('#e5edef'),1));p.drawLine(QPointF(xx,area.top()),QPointF(xx,area.bottom()))
                p.setPen(QColor('#526a6e'));p.drawText(QRectF(xx-25,area.bottom()+6,50,20),Qt.AlignmentFlag.AlignCenter,str(ms))
        def draw(values,color,width):
            path=QPainterPath();path.moveTo(px(0),py(values[0]))
            for index,value in enumerate(values[1:],1):path.lineTo(px(index),py(value))
            p.setPen(QPen(QColor(color),width));p.drawPath(path)
        for curve in curves:draw(curve,'#c4d4d6',.7)
        draw(y,'#183e42',2)
        draw(pt,'#488979',1.4)
        p.setPen(QColor('#526a6e'))
        name='D'+m['lead'] if m['lead'] in ('I','II','III') else m['lead']
        p.drawText(QRectF(48,6,self.width()-65,24),f"{name} · {median['group_size']} batimentos alinhados · tempo relativo ao QRS (ms)")
        p.drawText(QRectF(48,28,self.width()-65,24),'Medianas suavizadas: QRS (escura), P/T (verde) · limites globais')
        points=m.get('global_fiducials',{})
        flagged=False
        for quality in m.get('technical_quality',{}).get('boundaries',{}).values():
            if quality['status']!='review':continue
            flagged=True
            left,right=quality['range_samples']
            p.fillRect(QRectF(px(left),area.top(),max(2,px(right)-px(left)),area.height()),QColor(190,130,30,35))
        for on,off,color,name in [('pon','poff','#996800','P'),('qon','qoff','#295eab','QRS'),('ton','toff','#187963','T')]:
            indices=[points[key] for key in (on,off) if key in points]
            p.setPen(QPen(QColor(color),1.3,Qt.PenStyle.DashLine))
            for index in indices:p.drawLine(QPointF(px(index),area.top()),QPointF(px(index),area.bottom()))
            if indices:p.drawText(QRectF(px(np.mean(indices))-30,area.top()-20,60,20),Qt.AlignmentFlag.AlignCenter,name)
        p.setPen(QColor('#526a6e'))
        p.drawText(QRectF(48,self.height()-27,self.width()-60,22),'Faixas âmbar: variação dos marcos a revisar entre subconjuntos.' if flagged else 'Marcos calculados nas medianas suavizadas exibidas. Estimativa exploratória.')
