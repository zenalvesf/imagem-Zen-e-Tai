# Dados do site (gerados)

Os arquivos `.json` deste diretório **não são versionados** (≈48 MB). São gerados a
partir dos dados oficiais do TSE:

```bash
../baixar.sh            # baixa os BU Web + votação por seção para ../zips/
cd .. && python3 -I processar_2turno.py zips site/data
python3 -I comparativo_1turno.py zips site/data
```

Isso recria: `estados.json`, `municipios.json`, `sec_<UF>.json` (28), `comp1t.json`,
`swings.json`. O `index.html` ao lado os carrega via `fetch` relativo.

A versão publicada (com os dados embutidos) está em:
https://claude.ai/artifact/2PgFbiB37LviEjVAuYDLDP
