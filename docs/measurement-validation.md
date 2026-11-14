> Atualização 0.8.0: [fluxo exploratório, templates e fases](exploratory-080.md).
> As descrições 0.6/0.7 abaixo registram o método anterior; seus resultados de
> qualificação permanecem históricos e não são convertidos em validação clínica.

# Medições temporais e validação — 0.7.0

## Estado entregue

FC, duração P e QRS são estimativas experimentais separadas de DI e DII.
QT e QTcF ficam **indisponíveis na aplicação, JSON normal e impressão**: o
candidato não atingiu a cobertura mínima previamente definida em nenhuma das
duas derivações. Não foram relaxados limiares após a validação para liberar QT.
`measurements.py` aplica essa política; `measurement_engine.py` preserva o
candidato avaliado, byte a byte, para reprodução científica. Nenhuma dessas
medições é uma duração global de 12 derivações ou uma validação do aparelho.

## Método e processamento

O delineador `timing-dsp-1` é uma implementação independente de princípios de
derivadas em escalas gaussianas e proeminência. Não reproduz integralmente os
algoritmos publicados nem herda suas acurácias. Foram estudados o método
multiescala de [Martínez et al.](https://diec.unizar.es/~laguna/personal/publicaciones/wavedet_tbme04.pdf),
o [método de proeminência de Emrich et al.](https://github.com/JonasEmrich/prominence-delineator)
e o código oficial [NeuroKit2](https://neuropsychology.github.io/NeuroKit/_modules/neurokit2/ecg/ecg_delineate.html).
NeuroKit2 0.3.0 DWT/proeminência foram comparadores de desenvolvimento; não são
dependências distribuídas. O repositório de Emrich alerta que limites em torno
de R não necessariamente abrangem Q/S. A implementação de NeuroKit avaliada
contém escolhas dependentes do sinal para algumas ondas, razão para testar
explicitamente ondas negativas e bifásicas. Nenhum código GPL foi incorporado.

Exibição, impressão e entrada das redes mantêm o perfil operacional 0.6.0:
ganho comum empírico 1,5, sem inversão, filtros causais visuais e contratos
próprios dos modelos. **Medições agora partem do bruto**, independentemente dos
filtros visuais: Butterworth de ordem 2, passa-altas 0,5 Hz e passa-baixas 80 Hz,
aplicados para frente e para trás, sem notch adicional. Isso elimina o atraso
de fase desses filtros, mas não garante preservação de toda a morfologia.
A resposta interna do aparelho permanece desconhecida.

O detector usa banda auxiliar 5–25 Hz de fase zero, energia da derivada e dois
limiares relativos (0,12/0,25) que devem concordar. Exige pelo menos cinco QRS,
RR de 0,3–2 s e repetibilidade/contraste dos complexos. FC = 60/mediana(RR).
O maior segmento contínuo elegível é limitado a 30 s e exige 10 s. Não se
interpola contato perdido ou lacunas. Saturação, sinal constante, relógio
irregular e excesso de energia acima de 45 Hz provocam abstenção.

Os limites são buscados por batimento. QRS usa derivada gaussiana com sigma
2,5 amostras, envelope e limiares 5/10%; P/T usam sigma 3, proeminência em ambas
as polaridades e limiares de inclinação 30/50%. Dois limites devem concordar
em até seis amostras. Ondas pequenas, bifásicas/adjacentes ou na borda da janela
são recusadas. Os intervalos técnicos são QRS 40–250 ms, P 40–200 ms, onda T
70–400 ms e QT candidato 200–600 ms; não são faixas de normalidade.

Uma mediana exige ao menos três e 50% dos batimentos delimitados. IQR máximo:
20 ms para P/QRS e 30 ms para QT; variabilidade de posição do fim de P/T também
é verificada. Estes são critérios operacionais, não probabilidades. Ganho
positivo comum e inversão global não alteram a finalidade temporal; o traçado
gravado/exibido nunca é invertido por essa análise. Não se conclui a orientação
do decoder a partir de morfologia ou scores.

Cada resultado registra derivação, janela, amostras, filtro próprio, método,
quantidade de batimentos, motivos de recusa e política de liberação. A aba
Limites mostra o sinal de medição e os pontos de P/QRS aceitos. Candidatos de T
não são mostrados como evidência aceita de QT. DI e DII não são fundidas; as
quatro derivações algébricas não são quatro observações independentes.

## Referência e protocolo

Foi usado o [LUDB 1.0.1](https://physionet.org/content/ludb/1.0.1/), 200 pessoas,
10 s, 500 Hz, com marcações manuais específicas de cada derivação. A
[publicação original](https://arxiv.org/html/1809.03393v4) descreve anotação
conjunta por dois cardiologistas. Licença Open Data Commons Attribution 1.0;
DOI 10.13026/eegm-h675. Foram conferidos 2.805 arquivos contra SHA256SUMS.
Dados públicos e pessoais não acompanham o app nem o repositório.

Separação por pessoa: `default_rng(1729).permutation(arange(1,201))`, primeiras
40 para desenvolvimento, 160 restantes reservadas. I/II da mesma pessoa ficam
juntas. Sinais são reamostrados 500→300 Hz (`resample_poly(3,5)`) e quantizados
em 4/4096 mV para o adaptador de teste; isso **não** calibra contagens M2.
Tempos de referência ficam na base original, sem arredondamento para previsões.
O adaptador declara os canais públicos disponíveis, sem simular a confirmação
de contato M2 de 0,5 s. O tratamento de contato real não mudou.

Pareamento um a um dos QRS em ±100 ms, interior 0,6–9,4 s e intervalo coberto
pelos QRS anotados. Batimentos nas bordas sem referência são contados à parte.
Marcadores ausentes não são preenchidos: picos podem existir sem um limite de
onda. Houve uma execução interrompida por essa condição no leitor de referência;
ela não produziu resultados e não foi usada para ajustar o método. Após corrigir
o leitor/adaptador, o conjunto reservado foi concluído com método e parâmetros
congelados. O script público reproduziu exatamente os resultados do candidato.

Metas de engenharia previamente definidas: Se/PPV dos QRS candidatos ≥95%; FC
MAE ≤2 bpm/P90 ≤5 bpm; P/QRS/QT MAE ≤20/15/25 ms e P90 ≤40/35/50 ms. Exigia-se
cobertura ≥50% dos registros elegíveis em cada derivação. Elegibilidade de
referência: cinco QRS para FC, três ondas com limites para duração. São metas
do projeto, não certificação clínica. O erro é calculado entre saídas aceitas;
a cobertura e os recusados são parte do resultado, não desaparecem da avaliação.

## Resultado no conjunto reservado

160 pessoas, avaliadas separadamente em DI e DII. O erro abaixo compara medianas
por registro; batimentos e derivações não foram tratados como pessoas adicionais.

| Derivação | Medida | Registros aceitos/elegíveis | MAE | P90 absoluto | Máximo absoluto | Meta |
|---|---|---:|---:|---:|---:|---|
| DI | FC (bpm) | 149/158 (94.3%) | 0.26 | 0.59 | 2.47 | passou |
| DI | P (ms) | 78/139 (56.1%) | 9.31 | 16.88 | 34.30 | passou |
| DI | QRS (ms) | 136/160 (85.0%) | 10.04 | 18.35 | 56.00 | passou |
| DI | QT candidato (ms) | 62/160 (38.8%) | 14.92 | 25.04 | 55.30 | falhou: cobertura |
| DII | FC (bpm) | 154/159 (96.9%) | 0.23 | 0.54 | 2.56 | passou |
| DII | P (ms) | 88/139 (63.3%) | 6.71 | 15.09 | 26.30 | passou |
| DII | QRS (ms) | 139/159 (87.4%) | 11.11 | 19.76 | 88.70 | passou |
| DII | QT candidato (ms) | 70/159 (44.0%) | 14.02 | 24.13 | 42.30 | falhou: cobertura |

QT teve erro aceitável no subconjunto, mas falhou a cobertura: 38,75% em DI e
44,03% em DII. Por isso QT e QTc permanecem bloqueados. A fórmula candidata
é Fridericia `QT(ms)/RR(s)^(1/3)`, restrita a RR estável, 0,6–1,5 s e QRS <120 ms;
testá-la em sinais sintéticos não valida sua interpretação clínica.

QRS candidato: Se/PPV 99,05/99,52% em DI e 99,46/99,52% em DII. Foram excluídas
121/114 detecções de borda fora da extensão anotada. Saídas finais de FC podem
ser recusadas após essa detecção. Duas saídas de FC em DI e uma em DII tinham
menos de cinco referências manuais, portanto não entraram no erro de FC.
O resumo JSON inclui contagens por batimento e erros dos limites individuais.

O valor máximo de erro QRS foi 56,0 ms em DI e **88,7 ms em DII**. Portanto a
aprovação das metas médias não torna uma medição individual confiável para um
limiar clínico. Não se avaliou sensibilidade/especificidade para QRS ≥120 ms.
O app descreve a duração numérica e informa a referência adulta de 120 ms,
sem classificá-la como bloqueio ou produzir uma decisão robusta nesse limiar.

O comparador 0.6.0 no perfil empírico foi avaliado adicionalmente, sem ajustar o
candidato. MAE QRS entre aceitos: 26,76/34,34 ms e cobertura 36,88/39,62% (DI/DII);
P: 22,53/30,08 ms e cobertura 12,95/10,79%. Os conjuntos aceitos diferem, portanto
isso não prova melhora em todos os registros. Um comparador anterior no modo
Referência também está no relatório de avaliação local.

## Limitações e descrições determinísticas

A resolução de uma amostra é 3,33 ms; não é a acurácia. O teste de deslocamento
de uma amostra mostrou variação de até 6,67 ms em uma duração, pela discretização
de dois limites. Essa sensibilidade é documentada; não é intervalo de confiança.
O delineador congelado não foi retocado depois dos resultados reservados.
Ondas sobrepostas/bifásicas, baixa amplitude, ectopia, estimulação e artefatos
podem produzir abstenções ou erros. O LUDB é curto, hospitalar e de outro aparelho;
não demonstra desempenho no KardiaMobile, em gravações longas ou em outras populações.

As [recomendações AHA/ACCF/HRS sobre condução](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.013)
distinguem duração global e medidas por derivação. Bloqueios de ramo exigem
morfologia e precordiais ausentes neste app. QRS largo isolado não identifica
um bloqueio específico. A interpretação de ST fica indisponível: há escala e
orientação assumidas, resposta do aparelho não validada e filtros visuais que
alteram o segmento. Não se deduz infarto ou área inativa.

As [recomendações sobre tecnologia](https://doi.org/10.1016/j.jacc.2007.01.024)
discutem a distorção por filtros, especialmente passa-altas causais, e requisitos
de largura de banda diagnóstica que não são satisfeitos apenas por um sinal a
300 Hz. A mudança do filtro de medição não torna o app um ECG diagnóstico.
As [recomendações de QT](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.014)
tratam seleção de derivações, ondas T/U, variabilidade RR e limites de correção.
O [estudo de Vandenberk et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC4937268/)
avaliou fórmulas em contexto adulto selecionado; não valida QTc do KardiaOS.

Os registros locais fornecidos servem para funcionamento, sensibilidade e
integridade, não como referência de limites clínicos. Diagnósticos de PDFs não
são copiados como verdade. Scores das redes permanecem saídas não calibradas.

## Reprodução

Instalar as dependências opcionais de `requirements-validation.txt` num ambiente
de avaliação e obter LUDB 1.0.1 da fonte oficial, respeitando sua licença.
Não executar o benchmark sobre registros pessoais como se fossem LUDB.

```powershell
python scripts/validate_ludb.py --data CAMINHO_LUDB --split held_out --output CAMINHO_LOCAL/validacao.json
```

O script avalia o candidato e reporta se cada meta passou; não altera o gate do
app. `--baseline-source` permite comparar uma fonte original 0.6.0; o perfil
de comparação é explícito (`--baseline-profile empirical` ou `referenced`).
O resumo agregado, hashes de código e protocolo ficam em
`measurement-validation-summary.json`. Nenhum resultado pessoal entra nesse arquivo.
