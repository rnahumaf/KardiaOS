# Evidências dos critérios — 0.15.0

Achados, descrições morfológicas e possibilidades são links no Resumo. Cada
critério da tabela técnica também abre sua evidência por clique ou ativação
pelo teclado. A aba Curvas e marcos mantém a visão anterior em Todas as curvas.
O seletor de evidência permite consultar inclusive critérios não detectados ou
indisponíveis, preservando o motivo de indisponibilidade.

As derivações envolvidas usam o mesmo intervalo temporal e a mesma escala de mV.
Os gráficos mostram a mediana completa em verde e o subconjunto em âmbar tracejado.
A linha de base PR é subtraída apenas na apresentação da amplitude relativa;
nenhuma normalização de ganho, novo alinhamento ou alteração do sinal é aplicada.
Círculos numerados e faixas apontam os componentes, intervalos ou janelas de amostras
usados pela regra. A tabela relaciona os números aos valores, marcos e limiares.
O recorte de P evita que o QRS domine a escala. Limiares fora da faixa vertical são
indicados textualmente, sem comprimir a curva.

Os dados de `median-stability-3` incluem as curvas QRS e P/T das quatro medianas
já usadas para verificar estabilidade. A interface reutiliza esses valores e os
marcos `analysis_points`, sem redelinear ao clicar. O início de T continua fixado
na mediana completa para as comparações; os marcos delineados dos subconjuntos
permanecem registrados separadamente. As características de Q registram os
índices das amostras negativas iniciais; os descritores registram componentes e
limiares de engenharia. J e ST mostram a média das mesmas três amostras utilizadas
no cálculo, não uma amplitude pontual substituta. A faixa QT é o intervalo bruto;
a tabela explica a correção QTcF pelo RR. As curvas de evidência usam o canal de
medição QRS ou P/T pertinente ao critério, identificado pela família da regra.

Para frequência e regularidade, os pares de picos que geraram cada RR são
registrados dentro de cada segmento elegível. Nenhum par atravessa lacunas.
O traçado DI usa a visualização da gravação original; os pontos R e os valores RR
vêm da detecção usada pela análise. O gráfico de RR cobre a gravação completa,
inclusive batimentos excluídos do conjunto morfológico. Seu clique ou o controle
de início escolhe um trecho de 10 segundos no traçado. O realce mostra intervalos
fora da faixa de regularidade; quando o CV excede o limite, a sequência inteira
participa do critério e recebe realce. Para frequência, mostra a relação com o
limiar RR equivalente; a decisão continua usando a FC global da mediana dos RR.

## Regras exploratórias

`limb-rules-5` amplia a suposição explícita de adulto para frequência e intervalos
quando a idade é ausente ou inválida. Uma idade pediátrica válida mantém os
critérios de adulto indisponíveis. Os limiares numéricos não foram alterados.
Sem sexo, QTcF abaixo de ambos os limiares é não detectado; acima de ambos é achado;
entre eles é uma possibilidade dependente do sexo, somente nos detalhes.
Os limiares existentes de 450/460 ms são discutidos na
[recomendação AHA/ACCF/HRS, parte IV](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.014).
Comparar ambos sem sexo é uma política exploratória do aplicativo, não uma
recomendação clínica adicional dessa fonte.

A ausência de referência da polaridade deixa de impedir a avaliação de ritmo
sinusal. A suposição fica explícita; consistência e dispersão de P, associação
P–QRS, continuidade, quantidade e qualidade dos batimentos continuam necessárias.
Quando não satisfeitas, os motivos aparecem com valores e limites. Isso não
transforma ritmo regular isolado em ritmo sinusal.

A instabilidade de marcos ou de avaliação entre subconjuntos preserva o resultado
da mediana completa com aviso também nos critérios de intervalos. Um cruzamento
presente somente em subconjuntos aparece como possível nos detalhes. O cálculo de
QTc continua bloqueado pelas condições originais de RR/QRS; um subconjunto não
pode restaurar um QTc indisponível na mediana completa. Marcos ausentes não são
estimados pela interface. O delineador global e seus tempos não foram alterados.

## Verificação

Testes sintéticos cobrem os limites de QTc com sexo ausente, idade, polaridade,
intervalos instáveis, bloqueio de QTc preservado, identidade das curvas e dos
valores dos marcadores, pares RR sem cruzar lacunas, navegação, troca de subconjunto,
retorno à visão geral e ausência de dados antigos após nova análise.

A revisão local usa sete capturas, 37 curvas e 133 combinações de critério/origem,
com verificações de renderização em 850 e 1120 pixels e inspeção visual dos estados
pertinentes. Os arquivos originais permanecem intactos. Imagens e resultados
pessoais não são persistidos. Essa revisão não mede acurácia clínica.
