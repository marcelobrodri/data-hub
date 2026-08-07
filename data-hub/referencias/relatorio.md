# Relatório analítico

Arquivo `relatorio_analise.md`. Complementa o dashboard — não o repete. O dashboard mostra; o relatório explica e justifica as escolhas.

## Estrutura

Inclua apenas as seções aplicáveis. As de 1 a 7 são sempre aplicáveis.

**1. Visão geral dos dados**
O que são, origem, período coberto, granularidade, volume, abas consideradas e descartadas.

**2. Qualidade dos dados**
Problemas encontrados e o impacto de cada um sobre as conclusões. Toda transformação aplicada, com justificativa. Se alguma análise foi limitada por qualidade, diga qual e por quê.

**3. Principais resultados**
Os fatos mais relevantes, cada um com etiqueta e rastreabilidade (variável · recorte · cálculo · valor).

**4. Análises realizadas**
Uma tabela: análise · executada? · justificativa. Inclua as **não** executadas com o limiar que não foi atingido. Essa tabela é o que separa uma análise honesta de um gerador de gráficos.

| Análise | Executada | Motivo |
|---|---|---|
| Tendência temporal | Sim | 18 pontos mensais, acima do mínimo de 12 |
| Previsão | Não | 18 pontos, abaixo do mínimo de 24 |
| Percolação | Não | Nenhum par de colunas forma rede origem→destino |

**5. Principais conclusões**
Somente o que os dados sustentam. Cada uma etiquetada. Hipóteses claramente separadas dos fatos.

**6. Pontos de atenção**
Anomalias, limitações, comportamentos que exigem cautela na leitura.

**7. Questionamentos**
5 a 10 perguntas de investigação, cada uma ancorada na evidência que a originou.

**8. Previsibilidade** — apenas se houve previsão.
O que foi previsto, por que foi possível, método, validação (MAPE vs. *naïve*), limitações, interpretação.

**9. Exploração de percolação** — apenas se houve.
Por que foi considerada, como a rede foi construída, o que foi encontrado, comparação com grafo aleatório, limitações, e a natureza experimental da abordagem.

## Tom

Direto e verificável. Sem adjetivos de impacto ("resultado impressionante", "crescimento explosivo"). Números em pt-BR. Se algo não pôde ser concluído, escreva a frase inteira dizendo isso — não omita a análise em silêncio.
