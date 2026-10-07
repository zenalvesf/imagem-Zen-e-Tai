#!/usr/bin/env python3
"""Regenera resultado-por-estado.xml com os resultados oficiais do TSE
(Presidente e Governador por estado), a partir dos CSVs de consolidar_tse.py.

Uso:
  python3 baixar_tse.py --dir ./tse-json
  python3 consolidar_tse.py --dir ./tse-json --saida ./dados
  python3 atualizar_resultados.py --dados ./dados
"""
import argparse
import csv
import os
import xml.etree.ElementTree as ET
from collections import defaultdict

XML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultado-por-estado.xml")
CARGOS = ("Presidente", "Governador")
ORDEM_UF = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
            "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]


def ler(dados, nome):
    with open(os.path.join(dados, f"{nome}.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def cargo_xml(pai, cargo, resumo, cands):
    validos = int(resumo["validos"])
    no = ET.SubElement(pai, "cargo", {
        "nome": cargo, "status": "final", "urnasApuradasPct": "100",
        "aptos": resumo["aptos"], "comparecimento": resumo["comparecimento"],
        "abstencao": resumo["abstencao"], "brancos": resumo["brancos"], "nulos": resumo["nulos"],
        "validos": resumo["validos"]})
    for c in sorted(cands, key=lambda c: -c["votos"]):
        ET.SubElement(no, "candidato", {
            "nome": c["candidato"], "partido": c["partido"], "votos": str(c["votos"]),
            "pct": f"{100 * c['votos'] / validos:.2f}" if validos else "", "situacao": c["situacao"]})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dados", required=True, help="pasta com os CSVs de consolidar_tse.py")
    a = p.parse_args()

    resumo = {(r["uf"], r["cargo"]): r for r in ler(a.dados, "resumo_estado")}
    cands = defaultdict(list)
    nomes, regioes = {}, {}
    for r in ler(a.dados, "votos_estado"):
        nomes[r["uf"]], regioes[r["uf"]] = r["municipio"], r["regiao"]
        if r["cargo"] in CARGOS and r["tipo"] == "Candidato":
            cands[(r["uf"], r["cargo"])].append({**r, "votos": int(r["votos"])})

    raiz = ET.Element("eleicao", {"ano": "2026", "turno": "1", "data": "2026-10-04",
                                  "segundoTurno": "2026-10-25", "fonte": "TSE"})
    raiz.append(ET.Comment(
        " Resultado oficial do 1º turno das Eleições Gerais 2026 por estado. Fonte: TSE, "
        "resultados.tse.jus.br (eleições 6257 e 6259, totalização de 05/10/2026). "
        "Percentuais sobre votos válidos. Gerado por atualizar_resultados.py. "))

    # Brasil = soma dos estados + exterior (ZZ)
    br_res = defaultdict(int)
    br_cand = defaultdict(lambda: {"votos": 0})
    for uf in ORDEM_UF + ["ZZ"]:
        r = resumo.get((uf, "Presidente"))
        if not r:
            continue
        for k in ("aptos", "comparecimento", "abstencao", "brancos", "nulos", "validos"):
            br_res[k] += int(r[k])
        for c in cands[(uf, "Presidente")]:
            b = br_cand[c["candidato"]]
            b.update({"candidato": c["candidato"], "partido": c["partido"], "situacao": c["situacao"]})
            b["votos"] += c["votos"]
    brasil = ET.SubElement(raiz, "brasil")
    cargo_xml(brasil, "Presidente", {k: str(v) for k, v in br_res.items()}, list(br_cand.values()))

    estados = ET.SubElement(raiz, "estados")
    for uf in ORDEM_UF:
        e = ET.SubElement(estados, "estado", {"uf": uf, "nome": nomes[uf], "regiao": regioes[uf]})
        for cargo in CARGOS:
            if (uf, cargo) in resumo:
                cargo_xml(e, cargo, resumo[(uf, cargo)], cands[(uf, cargo)])

    arvore = ET.ElementTree(raiz)
    ET.indent(arvore, space="  ")
    arvore.write(XML, encoding="UTF-8", xml_declaration=True)
    print(f"Atualizado: {XML}")


if __name__ == "__main__":
    main()
