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
5. O perfil **Pesquisa — mV estimados** preserva a orientação digital e aplica
   ganho empírico 1,5, base 0,5 Hz, passa-baixas 40 Hz e notch 60 Hz. Preferências
   existentes são respeitadas. **Ajuste automático** é opcional.
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
  **Imprimir** e **Exportar PDF** mostram uma janela automática comum de 10 s.
  Seis derivações usam seis linhas sincronizadas; DI isolada usa linhas sucessivas.
  Uma onda padrão sustentada aparece em quadrado separado, na mesma escala.
  A prévia abre automaticamente após a análise. Menos de 10 s não gera laudo;
  sem qualidade suficiente, há somente traçado. Geometria incompatível com as
  margens ou amplitude bloqueia a saída, sem compressão. A gravação completa
  continua disponível na tela e no arquivo bruto.
- **A amplitude não foi calibrada.** O perfil padrão usa `1,5 × fator base` em
  mV estimados, sem inversão. É uma convenção operacional de pesquisa; não promove
  evidência de amplitude ou polaridade. O perfil Referência por canal continua
  disponível. [Método, filtros e proveniência](docs/research-profile.md).
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

## Análise automática local (0.8.0 exploratória)

A janela comum de 10 s é escolhida pela qualidade observada dos canais I/II,
sem consultar escores ou o valor QTc. Os classificadores reais são executados
nessa janela, com resultados ligados às suas amostras exatas. Uma lista única
mostra até três hipóteses e o modelo, sem números de score. Duplicatas equivalentes
mantêm o maior score bruto; isso não é consenso nem probabilidade calibrada.

FC/P/QRS mantêm o motor temporal 0.7.0. QTc exploratório combina limites da rede
própria treinada e template da morfologia predominante, com abstenção por qualidade
e discordância. A fórmula é Fridericia, sempre identificada. A saída numérica traz
derivação e `baixa confiança`; sem estimativa, `QTc: erro na estimativa`.
No papel não se imprime QT bruto. Não há edição manual de marcos.

A qualificação clínica de QT continua reprovada: a política exploratória é
separada e não declara aprovação do gate 0.7.0. mV e polaridade do decoder não
recebem validação automática. Não se produzem medidas para completar a página.
[Métodos, limiares, evidência, filtros e limites](docs/exploratory-080.md).
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
