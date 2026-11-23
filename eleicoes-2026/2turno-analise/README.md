# Análise do 2º turno 2026 — por seção, município e urna

Reprocessamento dos **Boletins de Urna (BU Web)** do 2º turno (25/10/2026) para
Presidente, com horário de encerramento/transmissão de cada urna, e comparativo
1º × 2º turno (migração de votos). Complementa as análises da pasta `eleicoes-2026/`.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `baixar.sh` | Baixa do TSE os BU Web (2º turno, 27 UFs + exterior) e a votação por seção nacional, em `./zips/`. |
| `processar_2turno.py` | Agrega por seção → `site/data/estados.json`, `municipios.json`, `sec_<UF>.json`. Valida o total nacional contra o oficial. |
| `comparativo_1turno.py` | Agrega o 1º turno, fecha a contabilidade 1T→2T, estima migração (regressão ecológica) e gera `swings.json`. |
| `site/index.html` | Site navegável (Brasil → estado → município → seção/urna) + aba de migração. Carrega `site/data/*.json`. |
| `urls_2t.txt` | URLs dos BU Web do 2º turno (referência). |

## Reproduzir

```bash
./baixar.sh
python3 -I processar_2turno.py zips site/data
python3 -I comparativo_1turno.py zips site/data
# depois abrir site/index.html servindo a pasta (fetch relativo precisa de http)
```

Versão publicada: https://claude.ai/artifact/2PgFbiB37LviEjVAuYDLDP
