"""Gera o instalador do Soil Analyzer para Windows: Soil_Analyzer.exe.

Rodar com o Python do ambiente de build (com as dependências de requirements.txt + pyinstaller):
    python desktop/build_exe.py [--makensis C:/caminho/makensis.exe] [--saida PASTA]

Etapas:
  1. ícone (desktop/soil_analyzer.ico, gerado com Pillow se não existir);
  2. PyInstaller (pasta única, com console: fechar a janela encerra o programa);
  3. LICENSE.txt, THIRD_PARTY_NOTICES.md e licencas/<pacote>/ com o texto da licença de cada
     biblioteca embutida (MIT, BSD e Apache pedem o texto junto da distribuição);
  4. NSIS -> <saida>/Soil_Analyzer.exe e o SHA-256 dele.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESKTOP = RAIZ / "desktop"
sys.path.insert(0, str(RAIZ))
from solo import NOME, __version__  # noqa: E402

TRABALHO = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "soil_analyzer_build"
ICONE = DESKTOP / "soil_analyzer.ico"
# só servem para gerar o executável; não vão dentro dele
SO_BUILD = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes", "pip",
            "setuptools", "wheel", "pytest", "pluggy", "iniconfig", "packaging-legacy"}


def gerar_icone():
    """Folha verde sobre faixas de solo (marrom), 16 a 256 px."""
    from PIL import Image, ImageDraw
    n = 256
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, n - 8, n - 8], radius=48, fill=(46, 94, 58, 255))
    for i, cor in enumerate([(122, 82, 48), (150, 104, 62), (176, 128, 80)]):
        y = 168 + i * 22
        d.rectangle([8, y, n - 8, y + 22], fill=cor + (255,))
    d.rounded_rectangle([8, 8, n - 8, n - 8], radius=48, outline=(30, 60, 38, 255), width=6)
    d.ellipse([78, 40, 178, 170], fill=(150, 214, 120, 255))
    d.line([128, 168, 128, 56], fill=(46, 94, 58, 255), width=8)
    for k in range(3):
        y = 80 + k * 26
        d.line([128, y + 18, 104, y], fill=(46, 94, 58, 255), width=5)
        d.line([128, y + 18, 152, y], fill=(46, 94, 58, 255), width=5)
    img.save(ICONE, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def pyinstaller():
    import PyInstaller.__main__
    args = [
        str(DESKTOP / "soil_analyzer.py"), "--noconfirm", "--clean", "--onedir", "--console",
        "--name", NOME, "--icon", str(ICONE),
        "--distpath", str(TRABALHO / "dist"), "--workpath", str(TRABALHO / "work"), "--specpath", str(TRABALHO),
        "--paths", str(RAIZ), "--add-data", f"{RAIZ / 'app.py'}{os.pathsep}.",
        "--collect-data", "streamlit", "--collect-submodules", "streamlit",
        "--collect-data", "plotly", "--collect-data", "reportlab", "--collect-data", "pdfminer",
        "--collect-all", "pypdfium2_raw", "--collect-all", "pypdfium2",
    ]
    for pacote in ("streamlit", "plotly", "narwhals", "pdfplumber", "pdfminer.six", "pypdfium2", "pyarrow",
                   "altair", "pandas", "numpy", "scikit-learn", "openpyxl", "reportlab", "rapidfuzz"):
        args += ["--copy-metadata", pacote]
    for fora in ("tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6",
                 "streamlit.external", "streamlit.testing"):
        args += ["--exclude-module", fora]
    PyInstaller.__main__.run(args)
    return TRABALHO / "dist" / NOME


def licencas(pasta_app: Path):
    """LICENSE.txt (com BOM, para a página do instalador), avisos e o texto da licença de cada pacote."""
    texto = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    (pasta_app / "LICENSE.txt").write_text(texto, encoding="utf-8-sig")
    shutil.copy(RAIZ / "THIRD_PARTY_NOTICES.md", pasta_app / "THIRD_PARTY_NOTICES.md")
    destino = pasta_app / "licencas"
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir()
    faltando = []
    for dist in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower()):
        nome = dist.metadata["Name"]
        if nome.lower() in SO_BUILD:
            continue
        # o caminho inteiro conta: alguns pacotes guardam em dist-info/licenses/LICENSES/Apache-2.0.txt
        arquivos = [f for f in (dist.files or []) if f.suffix not in (".py", ".pyc")
                    and any(p in str(f).upper() for p in ("LICEN", "COPYING", "NOTICE"))]
        pasta = destino / f"{nome}-{dist.version}"
        for f in arquivos:
            origem = Path(dist.locate_file(f))
            if origem.is_file():
                pasta.mkdir(exist_ok=True)
                shutil.copy(origem, pasta / f"{f.parent.name}_{f.name}" if (pasta / f.name).exists() else pasta / f.name)
        if not pasta.exists():
            faltando.append(nome)
            pasta.mkdir()
            licenca = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "ver PyPI"
            (pasta / "LICENCA.txt").write_text(f"{nome} {dist.version}\nLicença declarada: {licenca[:300]}\n",
                                               encoding="utf-8")
            if "apache" in licenca.lower():  # a Apache-2.0 pede o texto junto da distribuição
                shutil.copy(DESKTOP / "licencas_padrao" / "Apache-2.0.txt", pasta / "Apache-2.0.txt")
    python = Path(sys.base_prefix) / "LICENSE.txt"
    if python.exists():
        (destino / "Python").mkdir(exist_ok=True)
        shutil.copy(python, destino / "Python" / "LICENSE.txt")
    if faltando:
        print("Pacotes sem arquivo de licença no wheel (gravada a licença declarada):", ", ".join(faltando))


def tamanho_kb(pasta: Path) -> int:
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) // 1024


def nsis(pasta_app: Path, makensis: str, saida: Path) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    exe = saida / "Soil_Analyzer.exe"
    cmd = [makensis, "/V2", f"/DVERSAO={__version__}", f"/DORIGEM={pasta_app}", f"/DSAIDA={exe}",
           f"/DICONE={ICONE}", f"/DLICENCA={pasta_app / 'LICENSE.txt'}", f"/DTAMANHO_KB={tamanho_kb(pasta_app)}",
           str(DESKTOP / "instalador.nsi")]
    subprocess.run(cmd, check=True)
    return exe


def achar_makensis(dado: str | None) -> str:
    candidatos = [dado, os.environ.get("MAKENSIS"), shutil.which("makensis"),
                  *map(str, Path(sys.base_prefix).parent.glob("*/NSIS/makensis.exe")),
                  *map(str, (Path.home() / "miniforge3" / "envs").glob("*/NSIS/makensis.exe")),
                  r"C:\Program Files (x86)\NSIS\makensis.exe"]
    for c in candidatos:
        if c and Path(c).is_file():
            return c
    raise SystemExit("makensis.exe não encontrado: instale o NSIS (ex.: conda install -c conda-forge nsis) "
                     "ou passe --makensis.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--makensis", help="caminho do makensis.exe")
    ap.add_argument("--saida", default=str(TRABALHO / "saida"), help="pasta do Soil_Analyzer.exe")
    ap.add_argument("--reusar", action="store_true",
                    help="reaproveita o pacote do PyInstaller já gerado (refaz só licenças e instalador)")
    args = ap.parse_args()
    makensis = achar_makensis(args.makensis)
    if not ICONE.exists():
        gerar_icone()
    pasta_app = TRABALHO / "dist" / NOME
    if not (args.reusar and (pasta_app / f"{NOME}.exe").exists()):
        pasta_app = pyinstaller()
    licencas(pasta_app)
    exe = nsis(pasta_app, makensis, Path(args.saida))
    sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    print(f"\nInstalador: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)\nSHA-256: {sha}")
    (exe.parent / "Soil_Analyzer.exe.sha256").write_text(f"{sha}  Soil_Analyzer.exe\n", encoding="ascii")


if __name__ == "__main__":
    main()
