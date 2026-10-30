"""Regras agronômicas: faixas de interpretação do laudo, adubos do kit e doses por cultura e nível.

As faixas de P, K, pH (Mehlich-1) seguem Freire et al. (2013) e as de Ca, Mg, Al (KCl 1 N)
Brazão e Silva (2018), como no laudo PESAGRO-RIO. Doses: 5ª Aproximação (pastagens),
Embrapa CT 79 (BRS Capiaçu) e Embrapa Tabuleiros Costeiros (coqueiro).
"""
from __future__ import annotations

import re
import unicodedata

# Garantias (% em massa). O P2O5 do adubo fosfatado não é fixo: o usuário informa a garantia do rótulo
# (superfosfato simples comum 18%; o "reativo", 26%, padrão do programa; ou um composto com P).
NPK = "25-00-25"
SSP = "Superfosfato simples"
KCL = "Cloreto de potássio"
BORAX = "Bórax"
PRODUTOS = {
    NPK: {"N": 25, "P2O5": 0, "K2O": 25},
    SSP: {"N": 0, "P2O5": 26, "K2O": 0},  # P2O5 padrão; o motor usa o valor informado
    KCL: {"N": 0, "P2O5": 0, "K2O": 60},
}
P2O5_FOSFATADO_PADRAO = 26  # % de P2O5 do superfosfato simples reativo (padrão do programa)
SACO_KG = 50
NUTRIENTES = ["N", "P2O5", "K2O"]

CULTURAS = {
    "braquiaria": "Braquiária (manutenção)",
    "braquiaria_formacao": "Braquiária (reforma / replantio)",
    "capiacu": "Capim BRS Capiaçu (capineira)",
}
CULTURA_POR_ROTULO = {v: k for k, v in CULTURAS.items()}
V2_ALVO = {"braquiaria": 50, "braquiaria_formacao": 50, "capiacu": 60}
NIVEIS = {"economico": "Econômico", "medio": "Nível médio"}

# Doses em kg/ha/ano por classe do laudo: 25-00-25 em kg de produto; fósforo em kg de P2O5/ha,
# [dose, a cada N anos], convertido em kg de adubo pela garantia de P2O5 informada (kg = P2O5 / %).
DOSES = {
    "medio": {
        "npk": {
            "braquiaria": {"baixo": 400, "medio": 300, "alto": 200, "muito_alto": 200},
            "braquiaria_formacao": {"baixo": 400, "medio": 300, "alto": 200, "muito_alto": 200},
            "capiacu": {"baixo": 1000, "medio": 1000, "alto": 800, "muito_alto": 800},
        },
        "p2o5": {
            "braquiaria": {"baixo": [54, 1], "medio": [36, 1], "alto": [0, 1], "muito_alto": [0, 1]},
            "braquiaria_formacao": {"baixo": [90, 1], "medio": [63, 1], "alto": [27, 1], "muito_alto": [0, 1]},
            "capiacu": {"baixo": [108, 1], "medio": [63, 1], "alto": [36, 1], "muito_alto": [0, 1]},
        },
        "parcelas": {"braquiaria": 2, "braquiaria_formacao": 2, "capiacu": 4},
    },
    "economico": {
        "npk": {
            "braquiaria": {"baixo": 200, "medio": 150, "alto": 100, "muito_alto": 0},
            "braquiaria_formacao": {"baixo": 200, "medio": 150, "alto": 100, "muito_alto": 100},
            "capiacu": {"baixo": 500, "medio": 500, "alto": 400, "muito_alto": 300},
        },
        "p2o5": {
            "braquiaria": {"baixo": [36, 1], "medio": [27, 2], "alto": [0, 1], "muito_alto": [0, 1]},
            "braquiaria_formacao": {"baixo": [90, 1], "medio": [63, 1], "alto": [27, 1], "muito_alto": [0, 1]},
            "capiacu": {"baixo": [108, 1], "medio": [36, 1], "alto": [18, 1], "muito_alto": [0, 1]},
        },
        "parcelas": {"braquiaria": 1, "braquiaria_formacao": 1, "capiacu": 2},
    },
}
# Alternativa só com potássio nas pastagens (sem N), kg/ha/ano de cloreto de potássio por classe de K.
KCL_PASTAGEM = {"baixo": 75, "medio": 50, "alto": 0, "muito_alto": 0}

