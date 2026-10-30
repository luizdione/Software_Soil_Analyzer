"""Laudo de solo sintético em PDF, no formato da PESAGRO-RIO (cabeçalho em duas linhas, células mescladas).

Números, siglas, laboratório e texto são fictícios (valores inventados, coerentes entre si).
Usado pelos testes para exercitar a leitura de PDF sem depender de um laudo de verdade.
"""
from __future__ import annotations

import io

CAB1 = ["Identificação da Amostra", "Prof. (cm)", "Textura (Expedita)", "pH em água", "M.O. g Kg-1",
        "cmol dm3 c", "", "", "", "", "", "", "", "", "%", "", "mg dm3", ""]
CAB2 = ["Registro no Laboratório", "", "", "", "", "K", "Ca", "Mg", "Al", "H +Al", "Na", "SB", "t", "T",
        "V", "m", "P", "K"]
AMOSTRAS = [
    ["1 – P21", "0 – 20", "Média", "5,20", "30,50", "0,09", "3,10", "2,40", "0,2", "2,40", "0,08", "5,67", "5,87",
     "8,07", "70", "3,41", "6", "35"],
    ["2 – P903", "0 – 20", "Média", "5,30", "24,90", "0,15", "2,25", "1,20", "0,2", "2,50", "0,05", "3,65", "3,85",
     "6,15", "59", "5,19", "24", "60"],
    ["3 – P34", "0 – 20", "Média", "5,60", "29,80", "0,18", "2,40", "1,70", "0,1", "2,10", "0,04", "4,32", "4,42",
     "6,42", "67", "2,26", "15", "70"],
    ["4 – P58", "0 – 20", "Média", "6,00", "36,10", "0,11", "3,40", "2,80", "0", "1,70", "0,02", "6,33", "6,33",
     "8,03", "79", "0,00", "19", "42"],
]
DATA = "14/03/2025"


def laudo_pdf() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    estilos = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1 * cm, rightMargin=1 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    tabela = Table([CAB1, CAB2, *AMOSTRAS], repeatRows=2)
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        *[("SPAN", (j, 0), (j, 1)) for j in range(1, 5)],
        ("SPAN", (5, 0), (13, 0)), ("SPAN", (14, 0), (15, 0)), ("SPAN", (16, 0), (17, 0)),
    ]))
    doc.build([
        Paragraph("LAUDO DE ANÁLISE DE SOLO — exemplo sintético no formato PESAGRO-RIO", estilos["Title"]),
        Paragraph(f"Laboratório de Solos (fictício) · Data: {DATA} · Amostras de 0 a 20 cm", estilos["Normal"]),
        Spacer(1, 12), tabela,
    ])
    return buf.getvalue()


if __name__ == "__main__":
    from pathlib import Path
    Path("laudo_sintetico.pdf").write_bytes(laudo_pdf())
    print("laudo_sintetico.pdf gravado")
