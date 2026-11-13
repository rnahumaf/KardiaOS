"""Capture-scoped human provenance, never automatic electrical calibration."""
import copy,hashlib
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QFormLayout,QComboBox,QCheckBox,
    QLineEdit,QPushButton,QFileDialog,QDialogButtonBox,QMessageBox,QDoubleSpinBox)
from .orientation import DECODER_ID,POSITION_GUIDE,capture_digest,evidence_summary


class EvidenceDialog(QDialog):
    def __init__(self,recording,parent=None):
        super().__init__(parent);self.recording=recording;self.reference=None
        self.setWindowTitle('Evidencias independentes desta captura');self.resize(760,540)
        box=QVBoxLayout(self)
        note=QLabel('Posicao das maos/seta nao comprova o sinal digital nem mV. I+ preserva o bruto; I- multiplica por -1. Isso nao indica R positiva/negativa. Nenhuma evidencia e transferida automaticamente a outra captura.');note.setWordWrap(True);box.addWidget(note)
        state=QLabel(evidence_summary(recording));state.setWordWrap(True);box.addWidget(state)
        form=QFormLayout();self.kind=QComboBox()
        self.kind.addItem('Posicao fisica declarada','physical');self.kind.addItem('Convencao do decoder: referencia pareada revisada','decoder');self.kind.addItem('Amplitude: referencia eletrica revisada','amplitude')
        form.addRow('Registrar separadamente',self.kind)
        self.channel=QComboBox();self.channel.addItems(['I','II']);form.addRow('Canal (nao valida o outro)',self.channel)
        self.sign=QComboBox();self.sign.addItem('Preservar contagens (x+1)',1);self.sign.addItem('Aplicar x-1 pela referencia',-1);form.addRow('Convencao comprovada na referencia',self.sign)
        self.factor=QDoubleSpinBox();self.factor.setDecimals(10);self.factor.setRange(1e-8,1);self.factor.setValue(recording.meta['mv_per_count']);form.addRow('mV/contagem (fator comum do app)',self.factor)
        self.method=QLineEdit();self.method.setMaxLength(300);self.method.setPlaceholderText('Metodo, alinhamento simultaneo e origem; sem dados pessoais');form.addRow('Proveniencia/metodo',self.method)
        self.file=QPushButton('Selecionar artefato local da referencia');self.file.clicked.connect(self.choose);form.addRow('Documento rastreavel',self.file)
        box.addLayout(form)
        self.confirm=QCheckBox();box.addWidget(self.confirm)
        self.warning=QLabel('O programa registra sua revisao humana e o hash do artefato; nao verifica fisicamente a referencia. Nao use QRS positivo ou maior score para escolher o multiplicador.');self.warning.setWordWrap(True);box.addWidget(self.warning)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save);self.buttons.rejected.connect(self.reject);box.addWidget(self.buttons)
        self.kind.currentIndexChanged.connect(self.refresh);self.confirm.toggled.connect(self.enabled);self.method.textChanged.connect(self.enabled);self.refresh()
    def refresh(self):
        kind=self.kind.currentData();self.confirm.setChecked(False)
        self.channel.setEnabled(kind!='physical');self.sign.setEnabled(kind=='decoder');self.factor.setEnabled(kind=='amplitude');self.file.setEnabled(kind!='physical');self.method.setEnabled(kind!='physical')
        self.confirm.setText({'physical':'Declaro maos, seta/logo e contato conforme instrucoes oficiais nesta captura.',
            'decoder':'Revisei referencia pareada da mesma captura e deste canal; confirmei o multiplicador.',
            'amplitude':'Revisei referencia eletrica rastreavel para este canal e fator nesta captura.'}[kind]);self.enabled()
    def enabled(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(self.confirm.isChecked() and (self.kind.currentData()=='physical' or bool(self.reference and len(self.method.text().strip())>=12)))
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'Referencia local revisada')
        if not path:return
        try:
            source=Path(path)
            with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            self.reference=dict(reference_id=source.name,reference_sha256=digest);self.file.setText(source.name);self.enabled()
        except OSError:QMessageBox.warning(self,'Referencia','Nao foi possivel ler o artefato local.')
    def save(self):
        r=self.recording;kind=self.kind.currentData();now=datetime.now().astimezone().isoformat()
        ev=copy.deepcopy(r.meta.get('acquisition_evidence',{}))
        if not isinstance(ev,dict) or ev.get('schema')!=1:ev=dict(schema=1)
        item=dict(scope='capture',capture_sha256=capture_digest(r))
        if kind=='physical':item.update(status='user_declared',declared_at=now,source=POSITION_GUIDE);ev['physical']=item
        else:
            item.update(self.reference,method=self.method.text().strip(),reviewed_at=now)
            if kind=='decoder':item.update(status='reviewed_paired_reference',decoder_id=DECODER_ID,multiplier=self.sign.currentData())
            else:item.update(status='reviewed_amplitude_reference',mv_per_count=self.factor.value());r.meta['mv_per_count']=self.factor.value()
            if not isinstance(ev.get(kind),dict):ev[kind]={}
            ev[kind][self.channel.currentText()]=item
        r.meta['acquisition_evidence']=ev;r._automatic_analysis=None
        self.accept()
