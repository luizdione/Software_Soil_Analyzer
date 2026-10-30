"""Soil Analyzer para Windows: sobe o painel (Streamlit) só neste computador e abre o navegador.

É o ponto de entrada do executável gerado por desktop/build_exe.py (PyInstaller). Rodando do código:
    python desktop/soil_analyzer.py

- Dados (histórico, cadastro dos talhões): Documentos\\Soil Analyzer (ou a pasta em ANALISE_SOLO_DADOS).
- Cache do reconhecedor de colunas: %LOCALAPPDATA%\\Soil Analyzer\\cache.
- O servidor atende só em 127.0.0.1: os laudos não ficam visíveis para outras máquinas da rede.
- Se o programa já estiver aberto, um segundo clique só abre outra aba do navegador.
"""
from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
from pathlib import Path

RAIZ = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))  # pasta do app.py
sys.path.insert(0, str(RAIZ))
from solo import NOME, __version__  # noqa: E402

PORTA_PADRAO = 8520
LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home())) / NOME
ARQ_PORTA = LOCAL / "porta.txt"


def pasta_documentos() -> Path:
    """Pasta Documentos do Windows, mesmo quando redirecionada (ex.: para o OneDrive)."""
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]
    try:
        u = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")  # FOLDERID_Documents
        guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        caminho = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(caminho)) == 0:
            pasta = Path(caminho.value)
            ctypes.windll.ole32.CoTaskMemFree(caminho)
            return pasta
    except (AttributeError, OSError):
        pass
    return Path.home() / "Documents"


def no_ar(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/_stcore/health", timeout=1.5) as r:
            return r.read().strip() == b"ok"
    except OSError:
        return False


def porta_livre(preferida: int) -> int:
    for porta in [preferida, *range(preferida + 1, preferida + 50)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def abrir_quando_pronto(porta: int):
    for _ in range(240):  # até 2 min na primeira abertura (antivírus examinando os arquivos)
        if no_ar(porta):
            webbrowser.open(f"http://localhost:{porta}")
            print(f"\n  Painel aberto no navegador: http://localhost:{porta}")
            print("  Para encerrar o Soil Analyzer, feche esta janela.\n")
            return
        time.sleep(0.5)
    print(f"\n  O painel demorou a responder. Abra no navegador: http://localhost:{porta}\n")


def main():
    if os.name == "nt":
        ctypes.windll.kernel32.SetConsoleTitleW(f"{NOME} {__version__} - feche esta janela para encerrar")
    LOCAL.mkdir(parents=True, exist_ok=True)
    if ARQ_PORTA.exists():  # já aberto: só mostra de novo no navegador
        try:
            porta = int(ARQ_PORTA.read_text().strip())
            if no_ar(porta):
                webbrowser.open(f"http://localhost:{porta}")
                return
        except ValueError:
            pass

    dados = Path(os.environ.get("ANALISE_SOLO_DADOS") or pasta_documentos() / NOME)
    dados.mkdir(parents=True, exist_ok=True)
    os.environ["ANALISE_SOLO_DADOS"] = str(dados)
    os.environ.setdefault("ANALISE_SOLO_CACHE", str(LOCAL / "cache"))
    porta = porta_livre(PORTA_PADRAO)
    ARQ_PORTA.write_text(str(porta))

    print(f"  {NOME} {__version__}")
    print(f"  Seus dados ficam em: {dados}")
    print("  Abrindo o painel... (a primeira vez pode levar até um minuto)")
    threading.Thread(target=abrir_quando_pronto, args=(porta,), daemon=True).start()

    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", str(RAIZ / "app.py"),
                "--global.developmentMode=false", "--server.headless=true",
                "--server.address=127.0.0.1", f"--server.port={porta}",
                "--browser.gatherUsageStats=false", "--client.toolbarMode=viewer",
                "--theme.base=light", "--theme.primaryColor=#2E5E3A"]
    try:
        stcli.main()
    finally:
        ARQ_PORTA.unlink(missing_ok=True)


def _modulos_do_app():
    """Nunca é chamada: só mostra ao PyInstaller o que o app.py importa (ele não analisa o app.py)."""
    import plotly.graph_objects  # noqa: F401
    import plotly.subplots  # noqa: F401
    import solo.exportar  # noqa: F401
    import solo.historico  # noqa: F401
    import solo.leitor  # noqa: F401
    import solo.motor  # noqa: F401
    import solo.regras  # noqa: F401


if __name__ == "__main__":
    main()
