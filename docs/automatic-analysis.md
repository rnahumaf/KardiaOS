> Atualização 0.8.0: [fluxo exploratório, templates e fases](exploratory-080.md).
> As descrições 0.6/0.7 abaixo registram o método anterior; seus resultados de
> qualificação permanecem históricos e não são convertidos em validação clínica.

# Métodos e limites — 0.7.0

## Medições experimentais por derivação

FC, P e QRS usam uma cadeia temporal própria de fase zero, a partir do bruto,
com limites por batimento e resultados separados de DI/DII. Não dependem do
filtro visual, do ganho estimado ou da comprovação da convenção elétrica.
QT e QTcF permanecem indisponíveis nesta versão: o método falhou a cobertura
mínima no conjunto reservado LUDB. Não há preenchimento de campos nem ajuste
por score. A aba Limites permite inspecionar os pontos aceitos de P/QRS.

O protocolo, parâmetros, fontes primárias, erros, cobertura, falhas, outliers e
reprodução estão em [medição e validação](measurement-validation.md).
Descrições de QRS são numéricas e restritas à derivação. Bloqueio de ramo
específico, ST e classificação de QTc ficam indisponíveis com seus motivos.

## Hipóteses das redes

O perfil Pesquisa — mV estimados permite os modelos sob pressupostos
operacionais explicitamente separados de evidência. O perfil Referência por
canal exige convenção documentada. A comparação de inversões só existe na API
técnica explícita e nos testes, fora da interface normal e da impressão.
Consulte [perfil operacional](research-profile.md) e [evidências](orientation-evidence.md).

O primeiro trecho tecnicamente aceito de 10 s, buscado a cada 300 amostras (1 s nominal, saltando lacunas), é usado
por modelo. Não é selecionado pelo score. Se nenhum trecho servir, há motivo de
indisponibilidade. Não são preenchidas derivações ou lacunas. Interromper cancela
o subprocesso próprio de inferência e identifica o resultado como parcial.

Pesos, cabeças treinadas, rótulos e pré-processamento permanecem os de
[research-models.md](research-models.md). Os scores são sigmoid não calibrados;
não são comparáveis como confiança entre modelos, janelas ou derivações.
Não há calibração estatística nem validação de domínio KardiaMobile.

## Impressão e instalação

DI em linhas utiliza janelas contíguas de 10 s a 25 mm/s ou 5 s a 50 mm/s. Até
seis linhas podem caber, conforme a amplitude e o ganho; a altura é planejada
antes do desenho. Na prévia, um painel inferior reserva espaço para FC/P/QRS e os campos QT/QTcF indisponíveis e três maiores scores por modelo. Isso reduz a área disponível ao traçado sem mudar o ganho ou a velocidade. Todos os modelos disponíveis são listados, inclusive indisponibilidade; rótulos longos podem ser abreviados e continuam completos na análise. O processamento inicia automaticamente ao abrir a prévia e pode ser interrompido fechando-a. A impressão aguarda sua conclusão. As janelas da análise são explícitas e devem estar contidas no intervalo da folha; resultados de outro sinal ou fora da janela não são impressos. Os limites de cada faixa e o restante não impresso são
informados. Nenhuma amostra é duplicada/perdida nas fronteiras do trecho impresso.
A grade é física, sem ajuste horizontal/vertical para caber. O pulso ocupa 200 ms
e 1 mV segundo a escala declarada, que pode continuar provisória. Amplitude que
não cabe é recusada, não recortada. Nas seis derivações, as faixas superiores
têm 118 mm de sinal, além da área de calibração; DII contínua tem 250 mm.

Os testes Qt são executados com `QT_QPA_PLATFORM=offscreen`, sem interagir com
a sessão gráfica. O instalador verifica processos ativos, não os fecha e não
apaga configurações, capturas ou pesos. Não há backups ou cópias de rollback.
Testes sintéticos e de integração não substituem impressão física, calibração
elétrica/temporal ou validação clínica. Esses itens continuam não verificados.


## Verificação da versão

Os testes cobrem sinais sintéticos com durações conhecidas, inversão/ganho comum,
ruído, sinal ausente/curto, saturação/contato, lacunas e relógio incompatível;
ondas ausentes, QT/T na borda, QRS largo e RR variável; integração Qt offscreen,
reavaliação e interrupção; derivação por canal e modo técnico explícito; página A4 vetorial, cobertura
sem duplicação de amostras, pulso de 200 ms em ambas as velocidades e recusa de
recorte vertical. O fluxo completo foi exercitado com os três checkpoints reais
e entrada sintética, sem usar dados pessoais como fixtures ou publicar scores.
