# Perfil operacional de pesquisa — 0.6.0

## Escolha operacional e evidência

O padrão da interface é **Pesquisa — mV estimados** (`research-empirical-v1`).
Ele permite exploração local com pressupostos explícitos, sem transformar esses
pressupostos em calibração elétrica, validação do decoder ou validação clínica.
O perfil **Referência por canal** mantém o contrato de evidências independentes.
Uma preferência existente de perfil ou filtros é respeitada.

O perfil de pesquisa preserva os dois canais digitais: multiplicadores I=+1 e
II=+1. Não seleciona polaridade por score, onda R ou aparência. O ganho comum é
1,5 vezes o fator base do registro. Com o fator base provisório `10/65536`, isso
equivale a `0,0002288818359375 mV estimados/contagem`. Um fator base personalizado
continua preservado, e ambos os fatores ficam registrados nos resultados.

O multiplicador é um compromisso empírico de concordância entre pipelines em
gravações alternadas. A comparação analítica em uma banda comum motivou o valor
arredondado; as amplitudes nativas variaram por canal, filtro e gravação. Não se
tratava de uma referência elétrica simultânea. Contato, postura, filtros internos,
offset e ganho não foram identificados separadamente. O fator não é transferível
como calibração para outros aparelhos, firmware, pessoas ou condições. Usar um
ganho comum preserva as relações algébricas; não comprova igualdade dos ganhos
físicos dos canais. Não se declara reprodução exata de Omron/AliveCor.

## Sinal usado

1. Pares M2 signed int16 little-endian, sem inversão, a 300 Hz nominais. Os
   marcadores originais e todas as amostras recebidas são preservados.
2. Filtros causais padrão: passa-altas Butterworth de primeira ordem em 0,5 Hz,
   notch 60 Hz/Q30 e passa-baixas Butterworth de segunda ordem em 40 Hz.
   Não há substituição de batimentos, preenchimento de lacunas ou normalização
   de amplitude na exibição. Os controles podem alterar esses filtros; os valores
   efetivos ficam registrados. O ajuste automático de ruído é opcional e vem
   desligado para manter o pipeline padrão reprodutível.
3. Aplicação da escala estimada e derivação de III=II−I, aVR=−(I+II)/2,
   aVL=I−II/2 e aVF=II−I/2, somente quando os dois canais estão disponíveis.
4. Exibição e impressão usam esse mesmo sinal. As medidas de morfologia usam
   DI desse sinal; a detecção de complexos utiliza uma banda auxiliar de 5–25 Hz.
   Essa banda auxiliar não é o filtro do traçado exibido ou uma recomendação de
   banda diagnóstica. Os filtros causais podem deslocar/distorcer limites de onda,
   ST e amplitudes; uma cauda do QRS que se mistura com a onda seguinte pode
   impedir a delimitação mesmo em sinal sintético limpo. Nesse caso os intervalos
   permanecem indisponíveis. O relógio e a latência física não foram calibrados.
5. Os modelos recebem a janela desse mesmo sinal processado, seguida de seus
   contratos fixados em [research-models.md](research-models.md). A filtragem
   adicional do perfil é uma adaptação experimental, fora da validação dos autores.
   O notch de 50 Hz do ECGFounder é mantido no worker mesmo quando o perfil já
   aplicou 60 Hz. Normalização global torna um ganho comum positivo aproximadamente
   irrelevante para os scores; não valida a escala nem o equilíbrio entre canais.

A vista bruta mostra o fluxo digital convertido pelo perfil, sem os filtros
visuais. Ela não recebe scores ou medidas calculados no sinal filtrado. O termo
bruto não significa acesso ao ADC antes do processamento interno do aparelho.

## Janela, medidas e modelos

A análise automática trabalha dentro dos primeiros 30 s aceitos; a prévia usa
somente o intervalo que realmente cabe na folha. Cada modelo recebe o primeiro
trecho tecnicamente elegível de 10 s dentro desse intervalo, procurando em passos
de 300 amostras. Não há busca por score. Se a folha contiver menos de 10 s, ou
nenhum trecho contínuo elegível, o modelo fica indisponível. As medidas usam o
maior trecho contínuo de DI no intervalo, até 30 s, com início e duração próprios.
O painel identifica essas janelas; não atribui todos os scores a cada batimento.
Nas seis derivações, as faixas superiores são curtas e DII contínua delimita os
até 10 s da análise mostrada. Nenhum resultado de outro registro é anexado.

FC, P, QRS, QT e QTcF são medidas experimentais de DI, não intervalos globais de
12 derivações. Há abstinência por ausência/ruído, contato, lacunas, poucos
complexos, RR variável, baixa repetibilidade, limites de onda instáveis ou próximos
das bordas técnicas do delineador. A resolução nominal de 3,33 ms não representa
acurácia. QTcF usa Fridericia, `QT(ms)/RR(s)^(1/3)`, somente com QT delimitado,
RR estável de 0,6–1,5 s e QRS <120 ms. Não há números substitutos para campos
indisponíveis. Os critérios completos estão em [automatic-analysis.md](automatic-analysis.md).

ECGFounder 1L e DeepPSP 2L/6L continuam usando cabeças treinadas, rótulos originais
e SHA-256 fixados. Os scores sigmoid são saídas não calibradas; não são
probabilidades, diagnósticos ou medidas comparáveis de confiança entre redes.
Não são geradas precordiais, infarto/área inativa a partir de Q anormal ou
interpretações clínicas substitutas. A comparação de inversões saiu da interface
normal e da impressão; apenas a API técnica explícita permanece para testes.

## Persistência, cache e folha

`operational_profile` schema 1 registra identificador/versão, fator base,
multiplicador, fator efetivo, sinais e filtros efetivos. Cada resultado inclui
perfil, evidência separada, janela/índices, identidade do checkpoint e processamento
do worker. O campo `calibration_claim` é falso. `amplitude_verified`, referências
revisadas e posição física nunca são promovidos pela seleção do perfil.

Abrir arquivos antigos não os regrava. A interface aplica o perfil escolhido em
memória; bibliotecas que apenas carregam um arquivo legado mantêm o modo de
referência. Salvar explicitamente preserva as matrizes brutas e acrescenta o perfil
ao formato existente. Preferências, metadados antigos e configuração dos modelos
continuam separados. Não há upload, telemetria, backups ou cópias de rollback.

O cache em memória inclui sinal/tempo/contato, evidências, perfil/filtros efetivos,
janela e catálogo dos modelos. Jobs usam um snapshot imutável em memória;
resultados obsoletos são descartados. Mudar a janela cancela o job próprio e
calcula o intervalo novo; fechar interrompe somente esse subprocesso. Resultados
técnicos ou parciais não entram no cache normal.

A folha mantém milímetros, ganho e tempo físicos sem compressão. DI pode ocupar
linhas consecutivas; seis derivações usam faixas com origem vertical ajustada
para caber, sem alterar o ganho. O pulso mantém 1 mV estimado/200 ms e pode ter
origem vertical própria. Amplitude que não cabe é recusada. Uma nota única
identifica pesquisa/mV estimados/scores; pressupostos completos ficam aqui.

## Limites da verificação

Testes sintéticos verificam continuidade, abstinência, escala de PDF, vínculos
de janela e regressões de interface. Inferência local com pesos reais verifica
execução e rastreabilidade, não acurácia diagnóstica. Continuam pendentes referência
elétrica pareada, polaridade física do decoder por canal, validação do relógio,
benchmark de delineação, generalização dos modelos e impressão física com régua.
Resultados pessoais usados em QA permanecem fora do repositório e do instalador.
