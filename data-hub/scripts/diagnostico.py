#!/usr/bin/env python3
"""
diagnostico.py - Perfilamento determinístico de arquivos tabulares.

Não interpreta, não conclui, não decide análises. Apenas mede.
O julgamento analítico acontece depois, a partir do JSON produzido aqui.

Uso:
    python3 diagnostico.py <arquivo> [--out perfil.json] [--aba NOME]
"""

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constantes

LIMIARES = {
    "comparar_grupos_n": 30,
    "conclusao_categoria_pct": 5.0,
    "conclusao_categoria_n": 30,
    "correlacao_n": 50,
    "correlacao_r": 0.30,
    "tendencia_pontos": 12,
    "densidade_minima_periodo": 5,
    "sazonalidade_ciclos": 2,
    "qui_quadrado_celula_esperada": 5,
    "previsao_pontos": 24,
    "previsao_lacunas_pct": 20.0,
    "pareto_categorias": 10,
    "grafo_nos": 30,
    "grafo_arestas": 100,
}

PII_PADROES = {
    "cpf": re.compile(r"^\s*\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s*$"),
    "cnpj": re.compile(r"^\s*\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\s*$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$"),
    "telefone": re.compile(r"^\s*\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}\s*$"),
}

PII_NOMES_COLUNA = re.compile(
    r"cpf|cnpj|e-?mail|telefone|celular|fone|nome|cliente|titular|portador|"
    r"endere|logradouro|rg\b|passaporte|matricula|matrícula",
    re.IGNORECASE,
)

NOMES_DATA = re.compile(
    r"data|dt_|_dt|dia|mes|mês|ano|periodo|período|competencia|competência|"
    r"vencimento|emiss|refer|timestamp|hora", re.IGNORECASE
)

NOMES_ID = re.compile(
    r"^id$|_id$|^id_|codigo|código|cod_|_cod|chave|key|protocolo|numero|número|"
    r"num_|nota|documento|uc\b|conta|contrato|os\b|ticket", re.IGNORECASE
)

NUM_PT = re.compile(r"^\s*-?R?\$?\s*\d{1,3}(\.\d{3})*(,\d+)?\s*%?\s*$")
NUM_EN = re.compile(r"^\s*-?R?\$?\s*\d{1,3}(,\d{3})*(\.\d+)?\s*%?\s*$")


# ---------------------------------------------------------------- utilidades

def limpar(o):
    """Torna qualquer estrutura serializável em JSON."""
    if isinstance(o, dict):
        return {str(k): limpar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpar(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, 6)
    if o is pd.NaT or o is None:
        return None
    if isinstance(o, (pd.Timestamp, dt.datetime)):
        return o.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(o, dt.date):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, (dt.time, dt.timedelta)):
        return str(o)
    if isinstance(o, (np.ndarray,)):
        return limpar(o.tolist())
    if isinstance(o, (str, int, bool)):
        return o
    return str(o)  # último recurso: nunca deixar o JSON quebrar


def pct(parte, total):
    return round(100.0 * parte / total, 2) if total else 0.0


def tentar_numero_ptbr(serie):
    """Converte texto numérico pt-BR/en-US para float. Retorna (serie, formato) ou (None, None)."""
    amostra = serie.dropna().astype(str).head(300)
    if amostra.empty:
        return None, None
    pt = amostra.str.match(NUM_PT).mean()
    en = amostra.str.match(NUM_EN).mean()
    if max(pt, en) < 0.90:
        return None, None
    txt = serie.astype(str).str.replace(r"[R$%\s]", "", regex=True)
    if pt >= en:
        txt = txt.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        fmt = "pt-BR"
    else:
        txt = txt.str.replace(",", "", regex=False)
        fmt = "en-US"
    conv = pd.to_numeric(txt, errors="coerce")
    if conv.notna().sum() < serie.notna().sum() * 0.90:
        return None, None
    return conv, fmt


