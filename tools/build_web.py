"""Gera a versão para navegador do Soil Analyzer: o mesmo app.py rodando no navegador (stlite + Pyodide).

O laudo em PDF é lido e analisado no computador de quem usa (pdfplumber + pdfminer, Python puro);
nada é enviado ao servidor, que só entrega a página. O histórico fica no IndexedDB do navegador.

Rodar (com o Python que tem as dependências de requirements.txt):
    python tools/build_web.py [--saida dist] [--historico PASTA] [--gate-php CAMINHO --area AREA]

Saída:
    index.html   página com o código (e o histórico inicial, se pedido) embutidos
    fontes/      DejaVu Sans para o PDF (a Helvetica do reportlab não tem "→" nem "≤")
    .htaccess    CSP que libera a CDN do Pyodide (Apache); com --gate-php, nega o index.html direto
    index.php    só com --gate-php: inclui o PHP de login informado e chama exigirArea(AREA) antes de
                 entregar a página (o PHP precisa definir exigirArea)
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import importlib.util
import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
STLITE = "1.9.2"  # traz Streamlit 1.62 e Pyodide 0.29.3 (scikit-learn 1.7, scipy 1.14, pandas 2.3, Pillow)
# Python puro do PyPI (micropip) e pacotes prontos do Pyodide; o pdfplumber vai embutido (ver abaixo)
REQUISITOS = ["plotly==6.9.0", "openpyxl==3.1.5", "reportlab==4.5.0", "pdfminer.six==20260107", "Pillow",
              "scikit-learn", "scipy", "joblib"]
FONTES = RAIZ / "tools" / "fontes_web"
NOMES_FONTES = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]

# O pdfplumber (MIT, Python puro) depende do pypdfium2, que não existe para o navegador e só serve para
# desenhar páginas como imagem (page.to_image), recurso que o painel não usa. O pdfplumber vai embutido
# como arquivos e o pypdfium2 é trocado por um módulo vazio que só falha se alguém tentar desenhar.
PYPDFIUM2_VAZIO = '''"""Substituto do pypdfium2 no navegador: o Soil Analyzer não desenha páginas de PDF."""


def __getattr__(nome):
    raise ImportError("pypdfium2 não está disponível no navegador (só serve para page.to_image)")
'''

ENTRADA = '''\
"""Ponto de entrada no navegador: na primeira visita copia o histórico inicial e roda o app.py."""
import os
import runpy
import shutil
import types
from pathlib import Path

import streamlit.elements.widgets.data_editor as _editor

# stlite 1.9.2: com key= e linhas fixas, o st.data_editor ainda lê arrow_table.schema, mas o stlite tirou o
# pyarrow e o nome não existe (NameError). Esse esquema só entra na assinatura do widget, que já leva
# colunas, tipos e número de linhas; um esquema vazio basta.
if not hasattr(_editor, "arrow_table"):
    _editor.arrow_table = types.SimpleNamespace(schema=[])

hist = Path(os.environ["ANALISE_SOLO_DADOS"]) / "historico"
if not (hist / "analises.csv").exists() and Path("semente").is_dir():
    hist.mkdir(parents=True, exist_ok=True)
    for arq in Path("semente").iterdir():
        shutil.copy(arq, hist / arq.name)
runpy.run_path("app.py", run_name="__main__")
'''

PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Soil Analyzer</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@{stlite}/build/stlite.css">
<style>
  body {{ margin: 0; background: #ffffff; }}
  #aviso {{ font: 15px/1.5 system-ui, sans-serif; color: #2E5E3A; max-width: 560px; margin: 18vh auto 0;
            padding: 0 16px; text-align: center; }}
</style>
</head>
<body>
<div id="root">
  <p id="aviso">Carregando o Soil Analyzer…<br>
  Na primeira visita o navegador baixa o Python e as bibliotecas (1 a 2 minutos).
  O laudo em PDF é lido aqui mesmo, no seu computador: nada é enviado ao servidor.</p>
</div>
<script type="application/json" id="arquivos">{arquivos}</script>
<script type="module">
import {{ mount }} from "https://cdn.jsdelivr.net/npm/@stlite/browser@{stlite}/build/stlite.js";
const arquivos = JSON.parse(document.getElementById("arquivos").textContent);
for (const f of {fontes}) arquivos["solo/fontes/" + f] = {{ url: "fontes/" + f }};
mount({{
  entrypoint: "entrada.py",
  files: arquivos,
  requirements: {requisitos},
  idbfsMountpoints: ["/dados"],  // o stlite faz mkdir simples: o ponto tem de ficar na raiz
  env: {{ ANALISE_SOLO_DADOS: "/dados", ANALISE_SOLO_CACHE: "/dados/cache" }},
  streamlitConfig: {{
    "theme.base": "light", "theme.primaryColor": "#2E5E3A",
    "client.toolbarMode": "viewer", "browser.gatherUsageStats": false,
  }},
}}, document.getElementById("root"));
</script>
</body>
</html>
"""

