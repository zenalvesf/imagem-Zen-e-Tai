#!/usr/bin/env python3
"""Preenche resultado-por-estado.xml com os dados simplificados do TSE.

Os arquivos do TSE seguem o padrão (formato usado em 2022):
  {base}/{eleicao}/dados-simplificados/{uf}/{uf}-c{cargo:04d}-e{eleicao:06d}-r.json
com os campos "pst" (% de seções totalizadas) e "cand" (lista de candidatos
com "nm", "cc", "vap", "pvap", "e" e "st").

Uso:
  # baixando direto do TSE (os códigos de eleição de 2026 saem no ele-c.json)
  python3 atualizar_resultados.py --eleicao-presidente <cod> --eleicao-governador <cod>

  # ou a partir de JSONs já baixados numa pasta (mesmos nomes de arquivo)
  python3 atualizar_resultados.py --dir ./json --eleicao-presidente <cod> --eleicao-governador <cod>
"""
import argparse
import json
import os
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://resultados.tse.jus.br/oficial/ele2026"
CARGOS = {"Presidente": 1, "Governador": 3}
XML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultado-por-estado.xml")


def num(valor):
    return str(valor).replace(".", "").replace(",", ".") if valor not in (None, "") else ""


def carregar(uf, cargo, eleicao, pasta):
    nome = f"{uf}-c{cargo:04d}-e{eleicao:06d}-r.json"
    if pasta:
        caminho = os.path.join(pasta, nome)
        if not os.path.exists(caminho):
            return None
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    url = f"{BASE}/{eleicao}/dados-simplificados/{uf}/{nome}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as erro:
        print(f"  {uf} c{cargo}: falha ao baixar ({erro})")
        return None


def preencher(no_cargo, dados):
    for filho in list(no_cargo):
        if filho.tag == "candidato":
            no_cargo.remove(filho)
    pst = num(dados.get("pst"))
    no_cargo.set("urnasApuradasPct", pst)
    no_cargo.set("status", "final" if pst in ("100", "100.00") else "parcial")
    candidatos = sorted(dados.get("cand", []), key=lambda c: int(num(c.get("vap")) or 0), reverse=True)
    for c in candidatos:
        ET.SubElement(no_cargo, "candidato", {
            "nome": c.get("nm", ""),
            "partido": c.get("cc", ""),
            "votos": num(c.get("vap")),
            "pct": num(c.get("pvap")),
            "situacao": c.get("st", ""),
        })


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eleicao-presidente", type=int, required=True)
    p.add_argument("--eleicao-governador", type=int, required=True)
    p.add_argument("--dir", help="pasta com os JSONs do TSE já baixados")
    args = p.parse_args()
    eleicoes = {"Presidente": args.eleicao_presidente, "Governador": args.eleicao_governador}

    arvore = ET.parse(XML, ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    for estado in arvore.getroot().iter("estado"):
        uf = estado.get("uf").lower()
        for no_cargo in estado.findall("cargo"):
            nome = no_cargo.get("nome")
            dados = carregar(uf, CARGOS[nome], eleicoes[nome], args.dir)
            if dados:
                preencher(no_cargo, dados)
                print(f"  {uf.upper()} {nome}: {no_cargo.get('urnasApuradasPct')}% apurado")

    dados_br = carregar("br", CARGOS["Presidente"], eleicoes["Presidente"], args.dir)
    if dados_br:
        no_br = arvore.getroot().find("brasil/cargo")
        preencher(no_br, dados_br)
        no_br.set("fonte", "TSE")

    ET.indent(arvore, space="  ")
    arvore.write(XML, encoding="UTF-8", xml_declaration=True)
    print(f"Atualizado: {XML}")


if __name__ == "__main__":
    main()
