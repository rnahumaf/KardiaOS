# KardiaOS

Aplicativo Windows para pesquisa com KardiaMobile 6L. Recebe o fluxo BLE M2,
preserva as duas entradas digitais e apresenta D1 ou seis derivações, filtros ajustáveis,
reprodução local e relatório A4 paisagem. Não é um produto da AliveCor.

## Uso

1. Feche o aplicativo Kardia no celular.
2. No seletor **Derivações**, escolha **DI** para usar os dois eletrodos
   superiores. Escolha **6 derivações** ao apoiar também o eletrodo inferior
   na perna esquerda, conforme o fabricante.
3. Clique em **Iniciar**. O programa procura o aparelho e aguarda contato estável.
4. O traçado e o cronômetro começam após a verificação inicial. A duração padrão
   é 30 segundos e pode ser alterada antes de iniciar.
5. O perfil **Pesquisa — mV estimados** preserva a orientação digital e aplica
   ganho empírico 1,5, base 0,5 Hz, passa-baixas 40 Hz e notch 60 Hz. Preferências
   existentes são respeitadas. **Ajuste automático** é opcional.
6. Ao terminar, salve **.kardia** para preservar o bruto, ou exporte o PDF.
   Uma desconexão preserva o trecho recebido. **Abrir captura** permite reprodução
   e novos ajustes. Iniciar outra captura ou fechar oferece salvar os dados.

**Revisar como DI** restringe a exibição, a análise e o laudo de uma captura
existente à primeira derivação durante a sessão. Ao reabrir o arquivo, o
aplicativo usa as derivações registradas nele.

O modo de demonstração é explicitamente sintético. Nunca se mistura a uma sessão BLE.

## Escalas e limites

- A grade usa milímetros calculados a partir da dimensão física informada pelo
  monitor ao Windows. A escala acompanha a tela em que a janela estiver.
  Dados incorretos do monitor produzem erro físico; o diálogo de calibração permite
  conferir e corrigir separadamente os eixos com régua.
- O PDF usa dimensões físicas A4 (297 × 210 mm), grade de 1/5 mm, velocidade
  de 25 ou 50 mm/s e ganho de 5, 10 ou 20 mm/mV. Imprima a 100%, sem ajustar à página.
  Em **Imprimir** e **Exportar PDF**, DI ocupa as linhas do A4 com trechos
  consecutivos. Na escala padrão, uma captura de 30 s ocupa seis linhas de 5 s.
  Se a gravação exceder a capacidade da folha, o intervalo impresso inclui a
  janela automática de 10 s. O cabeçalho identifica os intervalos e a duração
  da gravação. Em seis derivações, as seis linhas mostram os mesmos 10 s.
  Uma onda padrão sustentada aparece em quadrado separado, na mesma escala.
  A prévia de impressão abre ao clicar em **Imprimir**. Menos de 10 s não gera laudo;
  sem qualidade suficiente, há somente traçado. Geometria incompatível com as
  margens ou amplitude bloqueia a saída, sem compressão. A gravação completa
  continua disponível na tela e no arquivo bruto.
- **A amplitude não foi calibrada.** O perfil padrão usa `1,5 × fator base` em
  mV estimados, sem inversão. É uma convenção operacional de pesquisa; não promove
  evidência de amplitude ou polaridade. O perfil Referência por canal continua
  disponível. [Método, filtros e proveniência](docs/research-profile.md).
- Os dois canais M2 são interpretados como I e II conforme a pesquisa de protocolo
  citada abaixo; III, aVR, aVL e aVF são derivados por identidades elétricas.
- O seletor define quais canais podem alimentar as derivações. Dentro desse
  limite, dois bits de cada palavra M2 sinalizam disponibilidade: `00` passa
  na verificação experimental, e os demais códigos bloqueiam o canal. O código
  `00` pode aparecer no segundo canal com dois eletrodos.
  Perda de contato bloqueia imediatamente as derivações dependentes; a recuperação
  exige 500 ms de confirmação, além da verificação de qualidade. D1 permanece
  disponível quando apenas o segundo canal está ausente. A transição física de
  retirada e retorno do eletrodo ainda requer conferência em nova captura.
