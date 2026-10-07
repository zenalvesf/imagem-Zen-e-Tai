#!/usr/bin/env python3
"""Confere log de urna x boletim de urna (BU) x totalização do TSE.

Para cada seção de um município (1º turno de 2026), baixa do TSE o BU e o log
da urna e confere:
  1. eleitores que votaram segundo o log ("O voto do eleitor foi computado")
     = comparecimento registrado no BU, para cada cargo;
  2. votos do log para cada cargo ("Voto confirmado para [X]" mais
     "Atribuído voto nulo por suspensão [X]", quando o eleitor não conclui),
     contando só os eleitores cujo voto foi computado, x votos do BU;
  3. soma dos BUs do município, por candidato, = total publicado pelo TSE.

O BU é um arquivo ASN.1 (DER). Este script lê a estrutura sem depender do
esquema oficial: localiza os blocos ResultadoVotacao (tipo de cargo,
comparecimento, totais por cargo) e TotalVotosVotavel (tipo de voto,
quantidade, partido/número) pela forma de cada SEQUENCE.

Os arquivos de urna não são guardados: cada seção é baixada, conferida e descartada.
O resultado de cada seção vai para <dir>/<uf>/<município>.jsonl, então uma
execução interrompida continua de onde parou.

Uso:
  python3 auditar_urnas.py --uf ba --dir ./urnas --saida ./auditoria            # estado inteiro
  python3 auditar_urnas.py --uf ac --municipio 01066 --dir ./urnas --saida ./auditoria
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import threading
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


def baixar_mem(url):
    for _ in range(5):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
    raise RuntimeError(f"falha ao baixar {url}")


def municipios_do_estado(pasta, uf):
    cfg = os.path.join(pasta, f"{uf}-p{PLEITO:06d}-cs.json")
    baixar(f"{BASE}/arquivo-urna/{PLEITO}/config/{uf}/{uf}-p{PLEITO:06d}-cs.json", cfg)
    with open(cfg, encoding="utf-8") as f:
        d = json.load(f)
    # seções com "nsp" são agregadas: os eleitores votam na urna da seção principal
    return [(m["cd"], m["nm"], [(z["cd"], s["ns"], s.get("nsp")) for z in m["zon"] for s in z["sec"]])
            for m in d["abr"][0]["mu"]]


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


def ler_bu(dados):
    """Devolve {id_eleicao: {'aptos': n, 'cargos': {cargo: {'comparecimento': n, 'votos': [..]}}}}."""
    env = der(dados)[0][3]
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
    votação, o log da urna substituída vem dentro, como outro .jez. O pacote pode trazer
    também cópias do mesmo log (memória interna "MI" e externa "ME")."""
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            if nome.endswith(".jez"):
                yield from textos_log(z.read(nome))
            elif nome.startswith("logd"):
                yield z.read(nome).decode("latin-1")


