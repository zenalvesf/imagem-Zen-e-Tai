#!/usr/bin/env python3
"""Junta os arquivos baixados por baixar_tse.py em tabelas CSV (separador ;).

Gera, na pasta de saída:
  votos_municipio.csv   votos por candidato, brancos e nulos em cada município
                        (Presidente, Governador, Senador)
  resumo_municipio.csv  aptos, comparecimento, abstenção, brancos, nulos e
                        válidos por município e cargo
  votos_estado.csv      o mesmo por estado, para todos os cargos (inclui
                        Deputados e votos de legenda)
  resumo_estado.csv     resumo por estado e cargo

Uso:
  python3 consolidar_tse.py --dir ./tse-json --saida ./dados
"""
import argparse
import csv
import json
import os

CARGOS = {1: ("Presidente", 6257), 3: ("Governador", 6259), 5: ("Senador", 6259),
          6: ("Deputado Federal", 6259), 7: ("Deputado Estadual", 6259),
          8: ("Deputado Distrital", 6259)}
POR_MUNICIPIO = (1, 3, 5)
REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul", "ZZ": "Exterior",
}
CAB_VOTOS = ["regiao", "uf", "cod_municipio", "municipio", "cargo", "tipo", "numero",
             "candidato", "partido", "situacao", "votos"]
CAB_RESUMO = ["regiao", "uf", "cod_municipio", "municipio", "cargo", "aptos", "comparecimento",
              "abstencao", "brancos", "nulos", "validos", "legenda"]


def inteiro(v):
    return int(v) if v not in (None, "") else 0


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def linhas(d, uf, cod, nome, cargo, com_legenda):
    """Devolve (linhas de votos, linha de resumo) de um arquivo do TSE."""
    base = [REGIAO.get(uf, ""), uf, cod, nome, CARGOS[cargo][0]]
    votos = []
    legenda = 0
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            if com_legenda and inteiro(par.get("tval")):
                legenda += inteiro(par["tval"])
                votos.append(base + ["Legenda", par["n"], f"Legenda {par['sg']}", par["sg"], "",
                                     inteiro(par["tval"])])
            for c in par["cand"]:
                votos.append(base + ["Candidato", c["n"], c["nmu"], par["sg"], c.get("st", ""),
                                     inteiro(c.get("vap"))])
    v, e = d["v"], d["e"]
    votos.append(base + ["Branco", "", "Brancos", "", "", inteiro(v.get("vb"))])
    votos.append(base + ["Nulo", "", "Nulos", "", "", inteiro(v.get("tvn"))])
    resumo = base + [inteiro(e.get("te")), inteiro(e.get("c")), inteiro(e.get("a")),
                     inteiro(v.get("vb")), inteiro(v.get("tvn")), inteiro(v.get("vv")), legenda]
    return votos, resumo


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", required=True)
    p.add_argument("--saida", required=True)
    a = p.parse_args()
    os.makedirs(a.saida, exist_ok=True)
    ufs = ler(os.path.join(a.dir, "mun-e006257-cm.json"))["abr"]

    saidas = {n: open(os.path.join(a.saida, f"{n}.csv"), "w", encoding="utf-8", newline="")
              for n in ("votos_municipio", "resumo_municipio", "votos_estado", "resumo_estado")}
    w = {n: csv.writer(f, delimiter=";") for n, f in saidas.items()}
    w["votos_municipio"].writerow(CAB_VOTOS)
    w["votos_estado"].writerow(CAB_VOTOS)
    w["resumo_municipio"].writerow(CAB_RESUMO)
    w["resumo_estado"].writerow(CAB_RESUMO)
    faltando = []

    for cargo, (_nome, ele) in CARGOS.items():
        sufixo = f"-c{cargo:04d}-e{ele:06d}-u.json"
        legenda = cargo in (6, 7, 8)
        for uf in ufs:
            sigla = uf["cd"].lower()
            arq = os.path.join(a.dir, f"{sigla}{sufixo}")
            if not os.path.exists(arq):
                continue
            vt, rs = linhas(ler(arq), sigla.upper(), "", uf["ds"].title() if sigla != "zz" else "Exterior",
                            cargo, legenda)
            w["votos_estado"].writerows(vt)
            w["resumo_estado"].writerow(rs)
            if cargo not in POR_MUNICIPIO or sigla == "zz":
                continue
            for mu in uf["mu"]:
                arq = os.path.join(a.dir, f"{sigla}{mu['cd']}{sufixo}")
                if not os.path.exists(arq):
                    faltando.append(arq)
                    continue
                vt, rs = linhas(ler(arq), sigla.upper(), mu["cd"], mu["nm"].title(), cargo, False)
                w["votos_municipio"].writerows(vt)
                w["resumo_municipio"].writerow(rs)
    for f in saidas.values():
        f.close()
    print(f"Gerado em {a.saida}. Arquivos de município ausentes: {len(faltando)}")


if __name__ == "__main__":
    main()