SEP_DATA = re.compile(r"[/\-]|\d{1,2}\s*de\s|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez",
                      re.IGNORECASE)


def tentar_data(serie):
    """Converte para datetime se >=90% dos não-nulos forem parseáveis.

    Guarda-corpo importante: números puros (1, 2, 3...) são aceitos pelo
    to_datetime como epoch e viram 1970-01-01. Uma coluna só é candidata a data
    se os valores contiverem separador de data ou nome de mês.
    """
    nn = serie.dropna()
    if nn.empty:
        return None
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    if pd.api.types.is_numeric_dtype(serie):
        return None
    amostra = nn.astype(str).head(300)
    if amostra.str.contains(SEP_DATA).mean() < 0.90:
        return None
    for dayfirst in (True, False):
        conv = pd.to_datetime(serie, errors="coerce", dayfirst=dayfirst, format="mixed")
        if conv.notna().sum() >= len(nn) * 0.90:
            return conv
    return None


# ---------------------------------------------------------------- leitura

def ler_csv(caminho):
    """Lê CSV/TSV testando encodings e separadores comuns no Brasil."""
    tentativas = []
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (";", ",", "\t", "|"):
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str,
                                 keep_default_na=True, engine="python",
                                 on_bad_lines="skip")
            except Exception:
                continue
            if df.shape[1] > 1 or sep == "|":
                tentativas.append((df.shape[1], enc, sep, df))
    if not tentativas:
        raise RuntimeError("Não foi possível ler o CSV com os encodings/separadores testados.")
    tentativas.sort(key=lambda t: -t[0])
    ncol, enc, sep, df = tentativas[0]
    return {"CSV": df}, {"encoding": enc, "separador": sep}


def ler_excel(caminho):
    xls = pd.ExcelFile(caminho)
    abas = {}
    for nome in xls.sheet_names:
        try:
            abas[nome] = xls.parse(nome, dtype=object)
        except Exception as e:
            abas[nome] = pd.DataFrame({"_erro_leitura": [str(e)]})
    return abas, {"abas_encontradas": xls.sheet_names}


def carregar(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".csv", ".tsv", ".txt"):
        return ler_csv(caminho)
    if ext in (".xlsx", ".xlsm", ".xls", ".xltx"):
        return ler_excel(caminho)
    raise RuntimeError(f"Extensão não suportada: {ext}")


def normalizar_cabecalho(df):
    """Se as primeiras linhas forem lixo, procura a linha de cabeçalho real."""
    if df.empty:
        return df, 0
    col_sem_nome = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
    if col_sem_nome < max(2, len(df.columns) * 0.5):
        return df, 0
    for i in range(min(10, len(df))):
        linha = df.iloc[i]
        preenchidos = linha.notna().sum()
        if preenchidos >= len(df.columns) * 0.7:
            novo = df.iloc[i + 1:].reset_index(drop=True)
            novo.columns = [str(x).strip() if pd.notna(x) else f"col_{j}"
                            for j, x in enumerate(linha)]
            return novo, i + 1
    return df, 0


# ---------------------------------------------------------------- perfil de coluna

