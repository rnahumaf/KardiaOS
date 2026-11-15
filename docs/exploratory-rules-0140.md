# Amplitudes exploratórias e descrições — 0.14.0

O motor `limb-rules-4` avalia P de amplitude elevada, elevação de J, rebaixamento
de ST, inversão e amplitude elevada de T, Q proeminente/QS mesmo sem calibração
validada ou com instabilidade dos marcos. Cada regra mantém os avisos específicos.
A polaridade exibida é assumida quando a convenção elétrica não tem referência;
nenhuma inversão, ganho ou referência é criada para obter uma hipótese.

Sem idade, os critérios de amplitude comparam exploratoriamente com os limiares
de adulto, com aviso. Idade pediátrica conhecida continua impedindo essa comparação.
As restrições dos critérios de intervalos, ritmo e QTc não mudaram. Tampouco mudaram
os valores numéricos dos limiares de amplitude, as derivações exigidas ou os grupos
de contiguidade. Um marco ou canal realmente ausente não é inventado.

## Mediana completa e subconjuntos

A conclusão usa os resultados da mediana completa. Se apenas uma das quatro
medianas de verificação satisfizer um critério, os detalhes mostram uma possível
alteração, suas derivações e os subconjuntos correspondentes. Esse resultado não
entra nos achados principais. A contiguidade é verificada dentro de cada
subconjunto; derivações de subconjuntos diferentes não são combinadas para
satisfazer o critério.

O início de T calculado na mediana completa também é usado para extrair as
características dos subconjuntos. O início delineado em cada subconjunto continua
registrado separadamente para auditar a variação, sem bloquear as regras de
amplitude. O delineador `global-median-5`, a suavização e os marcos globais não
mudaram. A qualidade passou a `median-stability-2` para registrar esse contrato.

## Descrições morfológicas

P bifásica, T bifásica e T com entalhe são descrições nas derivações afetadas.
Não alteram sozinhas a conclusão. Componentes discretos recebem “possível”.
O detector trabalha na mediana suavizada, referenciada à linha de base PR já
usada pelo motor. As evidências incluem índices relativos à onda, amplitudes
e, para entalhes, profundidade do vale. Não são probabilidades diagnósticas.

As heurísticas de engenharia exigem largura de pico de duas amostras e separação
de seis amostras na grade de 300 Hz. Para bifasicidade, os dois componentes devem
ter sinais opostos e superar ruído/proeminência. O limite discreto é o maior entre
duas vezes o ruído, 5% da amplitude e 0,010 mV para P ou 0,015 mV para T. O limite
para componentes definidos é o maior entre três vezes o ruído e 0,030 mV para P
ou 0,050 mV para T. Picos de uma amostra não bastam.

Entalhes exigem dois picos da mesma polaridade e um vale entre eles. O limite
discreto de profundidade é o maior entre duas vezes o ruído, 0,005 mV e 6% da
amplitude pico a pico; a razão entre picos precisa ser pelo menos 0,15. Para
um entalhe definido, usam-se três vezes o ruído, 0,015 mV, 15% e razão 0,30.
Esses parâmetros ajudam a distinguir componentes e ruído; não constituem
limiares clínicos validados.

A nomenclatura descritiva de ondas bifásicas e entalhadas e a referência de
amplitude seguem a discussão da [recomendação AHA/ACCF/HRS de 2009, parte IV](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.014).
O detector e seus limiares de engenharia não são prescritos por essa recomendação.

## Verificação

Testes sintéticos cobrem amplitude estimada, idade ausente/pediátrica, instabilidade,
marcos ausentes, contiguidade por subconjunto, início de T fixado na comparação,
bifasicidade discreta/definida, entalhes, polaridades opostas, ruído e isolamento
das descrições em relação à conclusão. A interface é verificada com critérios
expandidos e janela compacta.

A revisão visual local cobriu sete capturas e 37 curvas. Os arquivos originais
permaneceram intactos; imagens e resultados pessoais não foram salvos. Essa revisão
verifica coerência da implementação, sem estimar sensibilidade ou especificidade.
