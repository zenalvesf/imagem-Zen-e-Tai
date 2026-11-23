#!/usr/bin/env bash
# Baixa os dados oficiais do TSE usados pela analise do 2o turno de 2026.
# Gera ./zips/ com os BU Web de todos os estados (2o turno) + a votacao por
# secao nacional (que contem o 1o turno de Presidente, para o comparativo).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p zips && cd zips

API="https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna"
BUWEB="https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb"
SECAO="https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2026_BR.zip"

# BU Web do 2o turno, todos os estados + DF + exterior (ZZ). RR as vezes so
# aparece como .sha512 no indice, mas o .zip existe no mesmo padrao de nome.
UFS="AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ"
for uf in $UFS; do
  echo "bweb 2t $uf"
  curl -fsS --retry 4 -o "bweb_2t_${uf}.zip" \
    "${BUWEB}/bweb_2t_${uf}_261020260742.zip" || echo "  (falhou $uf — confira o sufixo de data no indice: $API)"
done

# Votacao por secao (Presidente, nacional): traz 1o e 2o turno. Usado pelo comparativo.
echo "votacao_secao BR"
curl -fsS --retry 4 -o votacao_secao_2026_BR.zip "$SECAO"

# descompacta os CSVs
for z in *.zip; do unzip -o "$z" >/dev/null; done
echo "OK. CSVs em $(pwd)"