- O bruto significa valores digitais recebidos do aparelho, não acesso ao ADC
  antes de qualquer processamento interno do fabricante.
- Ao vivo, filtros causais e buffer visual nominal de 60 ms. Na revisão concluída,
  tela/laudo/classificadores do perfil empírico usam filtros de fase zero por
  segmento contínuo, preservando as frequências escolhidas. Isso muda a resposta
  em magnitude em relação ao filtro causal. Latência BLE/hardware e escala
  elétrica não foram aferidas por referência externa.
- Os filtros de base e suavização podem alterar ST, amplitudes e morfologia.
  Não há substituição de batimentos, correção de arritmias ou diagnóstico.
- A heurística de contato identifica saturação, sinal constante e saltos intensos.
  Não é uma classificação clínica validada e pode produzir falsos positivos/negativos.
  Ruído de movimento não pode ser removido integralmente sem risco de alterar o ECG.
- Lacunas de transporte são inferidas por intervalos de chegada acima de 120 ms;
  o formato observado não fornece contador de sequência. Perdas menores podem não
  ser detectadas. Trechos de contato ruim são marcados, não interpolados.
- A grade tem ganho fixo. A revisão permite rolagem vertical para acomodar as
  derivações e amplitudes, sem reduzir o ganho. O bruto continua íntegro.

## Dados locais

O programa não usa contas, telemetria ou nuvem. O usuário escolhe onde salvar.
Arquivos `.kardia` versão 2 contêm `metadata.json`, `raw.npy`, `times.npy`,
`quality.npy` e `lead_modes.npy` (0, 1 ou 6 derivações disponíveis por amostra),
com hashes SHA-256. As amostras originais incluem preparação e contato ruim;
o início aceito e as configurações ficam nos metadados. O processamento não
sobrescreve os valores originais. Não há criptografia do arquivo.
Capturas da versão 1 continuam abrindo; a disponibilidade é inferida dos marcadores
originais. Salvar novamente grava a versão 2, sem alterar os valores recebidos.

Capturas pessoais e relatórios não devem entrar no Git. Os testes usam dados sintéticos.

## Análise local e revisão dos marcos (0.18.1 exploratória)

A gravação completa alimenta um alinhamento comum às derivações: cada batimento
recebe o mesmo deslocamento temporal em todas elas. Batimentos de morfologia
claramente distinta são excluídos do conjunto nas seis derivações, com motivo
visível. Eles continuam na sequência usada para frequência cardíaca e RR.

As medianas por derivação recebem suavização limitada e sustentam os limites globais de P, QRS e T e as
medidas P, QRS, PR, QT e QTc. Os mesmos marcadores aparecem nas curvas, inclusive
quando outra derivação sustenta o limite. A aba Curvas e marcos mostra as medianas e os
batimentos alinhados. Uma medida indisponível não esconde a curva. Não há retorno
à delineação de batimentos isolados nem participação do CompactSegmenter082 nas
medidas operacionais. QTc usa Fridericia, com condições explícitas de aplicação.

O detector procura as rampas iniciais e finais do QRS que se repetem nos
batimentos alinhados. Quando a tangente de P é instável, o motor verifica a
deflexão em diferentes escalas e nos batimentos individuais. Cada intervalo usa
seus próprios limites. Uma P com início e fim sustentados pode ter duração
publicada mesmo quando o QRS não permite medir o PR.

Na tela inicial, clique em **Revisar marcos…** ao lado de **MEDIDAS** para
conferir o início e o fim de P, QRS e T. O editor abre com a mediana inteira
a 100%, na velocidade e no ganho do traçado principal. Posicione o cursor
sobre o trecho desejado e role a roda do mouse para ampliar ou reduzir.
**Tamanho original** volta à escala inicial. Selecione um marco e a derivação,
clique ou arraste na curva e use as setas para ajustar uma amostra por vez
(3,33 ms).
**Dispersão dos batimentos** mostra a faixa entre os percentis 25 e 75 dos
batimentos alinhados. Use **Sem marca** quando o limite continuar duvidoso.
**Confirmar marcos e aplicar** recalcula os intervalos e os critérios
determinísticos a partir dos pontos exibidos. FC e RR vêm da sequência
original. **Salvar bruto** na tela inicial grava a revisão no arquivo
`.kardia`. O editor também está em **Detalhes da análise**, onde
**Salvar captura…** grava a mesma revisão.

