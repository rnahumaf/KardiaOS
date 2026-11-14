# Revisão exploratória 0.8.0

Esta versão introduz uma política **exploratória** de QT/QTc explicitamente
separada da qualificação 0.7.0. A calibração de confiança falhou; nenhum resultado
é apresentado como clinicamente validado. O gate e os resultados históricos
da versão 0.7.0 permanecem em `measurements.py` e
[measurement-validation.md](measurement-validation.md). O novo fluxo mantém
esses metadados e acrescenta `exploratory_qt` por derivação. Não declara que o
gate antigo passou e não preenche medidas indisponíveis.

## Janela, canais e rastreabilidade

A tela permite percorrer a gravação completa. O laudo usa uma janela comum de
10 s, selecionada sem escores de redes nem valor QT/QTc. Candidatas começam a
cada segundo, mais a última janela completa. Exigem tempo nominal de 300 Hz
contínuo, contato e qualidade dos canais nativos. A ordem considera estabilidade
observada de T, a pior qualidade dos canais e a qualidade média; empates favorecem
a janela anterior. III/aVR/aVL/aVF não recebem votos independentes: são derivados
algébricos de I/II reais. Não se fabricam precordiais.

Se houver algum trecho de seis derivações, procura-se uma janela comum I/II;
na ausência dela o laudo pode mostrar somente o traçado disponível. Não se
substitui DII por DI nem se utiliza uma janela de outra derivação. Gravações com
menos de 10 s não geram laudo. Sem janela tecnicamente elegível, o PDF contém
somente o traçado: sem métricas, templates ou hipóteses. Amostras observadas de
contato ruim podem ser vistas nessa saída, mas não são interpoladas nem analisadas;
canais ausentes e lacunas temporais continuam interrompidos.

Cada resultado inclui chave do sinal/processamento, versão, primeiro e último
índice, derivações, perfil, filtros, checkpoint, marcos e razões de abstenção.
As redes diagnósticas são executadas novamente na janela final. O cache exige
identidade do registro, perfil, processamento e escopo da solicitação. Uma análise
interrompida, antiga ou de outra janela não habilita impressão/exportação.

## Sinal, escala e fases

O perfil operacional preserva a orientação digital e o multiplicador empírico
1,5 sobre o fator base. Nenhuma inversão é escolhida por morfologia, score ou
QTc. Esse fator não comprova volts por contagem. Posição física declarada,
orientação elétrica referenciada por canal e amplitude validada continuam
estados distintos. Dados antigos não são promovidos a calibrados.

Ao vivo, os filtros continuam causais. Na revisão de registros concluídos,
tela, template visual, laudo e entrada dos classificadores do perfil empírico
usam os mesmos filtros de fase zero, calculados por segmento temporal contínuo
e por canal. Transições de contato ou qualidade também separam os segmentos,
evitando que amostras inválidas contaminem o trecho vizinho pelo filtro bilateral.
As frequências configuradas são preservadas; o padrão operacional é 0,5–40 Hz
com notch 60 Hz. Não se filtra atravessando lacunas nem se altera o bruto.
Passagem dupla modifica a resposta em magnitude em relação ao filtro causal.
Não há alegação de reprodução do filtro proprietário Enhanced/Standard.

FC/P/QRS usam o motor temporal 0.7.0 preservado, a partir do bruto. A proposta QT
usa QRS 0,5–80 Hz e T 0,5–30 Hz, ambos de fase zero. A rede própria normaliza a
entrada de uma derivação e usa 0,5–40 Hz. Isso é pré-processamento do modelo,
não normalização de amplitude do traçado nem do template. Os marcos permanecem
no relógio das amostras; as bandas distintas podem produzir contornos diferentes.
Os marcadores no quadrado são apenas início de QRS e fim de T efetivamente
usados no QT selecionado. P/QRS individuais continuam inspecionáveis na aba
Limites; não se inventam limites de P a partir do template.

## Template e QTc

Agrupamento por morfologia assinada do QRS, RR anterior/posterior e amplitude
relativa: correlação pelo menos 0,95, RR dentro de 10%, razão de amplitude entre
0,7 e 1,3. Só se permite translação inteira de até 9 amostras a 300 Hz. Usa-se a
mediana ponto a ponto do grupo predominante, sem warping ou reescala por batimento.
São exigidos pelo menos cinco batimentos semelhantes e 50% dos elegíveis.
Batimentos discordantes, artefatos e outros grupos não formam a onda padrão.

O fim de T usa uma tangente; contraste observado, dispersão, alternância e
polaridade de T são verificados. Limites individuais suficientes, IQR de QT de
até 20 ms e diferença template/mediana individual até 20 ms são exigidos. A rede
CompactSegmenter082 precisa ter limites do mesmo grupo, dispersão até 20 ms,
concordância até 20 ms e sua própria disponibilidade de janela. Probabilidade
de segmentação não se transforma em confiança clínica.