def perfilar_coluna(nome, serie, n_linhas):
    nulos = int(serie.isna().sum())
    info = {
        "nome": str(nome),
        "nulos": nulos,
        "pct_nulos": pct(nulos, n_linhas),
        "unicos": int(serie.nunique(dropna=True)),
        "cardinalidade_pct": pct(serie.nunique(dropna=True), max(n_linhas - nulos, 1)),
    }
    nn = serie.dropna()
    info["exemplos"] = limpar(list(nn.head(3).values)) if not nn.empty else []

    if nn.empty:
        info["tipo"] = "vazia"
        info["alerta"] = "coluna totalmente vazia"
        return info, None

    if info["unicos"] == 1:
        info["alerta"] = "valor constante — nenhuma informação discriminante"

    # data?
    conv_data = tentar_data(serie)
    if conv_data is not None and conv_data.notna().sum() > 0:
        d = conv_data.dropna()
        info["tipo"] = "data"
        info["min"] = d.min().strftime("%Y-%m-%d")
        info["max"] = d.max().strftime("%Y-%m-%d")
        info["amplitude_dias"] = int((d.max() - d.min()).days)
        info["dias_distintos"] = int(d.dt.normalize().nunique())
        info["meses_distintos"] = int(d.dt.to_period("M").nunique())
        return info, conv_data

    # numérico?
    conv_num = None
    if pd.api.types.is_numeric_dtype(serie):
        conv_num = pd.to_numeric(serie, errors="coerce")
    else:
        conv_num, fmt = tentar_numero_ptbr(serie)
        if conv_num is not None:
            info["formato_origem"] = fmt

    if conv_num is not None and conv_num.notna().sum() > 0:
        v = conv_num.dropna()
        q1, q3 = float(v.quantile(0.25)), float(v.quantile(0.75))
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        fora = int(((v < lo) | (v > hi)).sum()) if iqr > 0 else 0
        info.update({
            "tipo": "numerica",
            "min": float(v.min()), "max": float(v.max()),
            "media": float(v.mean()), "mediana": float(v.median()),
            "desvio": float(v.std()) if len(v) > 1 else 0.0,
            "q1": q1, "q3": q3,
            "zeros": int((v == 0).sum()),
            "negativos": int((v < 0).sum()),
            "outliers_iqr": fora,
            "pct_outliers": pct(fora, len(v)),
        })
        if info["desvio"] and info["media"]:
            info["cv"] = round(abs(info["desvio"] / info["media"]), 3)
        return info, conv_num

    # categórica
    txt = nn.astype(str).str.strip()
    contagem = txt.value_counts()
    info["tipo"] = "categorica"
    info["top"] = [{"valor": str(k), "n": int(v), "pct": pct(v, n_linhas)}
                   for k, v in contagem.head(15).items()]
    raras = contagem[contagem < LIMIARES["conclusao_categoria_n"]]
    info["categorias_raras"] = int(len(raras))
    info["pct_em_categorias_raras"] = pct(int(raras.sum()), n_linhas)
    info["comprimento_medio"] = round(float(txt.str.len().mean()), 1)

    # variação de caixa / espaços → inconsistência de preenchimento
    if txt.nunique() != txt.str.lower().str.strip().nunique():
        info["alerta_normalizacao"] = (
            "existem valores que diferem apenas por maiúsculas/minúsculas ou espaços"
        )
    return info, None


def detectar_pii(nome, serie):
    achados = []
    if PII_NOMES_COLUNA.search(str(nome)):
        achados.append("nome da coluna sugere dado pessoal")
    amostra = serie.dropna().astype(str).head(200)
    if not amostra.empty:
        for tipo, rx in PII_PADROES.items():
            if amostra.str.match(rx).mean() > 0.5:
                achados.append(f"formato de {tipo} detectado nos valores")
    return achados


# ---------------------------------------------------------------- perfil de tabela

