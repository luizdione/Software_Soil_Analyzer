"""Gera THIRD_PARTY_NOTICES.md a partir dos pacotes instalados no ambiente de build.

Rodar com o Python do ambiente de build:  python desktop/gerar_avisos.py
Lista cada biblioteca que vai dentro do instalador, com versão, licença declarada e site, e marca
para revisão qualquer licença copyleft (GPL/LGPL/AGPL/MPL), que não pode entrar num freeware sem cuidado.
"""
from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from build_exe import SO_BUILD  # noqa: E402

COPYLEFT = re.compile(r"\b(A?GPL|LGPL|EUPL|CDDL)\b|General Public", re.I)  # forte: impede freeware
MPL = re.compile(r"\bMPL\b|Mozilla", re.I)  # copyleft por arquivo: ok sem modificar e com o fonte disponível


def licenca(dist) -> str:
    m = dist.metadata
    expr = m.get("License-Expression")
    if expr:
        return expr
    classif = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    texto = (m.get("License") or "").strip()
    if classif:
        return "; ".join(dict.fromkeys(classif))
    return texto.splitlines()[0][:80] if texto else "ver site do projeto"


def site(dist) -> str:
    m = dist.metadata
    for u in m.get_all("Project-URL") or []:
        nome, _, url = u.partition(",")
        if nome.strip().lower() in ("source", "source code", "homepage", "home", "repository", "code"):
            return url.strip()
    return m.get("Home-page") or f"https://pypi.org/project/{m['Name']}/"


def main():
    linhas, revisar, mpl = [], [], []
    for dist in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower()):
        nome = dist.metadata["Name"]
        if nome.lower() in SO_BUILD:
            continue
        lic = licenca(dist)
        linhas.append(f"| {nome} | {dist.version} | {lic} | {site(dist)} |")
        if COPYLEFT.search(lic):
            revisar.append(f"{nome} ({lic})")
        elif MPL.search(lic):
            mpl.append(f"{nome} ({site(dist)})")
    texto = f"""# Componentes de terceiros

O Soil Analyzer é freeware (ver [LICENSE](LICENSE)). O instalador para Windows inclui o Python e as
bibliotecas abaixo, cada uma sob a sua própria licença. No programa instalado, o texto completo de
cada licença fica na pasta `licencas`.

| Componente | Versão | Licença | Site |
|---|---|---|---|
| Python (intérprete) | {sys.version.split()[0]} | PSF-2.0 (inclui OpenSSL Apache-2.0, libffi MIT, zlib, SQLite domínio público) | https://www.python.org |
{chr(10).join(linhas)}

Outros componentes:

| Componente | Licença | Uso |
|---|---|---|
| PyInstaller (bootloader) | GPL-2.0 com exceção que permite distribuir o programa empacotado sob qualquer licença | executável `Soil Analyzer.exe` |
| NSIS | zlib/libpng | instalador `Soil_Analyzer.exe` |
| DejaVu Sans | Bitstream Vera / domínio público (ver `tools/fontes_web/LICENSE_DEJAVU`) | só na versão para navegador |
| stlite | Apache-2.0 | só na versão para navegador (carregado da CDN jsdelivr) |
| Pyodide | MPL-2.0 (sem modificação, carregado da CDN jsdelivr) | só na versão para navegador |

O relatório em PDF usa a fonte Arial já instalada no Windows (não é distribuída com o programa).
"""
    if mpl:
        texto += ("\nComponentes sob MPL-2.0 (copyleft só nos próprios arquivos) vão sem nenhuma modificação; o "
                  "código-fonte deles está no projeto original: " + ", ".join(mpl) + ".\n")
    if revisar:
        texto += "\n**Licenças para revisar (copyleft forte):** " + ", ".join(revisar) + "\n"
    (RAIZ / "THIRD_PARTY_NOTICES.md").write_text(texto, encoding="utf-8")
    print(f"THIRD_PARTY_NOTICES.md: {len(linhas)} pacotes; revisar: {revisar or 'nenhum'}")


if __name__ == "__main__":
    main()
