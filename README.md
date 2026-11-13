# KardiaOS

Aplicativo Windows para pesquisa com KardiaMobile 6L. Recebe o fluxo BLE M2,
preserva as duas entradas digitais e apresenta D1 ou seis derivações, filtros ajustáveis,
reprodução local e relatório A4 paisagem. Não é um produto da AliveCor.

## Uso

1. Feche o aplicativo Kardia no celular.
2. Mantenha os dedos nos eletrodos superiores para D1. Para seis derivações,
   apoie também o eletrodo inferior na perna esquerda, conforme o fabricante.
3. Clique em **Iniciar**. O programa procura o aparelho e aguarda contato estável.
4. O traçado e o cronômetro começam após a verificação inicial. A duração padrão
   é 30 segundos e pode ser alterada antes de iniciar.
5. **Ajuste automático** escolhe controles de ruído por energia espectral, sem
   classificar ritmo cardíaco. Desmarque para ajustar os filtros manualmente.
6. Ao terminar, salve **.kardia** para preservar o bruto, ou exporte o PDF.
   Uma desconexão preserva o trecho recebido. **Abrir captura** permite reprodução
   e novos ajustes. Iniciar outra captura ou fechar oferece salvar os dados.

O modo de demonstração é explicitamente sintético. Nunca se mistura a uma sessão BLE.

## Escalas e limites

- A grade usa milímetros calculados a partir da dimensão física informada pelo
  monitor ao Windows. A escala acompanha a tela em que a janela estiver.
  Dados incorretos do monitor produzem erro físico; o diálogo de calibração permite
  conferir e corrigir separadamente os eixos com régua.
- O PDF usa dimensões físicas A4 (297 × 210 mm), grade de 1/5 mm, velocidade
  de 25 ou 50 mm/s e ganho de 5, 10 ou 20 mm/mV. Imprima a 100%, sem ajustar à página.
  **Imprimir** e **Exportar PDF** abrem a prévia de uma única folha, com início
  do trecho selecionável. A 25 mm/s, a parte superior mostra as seis derivações:
  D1/D2/D3 à esquerda e aVF/aVL/aVR à direita, com até 4,72 segundos por faixa. D2 contínua mostra até 10 segundos
  abaixo. A 50 mm/s, as durações caem pela metade, sem comprimir o eixo temporal.
  Com apenas D1 disponível no início selecionado, a folha contém somente D1.
  A prévia usa fundo opaco claro e seletor próprio de impressora, sem abrir o diálogo
  do Windows que não recebe a prévia deste fluxo Qt. **Imprimir 1 folha** envia a
  mesma página em uma cópia, sem frente e verso. A gravação bruta completa não é
  reduzida ao trecho impresso.
- **A amplitude inicial não foi calibrada.** O fator `10/65536 mV/contagem`
  é uma inferência experimental, não uma medição. Os relatórios identificam isso.
  A polaridade também requer confirmação externa. A calibração pode ser declarada
  pelo usuário mediante referência conhecida; o programa não verifica essa referência.
- Os dois canais M2 são interpretados como I e II conforme a pesquisa de protocolo
  citada abaixo; III, aVR, aVL e aVF são derivados por identidades elétricas.
- A disponibilidade usa uma interpretação experimental dos dois bits inferiores
  de cada palavra M2: `00` disponível; demais códigos indisponíveis. Dois arquivos
  locais rotulados confirmaram canal 2 com `01` no modo D1 e `00` no modo 6L,
  em todas as amostras aceitas. Isso não constitui documentação oficial do protocolo.
  Perda de contato bloqueia imediatamente as derivações dependentes; a recuperação
  exige 500 ms de confirmação, além da verificação de qualidade. D1 permanece
  disponível quando apenas o segundo canal está ausente. A transição física de
  retirada e retorno do eletrodo ainda requer conferência em nova captura.
- O bruto significa valores digitais recebidos do aparelho, não acesso ao ADC
  antes de qualquer processamento interno do fabricante.
- Os filtros são causais. Há um buffer visual nominal de 60 ms; o atraso do filtro
  depende da frequência e é estimado a 10 Hz na tela. Latência BLE, hardware e total
  não foram medidas por uma referência externa.
