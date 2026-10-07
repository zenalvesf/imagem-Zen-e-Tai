#!/usr/bin/env python3
"""Confere log de urna x boletim de urna (BU) x totalização do TSE.

Para cada seção de um município (1º turno de 2026), baixa do TSE o BU e o log
da urna e confere:
  1. eleitores que votaram segundo o log ("O voto do eleitor foi computado")
     = comparecimento registrado no BU, para cada cargo;
  2. votos do log para cada cargo ("Voto confirmado para [X]" mais
     "Atribuído voto nulo por suspensão [X]", quando o eleitor não conclui)
     x votos do BU para o mesmo cargo;
  3. soma dos BUs do município, por candidato, = total publicado pelo TSE.

O BU é um arquivo ASN.1 (DER). Este script lê a estrutura sem depender do
esquema oficial: localiza os blocos ResultadoVotacao (tipo de cargo,
comparecimento, totais por cargo) e TotalVotosVotavel (tipo de voto,
quantidade, partido/número) pela forma de cada SEQUENCE.

Uso:
  python3 auditar_urnas.py --uf ac --municipio 01066 --dir ./urnas --saida ./auditoria
"""
import argparse
import csv
import io
import json
import os
import re
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

BASE = "https://resultados.tse.jus.br/oficial/ele2026"
PLEITO = 3220
ELEICOES = {6257: "federal", 6259: "estadual"}
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal",
          7: "Deputado Estadual", 8: "Deputado Distrital"}
TIPO_VOTO = {1: "Nominal", 2: "Branco", 3: "Nulo", 4: "Legenda", 5: "Cargo sem candidato",
             6: "Nulo por apuração em separado", 7: "Nulo por apuração em separado"}


# ---------------------------------------------------------------- download
def baixar(url, destino):
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return True
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                dados = r.read()
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as f:
                f.write(dados)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
        except Exception:
            pass
    return False


def secoes_do_municipio(pasta, uf, mun):
    cfg = os.path.join(pasta, f"{uf}-p{PLEITO:06d}-cs.json")
    baixar(f"{BASE}/arquivo-urna/{PLEITO}/config/{uf}/{uf}-p{PLEITO:06d}-cs.json", cfg)
    with open(cfg, encoding="utf-8") as f:
        d = json.load(f)
    for m in d["abr"][0]["mu"]:
        if m["cd"] == mun:
            # seções com "nsp" são agregadas: os eleitores votam na urna da seção principal
            return m["nm"], [(z["cd"], s["ns"], s.get("nsp")) for z in m["zon"] for s in z["sec"]]
    raise SystemExit(f"Município {mun} não encontrado em {uf.upper()}")


def baixar_secao(pasta, uf, mun, zona, secao):
    base = f"{BASE}/arquivo-urna/{PLEITO}/dados/{uf}/{mun}/{zona}/{secao}"
    dsec = os.path.join(pasta, uf, mun, f"{zona}-{secao}")
    aux = os.path.join(dsec, "aux.json")
    if not baixar(f"{base}/p{PLEITO:06d}-{uf}-m{mun}-z{zona}-s{secao}-aux.json", aux):
        return dsec, "sem aux"
    with open(aux, encoding="utf-8") as f:
        info = json.load(f)
    hashes = [h for h in info.get("hashes", []) if h.get("st") in ("Totalizado", "Recebido")] or info.get("hashes", [])
    if not hashes:
        return dsec, info.get("st", "sem arquivos")
    h = hashes[-1]
    for a in h["arq"]:
        if a["tp"] in ("bu", "log"):
            baixar(f"{base}/{h['hash']}/{a['nm']}", os.path.join(dsec, a["tp"]))
    return dsec, info.get("st", "")


