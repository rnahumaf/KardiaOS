# Evidência de aquisição — 0.5.0

Este contrato vale para evidência validada/revisada, separada do novo
[perfil operacional assumido](research-profile.md). Selecionar o perfil não
altera nenhum destes estados.

Três estados independentes, por captura:

| Estado | O que informa | O que não estabelece |
| --- | --- | --- |
| Posição física declarada | Usuário declara mãos, seta/logo e contato conforme instruções | Sinal digital do decoder ou mV |
| Convenção do decoder | Referência pareada revisada para I e/ou II; multiplicador explícito | Convenção do outro canal ou amplitude |
| Amplitude | Referência elétrica revisada por canal, vinculada ao fator mV/contagem | Polaridade ou posicionamento |

O decoder M2 usa pares signed int16 little-endian, sem inversão. I+ é x+1 sobre
o bruto; I− é x−1, nunca sinônimo de onda R positiva/negativa. Identidade do canal
e polaridade não são a mesma evidência. Nenhum multiplicador é escolhido pelo
maior score, morfologia ou aparência do QRS.

No perfil Referência por canal, os modelos morfológicos exigem convenção documentada dos canais
usados: I para ECGFounder; I e II para DeepPSP 2L/6L. Se faltar, ficam
indisponíveis, com motivo. Havendo referência revisada, aplica-se uma única
convenção e recalculam-se III/aVR/aVL/aVF a partir dos canais orientados; o bruto
não muda. Um canal conhecido não valida o outro nem suas derivações dependentes.
O traçado mantém o bruto dos canais desconhecidos, explicitamente condicionado
aos estados exibidos. Não são geradas derivações precordiais.

FC e durações de P/QRS/QT/QTc usam DI e limites em valores absolutos. A inversão
global não muda essas estimativas. Elas continuam disponíveis quando os critérios
de sinal/delineação permitem, sem requerer evidência de sinal ou mV. Não são
medidas de amplitude, eixo, ST ou diagnóstico. O relógio continua nominal.

Os modelos normalizam o sinal após filtragem; a falta de calibração de um ganho
comum positivo não gera cenários de sinal. O fator provisório continua explícito.
A normalização não comprova ganhos relativos entre canais, morfologia, calibração
elétrica ou validade clínica. O limite técnico de 20 mV do DeepPSP usa a escala
configurada e pode recusar entradas com escala incorreta. Não é um medidor de mV.
Nenhuma interpretação clínica de amplitudes é disponibilizada sem sua referência.

O modo técnico precisa ser marcado explicitamente e compara I+/I− ou as quatro
combinações de I/II, independentemente do estado de amplitude. É pesquisa de
sensibilidade, não parte do fluxo normal. Não aparece na interface normal. Seus dados podem ser exportados por código, mas nunca reutiliza
o cache normal nem entra na folha padrão. A impressão rejeita resultados técnicos.

## Proveniência e migração

`acquisition_evidence`, schema 1, guarda campos separados `physical`, `decoder`
e `amplitude`. O botão Referência registra apenas o estado selecionado.
Referências de decoder/amplitude exigem canal, método, horário, identificador e
SHA-256 do artefato local, além do SHA-256 das amostras e tempos desta captura.
A convenção registra também a identidade do decoder e o multiplicador. O escopo
atual é somente esta captura; não existe promoção automática para todos os
dispositivos, firmwares ou capturas futuras.

O software registra **revisão humana declarada da referência**; calcular seu hash
não demonstra que o conteúdo seja uma referência correta. O usuário deve ter
comparado uma referência pareada rastreável da mesma captura e canal. Posição
física ou outro ECG sem correspondência simultânea não bastam. O aplicativo não
faz uma validação elétrica automática. Uma revisão documental não é validação
clínica do modelo.

Metadados antigos `amplitude_verified` e `research_calibration` são preservados,
mas não promovidos a prova independente: o checkbox antigo não documentava
canal, multiplicador e pareamento. Abrir um arquivo não altera seu conteúdo.
Novas evidências só persistem ao salvar explicitamente a captura. Mudar o fator
de amplitude invalida a referência de amplitude correspondente, sem invalidar
a convenção do decoder. Mudar amostras/tempos invalida o escopo da referência.
O cache inclui sinal, metadados, versão do contrato e modo de análise.

## Fontes e pendências

- [AliveCor: posicionamento físico](https://alivecor.zendesk.com/hc/en-us/articles/360025942974-How-do-I-take-a-6-Lead-recording-using-my-KardiaMobile-6L).
- [kardia-rs: identidade dos canais, polaridade e volts/contagem ainda não confirmados](https://github.com/ShaneBreazeale/kardia-rs/blob/main/docs/re/kardia-6l.md).
- [ECGFounder: seleção de I e normalização, revisão fixada](https://github.com/PKUDigitalHealth/ECGFounder/blob/04edac702b61c91face519774ddcc0cd712fef23/dataset.py).

As análises anteriores de registros distintos não fornecem uma referência
pareada. Nenhuma captura antiga foi marcada como validada nesta atualização.
Não houve novas capturas, manipulação física de eletrodos ou calibração elétrica.
