"""Histórico de análises por sigla (talhão) e cadastro de cada talhão (área, cultura, coqueiros).

Tudo fica em arquivos simples na pasta de dados, para abrir no Excel se precisar:
    historico/analises.csv            uma linha por amostra de cada laudo
    historico/talhoes.json            área (m²), cultura e coqueiros de cada sigla
    historico/aprendizado_colunas.csv correções de leitura confirmadas (treino do modelo)
"""
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .leitor import NUMERICOS
from .regras import ROT, br, classe_k, classe_p

COLUNAS = ["laudo_id", "data_laudo", "laboratorio", "arquivo", "sigla", "prof_cm", "textura", *NUMERICOS,
           "importado_em"]


class Historico:
    def __init__(self, pasta_dados):
        self.pasta = Path(pasta_dados) / "historico"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arq_analises = self.pasta / "analises.csv"
        self.arq_talhoes = self.pasta / "talhoes.json"
        self.arq_aprendizado = self.pasta / "aprendizado_colunas.csv"
        # cache do modelo treinado (~20 MB) fica fora da pasta de dados (que pode estar sincronizada
        # na nuvem); é refeito sozinho se sumir
        local = (os.environ.get("ANALISE_SOLO_CACHE")
                 or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Soil Analyzer" / "cache")
        self.arq_modelo = Path(local) / "modelo_colunas.joblib"

    # ---- análises
    def analises(self) -> pd.DataFrame:
        if not self.arq_analises.exists():
            return pd.DataFrame(columns=COLUNAS)
        df = pd.read_csv(self.arq_analises, dtype={"sigla": str, "laudo_id": str, "prof_cm": str, "textura": str,
                                                   "laboratorio": str, "arquivo": str, "data_laudo": str})
        return df.sort_values(["sigla", "data_laudo"]).reset_index(drop=True)

    def registrar(self, dados: pd.DataFrame, meta: dict) -> str:
        """Grava as amostras de um laudo. Reimportar o mesmo laudo substitui as linhas antigas."""
        data = meta.get("data_laudo") or date.today().isoformat()
        lab = re.sub(r"[^A-Za-z0-9]+", "", meta.get("laboratorio") or "") or "lab"
        laudo_id = f"{data}_{lab}"
        novas = dados.copy()
        novas["laudo_id"], novas["data_laudo"] = laudo_id, data
        novas["laboratorio"], novas["arquivo"] = meta.get("laboratorio", ""), meta.get("arquivo", "")
        novas["importado_em"] = datetime.now().isoformat(timespec="seconds")
        novas = novas.reindex(columns=COLUNAS)
        antigas = self.analises()
        chave = set(zip(novas["data_laudo"], novas["sigla"], novas["prof_cm"].fillna("")))
        manter = [(d, s, p) not in chave for d, s, p in zip(antigas["data_laudo"], antigas["sigla"],
                                                             antigas["prof_cm"].fillna(""))]
        tudo = pd.concat([antigas[manter], novas], ignore_index=True)
        tudo.to_csv(self.arq_analises, index=False, encoding="utf-8")
        return laudo_id

    def remover_laudo(self, laudo_id: str):
        df = self.analises()
        df[df["laudo_id"] != laudo_id].to_csv(self.arq_analises, index=False, encoding="utf-8")

    def atuais(self) -> pd.DataFrame:
        """A análise mais recente de cada sigla (0-20 cm quando houver mais de uma camada)."""
        df = self.analises()
        if df.empty:
            return df
        df = df.assign(_raso=~df["prof_cm"].fillna("").str.match(r"^\s*0\s*[-–]"))
        df = df.sort_values(["sigla", "data_laudo", "_raso"], ascending=[True, False, True])
        return df.drop_duplicates("sigla").drop(columns="_raso").reset_index(drop=True)

    def anterior(self, sigla: str, data_laudo: str):
        df = self.analises()
        df = df[(df["sigla"] == sigla) & (df["data_laudo"] < data_laudo)]
        return None if df.empty else df.sort_values("data_laudo").iloc[-1]

    # ---- talhões
    def talhoes(self) -> dict:
        if self.arq_talhoes.exists():
            return json.loads(self.arq_talhoes.read_text(encoding="utf-8"))
        return {}

    def salvar_talhoes(self, novos: dict):
        tudo = self.talhoes()
        for sigla, info in novos.items():
            tudo[sigla] = {**tudo.get(sigla, {}), **info}
        self.arq_talhoes.write_text(json.dumps(tudo, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- cópia do histórico (levar entre o computador e a versão online)
    def _arquivos(self) -> list[Path]:
        return [self.arq_analises, self.arq_talhoes, self.arq_aprendizado]

    def exportar_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for arq in self._arquivos():
                if arq.exists():
                    z.write(arq, arq.name)
        return buf.getvalue()

    def importar_zip(self, conteudo: bytes):
        """Substitui o histórico pelos arquivos do zip (só os três nomes conhecidos; o resto é ignorado)."""
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
        except zipfile.BadZipFile as e:
            raise ValueError("O arquivo não é um .zip válido.") from e
        nomes = {Path(n).name: n for n in z.namelist()}
        if self.arq_analises.name not in nomes:
            raise ValueError("O zip não tem analises.csv; não parece uma cópia do histórico.")
        lidos = {arq: z.read(nomes[arq.name]) for arq in self._arquivos() if arq.name in nomes}
        colunas = set(pd.read_csv(io.BytesIO(lidos[self.arq_analises]), nrows=0).columns)
        if not {"laudo_id", "data_laudo", "sigla"} <= colunas:
            raise ValueError("analises.csv do zip não tem as colunas laudo_id, data_laudo e sigla.")
        if self.arq_talhoes in lidos:
            json.loads(lidos[self.arq_talhoes].decode("utf-8"))
        for arq, dados in lidos.items():
            arq.write_bytes(dados)

    # ---- reconhecer siglas já analisadas
    def casar(self, siglas) -> pd.DataFrame:
        """Para cada sigla nova: 'conhecida' (já analisada), 'parecida' (grafia próxima) ou 'nova'."""
        conhecidas = sorted(set(self.analises()["sigla"]) | set(self.talhoes()))
        linhas = []
        for s in siglas:
            if s in conhecidas:
                linhas.append({"sigla": s, "situacao": "conhecida", "casar_com": s, "semelhanca": 100})
                continue
            achado = _mais_parecida(s, conhecidas) if conhecidas else None
            if achado and achado[1] >= 80:
                linhas.append({"sigla": s, "situacao": "parecida", "casar_com": achado[0],
                               "semelhanca": round(achado[1])})
            else:
                linhas.append({"sigla": s, "situacao": "nova", "casar_com": s, "semelhanca": 0})
        return pd.DataFrame(linhas)


def _mais_parecida(sigla: str, conhecidas: list[str]) -> tuple[str, float]:
    """(sigla conhecida mais parecida, semelhança 0-100). rapidfuzz se houver; difflib no navegador."""
    try:
        from rapidfuzz import fuzz, process
        achado = process.extractOne(sigla, conhecidas, scorer=fuzz.ratio)
        return achado[0], achado[1]
    except ImportError:  # Pyodide não tem rapidfuzz; a razão do difflib é a mesma medida
        from difflib import SequenceMatcher
        return max(((c, 100 * SequenceMatcher(None, sigla, c).ratio()) for c in conhecidas), key=lambda x: x[1])


# ---------------------------------------------------------------- comparação com a análise anterior
CAMPOS_COMPARAR = [("pH_agua", "pH", 2), ("V", "V%", 0), ("P", "P (mg/dm³)", 0), ("K_mg", "K (mg/dm³)", 0),
                   ("Ca", "Ca", 2), ("Mg", "Mg", 2), ("MO_g_kg", "M.O. (g/kg)", 1)]


def comparar(novo: pd.Series, antigo: pd.Series) -> tuple[pd.DataFrame, list[str]]:
    """Tabela antes x agora e leitura agronômica das mudanças de uma sigla."""
    linhas, alertas = [], []
    s = novo["sigla"]
    for campo, rot, nd in CAMPOS_COMPARAR:
        a, b = antigo.get(campo), novo.get(campo)
        if pd.isna(a) or pd.isna(b):
            continue
        linhas.append({"sigla": s, "atributo": rot, "antes": round(float(a), nd), "agora": round(float(b), nd),
                       "variação": round(float(b) - float(a), nd)})
    ca, cn = classe_p(antigo.get("P")), classe_p(novo.get("P"))
    ordem = ["baixo", "medio", "alto", "muito_alto"]
    if ca and cn and ordem.index(cn) > ordem.index(ca):
        alertas.append(f"{s}: o fósforo subiu de {ROT[ca].lower()} para {ROT[cn].lower()} "
                       f"({br(antigo['P'])} → {br(novo['P'])} mg/dm³). A correção funcionou; "
                       "o superfosfato passa a ser só de manutenção.")
    elif ca and cn and ordem.index(cn) < ordem.index(ca):
        alertas.append(f"{s}: o fósforo caiu de {ROT[ca].lower()} para {ROT[cn].lower()}; volte a repor fósforo.")
    ka, kn = antigo.get("K_mg"), novo.get("K_mg")
    if pd.notna(ka) and pd.notna(kn) and ka > 0:
        var = 100 * (kn - ka) / ka
        if var <= -20:
            alertas.append(f"{s}: o potássio caiu {br(-var)}% ({br(ka)} → {br(kn)} mg/dm³). A área está exportando "
                           "potássio; não reduza o K.")
        elif var >= 20 and classe_k(kn) != classe_k(ka):
            alertas.append(f"{s}: o potássio subiu para {ROT[classe_k(kn)].lower()} ({br(kn)} mg/dm³); a dose "
                           "de K foi ajustada para a nova classe.")
    va, vn = antigo.get("V"), novo.get("V")
    if pd.notna(va) and pd.notna(vn) and vn - va <= -10:
        alertas.append(f"{s}: a saturação por bases caiu {br(va - vn)} pontos ({br(va)}% → {br(vn)}%). "
                       "O solo está acidificando; acompanhe a necessidade de calcário.")
    ma, mn = antigo.get("MO_g_kg"), novo.get("MO_g_kg")
    if pd.notna(ma) and pd.notna(mn) and ma > 0 and (mn - ma) / ma <= -0.15:
        alertas.append(f"{s}: a matéria orgânica caiu {br(100 * (ma - mn) / ma)}%; mais palhada e menos pasto rapado "
                       "ajudam a recuperar.")
    return pd.DataFrame(linhas), alertas


def meses_entre(d1: str, d2: str) -> float:
    a, b = date.fromisoformat(d1), date.fromisoformat(d2)
    return (b - a).days / 30.44


def idade_meses(data_laudo: str, hoje: date | None = None) -> float:
    return meses_entre(data_laudo, (hoje or date.today()).isoformat()) if data_laudo else np.nan