- Os filtros de base e suavização podem alterar ST, amplitudes e morfologia.
  Não há substituição de batimentos, correção de arritmias ou diagnóstico.
- A heurística de contato identifica saturação, sinal constante e saltos intensos.
  Não é uma classificação clínica validada e pode produzir falsos positivos/negativos.
  Ruído de movimento não pode ser removido integralmente sem risco de alterar o ECG.
- Lacunas de transporte são inferidas por intervalos de chegada acima de 120 ms;
  o formato observado não fornece contador de sequência. Perdas menores podem não
  ser detectadas. Trechos de contato ruim são marcados, não interpolados.
- A grade tem ganho fixo. Valores fora da faixa vertical são recortados na exibição;
  reduza o ganho para inspecioná-los. O bruto continua íntegro.

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

## Análise automática local (0.4.0)

Após abrir ou concluir uma captura, **Análise automática** calcula as medições
experimentais de DI e avalia os modelos compatíveis no primeiro trecho contínuo
de 10 segundos que passa nas verificações técnicas. Não se escolhe a janela
pelo maior score. A interface separa informação do arquivo, medições e hipóteses
das redes. É possível interromper, reavaliar e exportar o resultado localmente.

As medições incluem FC por RR mediano, duração de P, QRS, QT e QTc Fridericia,
quando o sinal sustenta a delimitação. Campos indisponíveis mostram o motivo.
São estimativas de uma heurística conservadora de template mediano com limites
relativos, sem validação clínica. A base temporal é 300 Hz nominal; não houve
verificação independente do relógio do aparelho. Não se deduz mV ou orientação
a partir de durações ou scores.

ECGFounder usa I e preserva seus 150 rótulos; DeepPSP/CinC2021 tem checkpoints
para I–II e seis derivações de membros, com 21 rótulos cada. Na ausência de uma
referência declarada para a captura, o fluxo exploratório mostra **todas as
hipóteses de sinais**, sem escolher uma como correta: I+/I− ou as quatro
combinações de I/II. As demais derivações de membros são recalculadas para cada
combinação. Não são geradas precordiais. Os cinco maiores scores de cada cenário
são mostrados; a exportação contém todos, incluindo status parcial/interrompido.

Scores sigmoid não são probabilidades, laudos ou diagnósticos. Não há validação
clínica no KardiaMobile. Q anormal não determina área inativa/infarto, e rótulos
temporais não demonstram evolução entre exames. As observações de orientação
de uma captura não são promovidas a calibração universal.

O botão **Referência** mantém a análise dirigida anterior: ela fica inconclusiva
sem referência documentada de amplitude/polaridade. A declaração do usuário não
é medida pelo programa; não a marque para desbloquear resultados. O novo fluxo
exploratório não modifica essa declaração nem os dados originais.

Na prévia de impressão, **DI em linhas** distribui o trecho em linhas sucessivas
numa folha A4. Velocidade, ganho, pulso de 1 mV/200 ms, intervalos de cada linha
e tempo restante ficam explícitos. A 25 mm/s, uma captura usual de 30 s cabe em
três linhas; altura/amplitude, ganho e 50 mm/s podem limitar o trecho que cabe.
Nesse caso a prévia informa o restante. Não há compressão silenciosa nem
recorte vertical: reduza o ganho quando o traçado não couber. Lacunas permanecem
lacunas. O layout automático de seis derivações continua disponível.

Os checkpoints e o ambiente de pesquisa são opcionais, separados do instalador.
Com Python 3.11, no código-fonte distribuído:

```powershell
python scripts/setup_research.py --target "C:\Users\SEU_USUARIO\AppData\Local\Programs\KardiaOS"
```

Somente esse setup explícito baixa dependências e pesos das fontes fixadas e
confere SHA-256. O aplicativo não baixa modelos nem transmite ECGs na análise.
O instalador recusa atualização se encontrar o KardiaOS em execução; salve e
feche sua sessão manualmente antes de atualizar. Dados e preferências não são
removidos. [Limites e métodos de 0.4.0](docs/automatic-analysis.md).

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
