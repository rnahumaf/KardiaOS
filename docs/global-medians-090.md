# Medianas sincronizadas e intervalos globais — 0.9.0

> A versão 0.9.1 acrescenta suavização das medianas e revisa a seleção dos
> marcos, conforme [median-landmarks-091.md](median-landmarks-091.md).

A revisão usa a gravação completa para formar medianas sincronizadas. A janela
de 10 segundos continua definindo o trecho do relatório e a entrada contínua de
ECGFounder e DeepPSP. Alterar essa janela não altera as medianas nem as medidas.

## Alinhamento e exclusões

O motor identifica um relógio QRS nas entradas nativas simultâneas, pela energia
conjunta filtrada em 3–25 Hz. Cada batimento recebe uma translação inteira de até
12 amostras (40 ms), aplicada a todas as derivações. A referência é refinada em
três passagens por correlação conjunta. Derivações de baixa amplitude não precisam
detectar QRS sozinhas. As curvas mantêm amplitude, polaridade e duração originais;
não há deformação temporal nem normalização individual da amplitude.

Batimentos com QRS claramente distinto são excluídos simultaneamente nas
derivações: correlação abaixo de 0,80 ou resíduo relativo acima do maior entre
0,65 e a mediana dos resíduos acrescida de seis desvios absolutos medianos
escalados. P/T também podem indicar uma morfologia distinta, com resíduo acima
do maior entre 1,2 e esse limiar robusto, desde que a referência supere o ruído.
Essa comparação não é usada quando o RR adjacente menor que 0,8 s pode trazer
uma onda vizinha para a janela. RR diferente não é motivo de exclusão.

Os limiares são escolhas de engenharia exploratórias, sem calibração clínica.
As exclusões e seus motivos aparecem em Critérios. A sequência original dos
batimentos, inclusive os excluídos por morfologia, sustenta FC e RR. Não se
calculam intervalos atravessando lacunas ou perda de contato. Segmentos válidos
somente em I continuam contribuindo para ritmo em uma gravação mista.

A janela comum de cada batimento vai de −350 a +600 ms em relação ao QRS.
Batimentos sem essa janela completa ficam fora da mediana, com motivo próprio.
Nenhuma amostra de lacuna, saturação ou contato perdido é interpolada. As
capturas originais permanecem intactas.

## Limites e medidas

Cada derivação recebe uma mediana ponto a ponto do mesmo conjunto alinhado.
Os filtros de medição são de fase zero, aplicados separadamente aos segmentos
contínuos: 0,5–80 Hz para QRS e 0,5–30 Hz para P/T. A aba Limites mostra as
curvas individuais alinhadas, as medianas e os marcadores globais.

A delineação ocorre somente nas medianas. O motor usa os limites locais que
passam pelos critérios de contraste, duração e fechamento da onda para obter
o início mais precoce e o término mais tardio. A origem de cada limite fica
registrada. Esses marcadores são compartilhados por todas as medianas, mesmo
quando a onda não é visível em determinada projeção. São intervalos globais das
derivações disponíveis, não equivalentes a uma avaliação de 12 derivações.

P, QRS, PR e QT dependem desses limites. QTc usa Fridericia e RR original;
mantém a abstenção com RR mediano fora de 0,6–1,5 s, coeficiente de variação acima
de 0,10 ou QRS global de pelo menos 120 ms. Pelo menos três batimentos completos
aceitos são necessários para delinear a mediana. A indisponibilidade de uma
medida não esconde a curva nem invalida automaticamente as outras medidas.
Marcadores globais não são projetados sobre batimentos individuais do traçado.

O CompactSegmenter082 deixa de participar das medidas operacionais. Ele foi
integrado para sequências contínuas, e não há validação que sustente trocar sua
entrada por uma batida mediana. Não repetimos artificialmente a mediana para
preencher sua entrada nem usamos seus limites como alternativa. O código e as
validações históricas permanecem disponíveis para reprodução. ECGFounder e
DeepPSP mantêm as entradas contínuas e seus pré-processamentos próprios.

A nova política não herda a qualificação histórica do motor 0.7.0. Os resultados
são exploratórios, sem nova validação clínica, calibração de amplitude ou
classificação diagnóstica por limiar.

## Verificação

Os testes usam sinais sintéticos com projeção plana, inversão de polaridade,
QRS distinto, diferença isolada de T, RR irregular, lacunas, contato parcial e
ondas ausentes. Também verificam deslocamentos compartilhados, proveniência dos
limites, preservação das amostras, independência da janela do relatório e ausência
de recurso ao segmentador neural ou à delineação individual.

As sete capturas locais fornecidas pelo usuário são verificadas em memória.
Nenhuma captura, medição clínica, imagem ou conteúdo desses arquivos entra no
repositório ou no pacote. Essa verificação confirma o comportamento do software;
não mede a exatidão clínica dos limites contra anotações de referência.

Referência para o conceito de intervalos globais:
[AHA/ACCF/HRS, Part I: The Electrocardiogram and Its Technology, 2007](https://www.jacc.org/doi/10.1016/j.jacc.2007.01.024).
