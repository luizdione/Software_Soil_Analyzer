# Soil Analyzer

**Do laudo de análise de solo ao plano de calagem e adubação, em poucos cliques.**

O Soil Analyzer lê o laudo do laboratório (PDF, Excel ou CSV), reconhece sozinho as colunas
(pH, P, K, Ca, Mg, Al, H+Al, M.O., V%...), pede a área de cada talhão e entrega:

- **o que comprar**, em sacos de 50 kg (e o custo, se você informar os preços);
- **quanto aplicar** em cada talhão, em kg/ha, kg no talhão e g/m² (para aplicar à mão);
- **quando aplicar**, num calendário da safra das águas;
- **se precisa de calcário** (só quando a calagem compensa), com o tipo (calcítico ou dolomítico);
- um **relatório em PDF** e uma **planilha Excel** para levar ao campo ou à loja de insumos.

Ele guarda o histórico de cada talhão: na próxima análise, compara com a anterior e avisa o que
mudou (fósforo subiu, potássio caindo, solo acidificando, matéria orgânica caindo).

Culturas atendidas: **braquiária** (pastagem em manutenção ou em reforma), **capim BRS Capiaçu**
(capineira) e **coqueiros** dentro dos talhões. Os critérios seguem o *Manual de Calagem e
Adubação do Estado do Rio de Janeiro* (ver [Critérios](#critérios-agronômicos)).

Programa gratuito (**freeware**), em português, para Windows. Funciona sem internet.

---

## Baixar e instalar

1. Abra a página de versões: **<https://github.com/luizdione/Soil_Analyzer/releases/latest>**
2. Em **Assets**, clique em **`Soil_Analyzer.exe`** para baixar o instalador.
3. Dê duplo clique no arquivo baixado.
   - O Windows pode mostrar **"O Windows protegeu o computador"** (o instalador não tem
     assinatura digital paga). Clique em **Mais informações → Executar assim mesmo**.
4. Siga o instalador (Avançar → Aceito → Instalar). **Não precisa de senha de administrador.**
5. No fim, deixe marcado **"Abrir o Soil Analyzer agora"**. Depois, abra pelo atalho
   **Soil Analyzer** na Área de Trabalho ou no Menu Iniciar.

Requisitos: Windows 10 ou 11 de 64 bits e cerca de 500 MB livres em disco (o instalador tem
~105 MB; instalado, o programa ocupa ~390 MB).

> Para conferir o download, compare o SHA-256 do arquivo (PowerShell:
> `Get-FileHash .\Soil_Analyzer.exe`) com o publicado junto da versão.

## Como usar

Ao abrir, aparece uma **janela preta** (é o motor do programa) e, em seguida, o painel no seu
navegador. **Deixe a janela preta aberta enquanto usa; fechá-la encerra o programa.** O painel
só existe no seu computador (endereço `http://localhost:8520`): nada é enviado para a internet.

### 1. Nova análise

1. Clique em **Browse files** (ou arraste o arquivo) e escolha o laudo: PDF digital do
   laboratório, ou planilha XLSX/CSV.
2. Confira a **data do laudo** e o **laboratório**.
3. Abra **"Como o arquivo foi lido"** para ver como cada coluna foi reconhecida e a confiança.
   Se alguma estiver errada, troque o campo na coluna **"Reconhecido como"**: ao salvar, o
   programa aprende o formato daquele laboratório.
4. Em **Talhões deste laudo**, para cada amostra (sigla), informe:
   - **Área (m²)** do talhão (1 ha = 10.000 m²);
   - **Cultura**: braquiária (manutenção), braquiária (reforma/replantio) ou capiaçu;
   - **Coqueiros**: quantos há no talhão e a idade (0 se não houver).

   Siglas já analisadas antes aparecem como **"já analisada"** e trazem o cadastro. Se o
   laboratório escreveu diferente (ex.: `A-12` em vez de `A12`), ajuste em **"Usar como"** para
   juntar ao histórico certo.
5. Pronto: o plano aparece logo abaixo (**O que comprar**, **Quanto aplicar**, **Calendário**,
   **Como aplicar**, **Coqueiros** e **Alertas**).
6. Baixe o **relatório (PDF)** e a **planilha (Excel)**. Na aba *Compras* da planilha, digite os
   preços nas células amarelas: o custo sai por fórmula.
7. Clique em **Salvar este laudo e o cadastro dos talhões no histórico**.

### 2. Fazenda

Junta a **análise mais recente de cada talhão** (cada um pode ter sido analisado numa data
diferente) e refaz o plano da propriedade inteira. Ajuste áreas e culturas ali e clique em
**Salvar cadastro dos talhões**.

### 3. Histórico

Gráficos da evolução de pH, V%, fósforo e potássio de cada talhão ao longo dos laudos, e a
tabela com todas as análises. Para apagar um laudo importado por engano, use **Remover um laudo**.

### Barra lateral (ajustes)

| Ajuste | Para que serve |
|---|---|
| **Nível de adubação** | *Econômico* (menos adubo, mantém o pasto) ou *Nível médio* (mais produção). |
| **Pastagens só com cloreto de potássio** | Repõe só o potássio nas pastagens em manutenção, sem nitrogênio. |
| **PRNT do calcário (%)** | Poder do calcário que você vai comprar (está no rótulo). |
| **P₂O₅ do adubo fosfatado (%)** | Garantia de P₂O₅ do rótulo: superfosfato simples **reativo 26%** (padrão), superfosfato simples comum 18%, ou o 2º número de um adubo composto (04-14-08 → 14). |
| **Preços** | Preço por saco/tonelada, para o custo estimado. |
| **Cópia do histórico (.zip)** | Cópia de segurança, ou para levar o histórico a outro computador. |

## Onde ficam os seus dados

Na pasta **Documentos\Soil Analyzer** (arquivos simples, que abrem no Excel):

```
historico\analises.csv              uma linha por amostra de cada laudo
historico\talhoes.json              área, cultura e coqueiros de cada talhão
historico\aprendizado_colunas.csv   correções de leitura que o programa aprendeu
```

**Desinstalar** (Configurações → Aplicativos → Soil Analyzer → Desinstalar, ou o atalho no Menu
Iniciar) remove o programa, mas **mantém** essa pasta. **Atualizar**: basta instalar a versão nova
por cima; o histórico continua.

## Como o programa reconhece o laudo

1. **Extrai as tabelas** do PDF (pdfplumber) ou da planilha (pandas) e junta cabeçalhos de várias
   linhas; a data do laudo sai do texto.
2. **Lê o cabeçalho** de cada coluna com um classificador de texto (TF-IDF de n-gramas de
   caracteres + regressão logística): reconhece "pH H2O", "pH em água", "Fósforo (mg/dm3)",
   "P Mehlich"...
3. **Olha os valores** da coluna (faixa, mediana, casas decimais) com uma floresta aleatória, para
   separar, por exemplo, P de K ou Ca de Mg quando o cabeçalho é ambíguo.
4. **Atribui um campo a cada coluna** combinando as duas leituras (algoritmo húngaro), converte
   unidades (M.O. em dag/kg → g/kg) e calcula o que falta (K em cmolc, SB, T, V%).
5. **Aprende com as suas correções**: cada ajuste salvo vira exemplo de treino.

Limitações:
- **PDF escaneado** (foto/imagem, sem texto selecionável) não é lido: não há OCR. Peça ao
  laboratório o PDF digital ou digite o laudo numa planilha.
- Num **adubo composto**, o N e o K que ele traz não são descontados do 25-00-25.

## Critérios agronômicos

- Interpretação de P, K e pH (Mehlich-1) e de Ca, Mg e Al: Freire et al. (2013), *Manual de
  Calagem e Adubação do Estado do Rio de Janeiro*.
- Calagem pelo método da saturação por bases (V% alvo: 50% braquiária, 60% capiaçu); só é
  recomendada quando passa de 0,2 t/ha.
- Doses: 5ª Aproximação de Minas Gerais (Cantarutti et al., 1999) para pastagens; Embrapa,
  Circular Técnica 79 (Pereira et al., 2016) para o BRS Capiaçu; Embrapa Tabuleiros Costeiros,
  *A cultura do coqueiro*, para os coqueiros.
- O fósforo é recomendado em **kg de P₂O₅/ha** e convertido em kg de adubo pela garantia
  informada. Kit de compra: **25-00-25 + superfosfato simples** (+ bórax para coqueiros,
  calcário só quando compensa).

> **Aviso:** as recomendações são sugestões técnicas calculadas a partir do laudo. Elas não
> substituem a avaliação de um engenheiro agrônomo. Confira o laudo, as áreas e a garantia dos
> adubos antes de comprar ou aplicar.

---

## Para desenvolvedores

Código em Python (Streamlit). Estrutura:

```
app.py                  painel (3 abas)
solo/regras.py          faixas de interpretação, doses por cultura e nível, coqueiro
solo/leitor.py          leitura do laudo e reconhecimento de colunas por ML
solo/historico.py       histórico por talhão, cadastro, comparação, cópia em .zip
solo/motor.py           plano por talhão, calagem, coqueiros, calendário, compras
solo/exportar.py        relatório PDF e planilha Excel
desktop/soil_analyzer.py  ponto de entrada do programa instalado
desktop/build_exe.py    gera o instalador Soil_Analyzer.exe (PyInstaller + NSIS)
desktop/instalador.nsi  script do instalador
tools/build_web.py      versão para navegador (stlite/Pyodide), opcional
tests/                  testes (pytest)
```

**Rodar do código** (Python 3.11):

```bash
pip install -r requirements.txt
```

```bash
python desktop/soil_analyzer.py
```

(ou `abrir_dashboard.bat`, ou `python -m streamlit run app.py`). A pasta de dados pode ser
trocada pela variável de ambiente `ANALISE_SOLO_DADOS`.

**Testes:**

```bash
python -m pytest -q
```

O teste com um laudo PDF real só roda se a variável `LAUDO_PESAGRO` apontar para o arquivo; os
demais usam um laudo sintético gerado no próprio teste.

**Gerar o instalador** (precisa do NSIS, ex.: `conda install -c conda-forge nsis`):

```bash
pip install -r requirements.txt pyinstaller==6.22.3
```

```bash
python desktop/build_exe.py
```

O instalador sai em `%LOCALAPPDATA%\soil_analyzer_build\saida\Soil_Analyzer.exe`, com o SHA-256 ao
lado. Ele é publicado em **Releases** (não vai no repositório).

**Versão para navegador** (opcional): `python tools/build_web.py --help`. Gera uma página estática
em que o mesmo `app.py` roda no navegador (stlite); o laudo é lido no computador de quem usa.

## Licença

**Freeware** — uso livre e gratuito para qualquer finalidade; redistribuição do original sem
alterações e sem cobrança. Texto completo em [LICENSE](LICENSE). As bibliotecas de terceiros
mantêm as suas licenças: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Autor

Luiz Dione Barbosa De-Melo (De-Melo, L.D.B.) — Instituto Federal de Educação, Ciência e
Tecnologia do Rio de Janeiro (IFRJ). ORCID [0000-0003-2445-9943](https://orcid.org/0000-0003-2445-9943).

Como citar: De-Melo, L.D.B. *Soil Analyzer: laudo de análise de solo para plano de calagem e
adubação*. Versão 1.0. IFRJ, 2026. <https://github.com/luizdione/Soil_Analyzer>
