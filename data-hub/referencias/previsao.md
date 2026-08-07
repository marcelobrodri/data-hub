# Previsão

Leia este arquivo **somente** se `serie_temporal.apta_previsao == true` no perfil. Caso contrário, não há previsão a fazer — escreva no relatório o motivo exato que o diagnóstico registrou em `serie_temporal.motivo` e siga adiante.

Previsão é capacidade opcional. Ausência de previsão é um resultado válido.

## Antes de modelar, responda as seis perguntas

Se qualquer resposta for "não", não modele.

1. Existe uma pergunta de negócio que a previsão ajuda a responder?
2. A série tem estrutura adequada (≥ 24 pontos, ≤ 20% de lacunas)?
3. O comportamento é estável o bastante — sem quebra estrutural no último terço da série?
4. O resultado terá interpretação útil, não apenas uma linha bonita?
5. Existe forma de validar? (sempre existe: *holdout* dos últimos períodos)
6. O horizonte pedido é razoável frente ao histórico? Nunca prever mais que 1/3 do comprimento da série.

## Verificações obrigatórias antes do modelo

- **Lacunas**: reindexe a série na granularidade escolhida. Zeros verdadeiros e ausência de registro são coisas diferentes — decida qual é o caso e declare a decisão.
- **Período final incompleto**: mês/semana em andamento distorce a tendência. Remova-o e diga que removeu.
- **Quebra estrutural**: compare média e desvio do primeiro e do último terço. Diferença de média > 2 desvios do primeiro terço → sinalize e considere usar apenas o regime recente.
- **Sazonalidade**: só investigue com ≥ 2 ciclos completos (24 meses para sazonalidade anual mensal).

## Escolha do método — do mais simples para o mais complexo

Comece pelo mais simples que funcione. Um modelo sofisticado que não supera a linha de base não deve ser apresentado como resultado.

| Situação | Método |
|---|---|
| Linha de base obrigatória | *naïve* (último valor) e média móvel — **sempre calcule**, é o critério de comparação |
| Tendência sem sazonalidade | regressão linear sobre o tempo, ou Holt |
| Tendência com sazonalidade e ≥ 2 ciclos | Holt-Winters (`statsmodels.tsa.holtwinters.ExponentialSmoothing`) |
| Série curta ou ruidosa | apenas média móvel com intervalo empírico |

Não use ARIMA automático, Prophet, gradient boosting ou redes neurais nesta skill. Com as quantidades de dados que essa granularidade permite, eles adicionam opacidade sem adicionar acerto.

## Validação — sem isso, não publique

Separe os últimos 20% dos pontos (mínimo 3) como *holdout*. Treine no restante, preveja o holdout, e calcule:

- **MAPE** (ou MAE se houver zeros)
- MAPE do modelo *naïve* no mesmo holdout

Se o modelo não superar o *naïve*, reporte isso honestamente e apresente a projeção *naïve* como referência, ou nenhuma projeção. Um modelo pior que "o próximo valor é igual ao último" não é informação.

## Como apresentar

- Gráfico com histórico e projeção em traço distinto (tracejado), nunca na mesma cor sólida do observado.
- **Intervalo de incerteza sempre visível.** Uma linha de previsão sem banda de incerteza é enganosa.
- Texto obrigatório junto ao gráfico:
  - o que foi previsto e para qual horizonte;
  - por que a previsão foi considerada possível;
  - método utilizado e por que ele, e não outro;
  - MAPE no holdout e comparação com o *naïve*;
  - limitações explícitas (o que quebraria essa projeção).
- Etiqueta `[INTERPRETAÇÃO]`, nunca `[FATO]`. Previsão não é fato.
- Nunca escreva "vai atingir X". Escreva "a projeção aponta X, com erro médio de Y% na validação".