O painel inicial mostra classificação e uma tabela lateral compacta com FC, PR,
QRS, QT/QTc e duração de P, acima dos controles de aquisição. Quando o QTcF
está indisponível, o motivo mostra a condição que falhou e, quando aplicável,
a variabilidade dos RR observada e o limite usado pelo programa.
Os controles laterais usam uma linha por configuração, com seletores discretos,
botões destacados e foco visível. O cronômetro mostra as estatísticas de aquisição
em sua dica; o estado da captura e a comparação com o bruto também oferecem
informações auxiliares por dica, sem ocupar a lateral com parágrafos fixos.
Os detalhes da análise seguem o mesmo padrão visual: abas com seleção explícita,
ações compactas, critérios expansíveis com estado destacado e tabelas com linhas
alternadas. Os seletores ficam desabilitados enquanto não há dados disponíveis.
Idade e sexo opcionais ficam no painel e atualizam a análise automaticamente.
O nome do paciente é opcional e pode ser editado durante a captura ou após
**Abrir captura**. **Salvar bruto** grava o nome no arquivo local. O PDF e a
impressão mostram o nome preenchido e a data e hora de início da gravação. Para
capturas antigas, o aplicativo usa a data e a hora registradas no início da
sessão de captura. O cabeçalho reúne FC, duração de P, PR, QRS, QT e QTcF.
**Imprimir** abre a prévia. O usuário pode imprimir diretamente com marcos
automáticos ou, se houver revisão, escolher qual das duas análises usar nessa
impressão. **Exportar PDF** salva a análise ativa. O laudo informa a origem
dos marcos.
A suavização visual padrão é intensa (25 Hz), independente das medidas.

