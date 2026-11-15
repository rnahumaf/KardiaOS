# Marcos e classificação por regras — 0.10.0

A apresentação do resumo e os controles de idade/sexo foram atualizados na
[versão 0.11.0](ui-flows-0110.md). Os métodos e limiares abaixo permanecem os mesmos.

A análise padrão calcula medianas e aplica regras locais. Não abre processos de
inferência, não carrega pesos e não depende de uma rede disponível. O botão
**Análise neural…** abre a avaliação manual existente; uma rede só executa quando
o usuário solicita a avaliação de um modelo. Seus resultados ficam separados
naquela janela. A meta de dois segundos aplica-se à análise padrão após a captura,
com o aplicativo aberto, e inclui a apresentação da classificação.

## Marcos

O início de T usa uma regressão contínua por trechos: inclinação de ST seguida da
mudança para a subida de T. O algoritmo busca a posição da mudança, sem impor um
tempo fixo após R. Dois ajustes, terminando três e cinco amostras antes do pico,
precisam concordar em até quatro amostras. A melhora do erro sobre uma reta única
precisa ser de pelo menos 35%; a mudança de inclinação precisa superar o ruído.

O fim de T usa o retorno à faixa da base, com os limiares de 4% e 8% da proeminência
ou duas vezes o ruído, o maior. Os candidatos precisam ser estáveis. A exigência
anterior de concordância com a tangente deixa de cortar o término escolhido.
A fusão global continua rejeitando candidatos fracos isolados; derivações com
projeção forte podem sustentar um extremo sem votação majoritária.

P mantém a delimitação por tangentes estáveis aos flancos. A revisão visual não
justificou deslocar sistematicamente seu início. QRS e a suavização limitada das
medianas seguem o [método 0.9.1](median-landmarks-091.md). Todos os marcos vêm das
medianas exibidas; RR vem dos batimentos originais. O método e o cache mudam para
`global-median-3`.

## Regras e medidas

Cada regra retorna **detectado**, **não detectado** ou **indisponível**, com o
critério, motivo e derivações envolvidas. Ausência de dados não equivale a um
resultado negativo. As hipóteses permanecem exploratórias e mostram que as
amplitudes são estimadas pelo perfil ativo. O perfil referenciado continua exigindo
convenção elétrica por canal; o perfil empírico permite seus pressupostos explícitos.

| Grupo | Critério implementado |
| --- | --- |
| Ritmo | RR originais: CV acima de 10% ou desvio máximo da mediana acima de 15% indica irregularidade exploratória; sem inferir fibrilação atrial. |
| Frequência | Adultos: abaixo de 60 bpm ou acima de 100 bpm. |
| Intervalos | Adultos: PR abaixo de 120 ou acima de 200 ms; QRS a partir de 120 ms; P a partir de 120 ms. |
| QTcF | Adultos: a partir de 450 ms no sexo masculino ou 460 ms no feminino. Mantém as condições de RR/QRS do cálculo. |
| P | Amplitude acima de 0,25 mV em derivação inferior; largura global e descrição de bifasicidade. |
| J/ST | J a partir de +0,10 mV; ST em J+60 ms até −0,05 mV com inclinação horizontal/descendente. Exige duas derivações contíguas. |
| Q/QS | Q inicial com pelo menos 30 ms e 0,10 mV, ou QS, em I/aVL ou II/aVF. III isolada não satisfaz a regra. |
| T | Inversão até −0,10 mV em duas derivações contíguas; amplitude positiva acima de 0,50 mV em membro; bifasicidade e entalhes descritos. |

As amplitudes usam referência PR entre P e QRS. Sem espaço suficiente para essa
referência, ficam indisponíveis. ST+60 só é medido se ainda preceder T. As regras
não inferem infarto, alterações eletrolíticas, aumento de câmaras ou bloqueio de
ramo específico. As derivações de membros são projeções dependentes e não
substituem um ECG de 12 derivações. Os limiares de regularidade, ruído e forma são
escolhas de engenharia, não limiares diagnósticos validados neste dispositivo.

O suporte a ritmo sinusal exige P positiva em I/II, negativa em aVR, presença em
pelo menos 90% dos batimentos alinhados e dispersão do pico de P até 20 ms no
percentil 90. Usa a janela P comum, sem delinear intervalos individuais. Exclusões
morfológicas, lacunas ou qualidade insuficiente impedem essa conclusão. Esse
suporte automatizado não é uma comprovação eletrofisiológica da origem do ritmo.

A frase **“Ritmo sinusal, regular, sem alterações pelos critérios avaliados
(análise automática)”** só aparece com suporte de ritmo e todas as regras
necessárias disponíveis e negativas. Achados ganham prioridade na lista.
Quando falta evidência essencial, a conclusão é inconclusiva; achados parciais
continuam visíveis quando houver evidência para eles.

## Dados opcionais e saída

Idade em anos e sexo de referência são opcionais. **Aplicar e reavaliar** invalida
o cache e recalcula a análise. Os dados entram na captura somente quando o usuário
a salva; não alteram as amostras. Sem idade adulta, regras adultas ficam
indisponíveis; sem sexo, o critério correspondente de QTcF fica indisponível.
Não há regras pediátricas nesta versão.

A janela mostra todos os critérios e medidas por derivação. O PDF mantém uma
página, com a conclusão e até dois achados; informa quantos outros existem nos
detalhes. A classificação e as medidas completas acompanham o JSON exportado.

## Verificação e referências

Os testes usam sinais sintéticos com tempos, amplitudes, polaridades e derivações
conhecidos. Cobrem dados ausentes, idade/sexo, contiguidade, referência de amplitude,
cache, preservação de amostras e ausência de inferência automática. As sete capturas
locais são verificadas em memória, com comparação visual das 37 curvas e medição
do tempo até a interface renderizada. Não se guardam imagens ou resultados pessoais.
A revisão visual e esses testes não constituem validação clínica independente.

Referências dos critérios:

- [AHA/ACCF/HRS, parte IV — ST/T e QT](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.014).
- [AHA/ACCF/HRS, parte V — critérios de P](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.015).
- [Definição universal de infarto de 2018 — critérios eletrocardiográficos](https://doi.org/10.1093/eurheartj/ehy462); usados como descritores, sem diagnóstico de infarto.
- [ESC — diferença entre tangente e retorno à base](https://www.escardio.org/communities/councils/genomics/scientific-documents-and-publications/cardiogenomics-insights/volume-9/how-to-measure-the-qt-interval).
