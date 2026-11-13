# Métodos e limites — 0.5.0

## Medições experimentais de DI

O programa escolhe o trecho contínuo mais longo dentro da janela solicitada,
limitado a até 30 segundos desse trecho. Exige pelo menos 10 segundos, 300 Hz nominais,
tempos monotônicos espaçados por 1/300 s, contato aceito, sinal variável e sem
saturação. Uma tela de artefatos compara energia acima de 45 Hz à de 5–40 Hz.
Isso não detecta todo ruído e não é um escore clínico de qualidade.

No perfil de pesquisa, a morfologia vem do mesmo DI filtrado da exibição e
impressão. Uma banda auxiliar 5–25 Hz de fase zero detecta complexos pela energia
da derivada. No perfil Referência por canal, mantém-se o método anterior no bruto
com 0,5–40 Hz de fase zero para morfologia. Os filtros podem alterar limites de
onda; nem fase zero garante preservação integral. Ganho comum positivo e inversão
global não definem os tempos encontrados. O escopo é limitado à janela solicitada,
e a folha nunca recebe medidas externas ao seu intervalo.

Dois limiares de detecção precisam concordar. São necessários cinco complexos
candidatos, intervalos de 0,3–2 s e repetibilidade do template mediano. FC é
60/RR mediano. Não é um diagnóstico de ritmo. Para delinear, exigem-se correlação
mediana dos complexos >=0,92 e coeficiente de variação RR <=0,10; a correlação
não é probabilidade de acerto. Essa regra pode recusar arritmias verdadeiras.

Limites de onda são buscados no template pela volta à linha de base sob limiares
de 5% e 10% do pico, ou três vezes o ruído residual. Exige-se amplitude separada
do ruído, retorno à base antes da borda e concordância dos limites em até 20 ms.
As faixas técnicas são P 40–200 ms, QRS 40–200 ms, onda T 60–350 ms e QT
200–600 ms. Elas são limites do algoritmo, não faixas de normalidade clínica.
Valores fora delas ou a até uma amostra de suas bordas são indisponíveis, sem extrapolar ou completar ondas.
Ondas bifásicas, P/T sobrepostas, U, bloqueios, ruído periódico e baixa amplitude
podem confundir o algoritmo. Não há validação contra delineação de especialistas.

QTcF = QT(ms)/RR(s)^(1/3), a fórmula de Fridericia. Só é emitido com QT delimitado,
RR estável de 0,6–1,5 s e QRS <120 ms. Nem essa seleção elimina os limites da
correção por frequência. Não são aplicados limiares diagnósticos. A resolução
amostral nominal é 3,33 ms; o erro de delineação pode ser muito maior.

Referências de contexto, sem alegar equivalência/validação do algoritmo local:

- [AHA/ACCF/HRS: QT e repolarização](https://www.ahajournals.org/doi/10.1161/circulationaha.108.191096).
- [Estudo de fórmulas QTc](https://www.ahajournals.org/doi/10.1161/jaha.116.003264).
- [QT Database: anotações de limites P/QRS/T](https://physionet.org/content/qtdb/1.0.0/). Não usada como benchmark nesta entrega.

## Hipóteses das redes

O perfil Pesquisa — mV estimados permite os modelos sob pressupostos
operacionais explicitamente separados de evidência. O perfil Referência por
canal exige convenção documentada. A comparação de inversões só existe na API
técnica explícita e nos testes, fora da interface normal e da impressão.
Consulte [perfil operacional](research-profile.md) e [evidências](orientation-evidence.md).

O primeiro trecho tecnicamente aceito de 10 s, buscado a cada 300 amostras (1 s nominal, saltando lacunas), é usado
por modelo. Não é selecionado pelo score. Se nenhum trecho servir, há motivo de
indisponibilidade. Não são preenchidas derivações ou lacunas. Interromper cancela
o subprocesso próprio de inferência e identifica o resultado como parcial.

Pesos, cabeças treinadas, rótulos e pré-processamento permanecem os de
[research-models.md](research-models.md). Os scores são sigmoid não calibrados;
não são comparáveis como confiança entre modelos, janelas ou derivações.
Não há calibração estatística nem validação de domínio KardiaMobile.

## Impressão e instalação

DI em linhas utiliza janelas contíguas de 10 s a 25 mm/s ou 5 s a 50 mm/s. Até
seis linhas podem caber, conforme a amplitude e o ganho; a altura é planejada
antes do desenho. Na prévia, um painel inferior reserva espaço para FC/P/QRS/QT/QTcF e três maiores scores por modelo. Isso reduz a área disponível ao traçado sem mudar o ganho ou a velocidade. Todos os modelos disponíveis são listados, inclusive indisponibilidade; rótulos longos podem ser abreviados e continuam completos na análise. O processamento inicia automaticamente ao abrir a prévia e pode ser interrompido fechando-a. A impressão aguarda sua conclusão. As janelas da análise são explícitas e devem estar contidas no intervalo da folha; resultados de outro sinal ou fora da janela não são impressos. Os limites de cada faixa e o restante não impresso são
informados. Nenhuma amostra é duplicada/perdida nas fronteiras do trecho impresso.
A grade é física, sem ajuste horizontal/vertical para caber. O pulso ocupa 200 ms
e 1 mV segundo a escala declarada, que pode continuar provisória. Amplitude que
não cabe é recusada, não recortada. Nas seis derivações, as faixas superiores
têm 118 mm de sinal, além da área de calibração; DII contínua tem 250 mm.

Os testes Qt são executados com `QT_QPA_PLATFORM=offscreen`, sem interagir com
a sessão gráfica. O instalador verifica processos ativos, não os fecha e não
apaga configurações, capturas ou pesos. Não há backups ou cópias de rollback.
Testes sintéticos e de integração não substituem impressão física, calibração
elétrica/temporal ou validação clínica. Esses itens continuam não verificados.


## Verificação da versão

Os testes cobrem sinais sintéticos com durações conhecidas, inversão/ganho comum,
ruído, sinal ausente/curto, saturação/contato, lacunas e relógio incompatível;
ondas ausentes, QT/T na borda, QRS largo e RR variável; integração Qt offscreen,
reavaliação e interrupção; derivação por canal e modo técnico explícito; página A4 vetorial, cobertura
sem duplicação de amostras, pulso de 200 ms em ambas as velocidades e recusa de
recorte vertical. O fluxo completo foi exercitado com os três checkpoints reais
e entrada sintética, sem usar dados pessoais como fixtures ou publicar scores.
