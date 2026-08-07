# Data Intelligence Hub

Skill de análise exploratória para arquivos tabulares. Você envia uma planilha, ela devolve um **dashboard HTML interativo** e um **relatório analítico** — executando apenas as análises que os dados realmente sustentam.

O princípio é simples: se os dados permitem projetar os próximos meses, ela projeta. Se não permitem, ela escreve o motivo em vez de desenhar uma linha que não significa nada.

**Desenvolvedor:** Marcelo Brito Rodrigues · **LinkedIn:** [marcelobrodrigues](https://www.linkedin.com/in/marcelobrodrigues)

---

## Instalação

Copie a pasta `data-hub` para o diretório de skills do Claude:

| Sistema | Caminho |
|---|---|
| Windows | `%APPDATA%\Claude\skills\` |
| macOS / Linux | `~/.claude/skills/` |

Ou, no Cowork, arraste o arquivo `data-hub.skill` para a conversa e clique em **Salvar skill**.

## Uso

Envie a planilha e peça a análise, ou chame direto:

```
/data-hub
```

A skill vai perguntar qual é o seu objetivo, diagnosticar os dados e gerar os arquivos.

Formatos aceitos: `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.tsv` — inclusive CSV brasileiro com separador `;`, acentuação latin-1 e números no formato `1.234,56`.

## O que você recebe

- **`dashboard.html`** — arquivo único, sem dependências externas. Abre com duplo clique, funciona offline. Gráficos em SVG, filtros que recalculam tudo, tabela ordenável e um bloco de perguntas já respondidas.
- **`relatorio_analise.md`** — visão geral, qualidade dos dados, resultados, conclusões, pontos de atenção e questionamentos.
- **`analise.json`** — todos os números calculados, para conferência ou reuso.

## Como ela decide o que analisar

Um script mede os dados antes de qualquer julgamento. Cada análise só entra se passar no seu critério:

| Análise | Critério de entrada |
|---|---|
| Comparar dois grupos | n ≥ 30 em cada grupo |
| Conclusão sobre uma categoria | ≥ 5% dos registros ou n ≥ 30 |
| Correlação | n ≥ 50 e \|r\| ≥ 0,30 |
| Associação entre categorias | toda célula esperada ≥ 5 |
| Tendência temporal | ≥ 12 pontos com mediana ≥ 5 registros cada |
| Sazonalidade | ≥ 2 ciclos completos |
| Previsão | ≥ 24 pontos densos, ≤ 20% de lacunas |
| Pareto | ≥ 10 categorias |
| Percolação | rede origem→destino com ≥ 30 nós e ≥ 100 arestas |

O que não passa aparece no relatório com o limiar que faltou. A ausência de uma análise é um resultado, não uma omissão.

## Garantias

- **Rastreabilidade** — cada conclusão traz variável, recorte, cálculo e valor.
- **Etiquetas** — toda afirmação é marcada como `[FATO]`, `[INTERPRETAÇÃO]` ou `[HIPÓTESE]`.
- **Sem causalidade indevida** — correlação nunca vira causa; o verificador reprova quem tentar.
- **Verificação executável** — os indicadores são recalculados por um caminho independente e comparados com o dashboard antes da entrega.
- **Arquivo original intocado** — nenhuma transformação é aplicada em silêncio.

## Estrutura

```
data-hub/
├── SKILL.md                    fluxo, limiares e regras
├── scripts/
│   ├── diagnostico.py          perfilamento determinístico → perfil.json
│   └── verificar.py            recálculo independente dos KPIs
└── referencias/
    ├── dashboard.md            padrão do HTML e renderizador SVG
    ├── previsao.md             carregado só se a série for apta
    ├── percolacao.md           carregado só se houver rede
    └── relatorio.md            estrutura do relatório
```

## Requisitos

Python 3.10+ com `pandas`, `numpy` e `openpyxl`.

```bash
pip install pandas numpy openpyxl
```

## Uso avulso dos scripts

Os dois scripts funcionam fora da skill:

```bash
python3 scripts/diagnostico.py base.xlsx --out perfil.json
python3 scripts/verificar.py --analise analise.json --dados base.xlsx --dashboard dashboard.html
```

## Licença

MIT.