A classificação padrão usa regras locais de ritmo, intervalos e morfologia,
com critérios e motivos de indisponibilidade visíveis. Idade e sexo são opcionais.
Os critérios de amplitude usam milivolts estimados mesmo com instabilidade,
mostrando as limitações. Sem idade informada, comparam com os limiares de adulto
com aviso explícito, também nos critérios de frequência e intervalos. Sem sexo,
QTcF é comparado com ambos os limiares; discordâncias aparecem como possíveis
somente nos detalhes. O ritmo sinusal pode assumir a polaridade exibida, mantendo
as verificações de P, associação P–QRS e qualidade, com motivos específicos.
Quando as lacunas impedem a conclusão sobre a gravação inteira, o aplicativo
pode indicar ritmo regular compatível com sinusal nos trechos válidos. A
conclusão exige concordância entre os trechos avaliados e pelo menos 10 s
contínuos com associação P–QRS sustentada. [Referência sobre tiras contínuas de 10 s para análise de ritmo](https://www.ahajournals.org/doi/pdf/10.1161/circulationaha.106.180200).
Achados da mediana completa alimentam a conclusão. Alterações presentes apenas
em subconjuntos e descrições de P/T bifásicas ou T com entalhe ficam nos detalhes.
A instabilidade dos intervalos também preserva o resultado da mediana completa
com aviso. Marcos ausentes e bloqueios do cálculo de QTc por RR continuam ativos.
O início global de T é preservado nas comparações; sua variação é registrada.

Nos detalhes, clique em um achado ou descrição para abrir sua evidência em
**Curvas e marcos**. Derivações envolvidas ficam empilhadas com escalas comuns;
pontos e faixas numerados correspondem à tabela de valores e limiares. Possibilidades
de subconjuntos sobrepõem suas curvas à mediana completa, com seletor de origem.
Para frequência e regularidade, o gráfico de RR mostra a gravação inteira; clicar
em um RR localiza o trecho de 10 segundos no traçado contínuo.
[Método e apresentação das evidências na versão 0.15.0](docs/evidence-0150.md).
[Revisão dos limites de P e do ritmo na versão 0.16.0](docs/rhythm-0160.md).
[Seleção de derivações e avaliação do ritmo na versão 0.17.0](docs/leads-and-rhythm-0170.md).
[Critérios exploratórios e descrições da versão 0.14.0](docs/exploratory-rules-0140.md).

O botão **Análise neural…** abre a avaliação exploratória e inicia, em sequência,
ECGFounder 1L, DeepPSP 2L e DeepPSP 6L compatíveis com o trecho. Cada configuração
tem uma aba com progresso, scores ou o motivo de indisponibilidade. A execução
não exige referência pareada de polaridade e não valida amplitude nem polaridade.
As redes recebem 10 s contínuos do sinal bruto, na escala de amplitude configurada
e com a polaridade registrada, seguidos do pré-processamento próprio de cada modelo.
Filtros de visualização e o ganho empírico de 1,5 não alteram essa entrada, mesmo
quando o perfil de pesquisa estimada está selecionado. Lacunas, contato inadequado,
escala inválida e derivações ausentes continuam impedindo a execução correspondente.
Ao mudar o trecho, **Reavaliar todos** atualiza os resultados; cada modelo também
pode ser reavaliado separadamente. O JSON registra o contrato de entrada em
`input_contract`, separado das evidências e do perfil de visualização.
A análise padrão por regras não carrega redes nem pesos; sua meta é concluir e
apresentar a classificação em até dois segundos após a captura, com o aplicativo aberto.

Os intervalos são globais das derivações de membros disponíveis, sem precordiais.
A nova abordagem não herda a qualificação histórica do motor temporal nem declara
validação clínica. Os valores permanecem exploratórios; amplitude e polaridade
não recebem validação automática. No papel não se imprime QT bruto.
[Método, exclusões e limites da versão 0.9.0](docs/global-medians-090.md).
[Correção dos marcos e suavização na versão 0.9.1](docs/median-landmarks-091.md).
[Marcos, regras e limites da versão 0.10.0](docs/rules-0100.md).
[Painel inicial, classificação com pendências e fluxos da versão 0.11.0](docs/ui-flows-0110.md).
[Validação histórica do motor temporal](docs/measurement-validation.md).

## Desenvolvimento

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m kardiaos.app
.\.venv\Scripts\python.exe -m kardiaos.app --demo
```

Para testes e empacotamento, instale `pytest`, `pypdf` e `pyinstaller` no ambiente.
As versões utilizadas ficam em `requirements-lock.txt`. Execute:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\build.ps1
```

Para comparar os limites automáticos com as anotações manuais da LUDB 1.0.1,
instale `wfdb` no ambiente de validação e execute o comando abaixo com a pasta
da base. A comparação usa DI e as seis derivações de membros. A divisão fixa
reserva 40 registros para desenvolvimento e 160 para avaliação. O resultado
informa cobertura, erro de início e fim, quantos pares ficaram a até 20 ms da
referência em ambos os limites e quantos apareceram em registros sem anotação
da onda. [Base LUDB no PhysioNet](https://physionet.org/content/ludb/1.0.1/).

```powershell
.\.venv\Scripts\python.exe scripts/validate_median_ludb.py --data C:/dados/ludb/1.0.1 --baseline fa08afdb70 --split held_out
```

O build usa Inno Setup 6 e produz um instalador por usuário, sem exigir Python na
máquina de destino. A distribuição é em diretório para manter bibliotecas Qt
substituíveis. Código-fonte, licenças e instruções acompanham o instalador.
O executável não é assinado digitalmente nesta versão.

## Referências

- Protocolo experimental: https://github.com/ShaneBreazeale/kardia-rs
- Evidências M2: https://github.com/ShaneBreazeale/kardia-rs/blob/main/docs/re/kardia-6l.md
- Filtros causais: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html
- Escalas físicas: https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html

Licença MIT para o código KardiaOS; dependências mantêm suas próprias licenças.

A correção de reprodução, a distinção entre template e QT e a rastreabilidade de P estão em [playback-and-markers-081.md](docs/playback-and-markers-081.md).

[Qualidade técnica por marco e estabilidade entre medianas (0.12.0)](docs/measurement-quality-0120.md).

[Refinamento do fim de P, motivos do QTcF e tabela lateral (0.13.0)](docs/p-offset-and-sidebar-0130.md).
