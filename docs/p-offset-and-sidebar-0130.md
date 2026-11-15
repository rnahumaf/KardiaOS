# Fim de P e painel lateral — 0.13.0

O método `global-median-5` exige evidência do retorno de P à linha de base
antes de aceitar um candidato ao seu término. A tangente anterior podia
prolongar P quando a projeção apresentava deriva de base após o flanco.

O algoritmo ajusta duas retas contínuas à mediana já suavizada: uma para o
flanco terminal e outra para a base local, permitindo inclinação residual.
Repete o ajuste com uma janela três amostras menor. As transições precisam
concordar em até três amostras, e sua média deve ficar a até seis amostras da
tangente. A estimativa final combina a tangente e a transição. A frequência
nominal é 300 Hz; não existe posição fixa do término em relação ao QRS.

O ajuste exige queda na direção esperada, base com inclinação de no máximo
40% da inclinação do flanco e redução do erro quadrático para no máximo 65%
do ajuste por uma reta única. Esses parâmetros são critérios técnicos do
algoritmo, sem qualificação clínica. As estimativas intermediárias e os
motivos de rejeição acompanham os candidatos locais.

Um candidato terminal sem sustentação deixa de participar apenas do fim
global de P. Seu início pode continuar válido. Uma componente terminal
sustentada em uma única derivação continua elegível; não se exige maioria.
Sem nenhum término válido, a duração fica indisponível e a curva permanece
visível. Os controles de estabilidade da versão 0.12.0 continuam ativos.

## QTcF e interface

As condições de aplicação de Fridericia permanecem iguais: QT e QRS
disponíveis, QRS menor que 120 ms, pelo menos quatro RR, mediana de RR entre
600 e 1500 ms e coeficiente de variação de RR de no máximo 10%. A sequência
original completa continua alimentando RR, frequência e ritmo.

O motivo de indisponibilidade enumera as condições que falharam. A
variabilidade é o desvio padrão populacional dividido pela média dos RR,
apresentada em percentual. O programa distingue ausência de sexo de
referência e ausência de QTcF na classificação.

A tela inicial apresenta as seis medidas em uma tabela fixa de duas colunas
na lateral direita. A justificativa do QTcF aparece abaixo da tabela. Os
controles de aquisição e processamento rolam independentemente. Alertas de
qualidade por medida e suas explicações permanecem disponíveis.

## Verificação

- 289 testes passaram, incluindo sinais sintéticos com mudança de ganho,
  polaridade, posição temporal e deriva da base; candidatos terminais
  sustentados e rejeitados; equivalência das condições anteriores do QTcF;
  motivo de indisponibilidade e posicionamento da tabela.
- As sete capturas locais disponíveis foram revisadas em memória, com
  comparação visual antes/depois das 37 curvas. A revisão verificou também
  preservação dos demais marcos, das amostras e dos arquivos de origem.
- A tabela foi inspecionada em 1080 × 760 e 1440 × 920, incluindo medida
  indisponível e avisos de qualidade. Capturas pessoais e resultados
  individuais não acompanham o código nem o instalador.

Essa comparação é uma verificação de engenharia do conjunto disponível,
não uma validação clínica do delineador.
