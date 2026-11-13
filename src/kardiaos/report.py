"""One vector A4 landscape page, with physical scales and a selected excerpt."""
import io
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from .signal import LEADS


def pdf_bytes(recording, speed=25.0, gain=10.0, raw=False, offset=0.0):
    if not recording.n or recording.meta.get("start") is None:
        raise ValueError("Não há trecho estabilizado para imprimir.")
    if speed not in (25, 50) or gain not in (5, 10, 20):
        raise ValueError("Escala inválida.")
    begin = float(recording.meta["start"])
    end = min(float(recording.meta.get("end") or recording.last_time), recording.last_time)
    if not np.isfinite(offset) or offset < 0 or offset > max(0, end - begin):
        raise ValueError("Início do trecho inválido.")
    t0 = begin + offset
    span = 250 / speed
    t1 = min(t0 + span, end)
    mode = recording.mode_at(t0)
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=landscape(A4), pageCompression=1)
    c.setTitle("KardiaOS - ECG experimental")
    width, height = landscape(A4)
    times = recording.times[:recording.n]
    ecg = recording.lead_values(raw=raw)
    cfg = recording.config
    scale_label = "amplitude declarada pelo usuário" if recording.meta.get("amplitude_verified") else "amplitude estimada, não calibrada"
    c.setFillColor(HexColor("#fffcf1"))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(HexColor("#183e42"))
    c.setFont("Helvetica-Bold", 17)
    c.drawString(10 * mm, height - 14 * mm, "KardiaOS")
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 20 * mm, "ECG experimental de pesquisa | " + ("DADOS SINTÉTICOS" if recording.meta.get("synthetic") else "Captura local"))
    c.drawRightString(width - 10 * mm, height - 13 * mm, f"{speed:g} mm/s | {gain:g} mm/mV | 300 Hz nominais")
    c.drawRightString(width - 10 * mm, height - 19 * mm, scale_label)
    c.setFont("Helvetica", 8)
    c.drawString(10 * mm, height - 27 * mm, f"Trecho {offset:.1f} a {t1 - begin:.1f} s de {end - begin:.1f} s | Página 1/1")
    filters = "Bruto" if raw else f"Filtrado: base {cfg.baseline:g} Hz; passa-baixas {cfg.lowpass:g} Hz; rede {cfg.notch or 'desligada'}"
    c.drawRightString(width - 10 * mm, height - 27 * mm, filters)

    def strip(lead, x, top, w, h, duration, title=None):
        bottom = top - h
        baseline = top - (20 if h < 50 else h / 2)
        for j in range(int(w) + 1):
            c.setStrokeColor(HexColor("#cfb89e" if j % 5 == 0 else "#eedfcb"))
            c.setLineWidth(0.35 if j % 5 == 0 else 0.16)
            c.line((x + j) * mm, bottom * mm, (x + j) * mm, top * mm)
        for j in range(int(h) + 1):
            c.setStrokeColor(HexColor("#cfb89e" if j % 5 == 0 else "#eedfcb"))
            c.setLineWidth(0.35 if j % 5 == 0 else 0.16)
            c.line(x * mm, (bottom + j) * mm, (x + w) * mm, (bottom + j) * mm)
        c.saveState()
        clipping = c.beginPath()
        clipping.rect(x * mm, bottom * mm, w * mm, h * mm)
        c.clipPath(clipping, stroke=0)
        c.setStrokeColor(HexColor("#153f43"))
        c.setLineWidth(0.65)
        pulse = c.beginPath()
        pulse.moveTo((x + 1) * mm, baseline * mm)
        for dx, dy in ((2, 0), (2, gain), (7, gain), (7, 0), (9, 0)):
            pulse.lineTo((x + dx) * mm, (baseline + dy) * mm)
        c.drawPath(pulse)
        first, last = np.searchsorted(times, [t0, min(t0 + duration, end)], side="left")
        path = c.beginPath()
        connected = False
        for k in range(int(first), int(last)):
            value = ecg[k, lead]
            if not np.isfinite(value) or (k > first and times[k] - times[k - 1] > .12):
                connected = False
            if not np.isfinite(value):
                continue
            px = (x + 10 + (times[k] - t0) * speed) * mm
            py = (baseline + value * gain) * mm
            if connected:
                path.lineTo(px, py)
            else:
                path.moveTo(px, py)
            connected = True
        c.drawPath(path)
        c.restoreState()
        c.setFillColor(HexColor("#fffcf1"))
        c.rect((x + .5) * mm, (top - 5) * mm, 23 * mm, 4 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#183e42"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString((x + 1) * mm, (top - 4) * mm, title or LEADS[lead])

    if mode == 6:
        for row, (left, right) in enumerate(((0, 5), (1, 4), (2, 3))):
            strip(left, 10, 175 - row * 35, 135, 35, 125 / speed)
            strip(right, 152, 175 - row * 35, 135, 35, 125 / speed)
        strip(1, 10, 65, 277, 40, span, "D2 contínua")
    else:
        strip(0, 10, 175, 277, 100, span, "D1")
        c.setFont("Helvetica", 10)
        message = "Somente D1 disponível no início deste trecho. As demais derivações não foram geradas." if mode == 1 else "Contato indisponível no início deste trecho. Intervalos sem contato aparecem como lacunas em D1."
        c.drawString(10 * mm, 63 * mm, message)
    c.setFillColor(HexColor("#53635e"))
    c.setFont("Helvetica", 7)
    c.drawString(10 * mm, 17 * mm, "A4 paisagem, tamanho real (100%). Grade: 1 mm / 5 mm. Pulso: 1 mV na escala indicada. Uma folha contém apenas o trecho selecionado.")
    c.drawString(10 * mm, 12 * mm, "Uso experimental. Lacunas indicam contato inadequado ou interrupção. Contatos e polaridade seguem uma interpretação experimental M2.")
    c.drawString(10 * mm, 7 * mm, "Filtros atuais aplicados ao trecho. Valores fora da faixa são recortados; reduza o ganho se necessário. A gravação bruta permanece completa.")
    c.showPage()
    c.save()
    return stream.getvalue()
