# Tela inicial e fluxos de análise — 0.11.0

O painel inicial permanece visível e mostra classificação, FC, PR, QRS, QT,
QTcF e duração de P. Idade e sexo são opcionais, junto ao painel. Ao editar esses
campos ou o perfil de processamento, a análise atualiza automaticamente após
400 ms sem novas alterações. Resultados antigos deixam de aparecer durante a
atualização; respostas de outra captura ou de metadados antigos não são aplicadas.
Os dados opcionais são persistidos somente ao salvar a captura.

O resumo **“Sinusal, regular, normal nos critérios avaliados”** exige suporte
para origem sinusal, RR regular e ausência de achados nos critérios disponíveis.
Critérios indisponíveis continuam indisponíveis, com motivos visíveis abaixo;
não são convertidos em resultados negativos e não tornam toda a análise
inconclusiva. Achados permanecem visíveis mesmo quando outros critérios faltam.
A presença isolada de P ou a regularidade isolada não estabelece ritmo sinusal.
Os limiares e o método de medidas da versão 0.10.0 não mudaram.

**Detalhes da análise** abre três abas:

- **Resumo:** conclusão, achados e pendências agrupadas por motivo; critérios
  técnicos expansíveis, com todos os resultados e fundamentos.
- **Medidas:** intervalos globais e tabela de amplitudes por derivação.
- **Curvas e marcos:** seletor de derivação, medianas e batimentos alinhados,
  com os limites globais preservados.

A suavização visual padrão é **25 Hz · intensa**. Uma preferência visual explícita
fica salva para a próxima abertura. Em capturas concluídas, linha de base,
suavização, interferência, escala e comparação com o bruto afetam a visualização,
sem alterar a captura ou recalcular medidas, marcos e classificação. A análise
continua usando seus filtros próprios e suas medianas. O processamento registrado
na captura e usado no relatório e nas redes opcionais permanece preservado.
Durante a aquisição, os filtros causais continuam disponíveis para o traçado ao vivo.

A prévia de impressão abre exclusivamente por **Imprimir**. Concluir uma captura,
carregar arquivo, recalcular a análise ou ajustar controles não abre essa janela.
**Exportar PDF** solicita diretamente o destino do arquivo e o grava, sem passar
pela prévia. A análise neural continua manual nos detalhes.

Os testes dos fluxos usam somente dados sintéticos. A validação visual cobre a
janela principal em 1080 × 760 e 1440 × 920 e os detalhes em 850 × 650 e 1120 × 760,
com resumo, pendências, tabelas, critérios expandidos e curvas. Não há nova
validação clínica independente nesta versão.