# Janelas da safra (chuvas na Baixada Fluminense: out-abr) e onde entra cada parcela.
JANELAS = ["Out–Nov", "Dez", "Jan–Fev", "Mar–Abr"]
JANELAS_PARCELAS = {
    "braquiaria": {1: [0], 2: [0, 2]},
    "braquiaria_formacao": {1: [1], 2: [1, 2]},
    "capiacu": {2: [0, 2], 4: [0, 1, 2, 3]},
    "coqueiro": {3: [0, 2, 3]},
}

# Coqueiro-gigante em solo com P e K baixos: N, P2O5, K2O em g/planta/ano por idade (>= 7 usa a linha 7).
COQUEIRO_G_PLANTA = {2: (150, 50, 150), 3: (180, 60, 180), 4: (225, 75, 225), 5: (300, 100, 300),
                     6: (450, 150, 450), 7: (900, 300, 900)}
BORAX_G_PLANTA = 50          # adulto com sintoma de falta de boro (bórax = 11% B)
COQUEIRO_PARCELAS = 3

NC_MINIMA = 0.2              # t/ha; abaixo disso a calagem não compensa a operação
MESES_REANALISE = {"braquiaria": 24, "braquiaria_formacao": 12, "capiacu": 12}


# ---------------------------------------------------------------- classes do laudo
def classe_p(p):
    if p is None or p != p:
        return None
    return "baixo" if p <= 10 else "medio" if p <= 20 else "alto" if p <= 30 else "muito_alto"


def classe_k(k):
    if k is None or k != k:
        return None
    return "baixo" if k <= 45 else "medio" if k <= 90 else "alto" if k <= 135 else "muito_alto"


def classe_ca(ca):
    return "baixo" if ca <= 1.5 else ("medio" if ca <= 4.5 else "alto")


def classe_mg(mg):
    return "baixo" if mg < 0.5 else ("medio" if mg <= 1.5 else "alto")


def classe_al(al):
    return "baixo" if al < 0.3 else ("medio" if al <= 1.0 else "alto")


def classe_ph(ph):
    if ph < 4.4:
        return "extremamente ácido"
    if ph <= 5.3:
        return "fortemente ácido"
    if ph <= 6.5:
        return "moderadamente ácido"
    if ph <= 7.3:
        return "neutro"
    return "alcalino"


ROT = {"baixo": "Baixo", "medio": "Médio", "alto": "Alto", "muito_alto": "Muito alto", None: "—"}


# ---------------------------------------------------------------- utilidades
def br(x, nd=0):
    """Número no formato brasileiro (1.234,5)."""
    if x is None or x != x:
        return "—"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def br_kg(kg):
    """Quilos com uma casa abaixo de 10 kg (bórax: 1,2 kg, não 1 kg) e inteiros acima."""
    pequeno = kg is not None and kg == kg and abs(kg) < 10 and kg != round(kg)
    return br(kg, 1 if pequeno else 0)


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def normalizar_sigla(s) -> str:
    """'1 – A12', 'Amostra 1 - A-12', 'a 12' -> 'A12'."""
    t = sem_acento(str(s or "")).strip()
    t = re.sub(r"^\s*(amostra|amostra n[oº°]?)?\s*\d+\s*[-–—)]\s*", "", t, flags=re.I)
    t = re.sub(r"^\s*amostra\s*", "", t, flags=re.I)
    return re.sub(r"[\s\-_./]+", "", t).upper()


def sacos(kg: float) -> float:
    return kg / SACO_KG