GATE = """<?php
// Gerado por tools/build_web.py: exige login antes de entregar a página (o código vai embutido nela).
require_once $_SERVER['DOCUMENT_ROOT'] . '{gate}';
exigirArea('{area}');
readfile(__DIR__ . '/index.html');
"""

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob: data: "
       "https://cdn.jsdelivr.net https://fastly.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
       "https://fonts.googleapis.com; font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
       "img-src 'self' data: blob: https:; connect-src 'self' blob: data: https://cdn.jsdelivr.net "
       "https://fastly.jsdelivr.net https://pypi.org https://files.pythonhosted.org; worker-src 'self' blob: data:; "
       "frame-src 'self' blob: data:; frame-ancestors 'self'")

HTACCESS = """{gate_regras}AddType font/ttf .ttf

# O painel roda no navegador: baixa o stlite e o Python (Pyodide) da CDN jsdelivr e bibliotecas Python
# puras do PyPI (micropip).
#   'unsafe-eval' e 'wasm-unsafe-eval': instanciar o WebAssembly do Pyodide
#   worker-src blob: data: : o stlite cria o worker do Python a partir de um data: URL
<IfModule mod_headers.c>
    Header always set Content-Security-Policy "{csp}"
</IfModule>
"""

GATE_REGRAS = """# Todo acesso passa pelo index.php, que exige login.
DirectoryIndex index.php index.html

<Files "index.html">
    Require all denied
</Files>

"""


def pdfplumber_embutido() -> dict[str, str]:
    """Arquivos .py do pdfplumber instalado + licença MIT + substituto do pypdfium2."""
    spec = importlib.util.find_spec("pdfplumber")
    if spec is None:
        raise SystemExit("pdfplumber não está instalado neste Python (pip install -r requirements.txt).")
    pasta = Path(spec.origin).parent
    arqs = {f"pdfplumber/{p.relative_to(pasta).as_posix()}": p.read_text(encoding="utf-8")
            for p in sorted(pasta.rglob("*.py"))}
    dist = md.distribution("pdfplumber")
    licenca = next((f for f in dist.files or [] if "LICEN" in f.name.upper()), None)
    if licenca:
        arqs["pdfplumber/LICENSE.txt"] = Path(dist.locate_file(licenca)).read_text(encoding="utf-8")
    arqs["pypdfium2/__init__.py"] = PYPDFIUM2_VAZIO
    return arqs


def arquivos_do_app(historico: Path | None) -> dict[str, str]:
    arqs = {"entrada.py": ENTRADA, "app.py": (RAIZ / "app.py").read_text(encoding="utf-8")}
    for py in sorted((RAIZ / "solo").glob("*.py")):
        arqs[f"solo/{py.name}"] = py.read_text(encoding="utf-8")
    arqs.update(pdfplumber_embutido())
    if historico:
        for nome in ("analises.csv", "talhoes.json", "aprendizado_colunas.csv"):
            arq = historico / "historico" / nome
            if arq.exists():
                arqs[f"semente/{nome}"] = arq.read_text(encoding="utf-8")
    return arqs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default=str(RAIZ / "dist"), help="pasta gerada (padrão: dist/)")
    ap.add_argument("--historico", help="pasta de dados cujo historico/ vai embutido como histórico inicial")
    ap.add_argument("--gate-php", help="caminho (a partir da raiz do site) do PHP de login que define exigirArea()")
    ap.add_argument("--area", help="área passada a exigirArea() (obrigatória com --gate-php)")
    args = ap.parse_args()
    if bool(args.gate_php) != bool(args.area):
        ap.error("--gate-php e --area vão juntos")
    if args.gate_php and (":" in args.gate_php or not args.gate_php.startswith("/")):
        ap.error(f"--gate-php deve ser um caminho do site começando com / (recebido: {args.gate_php}); "
                 "no Git Bash, rode com MSYS_NO_PATHCONV=1 para ele não virar caminho do Windows")

    saida = Path(args.saida)
    arqs = arquivos_do_app(Path(args.historico) if args.historico else None)
    shutil.rmtree(saida, ignore_errors=True)
    (saida / "fontes").mkdir(parents=True)
    json_arqs = json.dumps(arqs, ensure_ascii=False).replace("</", "<\\/")  # não fechar o <script>
    (saida / "index.html").write_text(PAGINA.format(stlite=STLITE, arquivos=json_arqs,
                                                    fontes=json.dumps(NOMES_FONTES),
                                                    requisitos=json.dumps(REQUISITOS)), encoding="utf-8")
    if args.gate_php:
        (saida / "index.php").write_text(GATE.format(gate=args.gate_php, area=args.area), encoding="utf-8")
    (saida / ".htaccess").write_text(HTACCESS.format(gate_regras=GATE_REGRAS if args.gate_php else "", csp=CSP),
                                     encoding="utf-8")
    for f in [*NOMES_FONTES, "LICENSE_DEJAVU"]:
        shutil.copy(FONTES / f, saida / "fontes" / f)

    semente = sorted(k for k in arqs if k.startswith("semente/"))
    print(f"{saida} gerado: {len(arqs) - len(semente)} arquivos de código; histórico inicial: "
          f"{', '.join(Path(s).name for s in semente) or 'nenhum'}; login: {args.gate_php or 'sem'}")
    for p in sorted(saida.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(saida)}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
