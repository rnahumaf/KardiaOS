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
    def __init__(self, demo=False, diagnostic=False):
        super().__init__()
        self.demo, self.diagnostic = demo, diagnostic
        self.setWindowTitle("KardiaOS 0.3.0" + (" — demonstração sintética" if demo else ""))
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app.svg")))
        self.resize(1440, 920)
        self.setMinimumSize(1080, 760)
        self.settings = QSettings("KardiaOS", "KardiaOS")
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
        chart_column.addWidget(self.paper, 1)
        self.paper_note = label("* Amplitude estimada. Grade calculada pelas dimensões físicas do monitor.", "muted", True)
        chart_column.addWidget(self.paper_note)
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
        self.research_button = QPushButton("Avaliação experimental")
        self.research_button.clicked.connect(self.open_research)
        sidebar.addWidget(self.research_button)
        sidebar.addSpacing(8)
        rule = QFrame()
        rule.setObjectName("rule")
        sidebar.addWidget(rule)
        sidebar.addWidget(label("PROCESSAMENTO", "section"))
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
        sidebar.addWidget(label("Uso experimental. Filtros reduzem ruído, mas também alteram a morfologia. O bruto é preservado.", "muted", True))
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
        self.update_buttons()
        self.auto_changed(True)
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
        self.paper_note.setText(f"Grade: {physical.width():.0f} × {physical.height():.0f} mm · {source}. * Amplitude estimada até calibração.")
        self.paper.update()

    def set_state(self, text, detail=None):
        if self.state_label.text() != text and self.diagnostic:
            print(text, flush=True)
        self.state_label.setText(text)
        if detail is not None:
            self.detail.setText(detail)

    def auto_changed(self, checked):
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
        delay = Processor(config).delay_ms()
        self.latency.setText(f"Filtro: ~{delay:.0f} ms a 10 Hz\nBuffer visual: 60 ms. Latência do aparelho não medida.")
        self.paper.update()

    def raw_toggled(self, checked):
        self.paper.raw_mode = checked
        self.paper.update()

    def scales_changed(self):
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
        self.recording = Recording(self.demo)
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
        except Exception as exc:
            QMessageBox.warning(self, "Captura inválida", str(exc))

    def open_research(self):
        if self.live:
            return
        from .research_dialog import ResearchDialog
        ResearchDialog(self.recording, self).exec()

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
        verified = QCheckBox("Escala verificada com referência de amplitude conhecida")
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
            self.load_screen()

    def closeEvent(self, event):
        if self.live:
            self.stop("Janela encerrada pelo usuário")
            event.ignore()
            self.set_state("Finalizando", "Aguarde desconectar e feche a janela novamente para salvar ou descartar.")
        elif self.protect_recording():
            event.accept()
        else:
            event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--research-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KardiaOS")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    if args.research_smoke_test:
        from .smoke import check_research
        check_research()
        return
    if args.smoke_test:
        from .smoke import check
        check()
        return
    window = Window(args.demo, args.diagnostic)
    window.show()
    if args.start:
        QTimer.singleShot(500, window.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
