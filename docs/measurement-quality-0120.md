# Qualidade técnica dos marcos e medidas — 0.12.0

O rótulo fixo “baixa confiança” foi removido do fluxo das medianas. Medidas estáveis
mostram apenas o valor. Alertas específicos identificam o marco frágil; a tabela
mostra a faixa observada e os gráficos destacam a variação em âmbar. A faixa é uma
envoltória de sensibilidade, não um intervalo de confiança clínica ou uma
probabilidade de acerto. A validação clínica geral permanece separada.

São recalculadas quatro medianas: primeira metade, segunda metade, batimentos
alternados pares e ímpares. Os subconjuntos são determinísticos, correlacionados e
usam os mesmos batimentos aceitos, deslocamentos comuns e suavização limitada da
mediana principal. Não há nova seleção de morfologia, alinhamento independente,
normalização de amplitude ou delineação de batimentos isolados. A mediana principal
e seus valores não são substituídos pelas medianas de verificação.

A verificação requer pelo menos dez batimentos aceitos (cinco por subconjunto).
Com menos batimentos, a medida existente é preservada com “Estabilidade não
verificada: poucos batimentos”. Critérios dependentes ficam indeterminados.

Os limites de engenharia, incluindo a mediana principal na faixa observada, são:

| Marco | Variação máxima sem alerta |
|---|---:|
| Início/fim de QRS | 3 amostras / 10 ms |
| Início/fim de P | 6 amostras / 20 ms |
| Início/fim de T | 9 amostras / 30 ms |

Exceder o limite, não reproduzir o marco em algum subconjunto ou ter contraste
inferior a 12 produz alerta específico. O contraste usa o indicador do detector:
derivada/ruído para QRS e proeminência/ruído para P/T. Considera a projeção que
sustenta cada extremo global; as seis derivações não contam como votos independentes.
Os limiares acima são parâmetros técnicos versionados, não tolerâncias clínicas.

A calibração local examinou sete capturas do Desktop, com 37 curvas, sem modificar
arquivos nem reter imagens ou resultados pessoais. A inspeção comparou a mediana
principal às quatro medianas de subconjuntos. As mudanças amplas em T apareceram
mesmo com pequenas diferenças nas curvas, mostrando sensibilidade do detector à
linha de base. Os limites preservam esses alertas, em vez de ampliá-los para fazer
as capturas passarem. Fixtures sintéticas verificam estabilidade, contraste,
marcos ausentes, os limites exatos e uma amostra além deles. Este conjunto local
não estima sensibilidade/especificidade nem substitui validação independente.

As regras são reavaliadas com os intervalos e amplitudes das medianas de cada
subconjunto. Se a avaliação mudar ou faltar um marco necessário, somente a regra
dependente fica indeterminada. Isso inclui cruzamentos de limiar menores que a
tolerância visual do marco. Ritmo e frequência continuam usando os RR originais.
Um fim de T instável não altera a qualidade de P, QRS ou PR. Uma regra que permanece
do mesmo lado do limiar pode continuar disponível, com o alerta da medida visível.

A interface marca valores que exigem revisão, mantém o motivo no resumo e nos
detalhes e inclui aviso no relatório. O JSON registra parâmetros, contrastes,
faixas, cobertura dos subconjuntos e decisões. Não contém cópias adicionais das
curvas dos subconjuntos. A análise padrão continua sem redes neurais.
