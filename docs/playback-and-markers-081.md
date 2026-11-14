# Reprodução e rastreabilidade em 0.8.1

## Desenho e tempo

A reprodução usa tempo monotônico decorrido, independente do número de quadros.
Seu eixo horizontal continua sendo o tempo de cada amostra multiplicado pela
velocidade escolhida. Queda de quadros pode atrasar a apresentação, mas não
redefine a duração de uma onda nem a escala do PDF.

As verificações de finitude, lacunas e coordenadas são vetorizadas antes do
desenho. Cada amostra finita conserva sua coordenada; não há decimação,
interpolação através de gaps, normalização de amplitude ou deformação temporal.
A grade possui cache limitado e independente dos sinais. Registros pausados
não são repintados a cada tick; filtros, escalas, análise, cursor e monitor
continuam invalidando a apresentação. As chaves completas do registro e da
análise permanecem verificadas para evitar templates ou marcos de outro sinal.
A seleção de janela e as inferências permanecem fora do caminho de playback.

## P por derivação e por batimento

FC/P/QRS conservam o motor temporal congelado 0.7.0. Nenhum limiar foi ajustado
para concordar com uma leitura visual ou com dados de teste reservados.
A duração de P é a mediana das diferenças entre os índices de início e fim
aceitos, dividida por 300 Hz. Por exemplo, 24 amostras são 80 ms e 2 mm a
25 mm/s; 36 amostras são 120 ms e 3 mm. A resolução amostral não representa
o erro de delineação nem um intervalo de confiança.

O resultado identifica a derivação ao lado de P e QRS. Uma onda em DI pode ter
limites diferentes da onda em DII. A métrica é específica da derivação,
não uma duração global de 12 derivações. Quando não há consistência suficiente
entre batimentos, a medida continua indisponível.

Marcas discretas P mostram, na faixa contínua da derivação medida, os índices
efetivamente aceitos de cada batimento da janela analisada. Não são limites
manuais nem novos pontos inferidos sobre a mediana. O valor de um batimento
pode diferir da mediana indicada no cabeçalho. Marcos indisponíveis, de outra
derivação ou fora da janela não são desenhados. O quadrado representativo
continua exibindo somente os marcos realmente utilizados na medição do template.

O motor usa 0,5–80 Hz em fase zero e suavização gaussiana para os limites;
a revisão visual conserva os filtros configurados. A aba Limites permite
inspecionar a representação da medição e cada batimento. Diferenças de filtro,
ruído e limiar dificultam a comparação apenas pelo contorno visível. Isso não
constitui validação clínica dos limites.

## Template visual versus medição de QT

A existência de um grupo representativo e a disponibilidade de um intervalo
são estados diferentes. O template visual exige detecção estável, qualidade,
pelo menos cinco batimentos, grupo predominante e ausência das rejeições de
dispersão, alternância ou discordância de polaridade de T. Permanecem os limites
de correlação 0,95, RR anterior/posterior ±10%, amplitude relativa 0,7–1,3 e
translação inteira até nove amostras. Não há relaxamento desses critérios.

Falha de delimitação de QRS/T ou dispersão dos intervalos QT pode impedir uma
medida sem impedir a mediana visual de formas repetíveis. Esses casos podem
mostrar o quadrado, mas não recebem limites ou QTc inventados. Razões de
indisponibilidade da medição acompanham o template nos dados técnicos.
Toda estimativa QT/QTc conserva os critérios anteriores, concordância com o
modelo próprio e a apresentação exploratória de baixa confiança.

Os dados técnicos registram comparações RR/amplitude/correlação, grupo escolhido,
deslocamento por batimento e rejeições de borda/contraste. Não classificam
automaticamente grupos diferentes como ectopias ou como doença. Batimentos
discordantes continuam fora da onda predominante. Um traçado visualmente
sobreponível não é, por si só, referência clínica ou validação elétrica.

## Escopo de verificação

Testes sintéticos verificam coordenadas e gaps, escala 25 mm/s, pausa/reinício,
ausência de análise dentro do playback, seleção de derivação e proveniência dos
marcos. Casos adversariais mantêm abstenção de QT e rejeição de templates que
borrariam formas distintas. A suíte anterior permanece aplicável.
Registros fornecidos localmente servem apenas à verificação funcional privada.
Nenhuma nova alegação de acurácia independente é feita. Bases reservadas não
foram usadas e os motores congelados não foram retreinados.

A tela identifica o trecho analisado junto aos resultados, enquanto o controle de reprodução permite percorrer a gravação inteira. Um batimento visível fora dessa janela não é tratado como o batimento medido. O traço de tela usa espessura de um pixel lógico com antialiasing, sem mudar suas coordenadas nem a espessura do PDF.