QTcF = QT(ms) / RR(s)^(1/3). Fridericia é fixa e identificada; não se escolhe a
fórmula que produz o número mais favorável. O escopo técnico atual exige ao
menos quatro RR contextuais, RR mediano entre 0,6 e 1,5 s, CV até 0,10 e QRS
inferior a 120 ms. Esses são critérios de engenharia, não fronteiras clínicas
validadas. Dez segundos estáveis não comprovam estabilidade de RR nos minutos
anteriores; histerese QT/RR e diferenças individuais continuam relevantes.

A seleção DI/DII usa qualidade e estabilidade observada de T, sem consultar
valor ou disponibilidade de QTc. Uma derivação escolhida pode portanto resultar
em erro mesmo quando a outra tem candidato numérico. Isso evita escolher pelo
resultado. A tela e o papel usam exatamente:

- `QTc: 440 ms (DII; Fridericia; baixa confiança)` quando tecnicamente estimável;
- `QTc: erro na estimativa` quando não estimável.

Não há edição manual, intervalos de confiança validados ou classificação de QTc
normal/prolongado. O papel mostra QTc, não QT bruto. QRS largo isolado não
estabelece bloqueio de ramo; faltam derivações e critérios para diagnósticos
específicos e avaliação completa de ST/infarto.

## Evidência e modelo próprio

CompactSegmenter082: 81.756 parâmetros, implementação original MIT, treinada do
zero com LUDB 1.0.1. Separação por pessoa: 100 treino, 20 seleção, 80 calibração.
O checkpoint de 342.041 bytes tem SHA-256
`41f0b6474a9769f59ba0be099412c665b49be0ab99f9d171b5de3704c7b73cd8`.
Verificação estrita do hash, cabeça carregada integralmente e inferência em processo
local separado; sem inicialização aleatória para preencher resultados. Os avisos
MIT e atribuição LUDB acompanham o modelo. Não se incorpora BixECG ou seus pesos.

A política de confiança calibrada não passou. A comparação posterior de template
usou 40 pessoas já de desenvolvimento/treino: aceitação 13/40 em DI e 16/40 em
DII; MAE entre aceitos 14,97 e 19,90 ms, com viés negativo. Um erro individual em
DII chegou a 96 ms mesmo em um grupo cujo template passou. Esses resultados não
são validação externa nem sensibilidade/especificidade clínica. A seleção por
qualidade observada de T foi aprimorada após desenvolvimento e também não possui
validação independente. LUDB/QTDB já foram usados no projeto. Os grupos RDB
reservados não são consumidos pela integração, pelos testes ou pelos smokes.

O porte preservou resultados numéricos do protótipo congelado nos 20 sinais
sintéticos, usando pesos reais; outros cinco casos adversos com pequena variação
não constante também abstiveram. Casos incluem T ausente/baixa/negativa/bifásica,
entalhes, U separada/fundida, QRS largo, RR irregular, deriva de base, ruído,
lacunas, traçado curto, alternância, ectopia e translação. Sinais sintéticos e
registros locais funcionais não são referência clínica independente.

## Apresentação e impressão

Uma lista única traz até três hipóteses e o modelo de origem, sem números de
score. Equivalências semânticas são enumeradas explicitamente; para duplicatas
mantém-se o maior escore bruto e seu modelo. A ordenação por máximo é uma escolha
de apresentação exploratória: escalas de modelos não são comparáveis nem
probabilidades calibradas. Todos os escores e origens permanecem no JSON técnico.
Um único modelo pode preencher a lista. Sem resultados a área desaparece.

A4 paisagem: seis linhas de 10 s sincronizados; 10 s a 25 mm/s ocupam 250 mm.
Quadrado de pelo menos 24 mm, separação de 3 mm e margem para a identificação,
sempre na mesma escala temporal/amplitude do traçado. O quadrado é identificado
como Padrão, não continuação temporal. Sem template sustentado, não há caixa.
DI isolada usa linhas sucessivas cobrindo os mesmos 10 s; só a última recebe
quadrado. Não há seleção manual de trecho no laudo. A gravação completa continua
na reprodução e no arquivo bruto.

As margens mínimas informadas pelo driver são consideradas. Dimensões, ganho,
amplitude ou velocidade incompatíveis bloqueiam o laudo com motivo explícito;
não se comprime, muda duração ou recorta silenciosamente. Impressão é a 100%,
uma página e uma cópia. Testes digitais não verificam tolerâncias do mecanismo
físico, tinta/papel ou uma escala de monitor sem referência externa.

Após uma análise concluída, a prévia abre automaticamente uma vez por execução.
Repetição, troca de captura e cancelamento não reciclam uma página anterior.
Os testes Qt usam offscreen e dados sintéticos; não operam a sessão gráfica.

## Fontes primárias

- [LUDB 1.0.1, Kalyakulina et al., PhysioNet](https://physionet.org/content/ludb/1.0.1/),
  DOI 10.13026/eegm-h675, Open Data Commons Attribution License v1.0.
- [Vandenberk et al., JAHA 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4937268/):
  comparação das fórmulas; desempenho favorável de Fridericia/Framingham naquele
  conjunto não valida este delineador ou um limiar universal.
- [Andršová et al., Scientific Reports 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8275798/):
  variabilidade das correções e limitação de usar RR simultâneo sem história de
  estabilidade. Dez segundos não resolvem a histerese QT/RR.
