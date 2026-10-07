#!/usr/bin/env python3
"""Baixa do site de resultados do TSE os arquivos de todos os cargos
(1º turno de 2026) por estado e por município.

Eleições no TSE: 6257 = federal (Presidente), 6259 = estadual (Governador,
Senador, Deputado Federal, Estadual e Distrital).
Arquivos: {BASE}/{eleicao}/dados/{uf}/{uf}[{cod_mun}]-c{cargo:04d}-e{eleicao:06d}-u.json

Uso:
  python3 baixar_tse.py --dir ./tse-json
"""
import argparse
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://resultados.tse.jus.br/oficial/ele2026"
# (eleição, cargo, baixa por município?)
# Deputados vêm só por estado: por município são ~1 GB de arquivos.
CARGOS = [(6257, 1, True), (6259, 3, True), (6259, 5, True),
          (6259, 6, False), (6259, 7, False), (6259, 8, False)]


def baixar(url, destino):
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return "ok"
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                dados = r.read()
            with open(destino, "wb") as f:
                f.write(dados)
            return "ok"
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                return "404"
        except Exception:
            pass
    return "falha"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", required=True)
    p.add_argument("--threads", type=int, default=16)
    a = p.parse_args()
    os.makedirs(a.dir, exist_ok=True)

    mun_json = os.path.join(a.dir, "mun-e006257-cm.json")
    baixar(f"{BASE}/6257/config/mun-e006257-cm.json", mun_json)
    with open(mun_json, encoding="utf-8") as f:
        ufs = json.load(f)["abr"]

    tarefas = []
    for ele, cargo, por_mun in CARGOS:
        sufixo = f"-c{cargo:04d}-e{ele:06d}-u.json"
        abrs = ["br", "zz"] if cargo == 1 else []
        for uf in ufs:
            sigla = uf["cd"].lower()
            if sigla in ("br", "zz"):
                continue
            # DF não tem Deputado Estadual (tem Distrital) e só o DF tem Distrital
            if (cargo == 7 and sigla == "df") or (cargo == 8 and sigla != "df"):
                continue
            abrs.append(sigla)
            if por_mun:
                for mu in uf["mu"]:
                    tarefas.append((ele, sigla, f"{sigla}{mu['cd']}{sufixo}"))
        for sigla in abrs:
            tarefas.append((ele, sigla, f"{sigla}{sufixo}"))

    def executar(t):
        ele, sigla, nome = t
        return nome, baixar(f"{BASE}/{ele}/dados/{sigla}/{nome}", os.path.join(a.dir, nome))

    resultado = {"ok": 0, "404": 0, "falha": 0}
    falhas = []
    with ThreadPoolExecutor(a.threads) as ex:
        for nome, st in ex.map(executar, tarefas):
            resultado[st] += 1
            if st != "ok":
                falhas.append(nome)
    print(f"Arquivos: {len(tarefas)} | ok {resultado['ok']} | 404 {resultado['404']} | falha {resultado['falha']}")
    if falhas:
        print("Sem arquivo:", ", ".join(falhas[:20]), "..." if len(falhas) > 20 else "")


if __name__ == "__main__":
    main()