def ler_log(dados, secao=None):
    """secao: número da seção auditada. Linhas de uma urna carregada com outra seção
    (troca de mídia entre urnas) não entram na conta e viram ocorrência."""
    textos = list(textos_log(dados))
    # um log por urna; em ordem cronológica, mantendo a ordem original das linhas de cada um
    textos.sort(key=lambda t: next((l[:19] for l in t.splitlines() if l.startswith("04/10/2026")), "~"))
    computados, confirmados, suspensos, eventos = 0, Counter(), Counter(), Counter()
    por_hora = Counter()
    inicio = fim = None
    # votos de um eleitor só valem quando a urna registra "O voto do eleitor foi computado";
    # se a urna é desligada ou reiniciada no meio, o voto parcial é descartado e o eleitor
    # vota de novo desde o início
    pend_conf, pend_susp = Counter(), Counter()
    secao_da_urna, alheios = {}, Counter()
    vistas, ids_urna = set(), set()

    # voto confirmado até o último cargo e urna caída antes da linha "computado": às vezes a
    # urna chegou a gravar o voto, às vezes não. Fica separado; o BU decide (processar_secao)
    quase = {"n": 0, "confirmados": Counter(), "suspensos": Counter()}

    def descartar():
        if pend_conf.get("Presidente"):
            quase["n"] += 1
            quase["confirmados"].update(pend_conf)
            quase["suspensos"].update(pend_susp)
        elif pend_conf or pend_susp:
            eventos["Voto interrompido (urna desligada/reiniciada) e refeito pelo eleitor"] += 1
        pend_conf.clear()
        pend_susp.clear()

    for t in textos:
        for linha in t.splitlines():
            p = linha.split("\t")
            if len(p) < 5 or not linha.startswith("04/10/2026"):
                continue
            # cada linha termina com um código próprio; cópias MI/ME do mesmo log se repetem
            if linha in vistas:
                continue
            vistas.add(linha)
            data, nivel, id_urna, app, msg = p[:5]
            if app == "VOTA":
                ids_urna.add(id_urna)
            if msg.startswith("Seção Eleitoral: "):
                secao_da_urna[id_urna] = msg.split(": ", 1)[1].strip()
            if app != "VOTA":
                continue
            outra = secao_da_urna.get(id_urna)
            if secao and outra not in (None, secao, "0000"):
                if msg == "O voto do eleitor foi computado":
                    alheios[outra] += 1
                continue
            if msg == "Eleitor foi habilitado" or msg in ("Votação suspensa", "Iniciando aplicação - 1º turno"):
                descartar()
            elif msg == "O voto do eleitor foi computado":
                computados += 1
                por_hora[data[11:13]] += 1
                inicio = inicio or data
                fim = data
                confirmados.update(pend_conf)
                suspensos.update(pend_susp)
                pend_conf.clear()
                pend_susp.clear()
            m = RE_CARGO.match(msg)
            if m:
                pend_conf[m.group(1)] += 1
            m = RE_SUSP.match(msg)
            if m:
                pend_susp[m.group(1)] += 1
            if nivel in ("ERRO", "ALERTA"):
                eventos[f"{nivel}: {re.sub(r'[0-9]+', 'N', msg)}"] += 1
            elif msg == "Eleitor foi suspenso pelo mesário":
                eventos["Eleitor suspenso pelo mesário (não concluiu o voto)"] += 1
    descartar()
    for outra, n in alheios.items():
        eventos[f"Log publicado traz trecho da urna da seção {outra} ({n} votos dela, ignorados)"] += 1
    if len(ids_urna) > 1:
        eventos[f"Urna substituída durante a votação ({len(ids_urna)} urnas no log)"] += 1
    return {"computados": computados, "confirmados": dict(confirmados), "suspensos": dict(suspensos),
            "urnas": max(len(ids_urna), 1), "por_hora": dict(por_hora), "quase": quase,
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


# ---------------------------------------------------------------- seção
def processar_secao(uf, mun, zona, secao):
    base = f"{BASE}/arquivo-urna/{PLEITO}/dados/{uf}/{mun}/{zona}/{secao}"
    lin = {"zona": zona, "secao": secao}
    aux = baixar_mem(f"{base}/p{PLEITO:06d}-{uf}-m{mun}-z{zona}-s{secao}-aux.json")
    if aux is None:
        return {**lin, "situacao": "sem arquivos no TSE"}
    info = json.loads(aux)
    hashes = [h for h in info.get("hashes", []) if h.get("st") in ("Totalizado", "Recebido")] \
        or info.get("hashes", [])
    lin["situacao"] = info.get("st", "")
    if not hashes:
        return lin
    h = hashes[-1]
    arq = {a["tp"]: a["nm"] for a in h["arq"]}
    if "bu" not in arq and "busa" in arq:
        return apurada_pelo_sa(lin, base, h, arq)
    if "bu" not in arq or "log" not in arq:
        return {**lin, "situacao": f"{lin['situacao']} (sem BU/log)"}
    bu = ler_bu(baixar_mem(f"{base}/{h['hash']}/{arq['bu']}"))
    log = ler_log(baixar_mem(f"{base}/{h['hash']}/{arq['log']}"), secao)
    cargos, aptos = {}, None
    for ent in bu.values():
        aptos = aptos or ent["aptos"]
        cargos.update(ent["cargos"])
    comp = cargos.get("Presidente", next(iter(cargos.values()), {})).get("comparecimento")
    q = log["quase"]
    if q["n"]:
        # testa as duas hipóteses: votos da urna travada gravados ou não
        def fecha(incluir):
            k = 1 if incluir else 0
            if comp != log["computados"] + k * q["n"]:
                return False
            return all(sum(v["qtd"] for v in d["votos"]) ==
                       log["confirmados"].get(c, 0) + log["suspensos"].get(c, 0)
                       + k * (q["confirmados"].get(c, 0) + q["suspensos"].get(c, 0))
                       for c, d in cargos.items())
        gravado = fecha(True)
        if gravado or not fecha(False):
            log["computados"] += q["n"]
            log["confirmados"] = dict(Counter(log["confirmados"]) + q["confirmados"])
            log["suspensos"] = dict(Counter(log["suspensos"]) + q["suspensos"])
        rot = "voto gravado no BU" if gravado else "voto não gravado" if fecha(False) else "indeterminado"
        log["eventos"][f"Urna travou logo após o eleitor confirmar o último cargo ({rot})"] = q["n"]
    lin.update({"aptos_bu": aptos, "comparecimento_bu": comp, "votos_computados_log": log["computados"],
                "log_bate_bu": "OK" if comp == log["computados"] else "DIFERENTE",
                "primeiro_voto": log["primeiro_voto"], "ultimo_voto": log["ultimo_voto"],
                "urnas_no_log": log["urnas"], "votos_por_hora": json.dumps(log["por_hora"], sort_keys=True),
                "eventos_log": "; ".join(f"{k} ({v})" for k, v in log["eventos"].items())})
    soma = {}
    for cargo, dados in cargos.items():
        total = sum(v["qtd"] for v in dados["votos"])
        no_log = log["confirmados"].get(cargo, 0) + log["suspensos"].get(cargo, 0)
        lin[f"votos_bu_{cargo}"] = total
        lin[f"votos_log_{cargo}"] = no_log
        lin[f"bate_{cargo}"] = "OK" if no_log == total else "DIFERENTE"
        if total != no_log:
            lin["log_bate_bu"] = "DIFERENTE"
        c = Counter()
        for v in dados["votos"]:
            c[str(v["numero"]) if v["tipo"] == "Nominal" else v["tipo"]] += v["qtd"]
        soma[cargo] = dict(c)
    lin["soma"] = soma
    return lin


RE_MOTIVO = re.compile(r"Motivo da apura[cç][aã]o: (.+)")
RE_TIPO_SA = re.compile(r"Tipo de apura[cç][aã]o selecionada \((.+)\)")


def apurada_pelo_sa(lin, base, h, arq):
    """Seção apurada pelo Sistema de Apuração (votação em cédula, urna encerrada antes da hora,
    recuperação de votos): não há log de votação para conferir; o BU do SA (busa) entra na soma."""
    bu = ler_bu(baixar_mem(f"{base}/{h['hash']}/{arq['busa']}"))
    motivo = tipo = ""
    if "logsa" in arq:
        for texto in textos_log(baixar_mem(f"{base}/{h['hash']}/{arq['logsa']}")):
            for linha in texto.splitlines():
                p = linha.split("\t")
                if len(p) < 5:
                    continue
                m = RE_MOTIVO.match(p[4])
                motivo = m.group(1).strip() if m else motivo
                m = RE_TIPO_SA.match(p[4])
                tipo = m.group(1).strip() if m else tipo
    cargos, aptos = {}, None
    for ent in bu.values():
        aptos = aptos or ent["aptos"]
        cargos.update(ent["cargos"])
    comp = cargos.get("Presidente", next(iter(cargos.values()), {})).get("comparecimento")
    soma = {}
    for cargo, dados in cargos.items():
        c = Counter()
        for v in dados["votos"]:
            c[str(v["numero"]) if v["tipo"] == "Nominal" else v["tipo"]] += v["qtd"]
        soma[cargo] = dict(c)
    lin.update({"situacao": "Apurada pelo Sistema de Apuração (SA)", "log_bate_bu": "SA",
                "aptos_bu": aptos, "comparecimento_bu": comp,
                "eventos_log": f"Apurada pelo SA: {motivo or 'motivo não informado'} ({tipo or 'tipo não informado'}) (1)",
                "soma": soma})
    return lin


def resumir_municipio(a, uf, mun, nome_mun, linhas):
    soma = defaultdict(Counter)
    for l in linhas:
        for cargo, c in (l.get("soma") or {}).items():
            for k, q in c.items():
                soma[cargo][int(k) if k.isdigit() else k] += q
    linhas = [{k: v for k, v in l.items() if k != "soma"} for l in linhas]
    linhas.sort(key=lambda l: (l["zona"], l["secao"]))

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
    with open(os.path.join(a.saida, f"resumo_{uf}{mun}.json"), "w", encoding="utf-8") as f:
        json.dump({"uf": uf.upper(), "municipio": nome_mun, "codigo": mun, "secoes": linhas,
                   "comparacao": comparacao}, f, ensure_ascii=False)
    proprias = [l for l in linhas if l.get("log_bate_bu") not in ("agregada", "SA")]
    return (sum(l.get("log_bate_bu") == "OK" for l in proprias), len(proprias),
            sum(c["bate"] == "OK" for c in comparacao), len(comparacao))


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uf", required=True)
    p.add_argument("--municipio", default="todos", help="código TSE do município (5 dígitos) ou 'todos'")
    p.add_argument("--dir", required=True, help="pasta do resultado por seção e dos totais do TSE")
    p.add_argument("--saida", required=True)
    p.add_argument("--threads", type=int, default=24)
    a = p.parse_args()
    uf = a.uf.lower()
    os.makedirs(a.saida, exist_ok=True)
    os.makedirs(os.path.join(a.dir, uf), exist_ok=True)

    muns = [m for m in municipios_do_estado(a.dir, uf) if a.municipio in ("todos", m[0])]
    if not muns:
        raise SystemExit(f"Município {a.municipio} não encontrado em {uf.upper()}")
    feitos, pend = {}, []
    for mun, _nome, secoes in muns:
        arq = os.path.join(a.dir, uf, f"{mun}.jsonl")
        feitos[mun] = {}
        if os.path.exists(arq):
            with open(arq, encoding="utf-8") as f:
                for linha in f:
                    try:
                        l = json.loads(linha)
                    except ValueError:
                        continue
                    feitos[mun][(l["zona"], l["secao"])] = l
        for zona, secao, principal in secoes:
            if principal:
                feitos[mun][(zona, secao)] = {"zona": zona, "secao": secao, "log_bate_bu": "agregada",
                                              "situacao": f"agregada à seção {principal}"}
            elif (zona, secao) not in feitos[mun]:
                pend.append((mun, zona, secao))
    total = sum(len(s) for _m, _n, s in muns)
    print(f"{uf.upper()}: {len(muns)} municípios, {total} seções, {len(pend)} a processar", flush=True)

    trava = threading.Lock()
    feitas = [0]

    def tarefa(t):
        mun, zona, secao = t
        try:
            lin = processar_secao(uf, mun, zona, secao)
        except Exception as e:  # erro de rede persistente: fica para a próxima execução
            print(f"  erro {mun}/{zona}/{secao}: {e}", file=sys.stderr, flush=True)
            return
        with trava:
            with open(os.path.join(a.dir, uf, f"{mun}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(lin, ensure_ascii=False) + "\n")
            feitos[mun][(zona, secao)] = lin
            feitas[0] += 1
            if feitas[0] % 1000 == 0:
                print(f"  {feitas[0]} de {len(pend)} seções", flush=True)

    with ThreadPoolExecutor(a.threads) as ex:
        list(ex.map(tarefa, pend))

    tot = [0, 0, 0, 0]
    faltando = 0
    for mun, nome, secoes in muns:
        faltando += len(secoes) - len(feitos[mun])
        r = resumir_municipio(a, uf, mun, nome, list(feitos[mun].values()))
        tot = [x + y for x, y in zip(tot, r)]
    print(f"{uf.upper()}: log = BU em {tot[0]} de {tot[1]} urnas; soma dos BUs = TSE em {tot[2]} de {tot[3]} "
          f"totais; seções ainda sem resultado: {faltando}", flush=True)


if __name__ == "__main__":
    main()
