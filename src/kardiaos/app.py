import argparse
from pathlib import Path
import queue
import sys
import time
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSlider,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QStyle, QScrollArea)
from .ble import Stream
from .signal import FS, MV_PER_COUNT, FilterConfig, Processor, contact_ok, automatic_config
from .recording import Recording, save_recording, load_recording
from .paper import ECGPaper, Ruler, screen_geometry, screen_key
from .report import pdf_bytes
from .contact import channel_available
from .processing import EMPIRICAL,REFERENCED,DEFAULT_FILTERS,set_profile,profile_id,profile_label
from .automatic_analysis import analysis_key,cache_analysis,cached_analysis

STYLE = """
QMainWindow, QWidget { background: #f5f7f7; color: #203735; }
QLabel { color: #293d3a; }
QLabel#brand { font-size: 22px; font-weight: 650; letter-spacing: -0.5px; }
QLabel#muted { color: #657672; font-size: 12px; }
QLabel#section { color: #647671; font-size: 11px; font-weight: 650; letter-spacing: 1px; }
QLabel#timer { color: #174d4c; font-size: 36px; font-weight: 500; }
QLabel#status { color: #176a60; font-size: 14px; font-weight: 600; }
QPushButton { background: white; border: 1px solid #d6e0dc; border-radius: 6px; padding: 8px 14px; color: #29423e; }
QPushButton:hover { border-color: #739d92; background: #f6fbf9; }
QPushButton:pressed { background: #e2eee9; }
QPushButton:disabled { color: #a3b0aa; border-color: #e3e8e5; background: #f5f7f6; }
QPushButton#primary { background: #176b5d; color: white; border: 1px solid #176b5d; font-weight: 600; }
QPushButton#primary:hover { background: #125749; }
QPushButton#primary:disabled { background: #9bb9b0; border-color: #9bb9b0; }
QComboBox, QSpinBox, QDoubleSpinBox { border: 1px solid #d6e0dc; border-radius: 5px; background: white; padding: 6px 8px; min-height: 20px; color: #29423e; }
QComboBox:disabled { color: #87988f; background: #eff3f0; }
QCheckBox { spacing: 8px; color: #405a52; }
QCheckBox::indicator { width: 15px; height: 15px; }
QSlider::groove:horizontal { height: 4px; background: #dce5df; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #277969; border-radius: 2px; }
QSlider::handle:horizontal { background: #176b5d; width: 12px; margin: -4px 0; border-radius: 6px; }
QFrame#rule { background: #dce5e0; max-height: 1px; }
QDialog { background: #f7f9f7; }
QScrollBar:vertical { background: #edf2ef; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #b1c5bc; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def label(text, name="", wrap=False):
    item = QLabel(text)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def synthetic_pairs(first, count):
    t = np.arange(first, first + count) / FS
    phase = t % 0.86
    wave = (3600 * np.exp(-((phase - .30) / .013) ** 2)
            - 900 * np.exp(-((phase - .325) / .016) ** 2)
            + 550 * np.exp(-((phase - .50) / .07) ** 2)
            + 270 * np.exp(-((phase - .16) / .04) ** 2))
    noise = 120 * np.sin(2 * np.pi * 60 * t) + 40 * np.sin(2 * np.pi * 87 * t)
    baseline = 600 * np.sin(2 * np.pi * .18 * t)
    return np.column_stack((wave + noise + baseline, .8 * wave - noise + .7 * baseline)).astype(np.int16) & np.int16(-4)


class Window(QMainWindow):
    def __init__(self, demo=False, diagnostic=False, settings=None):
        super().__init__()
        self.demo, self.diagnostic = demo, diagnostic
        self.setWindowTitle("KardiaOS 0.10.0" + (" — demonstração sintética" if demo else ""))
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app.svg")))
        self.resize(1440, 920)
        self.setMinimumSize(1080, 760)
        self.settings = settings if settings is not None else QSettings("KardiaOS", "KardiaOS")
        self._preferences_ready=False
        self._analysis_thread=None;self._analysis_pending=False;self._closing_analysis=False
        self._preview_seen=set();self._preview_pending=None;self._auto_preview=None
        self._analysis_timer=QTimer(self);self._analysis_timer.setSingleShot(True);self._analysis_timer.setInterval(400);self._analysis_timer.timeout.connect(self.start_background_analysis)
        self.recording = None
        self.stream = None
        self.live = self.replaying = self.dirty = False
        self.stable = 0
        self.second_stable = 0
        self.accepted_wall = None
        self.last_auto = 0
        self.last_stats = 0
        self.replay_clock = 0
        self.replay_offset = 0
        self.stop_reason = ""
        self.pending_finish = False
        self.demo_index = 0
        self._screen_key = ""
        self._captured_reason = ""

        shell = QWidget()
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(24, 18, 24, 14)
        outer.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(label("KardiaOS", "brand"))
        header.addWidget(label("  /  Laboratório de ECG", "muted"))
        header.addStretch()
        header.addWidget(label("DADOS SINTÉTICOS" if demo else "PESQUISA  ·  PROCESSAMENTO LOCAL", "section"))
        outer.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)
        self.start_button = QPushButton("Iniciar")
        self.start_button.setObjectName("primary")
        self.start_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Parar")
        self.stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        toolbar.addWidget(self.start_button)
        toolbar.addWidget(self.stop_button)
        toolbar.addSpacing(8)
        toolbar.addWidget(label("Duração", "muted"))
        self.duration = QSpinBox()
        self.duration.setRange(10, 600)
        self.duration.setSingleStep(10)
        self.duration.setValue(30)
        self.duration.setSuffix(" s")
        toolbar.addWidget(self.duration)
        toolbar.addStretch()
        self.open_button = QPushButton("Abrir captura")
        self.open_button.clicked.connect(self.open_recording)
        self.save_button = QPushButton("Salvar bruto")
        self.save_button.clicked.connect(self.save)
        self.pdf_button = QPushButton("Exportar PDF")
        self.pdf_button.clicked.connect(self.export_pdf)
        self.print_button = QPushButton("Imprimir")
        self.print_button.clicked.connect(self.print_report)
        for button in (self.open_button, self.save_button, self.pdf_button, self.print_button):
            toolbar.addWidget(button)
        outer.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(20)
        chart_column = QVBoxLayout()
        chart_top = QHBoxLayout()
        self.lead_title = label("AGUARDANDO CONTATOS", "section")
        chart_top.addWidget(self.lead_title)
        chart_top.addStretch()
        self.scale_label = label("25 mm/s  ·  10 mm/mV*", "muted")
        chart_top.addWidget(self.scale_label)
        chart_column.addLayout(chart_top)
        self.paper = ECGPaper()
        self.paper_scroll=QScrollArea();self.paper_scroll.setWidgetResizable(True);self.paper_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.paper_scroll.setWidget(self.paper);chart_column.addWidget(self.paper_scroll,1)
        self.paper_note = label("* Amplitude estimada. Grade calculada pelas dimensões físicas do monitor.", "muted", True)
        chart_column.addWidget(self.paper_note)
        self.analysis_summary=label("", "muted", True);self.analysis_summary.hide();chart_column.addWidget(self.analysis_summary)
        playback = QHBoxLayout()
        self.play_button = QPushButton("Reproduzir")
        self.play_button.clicked.connect(self.replay)
        playback.addWidget(self.play_button)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderMoved.connect(self.scrub)
        playback.addWidget(self.seek, 1)
        self.position_label = label("00:00 / 00:00", "muted")
        playback.addWidget(self.position_label)
        chart_column.addLayout(playback)
        body.addLayout(chart_column, 1)

        side = QWidget()
        side.setFixedWidth(244)
        sidebar = QVBoxLayout(side)
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(10)
        sidebar.addWidget(label("AQUISIÇÃO", "section"))
        self.state_label = label("Pronto para iniciar", "status", True)
        sidebar.addWidget(self.state_label)
        self.timer_label = label("00:00.0", "timer")
        sidebar.addWidget(self.timer_label)
        self.detail = label("Feche o Kardia no celular. Mantenha os dedos nos eletrodos superiores e o inferior na perna esquerda.", "muted", True)
        sidebar.addWidget(self.detail)
        self.metrics = label("Nenhuma amostra recebida", "muted", True)
        sidebar.addWidget(self.metrics)
        self.research_button = QPushButton("Análise automática")
        self.research_button.clicked.connect(self.open_research)
        sidebar.addWidget(self.research_button)
        self.autorun=QCheckBox("Analisar ao concluir");self.autorun.setChecked(self.settings.value("research/autorun",True,type=bool));sidebar.addWidget(self.autorun)
        sidebar.addSpacing(8)
        rule = QFrame()
        rule.setObjectName("rule")
        sidebar.addWidget(rule)
        sidebar.addWidget(label("PROCESSAMENTO", "section"))
        self.profile_combo=QComboBox()
        self.profile_combo.addItem("Pesquisa · mV estimados",EMPIRICAL)
        self.profile_combo.addItem("Referência por canal",REFERENCED)
        self.profile_combo.setCurrentIndex(max(0,self.profile_combo.findData(self.settings.value('research/profile',EMPIRICAL))))
        sidebar.addWidget(self.profile_combo)
        self.auto = QCheckBox("Ajuste automático")
        self.auto.setChecked(True)
        self.auto.toggled.connect(self.auto_changed)
        sidebar.addWidget(self.auto)
        self.base = self.combo(sidebar, "Linha de base", [("Preservar", 0), ("0,05 Hz · leve", .05), ("0,5 Hz · padrão", .5), ("1 Hz · intensa", 1)], 2)
        self.smooth = self.combo(sidebar, "Suavização", [("Desligada", 0), ("25 Hz · intensa", 25), ("40 Hz · padrão", 40), ("80 Hz · leve", 80)], 2)
        self.notch = self.combo(sidebar, "Interferência elétrica", [("Desligada", 0), ("50 Hz", 50), ("60 Hz", 60)], 2)
        for combo in (self.base, self.smooth, self.notch):
            combo.currentIndexChanged.connect(self.manual_filter)
        self.raw_check = QCheckBox("Comparar com o bruto")
        self.raw_check.toggled.connect(self.raw_toggled)
        sidebar.addWidget(self.raw_check)
        self.latency = label("Filtros causais · buffer visual de 60 ms", "muted", True)
        sidebar.addWidget(self.latency)
        sidebar.addSpacing(6)
        scale_row = QHBoxLayout()
        self.speed = QComboBox()
        for value in (25, 50):
            self.speed.addItem(f"{value} mm/s", value)
        self.gain = QComboBox()
        for value in (5, 10, 20):
            self.gain.addItem(f"{value} mm/mV", value)
        self.gain.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self.scales_changed)
        self.gain.currentIndexChanged.connect(self.scales_changed)
        scale_row.addWidget(self.speed)
        scale_row.addWidget(self.gain)
        sidebar.addLayout(scale_row)
        self.cal_button = QPushButton("Tela e calibração")
        self.cal_button.clicked.connect(self.calibrate)
        sidebar.addWidget(self.cal_button)
        sidebar.addStretch(1)
        sidebar.addWidget(label("Detalhes do perfil em Análise > Detalhes técnicos.", "muted", True))
        side_scroll = QScrollArea()
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setFixedWidth(260)
        side_scroll.setWidget(side)
        body.addWidget(side_scroll)
        outer.addLayout(body, 1)
        self.footer = label("KardiaMobile 6L  /  M2 · 300 Hz nominais  /  Sem envio de dados", "muted")
        outer.addWidget(self.footer)
        self.tick_timer = QTimer(self)
        self.tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(16)
        for combo,key,default in ((self.base,'filters/baseline',.5),(self.smooth,'filters/lowpass',40),(self.notch,'filters/notch',60),(self.speed,'display/speed',25),(self.gain,'display/gain',10)):
            combo.blockSignals(True);combo.setCurrentIndex(max(0,combo.findData(float(self.settings.value(key,default)))));combo.blockSignals(False)
        self.auto.blockSignals(True);self.auto.setChecked(self.settings.value('filters/auto',False,type=bool));self.auto.blockSignals(False)
        self.duration.setValue(int(self.settings.value('capture/duration',30)))
        self.raw_check.setChecked(self.settings.value('display/raw',False,type=bool))
        self._preferences_ready=True
        self.profile_combo.currentIndexChanged.connect(self.profile_changed)
        self.autorun.toggled.connect(self.autorun_changed)
        self.duration.valueChanged.connect(self.save_preferences)
        self.scales_changed();self.update_buttons()
        self.auto_changed(self.auto.isChecked())
        QTimer.singleShot(100, self.bind_screen)

    def combo(self, layout, title, items, index):
        layout.addWidget(label(title, "muted"))
        combo = QComboBox()
        for text, data in items:
            combo.addItem(text, data)
        combo.setCurrentIndex(index)
        layout.addWidget(combo)
        return combo

    def bind_screen(self):
        if self.windowHandle():
            self.windowHandle().screenChanged.connect(self.load_screen)
        self.load_screen()

    def load_screen(self, *_):
        screen = self.screen()
        key = screen_key(screen)
        self._screen_key = key
        x, y = screen_geometry(screen)
        self.paper.ppmx = float(self.settings.value(f"screens/{key}/x", x))
        self.paper.ppmy = float(self.settings.value(f"screens/{key}/y", y))
        source = "ajustada com régua" if self.settings.value(f"screens/{key}/manual", False, type=bool) else "dimensões informadas pelo monitor"
        physical = screen.physicalSize()
        self.paper_note.setText(f"Grade física: {source} · amplitudes estimadas pelo perfil ativo.")
        self.paper.update()

    def set_state(self, text, detail=None):
        if self.state_label.text() != text and self.diagnostic:
            print(text, flush=True)
        self.state_label.setText(text)
        if detail is not None:
            self.detail.setText(detail)

    def auto_changed(self, checked):
        self.save_preferences()
        if not hasattr(self, "base"):
            return
        for combo in (self.base, self.smooth, self.notch):
            combo.setEnabled(not checked)
        if checked and self.recording and self.recording.n >= FS * 2:
            channels = 2 if self.recording.mode_at() == 6 else 1
            self.apply_filters(automatic_config(self.recording.raw[max(0, self.recording.n - 4 * FS):self.recording.n, :channels]))

    def manual_filter(self):
        if not self.auto.isChecked():
            self.apply_filters(FilterConfig(self.base.currentData(), self.smooth.currentData(), self.notch.currentData()))

    def apply_filters(self, config):
        for combo, value in ((self.base, config.baseline), (self.smooth, config.lowpass), (self.notch, config.notch)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        if self.recording and self.recording.config != config:
            self.recording.configure(config)
            self.dirty = True
            self.schedule_analysis()
        self.save_preferences()
        delay = Processor(config).delay_ms()
        self.latency.setText(f"Filtro: ~{delay:.0f} ms a 10 Hz\nBuffer visual: 60 ms. Latência do aparelho não medida.")
        self.paper.update()

    def raw_toggled(self, checked):
        self.paper.raw_mode = checked
        self.save_preferences()
        self.paper.update()

    def scales_changed(self):
        self.save_preferences()
        self.paper.speed, self.paper.gain = self.speed.currentData(), self.gain.currentData()
        self.scale_label.setText(f"{self.paper.speed:g} mm/s  ·  {self.paper.gain:g} mm/mV*")
        self.paper.update()

    def protect_recording(self):
        if not self.dirty or not self.recording or not self.recording.n:
            return True
        choice = QMessageBox.question(self, "Preservar captura", "Salvar os dados brutos antes de continuar?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def start(self):
        if self.live or not self.protect_recording():
            return
        self.replaying = False
        self._analysis_timer.stop()
        if self._analysis_thread is not None and self._analysis_thread.isRunning():self._analysis_thread.requestInterruption()
        self.analysis_summary.hide()
        self.recording = Recording(self.demo)
        set_profile(self.recording,self.profile_combo.currentData())
        self.recording.meta["duration_requested"] = self.duration.value()
        self.recording.meta["mv_per_count"] = float(self.settings.value("amplitude/factor", MV_PER_COUNT))
        self.recording.meta["amplitude_verified"] = self.settings.value("amplitude/verified", False, type=bool)
        self.recording.configure(FilterConfig(self.base.currentData(), self.smooth.currentData(), self.notch.currentData()))
        self.paper.recording = self.recording
        self.paper.cursor = 0
        self.paper.overlay = "Aguardando o sinal"
        self.paper.overlay_detail = "O traçado aparece após a verificação inicial de contato e estabilidade."
        self.live = True
        self.dirty = False
        self.stable = 0
        self.second_stable = 0
        self.accepted_wall = None
        self.pending_finish = False
        self.stop_reason = ""
        self.demo_index = 0
        self.demo_clock = time.monotonic()
        self.last_auto = self.last_stats = 0
        self.timer_label.setText("00:00.0")
        self.set_state("Procurando o 6L", "Dois contatos superiores: D1. Apoie também o eletrodo inferior na perna esquerda para seis derivações.")
        if not self.demo:
            self.stream = Stream()
            self.stream.start()
        self.update_buttons()

    def accept_samples(self, arrived, samples):
        r = self.recording
        if not self.live or self.pending_finish:
            return
        old_n = r.n
        gap = r.last_arrival is not None and arrived - r.last_arrival > .12
        r.append(arrived, samples)
        self.dirty = True
        if gap:
            self.stable = 0
            self.second_stable = 0
        window = r.raw[max(0, r.n - FS):r.n]
        available = channel_available(r.raw[old_n:r.n])
        good = bool(available[:, 0].all()) and contact_ok(window[:, :1])
        second_good = bool(available[:, 1].all()) and contact_ok(window[:, 1:])
        self.second_stable = self.second_stable + len(samples) if second_good and not gap else 0
        if self.second_stable < FS // 2:
            r.lead_modes[old_n:r.n] = np.minimum(r.lead_modes[old_n:r.n], 1)
        self.stable = self.stable + len(samples) if good and not gap else 0
        ready = r.n >= FS and self.stable >= FS // 2
        description = "Seis derivações disponíveis. Mantenha os três contatos." if r.mode_at() == 6 else "Somente D1 disponível. Para seis derivações, confira o contato inferior com a perna esquerda."
        if r.meta["start"] is None:
            self.set_state("Estabilizando o sinal", "Verificando contato e descartando o transiente inicial da exibição.")
            if ready:
                r.meta["start"] = float(r.times[old_n])
                self.accepted_wall = time.monotonic()
                self.paper.overlay = ""
                self.set_state("Gravando", description)
        if r.meta["start"] is not None:
            r.quality[old_n:r.n] = ready
            if not ready:
                self.set_state("Ajuste o contato", "O trecho capturado será preservado. O intervalo ruim ficará marcado como lacuna.")
            else:
                self.set_state("Gravando", description)
        if self.auto.isChecked() and r.n >= FS * 2 and time.monotonic() - self.last_auto > 4:
            channels = 2 if r.mode_at() == 6 else 1
            self.apply_filters(automatic_config(r.raw[max(0, r.n - FS * 4):r.n, :channels]))
            self.last_auto = time.monotonic()

    def stop(self, reason="Interrompida pelo usuário"):
        if not self.live or self.pending_finish:
            return
        self.stop_reason = reason
        self.pending_finish = True
        self.stop_button.setEnabled(False)
        if self.stream and self.stream.thread.is_alive():
            self.stream.stop()
            self.set_state("Finalizando", "Desconectando e preservando os dados capturados.")
        else:
            self.finish()

    def finish(self):
        r = self.recording
        self.live = self.pending_finish = False
        if r and r.n:
            if self.stop_reason == "Duração programada concluída" and r.meta.get("start") is not None:
                end = float(r.meta["start"]) + r.meta["duration_requested"]
                r.n = int(np.searchsorted(r.times[:r.n], end, side="right"))
            r.meta["end"] = r.last_time
            r.meta["reason"] = self.stop_reason or "Conexão encerrada"
            self.paper.cursor = r.last_time
            if r.meta["start"] is not None:
                self.paper.overlay = ""
                self.set_state("Captura preservada", r.meta["reason"] + ". Salve o bruto para reproduzir depois.")
            else:
                self.paper.overlay = "Não houve trecho estável"
                self.paper.overlay_detail = "Os dados recebidos podem ser salvos para investigação."
                self.set_state("Sem trecho estável", self.stop_reason or "Confira os três contatos e tente novamente.")
        else:
            self.paper.overlay = "Nenhum sinal recebido"
            self.paper.overlay_detail = "Toque os eletrodos e clique em Iniciar para tentar novamente."
            self.set_state("Captura não iniciada", self.stop_reason or "6L não encontrado.")
        self.update_buttons()
        self.schedule_analysis()

    def tick(self):
        now = time.monotonic()
        if self.live and self.demo and not self.pending_finish:
            target = int((now - self.demo_clock) * FS)
            count = min(target - self.demo_index, 90)
            if count > 0:
                self.accept_samples(now, synthetic_pairs(self.demo_index, count))
                self.demo_index += count
        if self.stream:
            for _ in range(512):
                try:
                    kind, data = self.stream.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "samples":
                    self.accept_samples(*data)
                elif kind == "status" and self.live and not self.pending_finish:
                    self.detail.setText(data)
                elif kind == "error" and self.live:
                    self.stop_reason = data
                    self.detail.setText(data)
                elif kind == "done" and self.live:
                    self.finish()
            if self.stream.overflow and self.live:
                self.stop_reason = "Fluxo excedeu a capacidade de processamento"
                if not self.stream.thread.is_alive():
                    self.finish()
        r = self.recording
        if self.live and r and r.n:
            silence = now - r.last_arrival
            if silence > .5 and r.meta["start"] is not None and not self.pending_finish:
                self.set_state("Ajuste o contato", "Sem novas amostras. O cronômetro continua; os dados anteriores permanecem preservados.")
            if self.accepted_wall is not None:
                elapsed = now - self.accepted_wall
                self.timer_label.setText(self.clock(min(elapsed, self.duration.value()), True))
                self.paper.cursor = max(float(r.meta["start"]), r.last_time + min(silence, .2) - .06)
                if elapsed >= self.duration.value() and not self.pending_finish:
                    self.stop("Duração programada concluída")
            if now - self.last_stats >= 1:
                self.metrics.setText(f"{r.n:,} pares de amostras\n{r.gaps} interrupção(ões) de transporte")
                if self.diagnostic:
                    print(f"Amostras={r.n}; aceitas={int(r.quality[:r.n].sum())}; lacunas={r.gaps}; estado={self.state_label.text()}", flush=True)
                self.last_stats = now
        if self.replaying and r:
            self.paper.cursor = self.replay_offset + now - self.replay_clock
            if self.paper.cursor >= r.last_time:
                self.paper.cursor = r.last_time
                self.replaying = False
                self.play_button.setText("Reproduzir")
        if r and r.meta.get("start") is not None:
            mode = r.mode_at(self.paper.cursor)
            self.lead_title.setText("SEIS DERIVAÇÕES" if mode == 6 else "D1 · UMA DERIVAÇÃO" if mode == 1 else "AJUSTE OS CONTATOS SUPERIORES")
            begin = float(r.meta["start"])
            length = max(.001, r.last_time - begin)
            elapsed = max(0, self.paper.cursor - begin)
            if not self.seek.isSliderDown():
                self.seek.setValue(int(min(1, elapsed / length) * 1000))
            self.position_label.setText(f"{self.clock(elapsed)} / {self.clock(length)}")
        if self.screen() and self._screen_key and screen_key(self.screen()) != self._screen_key:
            self.load_screen()
        # Paused records do not need 60 identical paints per second. Explicit
        # changes to filters, scale, analysis or screen already call update().
        visual_state=(id(r),r.n if r else 0,self.paper.cursor,self.live)
        if visual_state!=getattr(self,'_last_visual_state',None):
            self._last_visual_state=visual_state
            self.paper.update()

    @staticmethod
    def clock(seconds, decimal=False):
        minutes, seconds = divmod(max(0, seconds), 60)
        return f"{int(minutes):02d}:{seconds:04.1f}" if decimal else f"{int(minutes):02d}:{int(seconds):02d}"

    def update_buttons(self):
        have = bool(self.recording and self.recording.n)
        stable = have and self.recording.meta.get("start") is not None
        self.start_button.setEnabled(not self.live)
        self.stop_button.setEnabled(self.live and not self.pending_finish)
        self.duration.setEnabled(not self.live)
        self.open_button.setEnabled(not self.live)
        self.save_button.setEnabled(have and not self.live)
        self.research_button.setEnabled(not self.live)
        self.pdf_button.setEnabled(stable and not self.live)
        self.print_button.setEnabled(stable and not self.live)
        self.play_button.setEnabled(stable and not self.live)
        self.seek.setEnabled(stable and not self.live)
        self.cal_button.setEnabled(not self.live)
        self.profile_combo.setEnabled(not self.live)

    def replay(self):
        if not self.recording or self.live:
            return
        self.replaying = not self.replaying
        if self.replaying:
            start = float(self.recording.meta["start"])
            self.replay_offset = self.paper.cursor if self.paper.cursor < self.recording.last_time - .1 else start
            self.replay_clock = time.monotonic()
        self.play_button.setText("Pausar" if self.replaying else "Reproduzir")

    def scrub(self, value):
        r = self.recording
        if not r or r.meta.get("start") is None or self.live:
            return
        start = float(r.meta["start"])
        self.paper.cursor = start + (r.last_time - start) * value / 1000
        self.replay_offset, self.replay_clock = self.paper.cursor, time.monotonic()

    def save(self):
        if not self.recording or not self.recording.n:
            return False
        filename, _ = QFileDialog.getSaveFileName(self, "Salvar dados brutos", "captura.kardia", "Captura KardiaOS (*.kardia)")
        if not filename:
            return False
        try:
            save_recording(filename, self.recording)
            self.dirty = False
            self.set_state("Dados brutos salvos", "A captura inclui amostras originais, tempos, qualidade e parâmetros de processamento.")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return False

    def open_recording(self):
        if not self.protect_recording():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir dados brutos", "", "Captura KardiaOS (*.kardia)")
        if not filename:
            return
        try:
            recording = load_recording(filename)
            self.recording = recording
            stored=recording.meta.get('operational_profile')
            identifier=stored['id'] if stored else self.profile_combo.currentData()
            set_profile(recording,identifier)
            self.profile_combo.blockSignals(True);self.profile_combo.setCurrentIndex(self.profile_combo.findData(identifier));self.profile_combo.blockSignals(False)
            if not stored and identifier==EMPIRICAL:recording.configure(FilterConfig(self.base.currentData(),self.smooth.currentData(),self.notch.currentData()))
            self.paper.recording = recording
            self.paper.cursor = recording.last_time
            self.paper.overlay = "" if recording.meta.get("start") is not None else "Captura sem trecho estabilizado"
            self.apply_filters(recording.config)
            self.dirty = False
            self.replaying = False
            self.set_state("Captura carregada", "Dados sintéticos." if recording.meta.get("synthetic") else "Reprodução local. Você pode ajustar os filtros sem alterar o bruto.")
            self.metrics.setText(f"{recording.n:,} pares de amostras\n{recording.gaps} interrupção(ões)")
            self.timer_label.setText(self.clock(recording.last_time - float(recording.meta.get("start") or 0), True))
            self.update_buttons()
            self.schedule_analysis()
        except Exception as exc:
            QMessageBox.warning(self, "Captura inválida", str(exc))

    def save_preferences(self,*_):
        if not self._preferences_ready or self.demo:return
        for key,value in [('research/profile',self.profile_combo.currentData()),('research/autorun',self.autorun.isChecked()),
            ('filters/auto',self.auto.isChecked()),('filters/baseline',self.base.currentData()),('filters/lowpass',self.smooth.currentData()),('filters/notch',self.notch.currentData()),
            ('display/speed',self.speed.currentData()),('display/gain',self.gain.currentData()),('display/raw',self.raw_check.isChecked()),('capture/duration',self.duration.value())]:self.settings.setValue(key,value)

    def profile_changed(self,*_):
        self.save_preferences()
        if self.recording is not None:
            set_profile(self.recording,self.profile_combo.currentData());self.dirty=True;self.paper.update();self.schedule_analysis()

    def autorun_changed(self,*_):
        self.save_preferences()
        if not self.autorun.isChecked():
            self._analysis_timer.stop();self._analysis_pending=False
            if self._analysis_thread is not None and self._analysis_thread.isRunning():self._analysis_thread.requestInterruption()
        else:self.schedule_analysis()

    def schedule_analysis(self):
        if self.live or self.demo or not self.autorun.isChecked():return
        if self.recording is None or self.recording.meta.get('start') is None:return
        self.paper.analysis=None;self.paper.update();self._preview_pending=None
        self.analysis_summary.setText('Preparando análise local.');self.analysis_summary.show();self._analysis_timer.start()

    def start_background_analysis(self):
        if self.live or self.recording is None or self._closing_analysis or not self.autorun.isChecked():return
        if self._analysis_thread is not None and self._analysis_thread.isRunning():
            self._analysis_pending=True;self._analysis_thread.requestInterruption();return
        self._analysis_pending=False;r=self.recording
        previous=cached_analysis(r)
        if previous:self.background_result(r,previous);return
        from .analysis_dialog import AutomaticThread
        self._analysis_thread=AutomaticThread(r,self)
        self._analysis_thread.result_ready.connect(lambda value,record=r:self.background_result(record,value))
        self._analysis_thread.finished.connect(self.background_finished)
        self.analysis_summary.setText('Analisando o registro em segundo plano…');self.analysis_summary.show();self._analysis_thread.start()

    def background_result(self,record,result):
        if self.recording is not record:return
        if cache_analysis(record,result):
            self.paper.analysis=result;self.paper.update()
            lines=[]
            if not result.get('trace_only') and result.get('reportable'):
                from .report import measurement_line
                window=result['report_window'];start=window['offset_seconds'];stop=start+window['duration_seconds']
                lines=[f'Trecho do laudo: {start:g}–{stop:g} s',result.get('qtc_label','QTc: erro na estimativa'),measurement_line(result)]
                if result.get('classification'):lines.append(result['classification']['summary'])
                lines.extend(item['label']+' · '+item['model'] for item in result.get('hypotheses',[])[:3])
            self.analysis_summary.setText('\n'.join(lines) or result.get('reason') or 'Somente traçado; qualidade insuficiente para análise.')
            self.analysis_summary.show();self._preview_pending=(record,result,self)
            self.latency.setText('Revisão: filtros de fase zero.\nAo vivo: filtros causais e buffer de 60 ms.')
            if self._analysis_thread is None or not self._analysis_thread.isRunning():QTimer.singleShot(0,self.open_pending_preview)
        elif result.get('status')=='cancelled':self.analysis_summary.setText('Análise interrompida.')
        else:self.analysis_summary.setText(result.get('reason','Processamento alterado; reavaliando o registro.'))

    def background_finished(self):
        if self._closing_analysis:self.close()
        elif self._analysis_pending:self._analysis_timer.start()
        else:QTimer.singleShot(0,self.open_pending_preview)

    def auto_preview_result(self,record,result,preview_parent=None):
        self.background_result(record,result)
        if self._preview_pending is not None:self._preview_pending=(record,result,preview_parent or self)

    def open_pending_preview(self):
        pending=self._preview_pending;self._preview_pending=None
        if pending is None or self.live or self._closing_analysis or self._analysis_pending:return
        record,result,preview_parent=pending
        if self.recording is not record or result.get('source_key')!=analysis_key(record) or not result.get('reportable') or result.get('status')!='completed':return
        token=(result['source_key'],result.get('run_id'))
        if token in self._preview_seen:return
        if self._auto_preview is not None and self._auto_preview.isVisible():
            self._preview_pending=pending;return
        from .preview import PrintPreview
        preview=PrintPreview(record,self.speed.currentData(),self.gain.currentData(),self.raw_check.isChecked(),preview_parent,analysis=result)
        self._preview_seen.add(token);self._auto_preview=preview
        preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        preview.finished.connect(self.auto_preview_closed)
        preview.show()

    def auto_preview_closed(self,*_):
        self._auto_preview=None;QTimer.singleShot(0,self.open_pending_preview)

    def open_research(self):
        if self.live:
            return
        from .analysis_dialog import AutomaticAnalysisDialog
        AutomaticAnalysisDialog(self.recording, self).exec()

    def report(self):
        return pdf_bytes(self.recording, self.speed.currentData(), self.gain.currentData(), self.raw_check.isChecked())

    def export_pdf(self):
        self.print_report()

    def print_report(self):
        from .preview import PrintPreview
        try:
            preview = PrintPreview(self.recording, self.speed.currentData(),
                                   self.gain.currentData(), self.raw_check.isChecked(), self)
            preview.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Falha na prévia", str(exc))

    def calibrate(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tela e calibração")
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Escala física do monitor", "brand"))
        screen = self.screen()
        physical = screen.physicalSize()
        layout.addWidget(label(f"{screen.name()} · {physical.width():.0f} × {physical.height():.0f} mm informados pelo monitor.\nA grade usa essas dimensões e acompanha o monitor ao mover a janela.", "muted", True))
        layout.addWidget(Ruler(self.paper.ppmx, self.paper.ppmy))
        form = QFormLayout()
        horizontal, vertical = QDoubleSpinBox(), QDoubleSpinBox()
        for spin, value in ((horizontal, 100), (vertical, 50)):
            spin.setRange(10, 250)
            spin.setDecimals(1)
            spin.setValue(value)
            spin.setSuffix(" mm")
        form.addRow("Horizontal medido com régua", horizontal)
        form.addRow("Vertical medido com régua", vertical)
        manual = QCheckBox("Aplicar medidas conferidas com régua")
        form.addRow(manual)
        factor = QDoubleSpinBox()
        factor.setDecimals(9)
        factor.setRange(.00000001, .1)
        factor.setSingleStep(.000001)
        factor.setValue(float(self.settings.value("amplitude/factor", MV_PER_COUNT)))
        verified = QCheckBox("Declaracao legada de amplitude; referencia por canal em Analise > Referencia")
        verified.setChecked(self.settings.value("amplitude/verified", False, type=bool))
        form.addRow("mV por contagem digital", factor)
        form.addRow(verified)
        layout.addLayout(form)
        layout.addWidget(label("O valor inicial de amplitude é uma inferência das especificações do 6L. Não equivale a calibração. A polaridade também requer validação externa.", "muted", True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if manual.isChecked():
                self.settings.setValue(f"screens/{self._screen_key}/x", self.paper.ppmx * 100 / horizontal.value())
                self.settings.setValue(f"screens/{self._screen_key}/y", self.paper.ppmy * 50 / vertical.value())
                self.settings.setValue(f"screens/{self._screen_key}/manual", True)
            self.settings.setValue("amplitude/factor", factor.value())
            self.settings.setValue("amplitude/verified", verified.isChecked())
            if self.recording:
                self.recording.meta.update(mv_per_count=factor.value(), amplitude_verified=verified.isChecked())
                self.dirty = True
                self.schedule_analysis()
            self.load_screen()

    def closeEvent(self, event):
        self._analysis_timer.stop()
        if not self.live and self._analysis_thread is not None and self._analysis_thread.isRunning():
            self._closing_analysis=True;self._analysis_thread.requestInterruption();event.ignore();return
        if self.live:
            self.stop("Janela encerrada pelo usuário")
            event.ignore()
            self.set_state("Finalizando", "Aguarde desconectar e feche a janela novamente para salvar ou descartar.")
        elif self.protect_recording():
            event.accept()
        else:
            self._closing_analysis=False
            event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--validation-output", help=argparse.SUPPRESS)
    parser.add_argument("--automatic-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--research-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KardiaOS")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    if args.smoke_test or args.research_smoke_test or args.automatic_smoke_test:
        import json
        from . import __version__
        try:
            from .smoke import check, check_research, check_automatic
            selected = check_automatic if args.automatic_smoke_test else check_research if args.research_smoke_test else check
            details = selected() or {}
            outcome = dict(status="passed", version=__version__, synthetic_only=True, **details)
        except Exception as exc:
            outcome = dict(status="failed", version=__version__, error=type(exc).__name__ + ": " + str(exc), synthetic_only=True)
        # Offscreen smoke jobs do not enter app.exec(); dispose their widgets
        # while QApplication still owns the Qt runtime, including deferred objects.
        from PySide6.QtCore import QCoreApplication,QEvent
        app.processEvents()
        for widget in app.topLevelWidgets():widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        if args.validation_output:
            Path(args.validation_output).write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(0 if outcome["status"] == "passed" else 1)
    window = Window(args.demo, args.diagnostic)
    window.show()
    if args.start:
        QTimer.singleShot(500, window.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
