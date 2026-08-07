#!/usr/bin/env python3
"""
verificar.py - Verificação executável dos entregáveis.

Recalcula cada KPI por um caminho independente, direto do arquivo original, e
compara com o valor gravado em analise.json e com o valor impresso no HTML.
Também roda checagens estruturais no dashboard.

Uso:
    python3 verificar.py --analise analise.json --dados base.xlsx \
                         [--aba Planilha1] [--dashboard dashboard.html]

Contrato de analise.json (mínimo):
{
  "fonte": {"arquivo": "base.xlsx", "aba": "Planilha1"},
  "tratamentos": ["removidas 12 linhas duplicadas"],
  "kpis": [
    {"id": "registros", "rotulo": "Registros", "valor": 8310, "formato": "inteiro",
     "verificacao": {"tipo": "contagem"}},
    {"id": "receita", "rotulo": "Receita total", "valor": 1234567.89, "formato": "moeda",
     "verificacao": {"tipo": "soma", "coluna": "VALOR"}},
    {"id": "ticket", "rotulo": "Ticket médio", "valor": 148.6, "formato": "decimal",
     "verificacao": {"tipo": "media", "coluna": "VALOR"}},
    {"id": "clientes", "rotulo": "Clientes únicos", "valor": 412, "formato": "inteiro",
     "verificacao": {"tipo": "distintos", "coluna": "CLIENTE"}},
    {"id": "taxa_ok", "rotulo": "Taxa de sucesso", "valor": 87.4, "formato": "percentual",
     "verificacao": {"tipo": "proporcao", "coluna": "STATUS", "igual": "OK"}}
  ],
  "conclusoes": [{"texto": "...", "etiqueta": "FATO", "variavel": "...",
                  "recorte": "...", "calculo": "...", "valor": "..."}],
  "perguntas":  [{"pergunta": "...", "resposta": "...", "etiqueta": "FATO",
                  "calculo": "...", "recorte": "...", "palavras_chave": []}],
  "analises":   [{"nome": "Previsão", "executada": false, "motivo": "18 pontos < 24"}]
}

Filtro opcional em qualquer verificação:
  "filtro": {"coluna": "REGIAO", "igual": "Sul"}

Saída: relatório no stdout. Código 1 se houver divergência.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from diagnostico import carregar, normalizar_cabecalho, tentar_numero_ptbr

TOLERANCIA = 0.01  # 1%

OK, FALHA, AVISO = "  OK  ", " FALHA", " AVISO"
problemas = []
avisos = []


def log(marca, texto):
    print(f"[{marca}] {texto}")
    if marca == FALHA:
        problemas.append(texto)
    elif marca == AVISO:
        avisos.append(texto)


def numerica(df, coluna):
    """Devolve a coluna como float, tolerando formato pt-BR em texto."""
    if coluna not in df.columns:
        return None
    s = df[coluna]
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    conv, _ = tentar_numero_ptbr(s)
    return conv if conv is not None else pd.to_numeric(s, errors="coerce")


def aplicar_filtro(df, filtro):
    if not filtro:
        return df
    col = filtro.get("coluna")
    if col not in df.columns:
        return None
    s = df[col].astype(str).str.strip()
    if "igual" in filtro:
        return df[s == str(filtro["igual"]).strip()]
    if "em" in filtro:
        return df[s.isin([str(x).strip() for x in filtro["em"]])]
    return df


def recalcular(df, spec):
    """Recalcula um KPI a partir do dataframe. Retorna (valor, descricao) ou (None, erro)."""
    tipo = spec.get("tipo")
    col = spec.get("coluna")
    sub = aplicar_filtro(df, spec.get("filtro"))
    if sub is None:
        return None, f"coluna do filtro não existe: {spec.get('filtro')}"

    if tipo == "contagem":
        return float(len(sub)), f"len(df) com filtro={spec.get('filtro')}"
    if tipo == "distintos":
        if col not in sub.columns:
            return None, f"coluna inexistente: {col}"
        return float(sub[col].nunique(dropna=True)), f"nunique({col})"
    if tipo == "proporcao":
        if col not in sub.columns:
            return None, f"coluna inexistente: {col}"
        s = sub[col].astype(str).str.strip()
        alvo = str(spec.get("igual", "")).strip()
        base = len(s)
        if base == 0:
            return None, "base zero"
        return 100.0 * (s == alvo).sum() / base, f"% de {col} == '{alvo}'"
    if tipo in ("soma", "media", "mediana", "minimo", "maximo"):
        v = numerica(sub, col)
        if v is None:
            return None, f"coluna inexistente ou não numérica: {col}"
        v = v.dropna()
        if v.empty:
            return None, f"coluna sem valores numéricos: {col}"
        f = {"soma": v.sum, "media": v.mean, "mediana": v.median,
             "minimo": v.min, "maximo": v.max}[tipo]
        return float(f()), f"{tipo}({col})"
    return None, f"tipo de verificação desconhecido: {tipo}"


def proximo(a, b):
    if a is None or b is None:
        return False
    if abs(b) < 1e-9:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= TOLERANCIA


def fmt_ptbr(valor, formato):
    """Reproduz a formatação que o dashboard deveria ter usado."""
    def milhar(x, casas):
        s = f"{x:,.{casas}f}"
        return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if formato == "inteiro":
        return [milhar(round(valor), 0)]
    if formato == "moeda":
        return [milhar(valor, 2), "R$ " + milhar(valor, 2)]
    if formato == "percentual":
        return [milhar(valor, 1) + "%", milhar(valor, 1)]
    return [milhar(valor, 1), milhar(valor, 2)]


def normaliza(t):
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


# ---------------------------------------------------------------- checagens

def checar_kpis(analise, df):
    kpis = analise.get("kpis", [])
    if not kpis:
        log(AVISO, "analise.json não declara nenhum KPI verificável")
        return
    print(f"\n--- KPIs ({len(kpis)}) ---")
    for k in kpis:
        rot = k.get("rotulo", k.get("id", "?"))
        spec = k.get("verificacao")
        if not spec:
            log(AVISO, f"KPI '{rot}' sem bloco 'verificacao' — não pôde ser recalculado")
            continue
        calc, desc = recalcular(df, spec)
        if calc is None:
            log(FALHA, f"KPI '{rot}': não foi possível recalcular — {desc}")
            continue
        declarado = k.get("valor")
        if proximo(calc, declarado):
            log(OK, f"{rot}: {declarado} confere ({desc})")
        else:
            log(FALHA, f"KPI '{rot}': analise.json diz {declarado}, "
                       f"recálculo independente deu {round(calc, 4)} ({desc})")


def checar_html(analise, caminho):
    if not caminho or not os.path.exists(caminho):
        log(AVISO, "dashboard.html não informado ou inexistente — checagens de HTML puladas")
        return
    html = open(caminho, encoding="utf-8").read()
    # Separar o que o usuário lê do que é código. Dashboards renderizados em
    # tempo de execução colocam os números no JSON embutido, não no texto.
    codigo = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
    visivel = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    puro = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visivel))
    n = normaliza(puro)
    bruto = normaliza(html)
    print(f"\n--- Dashboard ({len(html):,} bytes) ---".replace(",", "."))

    # KPIs presentes no HTML
    for k in analise.get("kpis", []):
        val, fmtn = k.get("valor"), k.get("formato", "decimal")
        if val is None:
            continue
        alvos = fmt_ptbr(float(val), fmtn)
        cru = repr(float(val)) if float(val) % 1 else str(int(val))
        if any(a in puro for a in alvos):
            log(OK, f"valor do KPI '{k.get('rotulo')}' aparece formatado no HTML")
        elif cru in codigo or str(val) in codigo:
            log(OK, f"KPI '{k.get('rotulo')}' vem do JSON embutido e é formatado "
                    f"em tempo de execução")
        else:
            log(FALHA, f"KPI '{k.get('rotulo')}' = {val} não foi encontrado no HTML — "
                       f"nem como texto pt-BR ({alvos[0]}) nem no JSON embutido")

    # sujeira — apenas no texto visível; 'undefined' e 'NaN' são válidos em código.
    # Fronteira de palavra é obrigatória: "nan" é substring de "financeiro".
    for termo in ("undefined", "nan", "null"):
        if re.search(rf"\b{termo}\b", n):
            log(FALHA, f"o texto visível do HTML contém '{termo}' — resíduo de renderização")
    for termo in ("lorem ipsum", "[object object]", "null%"):
        if termo in n:
            log(FALHA, f"o texto visível do HTML contém '{termo}' — resíduo de renderização")
    if re.search(r"\bTODO\b|\bFIXME\b|\bXXX\b", puro):
        log(FALHA, "o texto visível do HTML contém marcador de pendência (TODO/FIXME/XXX)")

    # Zero dependências externas: nada de CDN. Um <script src> remoto some em rede
    # corporativa e o usuário recebe o dashboard sem gráfico nenhum.
    externos = re.findall(r'src="(https?://[^"]+)"', html)
    externos += re.findall(r'<link[^>]+href="(https?://[^"]+)"', html)
    if externos:
        log(FALHA, f"o dashboard carrega recurso externo: {sorted(set(externos))[:5]} — "
                   f"os gráficos devem ser SVG inline, sem CDN")
    else:
        log(OK, "nenhuma dependência externa — o arquivo funciona offline")

    # gráficos
    n_svg = len(re.findall(r"<svg", bruto))
    if "<canvas" in bruto:
        log(FALHA, "há <canvas> no HTML — o padrão desta skill é SVG inline")
    elif n_svg or "svgbarras" in bruto or "svglinha" in bruto or "svgempilhado" in bruto:
        log(OK, "gráficos renderizados em SVG inline")
    else:
        log(AVISO, "nenhum gráfico encontrado — confirme se isso é intencional "
                   "(nenhuma análise gráfica passou nos limiares)")

    # Assinatura obrigatória no cabeçalho — cláusula inegociável da skill.
    # Compara sem pontuação nem espaços: a marcação pode quebrar o texto em spans.
    compacto = re.sub(r"[^a-z0-9]", "", n)
    tem_nome = "desenvolvedormarcelobritorodrigues" in compacto
    tem_perfil = "linkedinmarcelobrodrigues" in compacto
    if tem_nome and tem_perfil:
        log(OK, "assinatura do autor presente no cabeçalho")
        if "linkedin.com/in/marcelobrodrigues" not in bruto:
            log(AVISO, "assinatura presente, mas sem link para o perfil do LinkedIn")
        if "credito" not in bruto:
            log(AVISO, "assinatura sem a caixa de destaque (classe .credito)")
    else:
        faltando = []
        if not tem_nome:
            faltando.append("'Desenvolvedor: Marcelo Brito Rodrigues'")
        if not tem_perfil:
            faltando.append("'LinkedIn: marcelobrodrigues'")
        log(FALHA, "assinatura obrigatória ausente ou alterada no cabeçalho — falta "
                   + " e ".join(faltando))

    # etiquetas
    for et in ("FATO", "INTERPRETA", "HIP"):
        if et.lower() not in n:
            log(AVISO, f"nenhuma etiqueta contendo '{et}' encontrada nas conclusões")

    # nota honesta do bloco de perguntas
    if analise.get("perguntas"):
        if "foram calculadas a partir dos dados" not in n:
            log(AVISO, "bloco de Perguntas & Respostas sem a nota sobre respostas pré-calculadas")
        for gatilho in ("digite sua pergunta", "faca uma pergunta", "pergunte aos dados"):
            if gatilho in n:
                log(FALHA, f"o HTML sugere entrada de pergunta livre ('{gatilho}'), "
                           "mas um HTML estático não gera respostas")

    # seções vazias. Cuidado: blocos preenchidos por JS têm apenas um id no HTML —
    # se o id é referenciado no código, a seção tem conteúdo em tempo de execução.
    for m in re.finditer(r"<section[^>]*>(.*?)</section>", html, re.S):
        interno = m.group(1)
        baixo = interno.lower()
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", interno)).strip()
        ids = re.findall(r'id="([^"]+)"', interno)
        preenchido_por_js = any(f"'{i}'" in codigo or f'"{i}"' in codigo for i in ids)
        tem_conteudo = ("<canvas" in baixo or "<table" in baixo or "<ul" in baixo
                        or preenchido_por_js or re.search(r"\d", txt) or len(txt) >= 60)
        if not tem_conteudo:
            log(FALHA, f"seção sem conteúdo no HTML: '{txt[:60]}'")

    # formatação en-US vazando
    if re.search(r"\d{1,3}(,\d{3})+\.\d", puro):
        log(AVISO, "há números no formato en-US (1,234.56) — a saída deve ser pt-BR")


def checar_conteudo(analise):
    print("\n--- Conteúdo analítico ---")
    conc = analise.get("conclusoes", [])
    if not conc:
        log(AVISO, "nenhuma conclusão declarada em analise.json")
    for c in conc:
        et = str(c.get("etiqueta", "")).upper()
        if et not in ("FATO", "INTERPRETACAO", "INTERPRETAÇÃO", "HIPOTESE", "HIPÓTESE"):
            log(FALHA, f"conclusão sem etiqueta válida: '{str(c.get('texto'))[:70]}'")
        faltando = [k for k in ("variavel", "recorte", "calculo") if not c.get(k)]
        if faltando:
            log(AVISO, f"conclusão sem rastreabilidade ({', '.join(faltando)}): "
                       f"'{str(c.get('texto'))[:60]}'")
        txt = normaliza(str(c.get("texto", "")))
        if et == "FATO" and re.search(r"\bcausou\b|\bdevido a\b|\bpor causa\b|\bprovocou\b", txt):
            log(FALHA, f"conclusão marcada como FATO afirma causalidade: "
                       f"'{str(c.get('texto'))[:70]}'")

    an = analise.get("analises", [])
    if not an:
        log(AVISO, "analise.json não lista quais análises foram ou não executadas")
    else:
        naoexec = [a for a in an if not a.get("executada")]
        for a in naoexec:
            if not a.get("motivo"):
                log(FALHA, f"análise '{a.get('nome')}' não executada e sem motivo registrado")
        log(OK, f"{len(an)} análises declaradas ({len(naoexec)} não executadas, com motivo)")

    p = analise.get("perguntas", [])
    if p and len(p) < 8:
        log(AVISO, f"apenas {len(p)} perguntas pré-calculadas (a referência pede 8 a 15)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analise", required=True)
    ap.add_argument("--dados", required=True)
    ap.add_argument("--aba", default=None)
    ap.add_argument("--dashboard", default=None)
    args = ap.parse_args()

    analise = json.load(open(args.analise, encoding="utf-8"))

    abas, _ = carregar(args.dados)
    aba = args.aba or analise.get("fonte", {}).get("aba")
    if aba and aba in abas:
        df = abas[aba]
    else:
        df = max(abas.values(), key=len)
        if aba:
            log(AVISO, f"aba '{aba}' não encontrada; usando a maior do arquivo")
    df, _ = normalizar_cabecalho(df)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    print(f"Base relida de forma independente: {len(df)} linhas x {df.shape[1]} colunas")
    if analise.get("tratamentos"):
        print("Atenção: analise.json declara tratamentos aplicados — pequenas diferenças de "
              "contagem podem ser legítimas:")
        for t in analise["tratamentos"]:
            print(f"  - {t}")

    checar_kpis(analise, df)
    checar_conteudo(analise)
    checar_html(analise, args.dashboard)

    print("\n" + "=" * 60)
    if problemas:
        print(f"{len(problemas)} DIVERGÊNCIA(S) — corrigir antes de entregar:")
        for p in problemas:
            print(f"  x {p}")
    if avisos:
        print(f"{len(avisos)} aviso(s):")
        for a in avisos:
            print(f"  ! {a}")
    if not problemas and not avisos:
        print("Nenhuma divergência encontrada.")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
