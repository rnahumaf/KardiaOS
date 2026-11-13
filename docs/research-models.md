# Avaliação experimental local

## Pesos e saídas preservadas

| Modelo | Entrada | Saídas treinadas | SHA-256 |
|---|---|---|---|
| ECGFounder 1L | I | 150, na ordem de tasks.txt | f863a38897fb49a27fec7e44008ea3c7bdbd29c77fa4a02ecbb8c56df4f37603 |
| DeepPSP CinC2021 2L | I, II | 21 | 187823e387553d07c72bef50b487b7b8fbbdbf99d4802c5a3a3174ec1a11fefa |
| DeepPSP CinC2021 6L | I, II, III, aVR, aVL, aVF | 21 | 29452c8bcad486672e17902337220710a076a4262af9afeca3ea138abc4b23d4 |

Não há cabeça aleatória, ajuste fino nem substituição dos pesos. O carregamento
é estrito (`strict=True`) e verifica SHA-256 antes de desserializar. O loader
`weights_only=True` permite somente contêineres de dados conhecidos. A cabeça
ECGFounder armazenada tem peso 150×1024 e bias 150. Não se usa o helper de fine-tuning
que substitui essa cabeça. Os checkpoints DeepPSP trazem classes, leads e configuração
de treinamento; esses contratos são conferidos antes da inferência.

Fontes verificadas:

- [ECGFounder, revisão de código](https://github.com/PKUDigitalHealth/ECGFounder/tree/04edac702b61c91face519774ddcc0cd712fef23), incluindo tasks.txt, dataset.py e util.py.
- [Checkpoint ECGFounder 1L](https://huggingface.co/PKUDigitalHealth/ECGFounder/blob/d9b1793951b2342f5f7e84f1ac03cd37f8a08724/1_lead_ECGFounder.pth).
- [Confirmação da ordem dos 150 rótulos pelos autores](https://huggingface.co/PKUDigitalHealth/ECGFounder/discussions/1).
- [DeepPSP/CinC2021, revisão fixada](https://github.com/DeepPSP/cinc2021/tree/9d88ab91ea8d3315479a227b68566484c18c0fb7), saved_models, official_phase_legacy/team_code.py e torch_ecg_bak.

PhysioNet/CinC2021 é um desafio; o modelo integrado é especificamente DeepPSP.
As 21 classes dos pesos são AF, AFL, BBB, CLBBB, CRBBB, IAVB, IRBBB, LAnFB, LPR,
LQT, NSIVCB, NSR, PAC, PRWP, PVC, QAb, SA, SB, STach, TAb e TInv. Cinco classes
especiais do pipeline original (Brady, LAD, RAD, PR, LQRSV) dependem de heurísticas
externas à rede e não são adicionadas. Não há fallback de ritmo sinusal para erro.
QAb significa qwave abnormal; não é convertido em área inativa ou infarto.
Rótulos temporais do ECGFounder não demonstram evolução entre exames.

O catálogo `src/kardiaos/assets/research_catalog.json` mantém URLs, hashes, ordem
de classes e nomes originais. Os códigos ECGF são índices locais, não SNOMED;
os códigos DeepPSP vêm da tabela de classes original.

## Entrada e processamento

A entrada é o bruto M2 de 300 Hz nominais. São selecionadas 3000 amostras contínuas
a partir do início aceito mais o deslocamento escolhido. `lead_values(raw=True)`
aplica a escala declarada e deriva apenas as quatro derivações de membros pelas
identidades elétricas. Não são criadas precordiais. I–II requer disponibilidade
do modo 6L, pois essa é a forma conservadora de reconhecer ambos os canais M2.

Pré-condições: escala e polaridade explicitamente referenciadas, 10 segundos
completos, contato/qualidade aceitos, marcadores M2 disponíveis, sem lacunas,
saturação ou sinal constante. Sinal incompatível resulta em inconclusivo, sem
scores. O reconhecimento de contato e qualidade é uma heurística de aquisição,
não um detector validado de todos os artefatos.

Os dois pipelines reamostram 300→500 Hz por `scipy.signal.resample_poly(5,3)`:

- ECGFounder: segue o dataset oficial de uma derivação: notch 50 Hz/Q30 com
  filtfilt, Butterworth ordem 4 de 0,67–40 Hz com filtfilt, subtração da mediana
  de 201 amostras e z-score global com epsilon 1e-8.
- DeepPSP: segue a configuração dos checkpoints e o pipeline oficial legado:
  Butterworth ordem 5 de 0,5–60 Hz com filtfilt e z-score global com epsilon 1e-7.
  Entradas acima de 20 mV são recusadas, em vez de substituir spikes como no código
  original. Não há preenchimento, extensão de janela ou fallback de classes.

A saída é sigmoid por classe, permitindo múltiplos scores altos. Não há calibração
estatística, limiar diagnóstico, validação clínica ou alegação de equivalência a
ECG de 12 derivações. A adaptação de sinais KardiaMobile a 300 Hz não foi validada
pelos autores. O notch oficial de 50 Hz é preservado mesmo em rede elétrica 60 Hz;
a interface descreve esse processamento. Os filtros visuais não entram na análise.

## Execução e privacidade

Inferência CPU em subprocesso isolado (`python -I`), com quatro threads PyTorch,
ambiente separado e protocolo local em memória. Nenhum identificador, nome de
arquivo clínico ou metadado pessoal é enviado ao worker. Não há código de rede no
pipeline de inferência. Somente o script explícito de setup baixa dependências
e pesos públicos. O JSON de resultados é salvo apenas por ação de exportação.

Os pesos ficam em `~/.kardiaos-research/models`, fora do Git e do instalador.
`research-runtime.json` aponta para o interpretador real e a pasta de modelos,
também fora do Git. A instalação traz o worker e o código dos modelos em `source`.
O setup resolve redirecionamento de AppData de aplicações Windows empacotadas.

## Verificação realizada nesta integração

41 testes passaram, cobrindo contratos, recusa de entradas incompatíveis,
calibração, preservação do bruto, mapeamento e reamostragem. Sinais sintéticos
geraram 150/21/21 scores finitos, repetíveis (diferença máxima zero nas repetições).
A comparação numérica com as funções oficiais de pré-processamento, usando a
mesma reamostragem e sinal sintético, teve diferença máxima zero nos três modelos.
A interface foi exercitada com processamento em thread, filtro de rótulos,
invalidação ao mudar modelo/janela e resultado inconclusivo, em 820×620 e 1020×760.

Os dois arquivos reais autorizados foram abertos somente localmente e seus hashes
permaneceram iguais. Ambos tinham escala/polaridade não verificadas; nenhum score
clínico foi emitido. A captura de uma derivação também foi recusada pelos modelos
de duas/seis derivações. Falta uma referência externa de amplitude e polaridade;
não é possível estabelecê-la apenas com os valores digitais dessas capturas.

No Alienware Core 7 240H, CPU, o trecho medido dentro do worker (carregamento da
rede e execução, sem início do processo e hash) ficou aproximadamente entre
0,7 e 1,3 s. Isso não mede a latência total da interface. RTX 5050 não foi usada.
Nenhum teste descrito aqui demonstra acurácia diagnóstica ou validação clínica.
