; Instalador do Soil Analyzer (NSIS 3). Gerado por desktop/build_exe.py, que passa:
;   /DVERSAO=1.0.0  /DORIGEM=<pasta do PyInstaller>  /DSAIDA=<Soil_Analyzer.exe>
;   /DICONE=<.ico>  /DLICENCA=<LICENSE.txt>  /DTAMANHO_KB=<n>
; Instala por usuário (sem administrador) em %LOCALAPPDATA%\Programs\Soil Analyzer.
; Desinstalar apaga só os arquivos do programa: os dados em Documentos\Soil Analyzer ficam.

Unicode true
!include "MUI2.nsh"

!define NOME "Soil Analyzer"
!define EXE "Soil Analyzer.exe"
!define AUTOR "Luiz Dione Barbosa De-Melo (IFRJ)"
!define CHAVE_DESINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoilAnalyzer"

Name "${NOME} ${VERSAO}"
OutFile "${SAIDA}"
InstallDir "$LOCALAPPDATA\Programs\${NOME}"
InstallDirRegKey HKCU "Software\${NOME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "${NOME} ${VERSAO} · freeware"

VIProductVersion "${VERSAO}.0"
VIAddVersionKey /LANG=1046 "ProductName" "${NOME}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "FileVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do ${NOME}"
VIAddVersionKey /LANG=1046 "CompanyName" "${AUTOR}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "© 2026 ${AUTOR} · freeware"

!define MUI_ICON "${ICONE}"
!define MUI_UNICON "${ICONE}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Instalar o ${NOME}"
!define MUI_WELCOMEPAGE_TEXT "O ${NOME} lê o laudo de análise de solo (PDF, Excel ou CSV) e monta o plano de calagem e adubação dos seus talhões.$\r$\n$\r$\nNão precisa de internet nem de senha de administrador. Seus dados ficam na pasta Documentos\${NOME}.$\r$\n$\r$\nClique em Avançar para continuar."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o ${NOME} agora"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENCA}"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "${NOME}" SecPrograma
  SetOutPath "$INSTDIR"
  ; atualização limpa: tira a versão anterior do programa (nunca os dados do usuário)
  RMDir /r "$INSTDIR\_internal"
  File /r "${ORIGEM}\*.*"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"

  CreateDirectory "$SMPROGRAMS\${NOME}"
  CreateShortcut "$SMPROGRAMS\${NOME}\${NOME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateShortcut "$SMPROGRAMS\${NOME}\Desinstalar ${NOME}.lnk" "$INSTDIR\Desinstalar.exe"
  CreateShortcut "$DESKTOP\${NOME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0

  WriteRegStr HKCU "Software\${NOME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayName" "${NOME}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "Publisher" "${AUTOR}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINST}" "UninstallString" "$\"$INSTDIR\Desinstalar.exe$\""
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "NoRepair" 1
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "EstimatedSize" ${TAMANHO_KB}
SectionEnd

Section "Uninstall"
  ; só o que o instalador pôs aqui (nunca RMDir /r no $INSTDIR inteiro: o usuário pode ter escolhido outra pasta)
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\licencas"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\THIRD_PARTY_NOTICES.md"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\${NOME}\${NOME}.lnk"
  Delete "$SMPROGRAMS\${NOME}\Desinstalar ${NOME}.lnk"
  RMDir "$SMPROGRAMS\${NOME}"
  Delete "$DESKTOP\${NOME}.lnk"

  DeleteRegKey HKCU "${CHAVE_DESINST}"
  DeleteRegKey HKCU "Software\${NOME}"
SectionEnd
