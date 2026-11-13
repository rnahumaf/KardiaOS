"""Independent evidence states. Legacy flags never establish decoder polarity."""
import hashlib
import json
import math
import re

DECODER_ID = 'kardiaos-m2-le-i16-pairs-no-inversion-v1'
POSITION_GUIDE = 'https://alivecor.zendesk.com/hc/en-us/articles/360025942974'


def capture_digest(recording):
    digest=hashlib.sha256()
    for data in (recording.raw,recording.times):digest.update(data[:recording.n].tobytes())
    return digest.hexdigest()


def _documented(entry,recording):
    return (isinstance(entry,dict) and entry.get('scope')=='capture'
            and entry.get('capture_sha256')==capture_digest(recording)
            and bool(re.fullmatch('[0-9a-f]{64}',str(entry.get('reference_sha256',''))))
            and len(str(entry.get('reference_id','')).strip())>=3
            and len(str(entry.get('method','')).strip())>=12
            and bool(entry.get('reviewed_at')))


def evidence_state(recording):
    if recording is None:
        return dict(physical='unknown',decoder={'I':None,'II':None},amplitude={'I':False,'II':False},legacy=False)
    meta=recording.meta;ev=meta.get('acquisition_evidence',{})
    if not isinstance(ev,dict) or ev.get('schema')!=1:ev={}
    physical=ev.get('physical',{})
    declared=(isinstance(physical,dict) and physical.get('status')=='user_declared'
              and physical.get('scope')=='capture' and physical.get('capture_sha256')==capture_digest(recording)
              and bool(physical.get('declared_at')))
    decoder={};amplitude={}
    for channel in ('I','II'):
        entry=ev.get('decoder',{}).get(channel,{}) if isinstance(ev.get('decoder',{}),dict) else {}
        valid=(_documented(entry,recording) and entry.get('status')=='reviewed_paired_reference'
               and meta.get('decoder_id',DECODER_ID)==DECODER_ID and entry.get('decoder_id')==DECODER_ID and type(entry.get('multiplier')) is int
               and entry['multiplier'] in (-1,1))
        decoder[channel]=entry['multiplier'] if valid else None
        amp=ev.get('amplitude',{}).get(channel,{}) if isinstance(ev.get('amplitude',{}),dict) else {}
        factor=meta.get('mv_per_count')
        amplitude[channel]=bool(_documented(amp,recording) and amp.get('status')=='reviewed_amplitude_reference'
            and isinstance(factor,(int,float)) and math.isfinite(factor) and factor>0 and amp.get('mv_per_count')==factor)
    return dict(physical='user_declared' if declared else 'unknown',decoder=decoder,amplitude=amplitude,
                legacy=bool(meta.get('research_calibration') or meta.get('amplitude_verified')))


def model_channels(key):return ('I',) if key=='ecgfounder_1l' else ('I','II')


def normal_signs(recording,key):
    if recording.meta.get('synthetic'):return (1,)*len(model_channels(key))
    state=evidence_state(recording);values=tuple(state['decoder'][v] for v in model_channels(key))
    return values if all(v is not None for v in values) else None


def evidence_summary(recording):
    state=evidence_state(recording)
    position='declarada pelo usuario' if state['physical']=='user_declared' else 'nao registrada'
    channels='; '.join(k+': '+('referencia revisada, x'+str(v) if v is not None else 'nao validada') for k,v in state['decoder'].items())
    amplitude='; '.join(k+': '+('referencia revisada' if v else 'provisoria') for k,v in state['amplitude'].items())
    return 'Posicao fisica: '+position+'. Decoder '+channels+'. Amplitude '+amplitude+'.'


def amplitude_label(recording):
    state=evidence_state(recording)
    return 'amplitude: referencia revisada por canal' if all(state['amplitude'].values()) else 'amplitude estimada, nao calibrada; evidencia por canal'
