"""Leitura de laudos de análise de solo (PDF, XLSX, CSV) com reconhecimento de colunas por ML.

Cada coluna da tabela vira um exemplo com duas evidências:
  - o texto do cabeçalho (n-gramas de caracteres -> regressão logística);
  - o perfil dos valores (faixa, mediana, % de inteiros, padrão "0-20"... -> floresta aleatória).
As probabilidades são combinadas e uma atribuição ótima (algoritmo húngaro) garante no máximo
uma coluna por campo. O modelo treina com exemplos sintéticos (sinônimos e faixas típicas) mais as
correções confirmadas pelo usuário (historico/aprendizado_colunas.csv) e é retreinado quando elas
mudam.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .regras import normalizar_sigla, sem_acento

VERSAO_MODELO = "1"

CAMPOS = ["sigla", "prof_cm", "textura", "pH_agua", "MO_g_kg", "K_cmolc", "Ca", "Mg", "Al", "H_Al", "Na",
          "SB", "t", "T", "V", "m", "P", "K_mg", "argila", "ignorar"]
NUMERICOS = ["pH_agua", "MO_g_kg", "K_cmolc", "Ca", "Mg", "Al", "H_Al", "Na", "SB", "t", "T", "V", "m",
             "P", "K_mg", "argila"]
ROTULOS = {
    "sigla": "Sigla / amostra", "prof_cm": "Profundidade", "textura": "Textura", "pH_agua": "pH em água",
    "MO_g_kg": "Matéria orgânica (g/kg)", "K_cmolc": "K (cmolc/dm³)", "Ca": "Ca (cmolc/dm³)",
    "Mg": "Mg (cmolc/dm³)", "Al": "Al (cmolc/dm³)", "H_Al": "H+Al (cmolc/dm³)", "Na": "Na (cmolc/dm³)",
    "SB": "Soma de bases (SB)", "t": "CTC efetiva (t)", "T": "CTC a pH 7 (T)", "V": "Saturação por bases V%",
    "m": "Saturação por Al m%", "P": "P Mehlich (mg/dm³)", "K_mg": "K (mg/dm³)", "argila": "Argila (g/kg)",
    "ignorar": "(ignorar coluna)",
}

SINONIMOS = {
    "sigla": ["identificação da amostra", "amostra", "sigla", "talhão", "gleba", "área", "identificação",
              "registro no laboratório", "código", "ponto", "local", "id amostra", "piquete"],
    "prof_cm": ["prof.", "profundidade", "prof. (cm)", "camada", "prof cm", "profundidade (cm)"],
    "textura": ["textura", "textura (expedita)", "classe textural", "textura expedita"],
    "pH_agua": ["ph", "ph em água", "ph água", "ph (h2o)", "ph h2o", "ph agua 1:2,5", "ph em agua"],
    "MO_g_kg": ["m.o.", "mo", "matéria orgânica", "materia organica", "m.o", "mat. orgânica"],
    "K_cmolc": ["k", "potássio", "k+", "k trocável"],
    "Ca": ["ca", "cálcio", "ca2+", "ca++", "ca trocável"],
    "Mg": ["mg", "magnésio", "mg2+", "mg++"],
    "Al": ["al", "alumínio", "al3+", "al trocável", "al+++"],
    "H_Al": ["h+al", "h + al", "acidez potencial", "h+al3+", "h +al", "(h+al)"],
    "Na": ["na", "sódio", "na+"],
    "SB": ["sb", "soma de bases", "s.b."],
    "t": ["t", "ctc efetiva", "ctc (t)", "t efetiva", "ctc efet."],
    "T": ["T", "ctc", "ctc ph 7", "ctc potencial", "ctc total", "ctc a ph 7,0", "ctc(t)"],
    "V": ["v", "v%", "saturação por bases", "v (%)", "sat. bases", "sat. por bases"],
    "m": ["m", "m%", "saturação por alumínio", "sat. al", "m (%)", "sat. por al"],
    "P": ["p", "fósforo", "p mehlich", "p meh", "p disponível", "p-mehlich 1", "fosforo"],
    "K_mg": ["k", "potássio", "k mehlich", "k disponível", "k+"],
    "argila": ["argila", "teor de argila", "argila total"],
    "ignorar": ["data", "observação", "laboratório", "nº", "n°", "cpf", "laudo", "responsável", "cultura",
                "município", "nº lab", "obs", "lote", "proprietário"],
}
UNIDADES = {
    "pH_agua": ["", "1:2,5", "h2o"], "MO_g_kg": ["g kg-1", "g/kg", "dag/kg", "%", "g dm-3"],
    "K_cmolc": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c", "meq/100cm3", "cmolc dm3"],
    "Ca": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c", "meq/100cm3"], "Mg": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"],
    "Al": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"], "H_Al": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"],
    "Na": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"], "SB": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"],
    "t": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"], "T": ["cmolc/dm3", "cmolc dm-3", "cmol dm3 c"],
    "V": ["%"], "m": ["%"], "P": ["mg/dm3", "mg dm-3", "mg dm3", "ppm"], "K_mg": ["mg/dm3", "mg dm-3", "mg dm3", "ppm"],
    "argila": ["g/kg", "g kg-1", "%"], "prof_cm": ["cm", ""], "sigla": [""], "textura": [""], "ignorar": [""],
}
# (mínimo, máximo, escala, casas decimais) das faixas típicas usadas para gerar exemplos.
FAIXAS = {
    "pH_agua": (4.0, 7.8, "lin", 2), "MO_g_kg": (5, 70, "log", 1), "K_cmolc": (0.02, 1.2, "log", 2),
    "Ca": (0.2, 9, "log", 2), "Mg": (0.1, 4.5, "log", 2), "Al": (0.0, 2.5, "zero", 1),
    "H_Al": (0.8, 12, "log", 2), "Na": (0.01, 0.6, "log", 2), "SB": (0.5, 14, "log", 2),
    "t": (0.8, 15, "log", 2), "T": (2.5, 18, "log", 2), "V": (8, 92, "lin", 0), "m": (0, 70, "zero", 2),
    "P": (1, 120, "log", 0), "K_mg": (8, 400, "log", 0), "argila": (80, 750, "log", 0),
}
TOKENS_UNIDADE = ("cmol", "mg dm", "mg/dm", "%", "g kg", "g/kg", "dag", "ppm", "meq", "dm3", "dm-3")


# ---------------------------------------------------------------- utilidades de texto e número
def numero(v):
    """'5,00' -> 5.0; '<0,1' -> 0.1; '1.234,5' -> 1234.5; texto -> None."""
    if v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return None if v != v else float(v)
    s = str(v).strip().replace(" ", "")
    s = re.sub(r"^[<>≤≥~]+", "", s)
    if not re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})*(,\d+)?|[-+]?\d+([.,]\d+)?", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "")
    return float(s.replace(",", "."))


def normalizar_cabecalho(texto) -> str:
    bruto = re.sub(r"\s+", " ", str(texto or "")).strip()
    tokens = re.split(r"[\s|]+", bruto)
    t = sem_acento(bruto).lower()
    t = t.replace("cmol dm3 c", "cmolc dm3").replace("cmol dm-3 c", "cmolc dm-3")
    marcas = []
    if "T" in tokens or "T(pH7)" in tokens:
        marcas.append("ctcpotencial")
    if "t" in tokens:
        marcas.append("ctcefetiva")
    if "m" in tokens or "m%" in tokens:
        marcas.append("saturacaoal")
    return (t + " " + " ".join(marcas)).strip()


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "nan", "None", "NaN")


def perfil_valores(valores) -> list[float]:
    """Vetor de atributos numéricos de uma coluna (usado pelo classificador de valores)."""
    vals = [str(v).strip() for v in valores if not _vazio(v)]
    n = len(vals) or 1
    nums = [x for x in (numero(v) for v in vals) if x is not None]
    frac_num = len(nums) / n
    faixa = sum(bool(re.fullmatch(r"\d+\s*[-–a]\s*\d+", v)) for v in vals) / n
    alfa = sum(bool(re.search(r"[A-Za-zÀ-ú]", v)) for v in vals) / n
    data = sum(bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", v)) for v in vals) / n
    comp = (np.mean([len(v) for v in vals]) if vals else 0) / 20
    if nums and frac_num >= 0.5:
        a = np.array(nums, dtype=float)
        med = float(np.median(a))
        num = [np.log10(abs(med) + 0.01), np.log10(abs(a.min()) + 0.01), np.log10(abs(a.max()) + 0.01),
               float(np.mean(np.isclose(a, np.round(a)))), float(np.mean(a <= 1)), float(np.mean(a <= 10)),
               float(np.mean(a <= 100)), float(np.std(a) / (abs(med) + 0.01)), float(np.mean(a == 0)),
               float(np.mean((a >= 3.5) & (a <= 8.5)))]
    else:
        num = [0.0] * 10
    return num + [frac_num, faixa, alfa, comp, data]


# ---------------------------------------------------------------- dados sintéticos para treino
def _valores_sinteticos(campo, rng, n):
    if campo == "sigla":
        estilo = rng.integers(4)
        base = [f"{rng.choice(list('ABCDGMPT'))}{rng.integers(1, 999)}" for _ in range(n)]
        if estilo == 1:
            base = [f"{i + 1} – {b}" for i, b in enumerate(base)]
        elif estilo == 2:
            base = [f"Amostra {i + 1}" for i in range(n)]
        elif estilo == 3:
            base = [f"Gleba {chr(65 + i % 26)}" for i in range(n)]
        return base
    if campo == "prof_cm":
        return [rng.choice(["0 – 20", "0-20", "20-40", "0 - 10", "0-20 cm"]) for _ in range(n)]
    if campo == "textura":
        return [rng.choice(["Média", "Arenosa", "Argilosa", "Muito argilosa", "Siltosa"]) for _ in range(n)]
    if campo == "ignorar":
        tipo = rng.integers(4)
        if tipo == 0:
            return [f"{rng.integers(1, 28):02d}/{rng.integers(1, 12):02d}/2026" for _ in range(n)]
        if tipo == 1:
            return [str(rng.integers(10000, 99999)) for _ in range(n)]
        if tipo == 2:
            return [rng.choice(["Pastagem", "Milho", "obs. reamostrar", "Capineira", "Café"]) for _ in range(n)]
        return [""] * n
    lo, hi, escala, casas = FAIXAS[campo]
    if escala == "log":
        v = np.exp(rng.uniform(np.log(lo), np.log(hi), n))
    elif escala == "zero":
        v = np.where(rng.random(n) < 0.4, 0.0, rng.uniform(max(lo, 0.05), hi, n))
    else:
        v = rng.uniform(lo, hi, n)
    if campo == "MO_g_kg" and rng.random() < 0.3:  # MO em dag/kg (%)
        v = v / 10
    v = np.round(v, casas)
    virgula = rng.random() < 0.7
    return [(f"{x:.{casas}f}".replace(".", ",") if virgula else f"{x:.{casas}f}") for x in v]


def _exemplos_sinteticos(seed=7):
    rng = np.random.default_rng(seed)
    textos, perfis, alvos = [], [], []
    for campo, sinonimos in SINONIMOS.items():
        for s in sinonimos:
            for u in UNIDADES.get(campo, [""]):
                variantes = {s, s.upper() if len(s) > 1 else s, s.capitalize() if len(s) > 1 else s,
                             f"{s} ({u})" if u else s, f"{u} | {s}" if u else s, f"{s} {u}".strip()}
                for var in variantes:
                    for _ in range(2):
                        textos.append(normalizar_cabecalho(var))
                        perfis.append(perfil_valores(_valores_sinteticos(campo, rng, int(rng.integers(3, 25)))))
                        alvos.append(campo)
    return textos, perfis, alvos


# ---------------------------------------------------------------- modelo
class ModeloColunas:
    """Classificador de colunas: texto do cabeçalho + perfil dos valores."""

    def __init__(self, arquivo_aprendizado: Path | None = None, cache: Path | None = None):
        self.arquivo_aprendizado = Path(arquivo_aprendizado) if arquivo_aprendizado else None
        self.cache = Path(cache) if cache else None
        self._texto = self._valores = None
        self.n_correcoes = 0
        self._carregar_ou_treinar()

    def _aprendizado(self) -> pd.DataFrame:
        if self.arquivo_aprendizado and self.arquivo_aprendizado.exists():
            return pd.read_csv(self.arquivo_aprendizado, dtype=str).fillna("")
        return pd.DataFrame(columns=["cabecalho", "campo", "valores"])

    def _chave(self, apr: pd.DataFrame) -> str:
        return hashlib.md5((VERSAO_MODELO + apr.to_csv(index=False)).encode()).hexdigest()

    def _carregar_ou_treinar(self):
        import joblib
        apr = self._aprendizado()
        chave = self._chave(apr)
        if self.cache and self.cache.exists():
            try:
                dados = joblib.load(self.cache)
                if dados.get("chave") == chave:
                    self._texto, self._valores, self.n_correcoes = dados["texto"], dados["valores"], len(apr)
                    return
            except Exception:
                pass
        self._treinar(apr)
        if self.cache:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump({"chave": chave, "texto": self._texto, "valores": self._valores}, self.cache)

    def _treinar(self, apr: pd.DataFrame):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline

        textos, perfis, alvos = _exemplos_sinteticos()
        for _, r in apr.iterrows():  # correções do usuário pesam 5x
            if r["campo"] not in CAMPOS:
                continue
            vals = json.loads(r["valores"]) if r["valores"] else []
            for _ in range(5):
                textos.append(normalizar_cabecalho(r["cabecalho"]))
                perfis.append(perfil_valores(vals))
                alvos.append(r["campo"])
        self.n_correcoes = len(apr)
        self._texto = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4), sublinear_tf=True),
                                    LogisticRegression(C=8, max_iter=3000))
        self._texto.fit(textos, alvos)
        self._valores = RandomForestClassifier(n_estimators=250, min_samples_leaf=2, random_state=0)
        self._valores.fit(np.array(perfis), alvos)

    def probabilidades(self, cabecalhos, colunas_valores) -> np.ndarray:
        """Matriz (colunas x CAMPOS) com a probabilidade combinada de cada campo."""
        pt = self._texto.predict_proba([normalizar_cabecalho(c) for c in cabecalhos])
        pv = self._valores.predict_proba(np.array([perfil_valores(v) for v in colunas_valores]))
        out = np.zeros((len(cabecalhos), len(CAMPOS)))
        for j, campo in enumerate(CAMPOS):
            a = pt[:, list(self._texto.classes_).index(campo)] if campo in self._texto.classes_ else 1e-6
            b = pv[:, list(self._valores.classes_).index(campo)] if campo in self._valores.classes_ else 1e-6
            out[:, j] = np.power(a + 1e-6, 0.65) * np.power(b + 1e-6, 0.35)
        return out / out.sum(axis=1, keepdims=True)


def atribuir(prob: np.ndarray) -> list[tuple[str, float]]:
    """Atribuição ótima coluna -> campo (cada campo real no máximo uma vez; 'ignorar' livre)."""
    from scipy.optimize import linear_sum_assignment
    n = prob.shape[0]
    ign = CAMPOS.index("ignorar")
    reais = [j for j in range(len(CAMPOS)) if j != ign]
    custo = -np.log(prob + 1e-9)
    matriz = np.hstack([custo[:, reais], np.repeat(custo[:, [ign]], n, axis=1)])
    linhas, cols = linear_sum_assignment(matriz)
    res = [("ignorar", 0.0)] * n
    for i, j in zip(linhas, cols):
        campo = CAMPOS[reais[j]] if j < len(reais) else "ignorar"
        res[i] = (campo, float(prob[i, CAMPOS.index(campo)]))
    return res


# ---------------------------------------------------------------- extração de tabelas
def _eh_dado(linha) -> bool:
    cel = [c for c in linha if not _vazio(c)]
    nums = sum(numero(c) is not None for c in cel)
    return nums >= 5 and nums >= 0.5 * len(cel)


def _cabecalhos(linhas_cab, ncols) -> list[str]:
    pedacos = [[] for _ in range(ncols)]
    for linha in linhas_cab:
        linha = list(linha) + [None] * (ncols - len(linha))
        preenchida, grupo = [], None
        for c in linha[:ncols]:
            if not _vazio(c):
                txt = re.sub(r"\s+", " ", str(c)).strip()
                grupo = txt if any(t in sem_acento(txt).lower() for t in TOKENS_UNIDADE) else None
                preenchida.append(txt)
            else:
                preenchida.append(grupo)  # grupo de unidade (ex.: "cmolc dm3") cobre as colunas à direita
        for j, c in enumerate(preenchida):
            if c and (not pedacos[j] or pedacos[j][-1] != c):
                pedacos[j].append(c)
    return [" | ".join(p) for p in pedacos]


def blocos_de_tabela(linhas) -> list[tuple[list[str], list[list]]]:
    """Encontra blocos de linhas de dados e monta o cabeçalho com as até 4 linhas acima."""
    blocos, i, fim_anterior = [], 0, 0
    while i < len(linhas):
        if _eh_dado(linhas[i]):
            j = i
            while j < len(linhas) and _eh_dado(linhas[j]):
                j += 1
            cab = [l for l in linhas[max(fim_anterior, i - 4):i] if sum(not _vazio(c) for c in l) >= 2]
            dados = linhas[i:j]
            ncols = max(len(l) for l in dados + cab)
            dados = [list(l) + [None] * (ncols - len(l)) for l in dados]
            usadas = [k for k in range(ncols) if any(not _vazio(l[k]) for l in dados)]
            cabs = _cabecalhos(cab, ncols)
            blocos.append(([cabs[k] for k in usadas], [[l[k] for k in usadas] for l in dados]))
            fim_anterior = i = j
        else:
            i += 1
    return blocos


def _linhas_pdf(conteudo: bytes) -> tuple[list[list], str]:
    """Tabelas e texto do PDF com pdfplumber (MIT). PDF escaneado (só imagem) não tem texto: sem OCR."""
    import pdfplumber
    linhas, texto = [], ""
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pagina in pdf.pages:
            texto += (pagina.extract_text() or "") + "\n"
            for tab in pagina.extract_tables():
                linhas.extend(tab)
                linhas.append([None])
    return linhas, texto


def _linhas_planilha(conteudo: bytes, nome: str) -> tuple[list[list], str]:
    if nome.lower().endswith(".csv") or nome.lower().endswith(".txt"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python", header=None, dtype=str,
                                 encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        folhas = {"csv": df}
    else:
        folhas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None, dtype=str)
    linhas, texto = [], ""
    for df in folhas.values():
        df = df.where(df.notna(), None)
        for row in df.itertuples(index=False):
            linhas.append(list(row))
            texto += " ".join(str(c) for c in row if c) + "\n"
        linhas.append([None])
    return linhas, texto


def _meta_do_texto(texto: str, nome: str) -> dict:
    data = None
    m = re.search(r"Data\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto) or re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", texto)
    if m:
        data = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    lab = "PESAGRO-RIO" if "PESAGRO" in texto.upper() else ""
    return {"data_laudo": data, "laboratorio": lab, "arquivo": nome}


# ---------------------------------------------------------------- montagem do resultado
@dataclass
class Leitura:
    dados: pd.DataFrame
    colunas: pd.DataFrame          # indice, cabecalho, campo, confianca, exemplo
    meta: dict
    avisos: list = field(default_factory=list)
    cabecalhos: list = field(default_factory=list)
    valores: list = field(default_factory=list)  # valores brutos por coluna


def _montar(cabecalhos, valores, mapa) -> tuple[pd.DataFrame, list[str]]:
    avisos = []
    n = len(valores[0]) if valores else 0
    col = {campo: valores[i] for i, campo in mapa.items() if campo != "ignorar"}
    df = pd.DataFrame(index=range(n))
    df["sigla"] = [normalizar_sigla(v) for v in col["sigla"]] if "sigla" in col else [f"A{i + 1}" for i in range(n)]
    if "sigla" not in col:
        avisos.append("Não achei a coluna de sigla; as amostras foram chamadas de A1, A2...")
    for campo in ("prof_cm", "textura"):
        df[campo] = [str(v or "").strip() for v in col[campo]] if campo in col else ""
    for campo in NUMERICOS:
        df[campo] = [numero(v) for v in col[campo]] if campo in col else np.nan
    df[NUMERICOS] = df[NUMERICOS].astype(float)

    if df["MO_g_kg"].notna().any() and df["MO_g_kg"].median() < 10:
        df["MO_g_kg"] *= 10
        avisos.append("Matéria orgânica estava em dag/kg (%); convertida para g/kg (×10).")
    if df["K_cmolc"].notna().any() and df["K_cmolc"].median() > 2 and df["K_mg"].isna().all():
        df["K_mg"], df["K_cmolc"] = df["K_cmolc"], np.nan
        avisos.append("A coluna de K estava em mg/dm³; reclassificada.")
    if df["K_mg"].isna().all() and df["K_cmolc"].notna().any():
        df["K_mg"] = (df["K_cmolc"] * 391).round(0)
        avisos.append("K em mg/dm³ calculado a partir do K em cmolc/dm³ (×391).")
    if df["K_cmolc"].isna().all() and df["K_mg"].notna().any():
        df["K_cmolc"] = (df["K_mg"] / 391).round(3)
        avisos.append("K em cmolc/dm³ calculado a partir do K em mg/dm³ (÷391).")
    na = df["Na"].fillna(0)
    soma = df["Ca"] + df["Mg"] + df["K_cmolc"] + na
    if df["SB"].isna().all() and soma.notna().any():
        df["SB"] = soma.round(2)
        avisos.append("SB calculada (Ca + Mg + K + Na).")
    elif soma.notna().any() and ((df["SB"] - soma).abs() > 0.35).any():
        ruins = ", ".join(df.loc[(df["SB"] - soma).abs() > 0.35, "sigla"])
        avisos.append(f"SB do laudo não bate com Ca + Mg + K + Na em: {ruins}. Confira a leitura das colunas.")
    if df["T"].isna().all() and df["H_Al"].notna().any():
        df["T"] = (df["SB"] + df["H_Al"]).round(2)
        avisos.append("T calculada (SB + H+Al).")
    if df["t"].isna().all() and df["Al"].notna().any():
        df["t"] = (df["SB"] + df["Al"]).round(2)
    if df["V"].isna().all() and df["T"].notna().any():
        df["V"] = (100 * df["SB"] / df["T"]).round(0)
        avisos.append("V% calculada (100 × SB / T).")
    if df["m"].isna().all() and df["Al"].notna().any():
        df["m"] = (100 * df["Al"] / (df["SB"] + df["Al"])).round(2)
    for campo, rot in (("pH_agua", "pH"), ("P", "fósforo"), ("K_mg", "potássio"), ("V", "V%"), ("T", "CTC (T)")):
        if df[campo].isna().all():
            avisos.append(f"Falta {rot}: confira o reconhecimento das colunas.")
    dup = df["sigla"][df["sigla"].duplicated()].unique()
    if len(dup):
        avisos.append("Siglas repetidas no laudo (camadas diferentes?): " + ", ".join(dup))
    return df, avisos


def reaplicar(leitura: Leitura, mapa: dict[int, str]) -> Leitura:
    """Remonta os dados com um mapeamento corrigido pelo usuário (índice da coluna -> campo)."""
    dados, avisos = _montar(leitura.cabecalhos, leitura.valores, mapa)
    colunas = leitura.colunas.copy()
    colunas["campo"] = [mapa[i] for i in colunas["indice"]]
    return Leitura(dados, colunas, leitura.meta, avisos, leitura.cabecalhos, leitura.valores)


def ler_laudo(conteudo: bytes, nome: str, modelo: ModeloColunas) -> Leitura:
    if nome.lower().endswith(".pdf"):
        linhas, texto = _linhas_pdf(conteudo)
    else:
        linhas, texto = _linhas_planilha(conteudo, nome)
    blocos = blocos_de_tabela(linhas)
    if not blocos:
        raise ValueError("Não encontrei uma tabela de resultados no arquivo. Se for um PDF escaneado, "
                         "exporte os resultados como planilha (XLSX ou CSV).")
    cabecalhos, dados = max(blocos, key=lambda b: len(b[1]) * len(b[0]))
    valores = [[l[k] for l in dados] for k in range(len(cabecalhos))]
    prob = modelo.probabilidades(cabecalhos, valores)
    atrib = atribuir(prob)
    mapa = {i: campo for i, (campo, _) in enumerate(atrib)}
    tabela, avisos = _montar(cabecalhos, valores, mapa)
    colunas = pd.DataFrame({
        "indice": range(len(cabecalhos)),
        "cabecalho": [c or f"(coluna {i + 1})" for i, c in enumerate(cabecalhos)],
        "campo": [c for c, _ in atrib],
        "confianca": [round(p, 2) for _, p in atrib],
        "exemplo": [", ".join(str(v) for v in col[:3]) for col in valores],
    })
    baixa = colunas[(colunas["confianca"] < 0.5) & (colunas["campo"] != "ignorar")]
    if len(baixa):
        avisos.insert(0, "Reconhecimento com pouca confiança em: " + ", ".join(baixa["cabecalho"]) + ". Confira.")
    return Leitura(tabela, colunas, _meta_do_texto(texto, nome), avisos, cabecalhos, valores)


def registrar_correcoes(arquivo: Path, leitura: Leitura):
    """Guarda o mapeamento confirmado como exemplo de treino (o modelo aprende com ele)."""
    arquivo = Path(arquivo)
    novo = pd.DataFrame({
        "cabecalho": leitura.cabecalhos,
        "campo": list(leitura.colunas["campo"]),
        "valores": [json.dumps([str(v) for v in col[:30]], ensure_ascii=False) for col in leitura.valores],
    })
    if arquivo.exists():
        antigo = pd.read_csv(arquivo, dtype=str).fillna("")
        novo = pd.concat([antigo, novo]).drop_duplicates(subset=["cabecalho", "campo"], keep="last")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    novo.to_csv(arquivo, index=False, encoding="utf-8")
