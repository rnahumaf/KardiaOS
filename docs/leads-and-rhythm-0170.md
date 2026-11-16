# Seleção de derivações e avaliação do ritmo

O modo de aquisição é escolhido antes de iniciar e registrado em
`metadata.json`. Em DI, o segundo canal recebido permanece no bruto e todas as
saídas usam somente a primeira derivação. Em seis derivações, a disponibilidade
continua sujeita à verificação de contato por amostra.

**Revisar como DI** é uma opção temporária para capturas com seis derivações
registradas. Ela limita a tela, as medidas, o laudo e as entradas dos modelos
na sessão atual. O modo de revisão participa da chave da análise e fica fora
do arquivo bruto.

A associação P–QRS compara a forma de P na sua própria janela e desconta a
inclinação local da linha de base. Ela usa os batimentos já alinhados. As
medidas e os marcos continuam vindo das medianas. A avaliação requer
concordância em pelo menos 90% dos batimentos e dispersão de até 20 ms.
Trechos que tenham pelo menos cinco batimentos também precisam concordar.

Para admitir uma interrupção breve, o critério de qualidade requer que pelo
menos 90% da gravação tenha sinal elegível e que a maior perda contínua seja
de até dois segundos. Os detalhes mostram o tempo efetivamente analisado.
Cada intervalo RR usa batimentos do mesmo segmento.

Em DI, a relação P–QRS consistente e o RR regular permitem apresentar
**Ritmo regular compatível com sinusal em DI**. Taquicardia continua sendo
avaliada pela FC em relação a 100 bpm. Quando o PR abaixo de 120 ms fica a
até uma amostra do limiar e os marcos são instáveis ou não verificados, o
valor permanece na tabela e aparece nos detalhes como **PR limítrofe**.
