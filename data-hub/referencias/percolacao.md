# Exploração de percolação

Leia este arquivo **somente** se `estrutura_grafo.apto == true` no perfil. Caso contrário, escreva no relatório:

> A teoria da percolação não foi aplicada porque os dados não apresentam estrutura de conectividade: [motivo registrado no diagnóstico].

E siga adiante. Essa é a resposta correta na grande maioria dos datasets tabulares.

## O critério é objetivo

Percolação exige uma **rede**. Uma rede exige duas colunas que apontem para o **mesmo universo de entidades** — origem→destino, cliente→cliente, subestação→subestação, fornecedor→fornecedor. Duas dimensões independentes (produto e região, por exemplo) formam um grafo bipartido de conveniência, não uma rede de propagação, e não justificam a análise.

O diagnóstico já testou: sobreposição de universos ≥ 30%, ≥ 30 nós, ≥ 100 arestas. Se passou, confirme manualmente que a relação faz sentido semântico antes de prosseguir. Um par estatisticamente qualificado mas semanticamente absurdo deve ser descartado — e o descarte, registrado.

## Esta é uma linha experimental

Trate como investigação de fenômeno, nunca como técnica preditiva. Diga isso explicitamente no dashboard e no relatório. Percolação não deve ser usada para fabricar previsibilidade onde os dados temporais não a sustentam.

## Procedimento

1. **Justifique** por que a estrutura sugere propagação, dependência ou comportamento coletivo. Se não conseguir escrever essa justificativa em duas frases concretas, pare aqui.
2. **Defina a rede**: o que é nó, o que é aresta, a aresta é dirigida?, tem peso?
3. **Descreva a topologia** com `networkx`: nº de nós, arestas, densidade, grau médio, distribuição de grau, coeficiente de agrupamento, nº de componentes conexas, tamanho da maior componente.
4. **Identifique clusters** (componentes conexas ou `greedy_modularity_communities`). Compare os clusters com as variáveis do dataset — eles correspondem a alguma dimensão conhecida (região, tipo, período)? Se sim, o cluster pode ser apenas essa variável em outra roupagem: diga isso.
5. **Procure o limiar.** Remova arestas em ordem crescente de peso (ou aleatoriamente, com várias repetições) e acompanhe o tamanho da maior componente. Um colapso abrupto indica limiar de percolação; um declínio suave indica que não há.
6. **Teste contra o acaso.** Gere 100 grafos aleatórios (Erdős–Rényi) com o mesmo nº de nós e arestas e compare agrupamento e tamanho da maior componente. Se a rede observada não se distingue do aleatório, **esse é o resultado** — reporte-o.
7. **Confronte com o resto da análise.** Os nós de maior grau ou centralidade correspondem aos casos que apareceram como anomalia ou concentração nas outras seções?

## Como apresentar

Seção separada, aberta pela frase: *"Análise exploratória — abordagem experimental, sem capacidade preditiva demonstrada."*

Inclua: descrição da rede · métricas topológicas · clusters encontrados e o que eles parecem representar · curva de percolação · comparação com o grafo aleatório · limitações.

Etiquete tudo como `[INTERPRETAÇÃO]` ou `[HIPÓTESE]`. Apenas as métricas topológicas medidas são `[FATO]`.

## O que não fazer

- Não afirme capacidade preditiva sem evidência empírica de que existe.
- Não interprete um limiar como ponto de ruptura operacional sem validação externa.
- Não aplique percolação a séries temporais só porque há "propagação no tempo" — tempo não é rede.
- Não use a análise para justificar uma conclusão que as outras seções não sustentaram.
