"""Soil Analyzer: laudo de análise de solo -> plano de calagem e adubação, com histórico por talhão.

Rodar:  programa instalado (Soil_Analyzer.exe), abrir_dashboard.bat ou python -m streamlit run app.py
Dados:  pasta em ANALISE_SOLO_DADOS (padrão: Documentos\\Soil Analyzer)
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from solo import NOME, __version__  # noqa: E402
from solo.exportar import gerar_pdf, gerar_xlsx  # noqa: E402
from solo.historico import Historico, comparar, meses_entre  # noqa: E402
from solo.leitor import ROTULOS, ModeloColunas, ler_laudo, reaplicar, registrar_correcoes  # noqa: E402
from solo.motor import recomendar  # noqa: E402
from solo.regras import (BORAX, CULTURA_POR_ROTULO, CULTURAS, KCL, NIVEIS, NPK, P2O5_FOSFATADO_PADRAO, ROT,  # noqa: E402
                         SSP, br, br_kg)

PASTA = Path(os.environ.get("ANALISE_SOLO_DADOS") or Path.home() / "Documents" / NOME)
NO_NAVEGADOR = sys.platform == "emscripten"  # versão online: Python no navegador (stlite/Pyodide)
CORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CAMPO_POR_ROTULO = {v: k for k, v in ROTULOS.items()}

st.set_page_config(page_title=f"{NOME} · solo → adubação", page_icon="🌱", layout="wide")
hist = Historico(PASTA)


@st.cache_resource(show_spinner="Preparando o reconhecedor de colunas (só na primeira vez)...")
def carregar_modelo(_versao_aprendizado: float) -> ModeloColunas:
    return ModeloColunas(hist.arq_aprendizado, hist.arq_modelo)


def modelo() -> ModeloColunas:
    versao = hist.arq_aprendizado.stat().st_mtime if hist.arq_aprendizado.exists() else 0.0
    return carregar_modelo(versao)


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header(f"🌱 {NOME}")
    st.caption("Laudo de solo → calagem e adubação")
    nivel = st.radio("Nível de adubação", list(NIVEIS), format_func=NIVEIS.get,
                     help="Econômico: mantém o pasto com menos adubo (menos lotação). "
                          "Nível médio: mais produção de capim, mais adubo.")
    so_kcl = st.checkbox("Pastagens em manutenção só com cloreto de potássio",
                         help="Repõe o potássio sem comprar nitrogênio. O pasto se mantém, mas produz menos capim.")
    prnt = st.number_input("PRNT do calcário (%)", 50, 130, 95)
    p2o5_pct = st.number_input(
        "P₂O₅ do adubo fosfatado (%)", min_value=1.0, max_value=60.0, value=float(P2O5_FOSFATADO_PADRAO), step=0.5,
        format="%.1f",
        help="Garantia de P₂O₅ (fósforo ativo) escrita no rótulo do saco. Superfosfato simples reativo: 26%; "
             "superfosfato simples comum: 18%; adubo composto: o 2º número da fórmula (ex.: 04-14-08 → 14). "
             "A dose de fósforo é calculada em P₂O₅ e convertida em kg desse adubo. Num composto, o N e o K "
             "que ele traz não são descontados do 25-00-25.")
    with st.expander("Preços (R$ por embalagem)"):
        precos = {
            SSP: st.number_input("Superfosfato simples (saco 50 kg)", 0.0, step=5.0),
            NPK: st.number_input("25-00-25 (saco 50 kg)", 0.0, step=5.0),
            KCL: st.number_input("Cloreto de potássio (saco 50 kg)", 0.0, step=5.0),
            "Calcário": st.number_input("Calcário (tonelada)", 0.0, step=10.0),
            BORAX: st.number_input("Bórax (pacote 1 kg)", 0.0, step=1.0),
        }
        precos = {k: v for k, v in precos.items() if v}
    n_laudos = hist.analises()["laudo_id"].nunique()
    onde = "guardados neste navegador" if NO_NAVEGADOR else f"em `{PASTA}`"
    st.caption(f"Histórico: {n_laudos} laudo(s), {len(hist.talhoes())} talhão(ões).  \nDados {onde}")
    with st.expander("Cópia do histórico (.zip)"):
        st.caption("Guarde uma cópia de segurança ou leve o histórico para outro computador: baixe aqui e "
                   "carregue no outro lado. Carregar substitui o histórico atual.")
        st.download_button("⬇️ Baixar histórico", hist.exportar_zip(), f"historico_solo_{date.today()}.zip",
                           "application/zip", width="stretch")
        zip_up = st.file_uploader("Carregar histórico", type=["zip"], key="zip_historico")
        if zip_up and st.button("Substituir o histórico por este arquivo", width="stretch"):
            try:
                hist.importar_zip(zip_up.getvalue())
                st.session_state.pop("arquivo", None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    st.caption(f"{NOME} {__version__} · freeware · sugestão técnica: valide as doses com um engenheiro agrônomo.")


# ---------------------------------------------------------------- blocos de exibição
def tabela_plano(plano: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({
        "Sigla": plano["sigla"], "Cultura": plano["cultura_rotulo"], "Área (m²)": plano["area_m2"].round(0),
        "P": plano["classe_P"].map(ROT), "K": plano["classe_K"].map(ROT),
        "P₂O₅ (kg/ha)": plano["P2O5_kg_ha"].round(0),
        "Superfosfato (kg)": plano["ssp_kg"].round(0), "Superfosfato (g/m²)": plano["ssp_g_m2"].round(1),
        "25-00-25 no ano (kg)": plano["npk_kg"].round(0), "Parcelas": plano["parcelas"],
        "25-00-25 por vez (g/m²)": (plano["npk_g_m2"] / plano["parcelas"].clip(lower=1)).round(0),
        "Quando (25-00-25)": plano["quando_npk"],
        "Cloreto de K (kg)": plano["kcl_kg"].round(0), "Calcário (kg)": plano["calcario_kg"].round(0),
    })
    if (plano["ssp_a_cada_anos"] > 1).any():
        t.insert(8, "Superfosfato a cada", plano["ssp_a_cada_anos"].map(lambda n: f"{n} anos" if n > 1 else "ano"))
    for col in ("Cloreto de K (kg)", "Calcário (kg)"):
        if not t[col].any():
            t = t.drop(columns=col)
    return t


def mostrar_resultado(res: dict, laudo: pd.DataFrame, comparacao: pd.DataFrame, alertas_hist: list, chave: str):
    st.subheader(f"O que comprar · safra {res['safra']}/{str(res['safra'] + 1)[-2:]}")
    compras = res["compras"]
    if compras.empty:
        st.info("Nenhum produto a comprar com os dados informados.")
    else:
        cols = st.columns(len(compras))
        for col, c in zip(cols, compras.to_dict("records")):
            col.metric(c["produto"], f"{c['embalagens']} × {c['embalagem'].split(' de ')[0]}", f"{br_kg(c['kg'])} kg",
                       delta_color="off")
        custo = compras["custo"].dropna().sum()
        if custo:
            st.markdown(f"**Custo estimado: R$ {br(custo, 2)}** (só dos produtos com preço informado)")

    st.subheader("Quanto aplicar em cada talhão")
    st.dataframe(tabela_plano(res["plano"]), hide_index=True, width="stretch")
    st.caption(f"Superfosfato calculado com {br(res['p2o5_pct'], 1)}% de P₂O₅ (barra lateral). "
               "À mão: g/m² = kg/ha ÷ 10. Pese uma vez quanto cabe na sua caneca ou lata.")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Calendário**")
        st.dataframe(res["calendario"].rename(columns={"sigla": "Talhão"}), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Como aplicar**")
        for cult, nota in sorted({(p["cultura_rotulo"], p["nota"]) for p in res["plano"].to_dict("records")}):
            st.markdown(f"- **{cult}:** {nota}")
    if not res["coqueiros"].empty:
        st.markdown("**Coqueiros** (na coroa, de 0,5 a 2 m do tronco, depois de capinar um círculo de 2 a 2,5 m)")
        st.dataframe(res["coqueiros"][["sigla", "n_plantas", "idade", "ssp_kg", "borax_g", "npk_kg", "parcelas",
                                       "kg_parcela", "ssp_total_kg", "npk_total_kg"]].rename(columns={
            "sigla": "Talhão", "n_plantas": "Coqueiros", "idade": "Idade", "ssp_kg": "Superfosfato kg/planta",
            "borax_g": "Bórax g/planta", "npk_kg": "25-00-25 kg/planta/ano", "parcelas": "Parcelas",
            "kg_parcela": "kg por vez", "ssp_total_kg": "Superfosfato total (kg)",
            "npk_total_kg": "25-00-25 total (kg)"}), hide_index=True, width="stretch")

    if not comparacao.empty or alertas_hist:
        st.subheader("Mudanças desde a análise anterior")
        for a in alertas_hist:
            st.info(a, icon="🔁")
        if not comparacao.empty:
            st.dataframe(comparacao, hide_index=True, width="stretch")
    for a in res["alertas"]:
        st.warning(a, icon="⚠️")

    d1, d2 = st.columns(2)
    sufixo = f"{res['safra']}_{chave}"
    d1.download_button("📄 Baixar relatório (PDF)", gerar_pdf(res, laudo, comparacao, alertas_hist),
                       f"plano_adubacao_{sufixo}.pdf", "application/pdf", width="stretch", key=f"pdf_{chave}")
    d2.download_button("📊 Baixar planilha (Excel)", gerar_xlsx(res, laudo, comparacao, alertas_hist),
                       f"plano_adubacao_{sufixo}.xlsx", width="stretch", key=f"xlsx_{chave}",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def comparar_com_historico(atual: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    tabelas, alertas = [], []
    for r in atual.to_dict("records"):
        ant = hist.anterior(r["sigla"], r["data_laudo"])
        if ant is not None:
            t, a = comparar(pd.Series(r), ant)
            tabelas.append(t.assign(**{"análise anterior": pd.to_datetime(ant["data_laudo"]).strftime("%d/%m/%Y")}))
            alertas += a
    return (pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()), alertas


def grafico_evolucao(df: pd.DataFrame, siglas: list):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    todas = sorted(hist.analises()["sigla"].unique())
    cor = {s: CORES[i % len(CORES)] for i, s in enumerate(todas)}  # cor fixa por sigla, não por ordem de filtro
    paineis = [("pH_agua", "pH em água", []), ("V", "Saturação por bases V%", []),
               ("P", "Fósforo (mg/dm³)", [(10, "baixo ≤ 10"), (20, "médio ≤ 20")]),
               ("K_mg", "Potássio (mg/dm³)", [(45, "baixo ≤ 45"), (90, "médio ≤ 90")])]
    fig = make_subplots(rows=2, cols=2, subplot_titles=[p[1] for p in paineis], vertical_spacing=0.16,
                        horizontal_spacing=0.08)
    for k, (campo, _, limites) in enumerate(paineis):
        lin, col = k // 2 + 1, k % 2 + 1
        for s in siglas:
            d = df[df["sigla"] == s].sort_values("data_laudo")
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(d["data_laudo"]), y=d[campo], mode="lines+markers", name=s, legendgroup=s,
                showlegend=k == 0, line=dict(color=cor[s], width=2),
                marker=dict(size=9, color=cor[s], line=dict(width=2, color="#fcfcfb")),
                hovertemplate=f"<b>{s}</b><br>%{{x|%d/%m/%Y}}: %{{y}}<extra></extra>"), row=lin, col=col)
        for y, rot in limites:
            fig.add_hline(y=y, line=dict(color="#b5b3ad", width=1, dash="dot"), row=lin, col=col,
                          annotation_text=rot, annotation_font=dict(size=10, color="#52514e"),
                          annotation_position="top left")
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#fcfcfb",
                      paper_bgcolor="rgba(0,0,0,0)", hovermode="closest", legend=dict(orientation="h", y=-0.08),
                      font=dict(color="#0b0b0b"))
    datas = sorted(pd.to_datetime(df.loc[df["sigla"].isin(siglas), "data_laudo"]).unique())
    if len(datas) <= 6:  # poucos laudos: um rótulo por data, sem repetir "09/2026" ao longo do eixo
        fig.update_xaxes(tickvals=datas, tickformat="%d/%m/%Y")
    else:
        fig.update_xaxes(tickformat="%m/%Y")
    fig.update_xaxes(showgrid=False, linecolor="#d5d3cd")
    fig.update_yaxes(gridcolor="#ecebe7", zeroline=False)
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------- abas
aba_nova, aba_fazenda, aba_hist = st.tabs(["📄 Nova análise", "🗺️ Fazenda (recompor tudo)", "📈 Histórico"])

with aba_nova:
    st.markdown("Envie o laudo do laboratório (PDF como o da PESAGRO, ou planilha XLSX/CSV). "
                "As colunas são reconhecidas automaticamente; confira, informe as áreas e veja o plano.")
    arq = st.file_uploader("Laudo de análise de solo", type=["pdf", "xlsx", "xls", "csv"])
    if arq:
        chave_arq = f"{arq.name}_{arq.size}"
        if st.session_state.get("arquivo") != chave_arq:
            try:
                st.session_state.leitura = ler_laudo(arq.getvalue(), arq.name, modelo())
                st.session_state.arquivo = chave_arq
            except Exception as e:  # arquivo sem tabela legível
                st.error(f"Não consegui ler o arquivo: {e}")
                st.stop()
        lei = st.session_state.leitura

        c1, c2 = st.columns(2)
        data_ini = date.fromisoformat(lei.meta["data_laudo"]) if lei.meta.get("data_laudo") else date.today()
        data_laudo = c1.date_input("Data do laudo", data_ini, format="DD/MM/YYYY").isoformat()
        laboratorio = c2.text_input("Laboratório", lei.meta.get("laboratorio", ""))

        conf = lei.colunas.loc[lei.colunas["campo"] != "ignorar", "confianca"]
        with st.expander(f"Como o arquivo foi lido: {len(conf)} colunas reconhecidas por ML "
                         f"(confiança média {br(100 * conf.mean())}%)", expanded=bool((conf < 0.5).any())):
            st.caption("Se alguma coluna estiver errada, troque o campo. Ao salvar no histórico, a correção "
                       "vira exemplo de treino e o reconhecedor aprende o formato desse laboratório.")
            editado = st.data_editor(
                lei.colunas.assign(campo=lei.colunas["campo"].map(ROTULOS))[["cabecalho", "campo", "confianca",
                                                                            "exemplo"]],
                column_config={
                    "cabecalho": st.column_config.TextColumn("Cabeçalho no arquivo"),
                    "campo": st.column_config.SelectboxColumn("Reconhecido como", options=list(ROTULOS.values()),
                                                              required=True),
                    "confianca": st.column_config.ProgressColumn("Confiança", min_value=0, max_value=1,
                                                                 format="percent"),
                    "exemplo": st.column_config.TextColumn("Primeiros valores"),
                },
                disabled=["cabecalho", "confianca", "exemplo"], hide_index=True, width="stretch",
                key=f"mapa_{chave_arq}")
            mapa = {i: CAMPO_POR_ROTULO[r] for i, r in enumerate(editado["campo"])}
            if mapa != dict(enumerate(lei.colunas["campo"])):
                lei = reaplicar(lei, mapa)
                st.session_state.leitura = lei
                st.session_state.mapa_corrigido = True
        for a in lei.avisos:
            st.warning(a)
        st.dataframe(lei.dados, hide_index=True, width="stretch")

        st.markdown("#### Talhões deste laudo")
        casam = hist.casar(list(lei.dados["sigla"]))
        talh = hist.talhoes()
        linhas = []
        for c in casam.to_dict("records"):
            t = talh.get(c["casar_com"], {})
            cult = t.get("cultura", "braquiaria")
            if cult == "braquiaria_formacao" and t.get("desde") and meses_entre(t["desde"], data_laudo) >= 6:
                cult = "braquiaria"  # reforma de uma safra anterior: agora é manutenção
            situacao = {"conhecida": "✅ já analisada", "nova": "🆕 nova",
                        "parecida": f"❓ parecida com {c['casar_com']} ({c['semelhanca']}%)"}[c["situacao"]]
            linhas.append({"Sigla no laudo": c["sigla"], "Situação": situacao, "Usar como": c["casar_com"],
                           "Cultura": CULTURAS[cult], "Área (m²)": t.get("area_m2"),
                           "Coqueiros": int(t.get("coqueiros_n") or 0), "Idade coqueiros": int(t.get("coqueiros_idade") or 7),
                           "Boro (folhas novas deformadas)": bool(t.get("coqueiros_boro", True))})
        st.caption("Siglas já analisadas trazem área e cultura do cadastro. Em \"Usar como\", troque para juntar uma "
                   "grafia diferente (ex.: A-12) ao histórico da sigla certa.")
        tal_ed = st.data_editor(pd.DataFrame(linhas), column_config={
            "Cultura": st.column_config.SelectboxColumn(options=list(CULTURAS.values()), required=True),
            "Área (m²)": st.column_config.NumberColumn(min_value=0, step=100, format="%d"),
            "Coqueiros": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            "Idade coqueiros": st.column_config.NumberColumn(min_value=1, max_value=80, step=1, format="%d anos"),
        }, disabled=["Sigla no laudo", "Situação"], hide_index=True, width="stretch", key=f"tal_{chave_arq}")

        renomear = dict(zip(tal_ed["Sigla no laudo"], tal_ed["Usar como"].fillna(tal_ed["Sigla no laudo"])))
        atual = lei.dados.assign(sigla=lei.dados["sigla"].map(renomear), data_laudo=data_laudo)
        talhoes_ui = {}
        for r in tal_ed.to_dict("records"):
            cult = CULTURA_POR_ROTULO[r["Cultura"]]
            antigo = talh.get(r["Usar como"], {})
            talhoes_ui[r["Usar como"]] = {
                "cultura": cult, "area_m2": float(r["Área (m²)"] or 0), "coqueiros_n": int(r["Coqueiros"] or 0),
                "coqueiros_idade": int(r["Idade coqueiros"] or 7),
                "coqueiros_boro": bool(r["Boro (folhas novas deformadas)"]),
                "desde": antigo.get("desde") if antigo.get("cultura") == cult else data_laudo}

        res = recomendar(atual, talhoes_ui, nivel, prnt, so_kcl, precos, p2o5_pct=p2o5_pct)
        comparacao, alertas_hist = comparar_com_historico(atual)
        st.divider()
        mostrar_resultado(res, atual, comparacao, alertas_hist, "laudo")

        st.divider()
        if st.button("💾 Salvar este laudo e o cadastro dos talhões no histórico", type="primary"):
            hist.registrar(atual.drop(columns="data_laudo"), {"data_laudo": data_laudo, "laboratorio": laboratorio,
                                                              "arquivo": arq.name})
            hist.salvar_talhoes(talhoes_ui)
            registrar_correcoes(hist.arq_aprendizado, lei)
            st.success("Salvo. A aba Fazenda já recompõe o plano com este laudo e o reconhecedor aprendeu o formato.")
            st.session_state.pop("arquivo", None)

with aba_fazenda:
    atuais = hist.atuais()
    if atuais.empty:
        st.info("Ainda não há laudos no histórico. Importe um na aba Nova análise e salve.")
    else:
        st.markdown("Junta **a análise mais recente de cada talhão** (cada sigla pode vir de um laudo diferente) "
                    "e refaz o plano da fazenda inteira.")
        talh = hist.talhoes()
        cad = pd.DataFrame([{
            "Sigla": s, "Laudo de": pd.to_datetime(d).strftime("%d/%m/%Y"),
            "Meses": round(meses_entre(d, date.today().isoformat())),
            "Cultura": CULTURAS[talh.get(s, {}).get("cultura", "braquiaria")],
            "Área (m²)": talh.get(s, {}).get("area_m2"), "Coqueiros": int(talh.get(s, {}).get("coqueiros_n") or 0),
            "Idade coqueiros": int(talh.get(s, {}).get("coqueiros_idade") or 7),
            "Boro (folhas novas deformadas)": bool(talh.get(s, {}).get("coqueiros_boro", True)),
        } for s, d in zip(atuais["sigla"], atuais["data_laudo"])])
        cad_ed = st.data_editor(cad, column_config={
            "Cultura": st.column_config.SelectboxColumn(options=list(CULTURAS.values()), required=True),
            "Área (m²)": st.column_config.NumberColumn(min_value=0, step=100, format="%d"),
            "Coqueiros": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            "Idade coqueiros": st.column_config.NumberColumn(min_value=1, max_value=80, step=1, format="%d anos"),
        }, disabled=["Sigla", "Laudo de", "Meses"], hide_index=True, width="stretch", key="cadastro")
        talhoes_ed = {r["Sigla"]: {
            "cultura": CULTURA_POR_ROTULO[r["Cultura"]], "area_m2": float(r["Área (m²)"] or 0),
            "coqueiros_n": int(r["Coqueiros"] or 0), "coqueiros_idade": int(r["Idade coqueiros"] or 7),
            "coqueiros_boro": bool(r["Boro (folhas novas deformadas)"]),
            "desde": talh.get(r["Sigla"], {}).get("desde")} for r in cad_ed.to_dict("records")}
        if st.button("💾 Salvar cadastro dos talhões"):
            hist.salvar_talhoes(talhoes_ed)
            st.success("Cadastro salvo.")
        res = recomendar(atuais, talhoes_ed, nivel, prnt, so_kcl, precos, p2o5_pct=p2o5_pct)
        st.divider()
        mostrar_resultado(res, atuais, pd.DataFrame(), [], "fazenda")

with aba_hist:
    df = hist.analises()
    if df.empty:
        st.info("Sem laudos salvos ainda.")
    else:
        siglas = sorted(df["sigla"].unique())
        escolha = st.multiselect("Talhões", siglas, default=siglas)
        if escolha:
            grafico_evolucao(df, escolha)
            if df.groupby("sigla")["data_laudo"].nunique().max() < 2:
                st.caption("Com um laudo por talhão, cada linha é um ponto só; a evolução aparece a partir do segundo laudo.")
        mostrar = df[df["sigla"].isin(escolha)].drop(columns=["importado_em"]).sort_values(["data_laudo", "sigla"],
                                                                                          ascending=[False, True])
        st.dataframe(mostrar, hide_index=True, width="stretch")
        with st.expander("Remover um laudo importado por engano"):
            laudo_id = st.selectbox("Laudo", sorted(df["laudo_id"].unique(), reverse=True))
            if st.checkbox(f"Confirmo remover o laudo {laudo_id} do histórico") and st.button("Remover"):
                hist.remover_laudo(laudo_id)
                st.success("Removido.")
                st.rerun()
