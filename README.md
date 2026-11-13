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
  do trecho selecionável. A 25 mm/s, a parte superior mostra 5 segundos:
  D1/D2/D3 à esquerda e aVF/aVL/aVR à direita. D2 contínua mostra até 10 segundos
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

## Avaliação experimental local (0.3.0)

Após abrir ou concluir uma captura, use **Avaliação experimental** na barra lateral.
Há duas avaliações independentes: ECGFounder para I (150 saídas) e DeepPSP/CinC2021
para I–II ou seis derivações de membros (21 saídas em cada checkpoint).
Escolha uma janela contínua de 10 segundos. A tabela preserva os rótulos originais,
permite busca e exportação JSON local. Não há interpretação automática como diagnóstico.

Os scores sigmoid não são probabilidades calibradas. A integração não tem validação
clínica no KardiaMobile. Sem referência documentada de amplitude e polaridade, o
resultado é **inconclusivo**, sem scores. O botão **Registrar referência de escala**
registra uma declaração do usuário; não mede nem verifica a referência. Não marque
essa declaração apenas para desbloquear a análise. A calibração é da captura atual;
salve-a explicitamente se quiser persistir seus metadados.

Os checkpoints são opcionais, separados do instalador. Para preparar outro computador,
com Python 3.11 disponível, execute no código-fonte:

```powershell
python scripts/setup_research.py --target "C:\Users\SEU_USUARIO\AppData\Local\Programs\KardiaOS"
python scripts/validate_research.py
```

O primeiro comando instala o ambiente de pesquisa e baixa exclusivamente pesos públicos
das fontes fixadas, conferindo SHA-256. O segundo testa o código-fonte e requer também
configuração na raiz do repositório (execute setup sem `--target`). Para verificar a
instalação configurada, execute `KardiaOS.exe --research-smoke-test`: usa somente
sinais sintéticos, todos os três checkpoints e o bloqueio de escala não verificada.
O aplicativo não baixa modelos durante a análise e não transmite ECGs.

Contratos de entrada, pré-processamento, fontes, licenças e limites estão em
[docs/research-models.md](docs/research-models.md).

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
