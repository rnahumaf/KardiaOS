# Dependências e protocolo

O ícone usa o traçado Activity de Lucide, com fundo e cores adaptados. A licença
ISC/MIT do projeto acompanha `src/kardiaos/assets/LUCIDE-LICENSE`.
Fonte: https://github.com/lucide-icons/lucide/blob/main/icons/activity.svg

A seta dos seletores usa Chevron Down da mesma coleção e licença, com cor adaptada.
Fonte: https://github.com/lucide-icons/lucide/blob/main/icons/chevron-down.svg

A marca dos checkboxes usa Check da mesma coleção e licença, com cor e espessura adaptadas.
Fonte: https://github.com/lucide-icons/lucide/blob/main/icons/check.svg

O protocolo de interoperabilidade M2 foi implementado a partir das evidências de
ShaneBreazeale/kardia-rs, disponível sob MIT ou Apache-2.0:
https://github.com/ShaneBreazeale/kardia-rs

As dependências são distribuídas sem modificações. Seus avisos de licença estão
em `licenses` na distribuição. Qt/PySide6 é usado sob LGPLv3; DLLs permanecem
separadas e podem ser substituídas por versões compatíveis. O código-fonte do
KardiaOS e as instruções para reconstruir o executável acompanham a distribuição.
Não se impõem restrições adicionais à modificação ou à engenharia reversa para
depuração dessas modificações.

Fontes das dependências:

- Qt/PySide6: https://code.qt.io/cgit/pyside/pyside-setup.git/ e https://code.qt.io/
- NumPy: https://github.com/numpy/numpy
- SciPy: https://github.com/scipy/scipy
- Bleak: https://github.com/hbldh/bleak
- ReportLab: https://hg.reportlab.com/hg-public/reportlab/
- Python: https://www.python.org/downloads/source/
- PyInstaller: https://github.com/pyinstaller/pyinstaller

KardiaMobile e AliveCor são marcas de seus respectivos titulares. KardiaOS não
é afiliado nem endossado por esses fabricantes.


## Modelos experimentais opcionais

ECGFounder: MIT, Copyright (c) 2025 PKUDigitalHealth. Arquitetura original em
`src/kardiaos/vendor/ecgfounder/net1d.py`, licença adjacente. Fonte fixada:
https://github.com/PKUDigitalHealth/ECGFounder/tree/04edac702b61c91face519774ddcc0cd712fef23
Checkpoint público hospedado por PKUDigitalHealth no Hugging Face (model card MIT).

DeepPSP/CinC2021: MIT, Copyright (c) 2021 KANG Jingsu and WEN Hao. Código original
em `src/kardiaos/vendor/deeppsp/torch_ecg_bak`; licença adjacente. Código e pesos:
https://github.com/DeepPSP/cinc2021/tree/9d88ab91ea8d3315479a227b68566484c18c0fb7

Os arquivos Python dos fornecedores foram preservados. A adaptação KardiaOS fica
fora dessas árvores. O instalador inclui seu código e licenças; os pesos são
obtidos separadamente pelo setup explícito. PyTorch e as dependências do ambiente
de pesquisa conservam seus avisos nos pacotes instalados. Versões utilizadas:
`requirements-research-lock.txt`. O uso destes modelos não implica certificação
ou endosso de KardiaOS pelos autores, AliveCor ou PhysioNet.


## Segmentador QT próprio incluído em 0.8.0

CompactSegmenter082 é implementação original MIT do projeto, com 81.756
parâmetros e checkpoint treinado do zero. Licença e atribuição acompanham
`src/kardiaos/assets/qt-segmenter-LICENSE.txt`; proveniência e hash em
`qt-segmenter-082.json`. Os pesos desse modelo próprio são incluídos no pacote.
O processo local de inferência usa o ambiente PyTorch de pesquisa existente.

Treino: Kalyakulina et al. (2021), Lobachevsky University Electrocardiography
Database v1.0.1, PhysioNet, DOI 10.13026/eegm-h675,
https://physionet.org/content/ludb/1.0.1/ . Base sob Open Data Commons Attribution
License v1.0; sua atribuição é preservada. A base de sinais não é redistribuída
no app. Não há dados pessoais do usuário no treinamento ou nos pesos.
Nenhum código ou checkpoint BixECG foi incorporado. A calibração de confiança
do segmentador próprio falhou; seu uso é exclusivamente exploratório.