# ---------------------------------------------------------------- DER
def der(buf, i=0, fim=None):
    """Lê elementos DER de buf[i:fim]; devolve lista de (classe, construido, tag, valor)."""
    fim = len(buf) if fim is None else fim
    out = []
    while i < fim:
        b = buf[i]; i += 1
        classe, cons, tag = b >> 6, bool(b & 0x20), b & 0x1F
        if tag == 0x1F:
            tag = 0
            while True:
                b = buf[i]; i += 1
                tag = (tag << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
        n = buf[i]; i += 1
        if n & 0x80:
            k = n & 0x7F
            n = int.from_bytes(buf[i:i + k], "big"); i += k
        val = der(buf, i, i + n) if cons else buf[i:i + n]
        out.append((classe, cons, tag, val))
        i += n
    return out


def inteiro(el):
    return int.from_bytes(el[3], "big", signed=True)


def eh(el, classe, tag, cons=None):
    return el[0] == classe and el[2] == tag and (cons is None or el[1] == cons)


UNIV, CTX = 0, 2
INTEGER, OCTET, ENUM, SEQ = 2, 4, 10, 16


def ler_bu(caminho):
    """Devolve {'eleicoes': {id: {'aptos':n, 'cargos': {cargo: {'comparecimento':n, 'votos': [..]}}}}}."""
    with open(caminho, "rb") as f:
        env = der(f.read())[0][3]
    conteudo = next(e for e in env if eh(e, UNIV, OCTET, False))[3]
    bu = der(conteudo)[0][3]
    res = {}

    def visitar(el):
        if not el[1]:
            return
        filhos = el[3]
        # ResultadoVotacaoPorEleicao: INTEGER idEleicao, INTEGER aptos, ..., SEQUENCE OF
        # ResultadoVotacao, assinaturas (OCTET STRING)
        lista = next((f for f in filhos if eh(f, UNIV, SEQ, True)), None)
        if (eh(el, UNIV, SEQ) and len(filhos) >= 3 and eh(filhos[0], UNIV, INTEGER)
                and inteiro(filhos[0]) in ELEICOES and lista is not None):
            ide = inteiro(filhos[0])
            ent = res.setdefault(ide, {"aptos": inteiro(filhos[1]), "cargos": {}})
            for rv in lista[3]:
                ler_resultado(rv[3], ent["cargos"])
            return
        for f in filhos:
            visitar(f)

    def ler_resultado(campos, cargos):
        # ResultadoVotacao: ENUM tipoCargo, INTEGER comparecimento, SEQUENCE OF TotalVotosCargo
        if not (len(campos) == 3 and eh(campos[0], UNIV, ENUM) and eh(campos[1], UNIV, INTEGER)):
            return
        comp = inteiro(campos[1])
        for tvc in campos[2][3]:
            c = tvc[3]
            cod = next((inteiro(x) for x in c[0][3] if not x[1]), None) if c[0][1] else inteiro(c[0])
            votos = []
            for tvv in c[-1][3]:
                ctx = {x[2]: x for x in tvv[3] if x[0] == CTX}
                tipo = inteiro(ctx[1]) if 1 in ctx else None
                qtd = inteiro(ctx[2]) if 2 in ctx else 0
                partido = numero = None
                if 3 in ctx and ctx[3][1]:
                    ints = [inteiro(x) for x in ctx[3][3] if eh(x, UNIV, INTEGER)]
                    if len(ints) >= 2:
                        partido, numero = ints[0], ints[1]
                votos.append({"tipo": TIPO_VOTO.get(tipo, str(tipo)), "qtd": qtd,
                              "partido": partido, "numero": numero})
            cargos[CARGOS.get(cod, str(cod))] = {"comparecimento": comp, "votos": votos}

    for el in bu:
        visitar(el)
    return res


# ---------------------------------------------------------------- log
RE_CARGO = re.compile(r"Voto confirmado para \[(.+?)\]")
RE_SUSP = re.compile(r"Atribu[ií]do voto nulo por suspens[aã]o \[(.+?)\]")


def textos_log(dados):
    """Devolve o texto de cada logd.dat do arquivo .jez. Quando a urna é trocada durante a
    votação, o log da urna substituída vem dentro, como outro .jez."""
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            if nome.endswith(".jez"):
                yield from textos_log(z.read(nome))
            elif nome.startswith("logd"):
                yield z.read(nome).decode("latin-1")


def ler_log(caminho):
    with open(caminho, "rb") as f:
        textos = list(textos_log(f.read()))
    computados, confirmados, suspensos, eventos = 0, Counter(), Counter(), Counter()
    por_hora = Counter()
    inicio = fim = None
    linhas = sorted(l for t in textos for l in t.splitlines()
                    if l[:10].count("/") == 2 and l[6:10] == "2026")
    for linha in linhas:
        p = linha.split("\t")
        if len(p) < 5:
            continue
        data, nivel, _id, app, msg = p[:5]
        if app != "VOTA":
            continue
        if msg == "O voto do eleitor foi computado":
            computados += 1
            por_hora[data[11:13]] += 1
            inicio = inicio or data
            fim = data
        m = RE_CARGO.match(msg)
        if m:
            confirmados[m.group(1)] += 1
        m = RE_SUSP.match(msg)
        if m:
            suspensos[m.group(1)] += 1
        if nivel in ("ERRO", "ALERTA"):
            eventos[f"{nivel}: {re.sub(r'[0-9]+', 'N', msg)}"] += 1
        elif msg == "Eleitor foi suspenso pelo mesário":
            eventos["Eleitor suspenso pelo mesário (não concluiu o voto)"] += 1
    if len(textos) > 1:
        eventos[f"Urna substituída durante a votação ({len(textos)} logs de urna)"] += 1
    return {"computados": computados, "confirmados": dict(confirmados), "suspensos": dict(suspensos),
            "urnas": len(textos), "por_hora": dict(por_hora),
            "primeiro_voto": inicio,
            "ultimo_voto": fim, "eventos": dict(eventos)}


# ---------------------------------------------------------------- TSE
def totais_tse(pasta, uf, mun, eleicao, cargo):
    nome = f"{uf}{mun}-c{cargo:04d}-e{eleicao:06d}-u.json"
    arq = os.path.join(pasta, "tse", nome)
    if not baixar(f"{BASE}/{eleicao}/dados/{uf}/{nome}", arq):
        return None
    with open(arq, encoding="utf-8") as f:
        d = json.load(f)
    cands = {}
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                cands[int(c["n"])] = (c["nmu"], int(c["vap"] or 0))
    v = d["v"]
    return {"cands": cands, "brancos": int(v["vb"]), "nulos": int(v["tvn"]),
            "comparecimento": int(d["e"]["c"])}


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uf", required=True)
    p.add_argument("--municipio", required=True, help="código TSE do município (5 dígitos)")
    p.add_argument("--dir", required=True, help="pasta de cache dos arquivos baixados")
    p.add_argument("--saida", required=True)
    p.add_argument("--threads", type=int, default=12)
    a = p.parse_args()
    uf, mun = a.uf.lower(), a.municipio
    os.makedirs(a.saida, exist_ok=True)

    nome_mun, secoes = secoes_do_municipio(a.dir, uf, mun)
    print(f"{nome_mun} ({uf.upper()}): {len(secoes)} seções")
    agregadas = [(z, s, p) for z, s, p in secoes if p]
    proprias = [(z, s) for z, s, p in secoes if not p]
    with ThreadPoolExecutor(a.threads) as ex:
        baixados = list(ex.map(lambda zs: (zs, *baixar_secao(a.dir, uf, mun, *zs)), proprias))

    linhas, soma = [], defaultdict(Counter)
    for zona, secao, principal in agregadas:
        linhas.append({"zona": zona, "secao": secao, "situacao": f"agregada à seção {principal}",
                       "log_bate_bu": "agregada"})
    for (zona, secao), dsec, st in baixados:
        bu_arq, log_arq = os.path.join(dsec, "bu"), os.path.join(dsec, "log")
        if not (os.path.exists(bu_arq) and os.path.exists(log_arq)):
            linhas.append({"zona": zona, "secao": secao, "situacao": f"sem BU/log ({st})"})
            continue
        bu, log = ler_bu(bu_arq), ler_log(log_arq)
        cargos = {}
        aptos = None
        for ide, ent in bu.items():
            aptos = aptos or ent["aptos"]
            cargos.update(ent["cargos"])
        comp = cargos.get("Presidente", next(iter(cargos.values()), {})).get("comparecimento")
        lin = {"zona": zona, "secao": secao, "situacao": st, "aptos_bu": aptos,
               "comparecimento_bu": comp, "votos_computados_log": log["computados"],
               "log_bate_bu": "OK" if comp == log["computados"] else "DIFERENTE",
               "primeiro_voto": log["primeiro_voto"], "ultimo_voto": log["ultimo_voto"],
               "urnas_no_log": log["urnas"], "votos_por_hora": json.dumps(log["por_hora"], sort_keys=True),
               "eventos_log": "; ".join(f"{k} ({v})" for k, v in log["eventos"].items())}
        for cargo, dados in cargos.items():
            total = sum(v["qtd"] for v in dados["votos"])
            no_log = log["confirmados"].get(cargo, 0) + log["suspensos"].get(cargo, 0)
            lin[f"votos_bu_{cargo}"] = total
            lin[f"votos_log_{cargo}"] = no_log
            lin[f"bate_{cargo}"] = "OK" if no_log == total else "DIFERENTE"
            for v in dados["votos"]:
                chave = v["numero"] if v["tipo"] in ("Nominal",) else v["tipo"]
                soma[cargo][chave] += v["qtd"]
        linhas.append(lin)

    campos = sorted({k for l in linhas for k in l}, key=lambda k: (
        ["zona", "secao", "situacao", "aptos_bu", "comparecimento_bu", "votos_computados_log",
         "log_bate_bu"].index(k) if k in ("zona", "secao", "situacao", "aptos_bu", "comparecimento_bu",
                                           "votos_computados_log", "log_bate_bu") else 99, k))
    with open(os.path.join(a.saida, f"secoes_{uf}{mun}.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        w.writeheader()
        w.writerows(linhas)

    comparacao = []
    for cargo_cod, eleicao in ((1, 6257), (3, 6259), (5, 6259)):
        cargo = CARGOS[cargo_cod]
        tse = totais_tse(a.dir, uf, mun, eleicao, cargo_cod)
        if not tse:
            continue
        # votos nominais em números fora da lista do TSE (candidatura indeferida/retirada)
        # são contados pelo TSE como nulos ("nulo técnico")
        tecnicos = sum(q for k, q in soma[cargo].items() if isinstance(k, int) and k not in tse["cands"])
        for numero, (nome, votos_tse) in sorted(tse["cands"].items(), key=lambda x: -x[1][1]):
            bu = soma[cargo].get(numero, 0)
            comparacao.append({"cargo": cargo, "candidato": nome, "numero": numero, "votos_tse": votos_tse,
                               "soma_bus": bu, "bate": "OK" if bu == votos_tse else "DIFERENTE"})
        for tipo, chave in (("Brancos", "Branco"), ("Nulos", "Nulo")):
            bu = soma[cargo].get(chave, 0)
            if chave == "Nulo":
                bu += sum(q for k, q in soma[cargo].items() if isinstance(k, str) and k.startswith("Nulo por"))
                bu += tecnicos
                tipo = f"Nulos (inclui {tecnicos} nulo(s) técnico(s))" if tecnicos else tipo
            vt = tse["brancos"] if chave == "Branco" else tse["nulos"]
            comparacao.append({"cargo": cargo, "candidato": tipo, "numero": "", "votos_tse": vt,
                               "soma_bus": bu, "bate": "OK" if bu == vt else "DIFERENTE"})
    with open(os.path.join(a.saida, f"comparacao_{uf}{mun}.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cargo", "candidato", "numero", "votos_tse", "soma_bus", "bate"],
                           delimiter=";")
        w.writeheader()
        w.writerows(comparacao)

    ok = sum(1 for l in linhas if l.get("log_bate_bu") == "OK")
    print(f"Seções com urna própria: {len(proprias)} (+{len(agregadas)} agregadas). "
          f"Log = BU: {ok} de {len(proprias)}")
    print(f"Candidatos/brancos/nulos com soma dos BUs = TSE: "
          f"{sum(1 for c in comparacao if c['bate'] == 'OK')} de {len(comparacao)}")
    with open(os.path.join(a.saida, f"resumo_{uf}{mun}.json"), "w", encoding="utf-8") as f:
        json.dump({"uf": uf.upper(), "municipio": nome_mun, "codigo": mun, "secoes": linhas,
                   "comparacao": comparacao}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