def perfilar_tabela(nome_aba, df):
    df, linhas_puladas = normalizar_cabecalho(df)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    n, m = df.shape

    res = {
        "aba": nome_aba,
        "linhas": int(n),
        "colunas": int(m),
        "linhas_ignoradas_no_topo": linhas_puladas,
        "nomes_colunas": [str(c) for c in df.columns],
        "avisos": [],
    }
    if n == 0 or m == 0:
        res["avisos"].append("tabela vazia")
        res["colunas_detalhe"] = []
        return res

    if n < 10:
        res["avisos"].append(
            f"apenas {n} linhas — provavelmente aba auxiliar, não tabela-fato")

    dup = int(df.duplicated().sum())
    res["duplicatas_linha_completa"] = dup
    res["pct_duplicatas"] = pct(dup, n)
    if dup:
        res["avisos"].append(f"{dup} linhas completamente duplicadas ({pct(dup, n)}%)")

    detalhes, convertidas, pii = [], {}, {}
    for col in df.columns:
        info, conv = perfilar_coluna(col, df[col], n)
        detalhes.append(info)
        if conv is not None:
            convertidas[str(col)] = conv
        p = detectar_pii(col, df[col])
        if p:
            pii[str(col)] = p
    res["colunas_detalhe"] = detalhes
    res["pii_suspeita"] = pii

    tipos = {d["nome"]: d["tipo"] for d in detalhes}
    idx = {d["nome"]: d for d in detalhes}

    cols_data = [c for c, t in tipos.items() if t == "data"]
    cols_num = [c for c, t in tipos.items() if t == "numerica"]
    cols_cat = [c for c, t in tipos.items() if t == "categorica"]

    # Identificadores. Cuidado: métrica contínua também tem cardinalidade alta —
    # uma coluna numérica só é identificador se o nome indicar isso.
    ids = []
    for c, t in tipos.items():
        if t in ("data", "vazia"):
            continue
        card = idx[c]["cardinalidade_pct"]
        nome_id = bool(NOMES_ID.search(c))
        if t == "numerica":
            if nome_id and card > 90:
                ids.append(c)
        elif card > 95 or (nome_id and card > 50):
            ids.append(c)

    for d in detalhes:
        n_ = d["nome"]
        d["papel"] = ("identificador" if n_ in ids else
                      "data" if tipos[n_] == "data" else
                      "metrica" if tipos[n_] == "numerica" else
                      "dimensao" if tipos[n_] == "categorica" else "indefinido")

    # limiar de unicidade proporcional: em base pequena, 4 valores distintos já é métrica
    min_unicos = min(5, max(2, n * 0.1))
    res["candidatos"] = {
        "data": cols_data,
        "metrica": [c for c in cols_num if c not in ids and idx[c]["unicos"] > min_unicos],
        "dimensao": [c for c in cols_cat
                     if c not in ids and 1 < idx[c]["unicos"] <= max(50, n * 0.05)],
        "numerica_usavel_como_dimensao": [c for c in cols_num
                                          if c not in ids and 1 < idx[c]["unicos"] <= 10],
        "identificador": ids,
        "alta_cardinalidade_texto": [c for c in cols_cat
                                     if idx[c]["cardinalidade_pct"] > 80 and c not in ids],
    }

    # ---- aptidão de série temporal
    st = {"apta_tendencia": False, "apta_previsao": False, "motivo": ""}
    if not cols_data:
        st["motivo"] = "nenhuma coluna de data identificada"
    else:
        melhor = max(cols_data, key=lambda c: idx[c]["amplitude_dias"])
        d = convertidas[melhor].dropna()
        st["coluna"] = melhor
        st["periodo"] = {"inicio": idx[melhor]["min"], "fim": idx[melhor]["max"]}
        for rot, freq in (("diaria", "D"), ("semanal", "W"), ("mensal", "M")):
            per = d.dt.to_period(freq)
            pontos = int(per.nunique())
            span = int(per.max().ordinal - per.min().ordinal + 1) if pontos else 0
            lacunas = pct(span - pontos, span) if span else 100.0
            # Densidade: um ponto formado por 1 ou 2 registros é ruído, não sinal.
            # Ter muitos pontos esparsos não torna a série analisável.
            dens = float(per.value_counts().median()) if pontos else 0.0
            densa = dens >= LIMIARES["densidade_minima_periodo"]
            st[rot] = {"pontos": pontos, "periodos_no_intervalo": span,
                       "pct_lacunas": lacunas, "registros_por_periodo_mediana": dens,
                       "densidade_suficiente": densa}
            if pontos >= LIMIARES["tendencia_pontos"] and densa:
                st["apta_tendencia"] = True
                st.setdefault("granularidade_tendencia", rot)
            if (pontos >= LIMIARES["previsao_pontos"] and densa
                    and lacunas <= LIMIARES["previsao_lacunas_pct"]):
                st["apta_previsao"] = True
                st.setdefault("granularidade_previsao", rot)
        if not st["apta_tendencia"]:
            passou_pontos = [r for r in ("diaria", "semanal", "mensal")
                             if st[r]["pontos"] >= LIMIARES["tendencia_pontos"]]
            if passou_pontos:
                st["motivo"] = (
                    "nenhuma granularidade combina volume e densidade: "
                    + "; ".join(f"{r} tem {st[r]['pontos']} pontos mas mediana de "
                                f"{st[r]['registros_por_periodo_mediana']:g} registro(s) por "
                                f"período (mínimo {LIMIARES['densidade_minima_periodo']})"
                                for r in passou_pontos)
                    + "; nas demais granularidades faltam pontos")
            else:
                st["motivo"] = (f"menos de {LIMIARES['tendencia_pontos']} pontos "
                                f"em qualquer granularidade testada")
        elif not st["apta_previsao"]:
            st["motivo"] = (f"tendência possível, mas previsão exige "
                            f"{LIMIARES['previsao_pontos']}+ pontos com "
                            f"<= {LIMIARES['previsao_lacunas_pct']}% de lacunas")
    res["serie_temporal"] = st

    # ---- estrutura de grafo (pré-requisito para percolação)
    grafo = {"apto": False, "pares": []}
    cand = [c for c in tipos
            if tipos[c] in ("categorica", "numerica") and 1 < idx[c]["unicos"] <= n]
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            sub = df[[a, b]].dropna()
            if len(sub) < LIMIARES["grafo_arestas"]:
                continue
            va = set(sub[a].astype(str).str.strip())
            vb = set(sub[b].astype(str).str.strip())
            sobrep = len(va & vb) / max(len(va | vb), 1)
            arestas = int(sub.drop_duplicates().shape[0])
            nos = len(va | vb)
            # Só é grafo de verdade se os dois lados compartilham o mesmo universo
            # de entidades (origem→destino), não duas dimensões independentes.
            if sobrep >= 0.30 and nos >= LIMIARES["grafo_nos"] and arestas >= LIMIARES["grafo_arestas"]:
                grafo["pares"].append({
                    "origem": a, "destino": b, "nos": nos, "arestas": arestas,
                    "sobreposicao_universos": round(sobrep, 3),
                })
                grafo["apto"] = True
    if not grafo["apto"]:
        grafo["motivo"] = (
            "nenhum par de colunas forma rede origem→destino sobre o mesmo universo "
            f"de entidades com >= {LIMIARES['grafo_nos']} nós e "
            f">= {LIMIARES['grafo_arestas']} arestas"
        )
    res["estrutura_grafo"] = grafo

    # ---- correlações entre métricas (só reporta, não conclui)
    corr = []
    metricas = res["candidatos"]["metrica"]
    if len(metricas) >= 2:
        mat = pd.DataFrame({c: convertidas[c] for c in metricas if c in convertidas})
        if mat.shape[1] >= 2:
            cm = mat.corr(numeric_only=True)
            for i, a in enumerate(cm.columns):
                for b in cm.columns[i + 1:]:
                    r = cm.loc[a, b]
                    npar = int(mat[[a, b]].dropna().shape[0])
                    if pd.isna(r):
                        continue
                    corr.append({
                        "a": a, "b": b, "r": round(float(r), 3), "n": npar,
                        "atende_limiar": bool(npar >= LIMIARES["correlacao_n"]
                                              and abs(r) >= LIMIARES["correlacao_r"]),
                    })
            corr.sort(key=lambda x: -abs(x["r"]))
    res["correlacoes"] = corr[:20]

    # ---- associação entre dimensões categóricas (viabilidade de qui-quadrado)
    # Em bases só de categorias, esta é a análise inferencial cabível — e ela tem
    # pré-requisito próprio: toda célula esperada >= 5.
    assoc = []
    dims = res["candidatos"]["dimensao"]
    for i, a in enumerate(dims):
        for b in dims[i + 1:]:
            ct = pd.crosstab(df[a].astype(str).str.strip(), df[b].astype(str).str.strip())
            if ct.size == 0 or ct.values.sum() == 0:
                continue
            tot = ct.values.sum()
            esp = np.outer(ct.sum(axis=1), ct.sum(axis=0)) / tot
            min_esp = float(esp.min())
            baixas = int((esp < LIMIARES["qui_quadrado_celula_esperada"]).sum())
            viavel = bool(min_esp >= LIMIARES["qui_quadrado_celula_esperada"])
            assoc.append({
                "a": a, "b": b, "formato": f"{ct.shape[0]}x{ct.shape[1]}", "n": int(tot),
                "menor_frequencia_esperada": round(min_esp, 2),
                "celulas_esperadas_abaixo_de_5": baixas,
                "total_celulas": int(esp.size),
                "qui_quadrado_viavel": viavel,
                "motivo": "" if viavel else (
                    f"{baixas} de {esp.size} células têm frequência esperada abaixo de "
                    f"{LIMIARES['qui_quadrado_celula_esperada']} (menor: {round(min_esp, 2)}) — "
                    f"o teste não é válido sem agrupar categorias"),
            })
    res["associacoes_categoricas"] = assoc

    # ---- colunas derivadas por aritmética exata (c = a*b, a+b, a-b, a/b)
    # Importante: uma coluna derivada correlaciona perfeitamente com suas parcelas.
    # Reportar isso como "descoberta" seria um artefato, não um resultado.
    derivadas = []
    numcols = [c for c in cols_num if c in convertidas]
    for c in numcols:
        alvo = convertidas[c]
        for i, a in enumerate(numcols):
            if a == c:
                continue
            for b in numcols[i + 1:]:
                if b == c:
                    continue
                va, vb = convertidas[a], convertidas[b]
                for rot, calc in (("produto", va * vb), ("soma", va + vb),
                                  ("diferenca", va - vb), ("diferenca", vb - va)):
                    par = pd.concat([alvo, calc], axis=1).dropna()
                    if len(par) < max(5, n * 0.5):
                        continue
                    if np.allclose(par.iloc[:, 0], par.iloc[:, 1], rtol=1e-6, atol=1e-6):
                        derivadas.append({"coluna": c, "relacao": rot,
                                          "a": a, "b": b, "linhas_conferidas": int(len(par))})
                        break
    res["colunas_derivadas"] = derivadas
    for d_ in derivadas:
        res["avisos"].append(
            f"'{d_['coluna']}' é resultado exato de {d_['a']} {d_['relacao']} {d_['b']} — "
            f"não tratar a correlação entre elas como descoberta")

    # ---- avisos de qualidade
    for d in detalhes:
        if d["pct_nulos"] >= 30:
            res["avisos"].append(f"coluna '{d['nome']}': {d['pct_nulos']}% de valores ausentes")
        if d.get("alerta"):
            res["avisos"].append(f"coluna '{d['nome']}': {d['alerta']}")
        if d.get("alerta_normalizacao"):
            res["avisos"].append(f"coluna '{d['nome']}': {d['alerta_normalizacao']}")
        if d.get("pct_outliers", 0) >= 5:
            res["avisos"].append(
                f"coluna '{d['nome']}': {d['pct_outliers']}% dos valores fora do intervalo IQR")
        if d.get("pct_em_categorias_raras", 0) >= 20 and d.get("papel") != "identificador":
            res["avisos"].append(
                f"coluna '{d['nome']}': {d['pct_em_categorias_raras']}% dos registros estão "
                f"em categorias com menos de {LIMIARES['conclusao_categoria_n']} ocorrências")
    # PII: separar o que foi detectado no VALOR (forte) do que veio só do NOME da
    # coluna (fraco — "cliente" costuma ser pessoa jurídica).
    forte = [c for c, m in pii.items() if any("formato de" in x for x in m)]
    fraco = [c for c in pii if c not in forte]
    if forte:
        res["avisos"].append(
            f"DADO PESSOAL confirmado pelo formato dos valores em: {', '.join(forte)} — "
            f"mascarar antes de gerar o dashboard")
    if fraco:
        res["avisos"].append(
            f"colunas cujo NOME sugere dado pessoal (verificar, pode ser pessoa jurídica): "
            f"{', '.join(fraco)}")

    # ---- porte para embutir no dashboard
    res["porte"] = {
        "linhas": int(n),
        "embutir_dados_brutos": bool(n <= 5000),
        "recomendacao": ("embutir o dataset completo no HTML" if n <= 5000 else
                         "embutir apenas agregados pré-calculados + amostra de 1.000 linhas"),
    }
    return res


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--out", default="perfil.json")
    ap.add_argument("--aba", default=None, help="perfilar apenas uma aba")
    args = ap.parse_args()

    if not os.path.exists(args.arquivo):
        sys.exit(f"Arquivo não encontrado: {args.arquivo}")

    abas, meta = carregar(args.arquivo)
    if args.aba:
        if args.aba not in abas:
            sys.exit(f"Aba '{args.aba}' não existe. Disponíveis: {list(abas)}")
        abas = {args.aba: abas[args.aba]}

    tabelas = [perfilar_tabela(nome, df) for nome, df in abas.items()]

    # abas com mesmo esquema?
    esquemas = {}
    for t in tabelas:
        esquemas.setdefault(tuple(t["nomes_colunas"]), []).append(t["aba"])
    consolidaveis = [v for v in esquemas.values() if len(v) > 1]

    principais = [t for t in tabelas if t["linhas"] >= 10]
    principais.sort(key=lambda t: -t["linhas"])

    perfil = {
        "arquivo": os.path.basename(args.arquivo),
        "tamanho_bytes": os.path.getsize(args.arquivo),
        "leitura": meta,
        "limiares_aplicados": LIMIARES,
        "n_abas": len(tabelas),
        "tabela_fato_sugerida": principais[0]["aba"] if principais else None,
        "abas_auxiliares": [t["aba"] for t in tabelas if t["linhas"] < 10],
        "abas_com_mesmo_esquema": consolidaveis,
        "tabelas": tabelas,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(limpar(perfil), f, ensure_ascii=False, indent=2)

    # resumo legível no stdout
    print(f"Arquivo: {perfil['arquivo']}  |  abas: {perfil['n_abas']}")
    if consolidaveis:
        print(f"Abas com esquema idêntico (candidatas a consolidação): {consolidaveis}")
    for t in tabelas:
        print(f"\n[{t['aba']}] {t['linhas']} linhas x {t['colunas']} colunas")
        if t["linhas"] == 0:
            continue
        c = t.get("candidatos", {})
        print(f"  datas.......: {c.get('data')}")
        print(f"  métricas....: {c.get('metrica')}")
        print(f"  dimensões...: {c.get('dimensao')}")
        print(f"  ids.........: {c.get('identificador')}")
        st = t.get("serie_temporal", {})
        print(f"  série temporal: tendência={st.get('apta_tendencia')} "
              f"previsão={st.get('apta_previsao')} {st.get('motivo','')}")
        viaveis = [f"{x['a']}x{x['b']}" for x in t.get("associacoes_categoricas", [])
                   if x["qui_quadrado_viavel"]]
        if t.get("associacoes_categoricas"):
            print(f"  qui-quadrado viável em: {viaveis or 'nenhum par'}")
        print(f"  grafo/percolação: apto={t.get('estrutura_grafo',{}).get('apto')}")
        if t["avisos"]:
            print("  avisos:")
            for a in t["avisos"][:15]:
                print(f"    - {a}")
    print(f"\nPerfil completo gravado em: {args.out}")


if __name__ == "__main__":
    main()
