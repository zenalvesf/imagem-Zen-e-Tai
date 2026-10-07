#!/usr/bin/env python3
"""Gera painel-eleicoes-2026.html (tabela dinâmica estilo BI) a partir dos CSVs
de consolidar_tse.py, embutindo os dados em formato compacto no template.

Uso:
  python3 gerar_painel.py --dados ./dados
"""
import argparse
import csv
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))


def ler(dados, nome):
    with open(os.path.join(dados, f"{nome}.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def compactar(votos, resumo, por_municipio):
    """Locais e candidatos viram dicionários; cada linha vira [local, candidato, votos]."""
    locais, idx_l = [], {}
    cands, idx_c = [], {}
    v = []

    def local(r):
        k = (r["uf"], r["cod_municipio"]) if por_municipio else (r["uf"],)
        if k not in idx_l:
            idx_l[k] = len(locais)
            locais.append([r["regiao"], r["uf"], r["municipio"]] if por_municipio else [r["regiao"], r["uf"]])
        return idx_l[k]

    def cand(c):
        c = tuple(c)
        if c not in idx_c:
            idx_c[c] = len(cands)
            cands.append(list(c))
        return idx_c[c]

    for r in votos:
        votos_n = int(r["votos"])
        if votos_n == 0:
            continue
        v += [local(r), cand([r["cargo"], r["tipo"], r["numero"], r["candidato"], r["partido"],
                              r["situacao"]]), votos_n]
    for r in resumo:
        v += [local(r), cand([r["cargo"], "Abstenção", "", "Abstenção", "", ""]), int(r["abstencao"])]
    return {"l": locais, "c": cands, "v": v}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dados", required=True)
    p.add_argument("--saida", default=os.path.join(AQUI, "painel-eleicoes-2026.html"))
    a = p.parse_args()
    re_ = ler(a.dados, "resumo_estado")
    dados = {
        "mun": compactar(ler(a.dados, "votos_municipio"), ler(a.dados, "resumo_municipio"), True),
        "uf": compactar(ler(a.dados, "votos_estado"), re_, False),
        "aptosPres": sum(int(r["aptos"]) for r in re_ if r["cargo"] == "Presidente"),
    }
    with open(os.path.join(AQUI, "painel_template.html"), encoding="utf-8") as f:
        html = f.read()
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("/*__DADOS__*/", js)
    with open(a.saida, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Gerado: {a.saida} ({os.path.getsize(a.saida) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
