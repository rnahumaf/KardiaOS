"""Full recording viewer, one lead per row, representative templates at true scale."""
import math
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QFont
from PySide6.QtWidgets import QWidget
from .signal import LEADS
PAPER=QColor('#fffcf1');MINOR=QColor('#eedfcb');MAJOR=QColor('#cfb89e');INK=QColor('#153f43')


def trace_path(times, values, left, x_origin, baseline, time_scale, amplitude_scale, continuous=None):
    """Preserve every sample and break; vectorize only the coordinate/validity tests."""
    times=np.asarray(times);values=np.asarray(values)
    xs=x_origin+(times-left)*time_scale;ys=baseline-values*amplitude_scale
    valid=np.isfinite(values)
    if continuous is None:continuous=np.r_[False,np.isclose(np.diff(times),1/300,atol=1e-6,rtol=0)]
    path=QPainterPath();previous=False
    for x,y,ok,join in zip(xs,ys,valid,continuous):
        if ok:
            if previous and join:path.lineTo(float(x),float(y))
            else:path.moveTo(float(x),float(y))
        previous=bool(ok)
    return path


class ECGPaper(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(640,500)
        self.recording=None;self.cursor=0.;self.ppmx=self.ppmy=4.;self.speed=25.;self.gain=10.;self.raw_mode=False
        self.overlay='Pronto para uma nova captura';self.overlay_detail='Toque os dois eletrodos superiores e apoie o inferior na perna esquerda.'
        self.analysis=None;self.display_config=None;self._grid_cache={};self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def display_values(self, first, last):
        from .review_signal import waveform_values
        return waveform_values(self.recording,first,last,raw=self.raw_mode,display_config=self.display_config)

    def current_analysis(self):
        from .automatic_analysis import analysis_key
        a=self.analysis;r=self.recording
        if r is None or not a or a.get('source_key')!=analysis_key(r) or a.get('status')!='completed' or a.get('trace_only'):return {}
        return a

    def current_templates(self):
        return self.current_analysis().get('representative',{})

    def update(self,*args):
        r=self.recording;mode=r.mode_at(self.cursor) if r is not None and r.n else 1
        rows=6 if mode==6 else 1
        # Vertical scrolling preserves the scale, even with a large amplitude envelope.
        height=30.*self.ppmy
        if r is not None and r.n and r.meta.get('start') is not None:
            a=max(0,int(np.searchsorted(r.times[:r.n],self.cursor-15)));b=int(np.searchsorted(r.times[:r.n],self.cursor,side='right'))
            values=self.display_values(a,b)
            for ch in range(6 if mode==6 else 1):
                v=values[:,ch];v=v[np.isfinite(v)]
                if len(v):height=max(height,(max(self.gain,float(v.max())*self.gain)-min(0.,float(v.min())*self.gain)+7)*self.ppmy)
        minimum=max(500,int(rows*(height+10)+24))
        if self.minimumHeight()!=minimum:self.setMinimumHeight(minimum)
        return super().update(*args)

    def paintEvent(self,_):
        p=QPainter(self);p.fillRect(self.rect(),PAPER);r=self.recording
        visible=r is not None and r.n and r.meta.get('start') is not None
        mode=r.mode_at(self.cursor) if visible else 1;displayed=range(6) if mode==6 else (0,);analysis=self.current_analysis();templates=analysis.get('representative',{})
        margin=12.;rh=(self.height()-24)/len(displayed);side=max(24.,.96*self.speed)
        for v in templates.values():
            array=np.asarray(v['raw_values_mv' if self.raw_mode else 'values_mv']);side=max(side,float(np.ptp(array))*self.gain+4)
        boxw=side*self.ppmx;boxh=side*self.ppmy;gap=3*self.ppmx;gutter=max(9.,4+.2*self.speed)*self.ppmx
        reserve=(boxw+gap) if templates else 0.;datax=margin+gutter;endx=self.width()-margin-reserve
        duration=max(.5,(endx-datax)/(self.speed*self.ppmx));start=float(r.meta['start']) if visible else 0.
        right=max(start+duration,self.cursor);left=right-duration
        times=r.times[:r.n] if visible else np.empty(0);first=int(np.searchsorted(times,max(start,left)));last=int(np.searchsorted(times,min(self.cursor,right),side='right'));last=max(first,last)
        values=self.display_values(first,last) if visible else None
        continuous=np.r_[False,np.isclose(np.diff(times[first:last]),1/300,atol=1e-6,rtol=0)]
        def grid(rect):
            key=(rect.width(),rect.height(),self.ppmx,self.ppmy)
            paths=self._grid_cache.get(key)
            if paths is None:
                paths=(QPainterPath(),QPainterPath())
                for axis,size,step in [(0,rect.width(),self.ppmx),(1,rect.height(),self.ppmy)]:
                    for j in range(math.ceil(size/step)+1):
                        path=paths[int(j%5==0)]
                        if axis==0:path.moveTo(j*step,0);path.lineTo(j*step,rect.height())
                        else:path.moveTo(0,j*step);path.lineTo(rect.width(),j*step)
                self._grid_cache[key]=paths
                if len(self._grid_cache)>8:self._grid_cache.pop(next(iter(self._grid_cache)))
            p.save();p.translate(rect.topLeft());p.setRenderHint(QPainter.RenderHint.Antialiasing,False)
            for path,color,width in zip(paths,(MINOR,MAJOR),(.35,.7)):
                p.setPen(QPen(color,width));p.drawPath(path)
            p.restore()
        for row,ch in enumerate(displayed):
            rect=QRectF(datax,14+row*rh,max(1,endx-datax),rh-12);p.save();p.setClipRect(rect);grid(rect);p.restore()
            arr=values[:,ch] if visible else np.array([]);finite=arr[np.isfinite(arr)]
            low=min(0.,float(finite.min())*self.gain) if len(finite) else 0.;high=max(self.gain,float(finite.max())*self.gain) if len(finite) else self.gain
            baseline=rect.center().y()+(low+high)/2*self.ppmy
            p.setRenderHint(QPainter.RenderHint.Antialiasing,True);p.setPen(QPen(INK,1.0))
            pulse=QPainterPath(QPointF(margin,baseline))
            for x,y in [(1,0),(1,-self.gain),(1+.2*self.speed,-self.gain),(1+.2*self.speed,0),(2+.2*self.speed,0)]:pulse.lineTo(margin+x*self.ppmx,baseline+y*self.ppmy)
            p.drawPath(pulse)
            path=trace_path(times[first:last],arr,left,datax,baseline,self.speed*self.ppmx,self.gain*self.ppmy,continuous)
            p.save();p.setClipRect(rect);p.drawPath(path);p.restore()
            from .timing_markers import p_intervals
            p.save();p.setClipRect(rect);p.setPen(QPen(QColor('#8c6e39'),.9));p.setFont(QFont('Segoe UI',7))
            for mark in p_intervals(analysis,['I','II','III','aVR','aVL','aVF'][ch],first,last):
                for k in (mark['on'],mark['off']):
                    value=values[k-first,ch]
                    if np.isfinite(value):
                        xx=datax+(times[k]-left)*self.speed*self.ppmx;yy=baseline-value*self.gain*self.ppmy
                        p.drawLine(QPointF(xx,yy-.7*self.ppmy),QPointF(xx,yy+.7*self.ppmy))
                k=mark['on'];value=values[k-first,ch]
                if np.isfinite(value):p.drawText(QPointF(datax+(times[k]-left)*self.speed*self.ppmx,baseline-value*self.gain*self.ppmy-1.1*self.ppmy),'P')
            p.restore()
            p.setFont(QFont('Segoe UI',9,QFont.Weight.DemiBold));p.drawText(QPointF(datax,rect.top()-2),LEADS[ch])
            template=templates.get(['I','II','III','aVR','aVL','aVF'][ch])
            if template:
                br=QRectF(endx+gap,rect.center().y()-boxh/2,boxw,boxh);p.save();p.setClipRect(br);grid(br);p.restore()
                p.setPen(QPen(QColor('#899c96'),.7));p.drawRect(br);p.setPen(INK);p.setFont(QFont('Segoe UI',8));p.drawText(QPointF(br.left(),br.top()-2),'Mediana')
                t=np.asarray(template['time_seconds']);v=np.asarray(template['raw_values_mv' if self.raw_mode else 'values_mv'])
                xx=br.left()+(br.width()-(t[-1]-t[0])*self.speed*self.ppmx)/2+(t-t[0])*self.speed*self.ppmx
                yy=br.center().y()-(v-(v.min()+v.max())/2)*self.gain*self.ppmy
                path=QPainterPath(QPointF(xx[0],yy[0]))
                for x,y in zip(xx[1:],yy[1:]):path.lineTo(x,y)
                p.setPen(QPen(INK,1.0));p.drawPath(path)
                p.setPen(QPen(QColor('#6e817d'),1))
                for marker in template.get('markers',[]):
                    k=marker['index']
                    if 0<=k<len(xx):p.drawLine(QPointF(xx[k],yy[k]-.8*self.ppmy),QPointF(xx[k],yy[k]+.8*self.ppmy))
        if self.overlay:
            panel=QRectF(20,self.height()/2-48,self.width()-40,96);p.setPen(QPen(QColor('#dfd3bd'),1));p.setBrush(PAPER);p.drawRoundedRect(panel,10,10)
            p.setPen(INK);p.setFont(QFont('Segoe UI',13,QFont.Weight.DemiBold));p.drawText(panel.adjusted(10,8,-10,-40),Qt.AlignmentFlag.AlignCenter,self.overlay)
            p.setFont(QFont('Segoe UI',9));p.drawText(panel.adjusted(18,43,-18,-6),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.overlay_detail)
        p.end()


def screen_geometry(screen):
    size = screen.physicalSize()
    rect = screen.geometry()
    if size.width() > 10 and size.height() > 10:
        return rect.width() / size.width(), rect.height() / size.height()
    fallback = screen.logicalDotsPerInch() / 25.4
    return fallback, fallback


def screen_key(screen):
    return f"{screen.name()}_{screen.size().width()}x{screen.size().height()}_{screen.devicePixelRatio()}"


class Ruler(QWidget):
    def __init__(self, px, py):
        super().__init__()
        self.px, self.py = px, py
        self.setMinimumSize(int(100 * px + 60), int(50 * py + 60))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), PAPER)
        p.setPen(QPen(INK, 1))
        p.drawLine(QPointF(30, 30), QPointF(30 + 100 * self.px, 30))
        p.drawLine(QPointF(30, 30), QPointF(30, 30 + 50 * self.py))
        for i in range(101):
            h = 10 if i % 10 == 0 else 6 if i % 5 == 0 else 3
            p.drawLine(QPointF(30 + i * self.px, 30), QPointF(30 + i * self.px, 30 + h))
        for i in range(51):
            h = 10 if i % 10 == 0 else 6 if i % 5 == 0 else 3
            p.drawLine(QPointF(30, 30 + i * self.py), QPointF(30 + h, 30 + i * self.py))
        p.drawText(QRectF(70, 60, self.width() - 90, 80), Qt.TextFlag.TextWordWrap,
                   "Referências: 100 mm na horizontal e 50 mm na vertical.\nMeça entre os extremos das linhas.")
        p.end()
