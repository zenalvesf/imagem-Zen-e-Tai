# HANDOFF — Análise do 2º turno 2026 (Presidente)

_Atualizado em 2026-11-23. Trabalho em `eleicoes-2026/2turno-analise/`._

## Objetivo

Investigar, com **dados oficiais do TSE**, hipóteses sobre o 2º turno de 2026
(Lula × Flávio Bolsonaro, 25/10/2026): horário de encerramento das urnas e
"votos após as 17h", integridade da apuração e migração de votos entre turnos.
Entregar um **site navegável** (Brasil → estado → município → seção/urna) para o
usuário conferir cada número por conta própria.

## O que foi feito

1. **Base por seção, Brasil todo.** Baixados os BU Web do 2º turno (27 UFs +
   exterior) e agregados seção a seção. A soma nacional **reproduz o resultado
   oficial ao voto**: Lula **64.256.232 (51,79%)**, Flávio **59.826.041 (48,21%)**.
   Essa é a checagem de integridade central — passou.
2. **Horário por urna.** O BU Web traz `DT_ABERTURA`, `DT_ENCERRAMENTO`,
   `DT_EMISSAO_BU` e `DT_BU_RECEBIDO` por seção. Cruzamos horário × votos.
3. **Comparativo 1º × 2º turno.** Contabilidade nacional que fecha exatamente, e
   estimativa de migração por regressão ecológica entre os ~5.715 municípios.
4. **Site publicado** (privado, na conta do usuário):
   **https://claude.ai/artifact/2PgFbiB37LviEjVAuYDLDP** (Version 4). Abas:
   *Explorar urnas* e *Migração 1º→2º turno* (contabilidade, estimativa, ranking
   de estados, municípios onde o Flávio recuou).
5. **CSVs da Bahia** entregues ao usuário (`ba_secoes.csv`, `ba_municipios.csv`).

## Achados principais

- **"Votos após as 17h" não é indício de nada.** A votação encerra às 17h; a urna
  mais cedo encerrou 17:00:10. Logo ~100% dos votos vêm de urnas encerradas "após
  as 17h" — é o funcionamento normal. A proporção Lula/Flávio é **estável entre
  todas as faixas de horário** (nacional ~51,6% no pico 17:00–17:10; urnas tardias
  votam igual). Encerramento tardio ≠ inserção de voto (o BU é congelado no
  encerramento). Tardança concentrada no Nordeste e na prorrogação judicial daquele
  domingo.
- **Contabilidade 1T→2T fecha ao voto.** Ganho combinado Lula+Flávio = **+14.098.232**
  = eliminados liberados (**+9.321.993**) + novos válidos (**+4.776.239**: −2,96 mi
  de abstenção e −1,82 mi de brancos/nulos). Lula ficou com 73,6% do ganho.
- **Migração estimada (ecológica):** ~58% dos votos dos eliminados → Lula; ~95% dos
  votos novos (ex-abstenção/branco/nulo) → Lula. Ou seja, a virada vem da
  **mobilização**, não de "converter a direita". Flávio **cresceu** +3,7 mi no
  agregado; só recuou em 950 municípios pequenos de N/NE onde Lula já dominava.
- **Nenhum recorte produziu assinatura de manipulação.**

## Decisões

- **Fonte:** BU Web (`bweb_2t_<UF>`) do portal de dados abertos do TSE, por ser CSV
  com horários por urna. Cross-check com `votacao_secao_2026_BR` (bate ao voto).
- **Classificação por NÚMERO do votável** (13=Lula, 22=Flávio, 95=Branco, 96=Nulo),
  e **filtro `DS_CARGO_PERGUNTA == 'Presidente'`** — necessário porque AC, AM, DF,
  ES, RN e TO têm 2º turno de **governador** no mesmo arquivo (foi o bug que, se
  ignorado, dá Flávio ganhando).
- **Fuso horário** normalizado para Brasília nos cortes de horário (AC +2h;
  AM/MT/MS/RO/RR +1h). Limitação conhecida: o Amazonas tem municípios em dois
  fusos, então ~556 seções aparecem como "<17h" por aproximação — artefato, não
  anomalia.
- **Honestidade metodológica:** a migração é **inferência ecológica** (estima de
  totais por município, não do voto individual); deixado explícito no site.
- **Dados grandes não versionados:** os `.json` do site (~48 MB) e os CSVs do TSE
  (~1,5 GB) são regeneráveis pelos scripts; o site publicado já tem os dados
  embutidos.

## Estado atual

- Site publicado e funcional (Version 4), privado na conta do usuário.
- Scripts de reprodução versionados em `eleicoes-2026/2turno-analise/`.
- Os dados brutos e os `.json` gerados **não** estão no repo (efêmeros no
  scratchpad desta sessão; recriáveis com `baixar.sh` + os dois scripts).

## Próximos passos (ideias deixadas em aberto)

- Mapa/coropleto por estado da virada (hoje é tabela/ranking).
- Aba destacando as seções de encerramento mais tardio de cada estado.
- Abstenção por município 1T×2T (exige `aptos` do 1º turno — baixar `detalhe` ou
  BU Web do 1º turno).
- Reproduzir a verificação para outros cargos (governador 2º turno) se desejado.

## Como retomar

```bash
cd eleicoes-2026/2turno-analise
./baixar.sh
python3 -I processar_2turno.py zips site/data      # valida total nacional
python3 -I comparativo_1turno.py zips site/data     # contabilidade + migração
```
Para atualizar o site publicado, republicar `site/index.html` + `site/data/` no
mesmo artifact (mesma URL acima).
