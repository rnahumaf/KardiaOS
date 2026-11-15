# Suavização das medianas e revisão dos marcos — 0.9.1

A revisão corrige dois problemas do motor 0.9.0: a derivada de QRS vinha de
uma curva com suavização gaussiana adicional, diferente da curva exibida;
candidatos fracos podiam prolongar os limites globais até oscilações da base.
O alinhamento comum, as exclusões simultâneas, o RR original e as entradas
contínuas dos classificadores seguem o [contrato anterior](global-medians-090.md).

## Curvas usadas nas medidas

Depois dos filtros de fase zero e da mediana ponto a ponto, cada curva recebe
Savitzky–Golay de sete amostras e grau quatro. A mistura entre o resultado e a
mediana anterior limita a alteração de cada amostra a 1,5% da amplitude pico a
pico daquela curva. Portanto, a mudança pico a pico não ultrapassa 3% dessa
amplitude. Esse orçamento vale para a curva inteira, não para cada onda de
baixa amplitude separadamente. Não há renormalização de amplitude.

O filtro é simétrico no interior e usa ajuste polinomial nas bordas. Ele reduz
oscilações rápidas de forma moderada, sem prometer eliminar todo o ruído ou
preservar exatamente cada extremo. Uma filtragem mais intensa pode apagar
componentes pequenos e alterar os limites. Não se acrescenta correção agressiva
da linha de base que possa modificar ST/T.

O detector recebe exatamente as medianas suavizadas mostradas em Limites:
QRS em 0,5–80 Hz e P/T em 0,5–30 Hz. Não há uma segunda suavização gaussiana
oculta. As curvas individuais continuam visíveis. O JSON identifica o método,
a mistura aplicada e a mediana QRS anterior à suavização.

## Candidatos e limites globais

QRS usa a derivada da curva exibida e estima o ruído fora do complexo. O
detector procura transições sustentadas para regiões de baixa atividade e
verifica a estabilidade entre dois limiares. P usa tangentes aos dois flancos
principais; ajustes com três e cinco pontos precisam concordar. Isso evita
estender P até uma oscilação distante. P bifásica ambígua permanece indisponível.

T combina a separação da onda em relação à base e o término por tangente.
Os dois métodos precisam concordar em até 30 ms. Morfologia complexa ou
contraste insuficiente impede que aquela projeção defina o limite.

O motor combina o início mais precoce e o fim mais tardio dos candidatos
aceitos. Rejeita candidatos de contraste muito inferior e extremos fracos
distantes das projeções fortes. Uma projeção forte isolada continua válida:
as seis derivações de membros são dependentes, não seis votos independentes.
O JSON registra candidatos, qualidade, rejeições e derivações que sustentam
cada extremo. Os limites resultantes são compartilhados em todas as curvas.

O método e a chave de cache mudam para `global-median-2`, evitando reutilizar
resultados anteriores. A indisponibilidade de um limite não esconde a mediana.

## Verificação e alcance

Os testes cobrem pulsos de duração conhecida, QRS largo, inversão de polaridade,
ruído, limites da alteração de amplitude, rejeição de extremos fracos e identidade
entre a curva exibida e a entrada do detector. A revisão visual compara a versão
anterior e a nova nas sete capturas locais, com 37 curvas, em visão completa e
com ampliação do QRS. Os arquivos são lidos em memória e permanecem intactos;
nenhuma captura ou medição pessoal integra o repositório.

Essa verificação demonstra comportamento e melhora visual nesses casos. Não
substitui validação clínica independente contra limites anotados por especialistas.
Os limiares continuam exploratórios, e o método anterior fica disponível no
histórico e nos módulos de reprodução.

Referências: [SciPy — Savitzky–Golay](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html)
e [AHA/ACCF/HRS — tecnologia do ECG](https://www.jacc.org/doi/10.1016/j.jacc.2007.01.024).
