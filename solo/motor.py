"""Motor de recomendação: do laudo (uma linha por sigla) + cadastro dos talhões ao plano de adubação.

Kit de compra: 25-00-25 + superfosfato simples (+ cloreto de potássio opcional nas pastagens,
bórax para coqueiros, calcário só quando a calagem compensa). O fósforo é recomendado em kg de P2O5
e convertido em kg do adubo fosfatado pela garantia informada (padrão: superfosfato reativo, 26%).
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .historico import idade_meses
from .regras import (BORAX, BORAX_G_PLANTA, COQUEIRO_G_PLANTA, COQUEIRO_PARCELAS, CULTURAS, DOSES, JANELAS,
                     JANELAS_PARCELAS, KCL, KCL_PASTAGEM, MESES_REANALISE, NC_MINIMA, NPK, P2O5_FOSFATADO_PADRAO,
                     PRODUTOS, SACO_KG, SSP, V2_ALVO, br, classe_k, classe_p, classe_ph)

CALCARIO = "Calcário"
NOTAS = {
    "braquiaria": "A lanço com o solo úmido, logo após a saída do gado do piquete.",
    "braquiaria_formacao": ("Superfosfato a lanço logo antes da gradagem leve; semear raso (1–2 cm). "
                            "O 25-00-25 vai 30–45 dias após o capim nascer, nunca junto com a semente."),
    "capiacu": "25-00-25 logo após cada corte, com o solo úmido. Repita a análise todo ano.",
}


def safra(data_laudo: str | None) -> int:
    """Ano de início da safra das chuvas (out-abr) correspondente à data do laudo."""
    d = date.fromisoformat(data_laudo) if data_laudo else date.today()
    return d.year if d.month >= 6 else d.year - 1


def rotulos_janelas(ano: int) -> list[str]:
    return [f"{JANELAS[0]}/{ano}", f"{JANELAS[1]}/{ano}", f"{JANELAS[2]}/{ano + 1}", f"{JANELAS[3]}/{ano + 1}"]


def _fracao_p2o5(p2o5_pct: float) -> float:
    if not p2o5_pct or not 1 <= float(p2o5_pct) <= 60:
        raise ValueError(f"Garantia de P2O5 do adubo fosfatado fora da faixa (1 a 60%): {p2o5_pct}")
    return float(p2o5_pct) / 100


def doses_coqueiro(idade: int, borax: bool = True, p2o5_pct: float = P2O5_FOSFATADO_PADRAO) -> dict:
    n, p2o5, k2o = COQUEIRO_G_PLANTA[min(max(int(idade or 7), 2), 7)]
    npk = round(max(n, k2o) / (PRODUTOS[NPK]["N"] / 100) / 1000, 1)
    ssp = round(p2o5 / _fracao_p2o5(p2o5_pct) / 1000, 1)
    return {"npk_kg": npk, "ssp_kg": ssp, "borax_g": BORAX_G_PLANTA if (borax and (idade or 7) >= 7) else 0,
            "parcelas": COQUEIRO_PARCELAS, "kg_parcela": round(npk / COQUEIRO_PARCELAS, 2),
            "N_g": npk * 250, "P2O5_g": round(ssp * 1000 * _fracao_p2o5(p2o5_pct)), "K2O_g": npk * 250}


def recomendar(atual: pd.DataFrame, talhoes: dict, nivel: str = "economico", prnt: float = 95,
               so_kcl: bool = False, precos: dict | None = None, hoje: date | None = None,
               p2o5_pct: float = P2O5_FOSFATADO_PADRAO) -> dict:
    """atual: uma linha por sigla (colunas do leitor + data_laudo). Retorna tabelas do plano.

    p2o5_pct: garantia de P2O5 (%) do adubo fosfatado usado (superfosfato simples ou composto).
    """
    precos = precos or {}
    fracao = _fracao_p2o5(p2o5_pct)
    D = DOSES[nivel]
    ano = safra(atual["data_laudo"].dropna().max() if "data_laudo" in atual and atual["data_laudo"].notna().any()
                else None)
    janelas = rotulos_janelas(ano)
    plano, coqs, alertas = [], [], []
    for r in atual.to_dict("records"):
        s = r["sigla"]
        t = talhoes.get(s, {})
        cult = t.get("cultura") if t.get("cultura") in CULTURAS else "braquiaria"
        ha = float(t.get("area_m2") or 0) / 10000
        cp, ck = classe_p(r.get("P")), classe_k(r.get("K_mg"))
        npk = D["npk"][cult][ck] if ck else 0
        p2o5, intervalo = D["p2o5"][cult][cp] if cp else (0, 1)
        ssp = p2o5 / fracao  # kg/ha do adubo fosfatado
        kcl = 0
        if so_kcl and cult == "braquiaria" and ck:
            kcl, npk = KCL_PASTAGEM[ck], 0
        parcelas = D["parcelas"][cult] if npk else 0
        idx = JANELAS_PARCELAS[cult].get(parcelas, list(range(parcelas)))
        v2 = V2_ALVO[cult]
        V, T, Ca, Mg = (r.get(k) for k in ("V", "T", "Ca", "Mg"))
        nc = max(0.0, (v2 - V) * T / prnt) if pd.notna(V) and pd.notna(T) else np.nan
        nc_ap = nc if pd.notna(nc) and nc >= NC_MINIMA else 0.0
        ca_mg = Ca / Mg if pd.notna(Ca) and pd.notna(Mg) and Mg else np.nan
        tipo_calc = "calcítico" if pd.notna(ca_mg) and ca_mg < 2 else "dolomítico"
        idade = idade_meses(r.get("data_laudo"), hoje)
        if pd.notna(idade) and idade > MESES_REANALISE[cult]:
            alertas.append(f"{s}: a análise tem {br(idade)} meses; para {CULTURAS[cult].lower()} o ideal é "
                           f"refazer a cada {MESES_REANALISE[cult]} meses.")
        if not ha:
            alertas.append(f"{s}: informe a área em m² para calcular as quantidades.")
        if nc_ap:
            alertas.append(f"{s}: calagem de {br(nc_ap, 2)} t/ha com calcário {tipo_calc} (PRNT {br(prnt)}%), "
                           "60 a 90 dias antes da adubação.")
        if cp is None or ck is None:
            alertas.append(f"{s}: faltam P ou K no laudo; a dose desses nutrientes não foi calculada.")
        nut = {k: npk * PRODUTOS[NPK].get(k, 0) / 100 + kcl * PRODUTOS[KCL].get(k, 0) / 100
               for k in ("N", "P2O5", "K2O")}
        nut["P2O5"] += p2o5  # o N e o K de um composto com P não são descontados
        plano.append({
            "sigla": s, "cultura": cult, "cultura_rotulo": CULTURAS[cult], "area_m2": ha * 10000, "area_ha": ha,
            "data_laudo": r.get("data_laudo"), "idade_analise_meses": idade,
            "pH": r.get("pH_agua"), "classe_pH": classe_ph(r["pH_agua"]) if pd.notna(r.get("pH_agua")) else None,
            "P": r.get("P"), "classe_P": cp, "K_mg": r.get("K_mg"), "classe_K": ck, "V": V, "V_meta": v2,
            "Ca_Mg": ca_mg, "K_pct_CTC": 100 * r.get("K_cmolc", np.nan) / T if pd.notna(T) and T else np.nan,
            "NC_t_ha": nc, "calcario_t_ha": nc_ap, "calcario_tipo": tipo_calc if nc_ap else "",
            "ssp_kg_ha": ssp, "ssp_a_cada_anos": intervalo, "npk_kg_ha": npk, "kcl_kg_ha": kcl,
            "parcelas": parcelas, "npk_kg_ha_parcela": npk / parcelas if parcelas else 0,
            "quando_npk": ", ".join(janelas[j] for j in idx) if parcelas else "",
            "ssp_kg": ssp * ha, "npk_kg": npk * ha, "kcl_kg": kcl * ha, "calcario_kg": nc_ap * 1000 * ha,
            "ssp_g_m2": ssp / 10, "npk_g_m2": npk / 10, "kcl_g_m2": kcl / 10,
            **{f"{k}_kg_ha": v for k, v in nut.items()},
            "nota": NOTAS[cult],
        })
        n_coq = int(t.get("coqueiros_n") or 0)
        if n_coq:
            d = doses_coqueiro(int(t.get("coqueiros_idade") or 7), bool(t.get("coqueiros_boro", True)), p2o5_pct)
            coqs.append({"sigla": s, "n_plantas": n_coq, "idade": int(t.get("coqueiros_idade") or 7), **d,
                         "npk_total_kg": d["npk_kg"] * n_coq, "ssp_total_kg": d["ssp_kg"] * n_coq,
                         "borax_total_kg": d["borax_g"] * n_coq / 1000})

    plano = pd.DataFrame(plano)
    coqueiros = pd.DataFrame(coqs)

    # calendário (áreas em kg/ha; coqueiros em kg/planta)
    cal = []
    for p in plano.to_dict("records"):
        lin = {"sigla": p["sigla"]}
        idx = JANELAS_PARCELAS[p["cultura"]].get(p["parcelas"], list(range(p["parcelas"])))
        for j, jan in enumerate(janelas):
            itens = []
            if j == 0 and p["cultura"] == "braquiaria_formacao":
                itens.append("gradagem leve + semeadura")
            if j == 0 and p["ssp_kg_ha"]:
                itens.append(f"superfosfato {br(p['ssp_kg_ha'])} kg/ha")
            if j == 0 and p["kcl_kg_ha"]:
                itens.append(f"cloreto de potássio {br(p['kcl_kg_ha'])} kg/ha")
            if j in idx and p["parcelas"]:
                itens.append(f"25-00-25 {br(p['npk_kg_ha_parcela'])} kg/ha")
            lin[jan] = "; ".join(itens) or "—"
        cal.append(lin)
    for c in coqs:
        lin = {"sigla": f"{c['sigla']} · coqueiros"}
        idx = JANELAS_PARCELAS["coqueiro"][COQUEIRO_PARCELAS]
        for j, jan in enumerate(janelas):
            itens = []
            if j == 0:
                itens.append(f"superfosfato {br(c['ssp_kg'], 1)} kg/planta")
                if c["borax_g"]:
                    itens.append(f"bórax {br(c['borax_g'])} g/planta")
            if j in idx:
                itens.append(f"25-00-25 {br(c['kg_parcela'], 1)} kg/planta")
            lin[jan] = "; ".join(itens) or "—"
        cal.append(lin)
    calendario = pd.DataFrame(cal)

    # compras
    def soma(df, col):
        return float(df[col].sum()) if not df.empty and col in df else 0.0
    itens = [
        (f"{SSP} ({br(p2o5_pct, 1 if p2o5_pct % 1 else 0)}% P₂O₅)",
         soma(plano, "ssp_kg") + soma(coqueiros, "ssp_total_kg"), SACO_KG, "saco de 50 kg"),
        (NPK, soma(plano, "npk_kg") + soma(coqueiros, "npk_total_kg"), SACO_KG, "saco de 50 kg"),
        (KCL, soma(plano, "kcl_kg"), SACO_KG, "saco de 50 kg"),
        (f"{CALCARIO} (PRNT {br(prnt)}%)", soma(plano, "calcario_kg"), 1000, "tonelada"),
        (BORAX, soma(coqueiros, "borax_total_kg"), 1, "pacote de 1 kg"),
    ]
    compras = []
    for nome, kg, emb, unidade in itens:
        if kg <= 0:
            continue
        n = math.ceil(round(kg / emb, 6))
        preco = precos.get(nome.split(" (")[0])
        compras.append({"produto": nome, "kg": round(kg, 1), "embalagens": n, "embalagem": unidade,
                        "preco_embalagem": preco, "custo": n * preco if preco else None})
    compras = pd.DataFrame(compras, columns=["produto", "kg", "embalagens", "embalagem", "preco_embalagem", "custo"])

    return {"plano": plano, "coqueiros": coqueiros, "calendario": calendario, "compras": compras,
            "alertas": alertas, "safra": ano, "janelas": janelas, "nivel": nivel, "prnt": prnt, "so_kcl": so_kcl,
            "p2o5_pct": p2o5_pct}
