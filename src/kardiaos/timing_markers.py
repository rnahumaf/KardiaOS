"""Actual accepted per-beat P endpoints, never projected onto a median template."""

def p_intervals(analysis,lead,first,last):
    if not analysis or analysis.get('status')!='completed' or analysis.get('trace_only') or lead!=analysis.get('selected_lead'):return []
    root=analysis.get('measurements',{});items=[root]+root.get('additional_leads',[])
    measurement=next((m for m in items if m.get('lead')==lead),{})
    if measurement.get('metrics',{}).get('p_duration',{}).get('value') is None:return []
    # Global markers belong to the median only, never invented on individual beats.
    if measurement.get('global_intervals'):return []
    window=analysis.get('report_window') or {};a=window.get('first_sample',0);b=window.get('last_sample_exclusive',0)
    points=[]
    for beat in measurement.get('fiducials',[]):
        on,off=beat.get('pon'),beat.get('poff')
        if isinstance(on,int) and isinstance(off,int) and max(a,first)<=on<off<min(b,last):
            points.append(dict(on=on,off=off,r=beat['r'],duration_ms=(off-on)/300*1000,lead=lead,method=measurement.get('method_version')))
    return points
