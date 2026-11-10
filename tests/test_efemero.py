"""Versão sem histórico (SOIL_ANALYZER_EFEMERO=1, a da página online aberta): começa em branco, aceita os
resultados digitados à mão, gera o plano e o PDF e não grava nada.

O st.data_editor não é editável pelo AppTest; um script intermediário troca o editor por uma função que
devolve a tabela com as edições da variável TESTE_EDICOES (JSON coluna -> valores).
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from laudo_sintetico import laudo_pdf
from solo.leitor import montar_digitado
from solo.motor import recomendar

APP = Path(__file__).resolve().parents[1] / "app.py"
INTERMEDIARIO = f'''
import json, os, runpy
import streamlit as st

def _editor(data, *args, **kwargs):
    df = data.copy()
    for col, vals in json.loads(os.environ.get("TESTE_EDICOES", "{{}}")).items():
        if col in df.columns and len(df):
            df[col] = df[col].astype(object)
            for i, v in enumerate(vals[:len(df)]):
                df.at[i, col] = v
    return df

st.data_editor = _editor

_laudo = os.environ.get("TESTE_LAUDO")
if _laudo:
    import io
    from pathlib import Path

    def _uploader(label, *args, **kwargs):
        if not label.startswith("Laudo"):
            return None
        arq = io.BytesIO(Path(_laudo).read_bytes())
        arq.name, arq.size = Path(_laudo).name, len(arq.getvalue())
        return arq
    st.file_uploader = _uploader

runpy.run_path({str(APP)!r}, run_name="__main__")
'''


def test_digitado_calcula_sb_t_v_e_mantem_nomes():
    tabela = pd.DataFrame({"sigla": ["Pasto de cima", "", "Pasto de cima"], "P": [4.0, 12.0, None],
                           "K_mg": [78.2, 50.0, None], "Ca": [2.0, None, None], "Mg": [1.0, None, None],
                           "H_Al": [4.8, None, None], "V": [None, 55.0, None], "T": [None, 7.5, None]})
    dados, avisos = montar_digitado(tabela)
    assert list(dados["sigla"]) == ["Pasto de cima", "Talhão 2", "Pasto de cima (2)"]
    assert dados.loc[0, "K_cmolc"] == pytest.approx(0.2)
    assert dados.loc[0, "SB"] == pytest.approx(3.2)
    assert dados.loc[0, "T"] == pytest.approx(8.0)
    assert dados.loc[0, "V"] == pytest.approx(40)
    assert dados.loc[1, "V"] == 55 and dados.loc[1, "T"] == 7.5  # o que veio digitado não muda
    assert len(avisos) == 1 and avisos[0].startswith("Pasto de cima (2):")

    res = recomendar(dados.iloc[:1].assign(data_laudo="2026-11-10"),
                     {"Pasto de cima": {"cultura": "braquiaria", "area_m2": 10000}}, p2o5_pct=26)
    assert res["plano"].loc[0, "ssp_kg"] > 0  # P 4 mg/dm³ = baixo: leva superfosfato


@pytest.fixture
def app(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    script = tmp_path / "intermediario.py"
    script.write_text(INTERMEDIARIO, encoding="utf-8")
    dados = tmp_path / "dados"
    monkeypatch.setenv("SOIL_ANALYZER_EFEMERO", "1")
    monkeypatch.setenv("ANALISE_SOLO_DADOS", str(dados))
    monkeypatch.setenv("ANALISE_SOLO_CACHE", str(tmp_path / "cache"))

    def rodar(edicoes: dict | None = None, laudo: Path | None = None):
        monkeypatch.setenv("TESTE_EDICOES", json.dumps(edicoes or {}))
        if laudo:
            monkeypatch.setenv("TESTE_LAUDO", str(laudo))
        at = AppTest.from_file(str(script), default_timeout=120)
        at.run()
        assert not at.exception, at.exception
        return at, dados
    return rodar


def test_abre_em_branco_sem_abas_nem_historico(app):
    at, _ = app()
    assert len(at.tabs) == 0
    assert "Nada fica guardado" in " ".join(c.value for c in at.sidebar.caption)
    assert not any("Cópia do histórico" in e.label for e in at.sidebar.expander)
    assert at.text_input[0].value == ""
    assert not at.get("download_button")


def test_digitar_gera_pdf_e_nao_grava_nada(app):
    edicoes = {"Talhão": ["Pasto de cima"], "Cultura": ["Braquiária (manutenção)"], "Área (m²)": [10000],
               "P (mg/dm³)": [4.0], "K (mg/dm³)": [40.0], "pH em água": [5.2], "V%": [35.0],
               "CTC a pH 7 (T)": [6.0]}
    at, dados = app(edicoes)
    modo = next(r for r in at.radio if r.label == "Como informar a análise de solo")
    modo.set_value("Digitar os resultados")
    at.text_input[0].set_value("Sítio Teste")
    at.run()
    assert not at.exception, at.exception
    assert any("O que comprar" in s.value for s in at.subheader)
    rotulos = [b.proto.label for b in at.get("download_button")]
    assert "📄 Baixar relatório (PDF)" in rotulos
    historico = dados / "historico"
    assert not (historico / "analises.csv").exists() and not (historico / "talhoes.json").exists()


def test_talhao_sem_cultura_fica_fora_do_plano(app):
    at, _ = app({"Talhão": ["Sem cultura"], "Área (m²)": [5000], "P (mg/dm³)": [4.0], "K (mg/dm³)": [40.0]})
    next(r for r in at.radio if r.label == "Como informar a análise de solo").set_value("Digitar os resultados")
    at.run()
    assert not at.exception, at.exception
    assert any("Escolha a cultura e informe a área de: Sem cultura" in i.value for i in at.info)
    assert not at.get("download_button")


def test_laudo_pdf_sem_cadastro_previo(app, tmp_path):
    laudo = tmp_path / "laudo_sintetico.pdf"
    laudo.write_bytes(laudo_pdf())
    at, dados = app({"Cultura": ["Capim BRS Capiaçu (capineira)", "Braquiária (manutenção)"],
                     "Área (m²)": [5000, 12000]}, laudo=laudo)
    assert any("Escolha a cultura e informe a área de: P34, P58" in i.value for i in at.info)
    assert "📄 Baixar relatório (PDF)" in [b.proto.label for b in at.get("download_button")]
    assert not (dados / "historico" / "analises.csv").exists()
