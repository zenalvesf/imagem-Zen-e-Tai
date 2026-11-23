#!/usr/bin/env python3
"""
Comparativo 1o x 2o turno (Presidente, 2026).

Entrada:
  ./zips/votacao_secao_2026_BR.csv   (dentro de votacao_secao_2026_BR.zip)
  ./site/data/estados.json, municipios.json   (gerados por processar_2turno.py)

Saida:
  ./site/data/comp1t.json   (1o turno por municipio/estado/nacional)
  ./site/data/swings.json   (virada em pp por municipio)
  imprime a contabilidade nacional e a regressao ecologica de migracao.

Uso: python3 -I comparativo_1turno.py [dir_zips] [dir_site_data]
"""
import csv, collections, json, os, sys, statistics as st

ZIPDIR = sys.argv[1] if len(sys.argv) > 1 else 'zips'
D      = sys.argv[2] if len(sys.argv) > 2 else 'site/data'
CSV1T  = os.path.join(ZIPDIR, 'votacao_secao_2026_BR.csv')

# --- 1o turno: agrega por municipio (13=Lula, 22=Flavio, 95=Branco, 96=Nulo, resto=Outros) ---
mun = collections.defaultdict(collections.Counter)
est = collections.defaultdict(collections.Counter)
nat = collections.Counter()
with open(CSV1T, encoding='latin-1', newline='') as fh:
    r = csv.reader(fh, delimiter=';'); h = next(r); idx = {n: i for i, n in enumerate(h)}
    iT = idx['NR_TURNO']; iUF = idx['SG_UF']; iM = idx['CD_MUNICIPIO']
    iNR = idx['NR_VOTAVEL']; iQ = idx['QT_VOTOS']
    for row in r:
        if row[iT] != '1': continue
        q = int(row[iQ]); nr = row[iNR]; uf = row[iUF]; key = (uf, row[iM])
        t = 'L1' if nr == '13' else 'F1' if nr == '22' else 'B1' if nr == '95' else 'N1' if nr == '96' else 'O1'
        mun[key][t] += q; est[uf][t] += q; nat[t] += q

json.dump({'nacional': dict(nat),
           'estados': {uf: dict(c) for uf, c in est.items()},
           'mun': {f"{uf}|{cod}": {'L1': c['L1'], 'F1': c['F1'], 'O1': c['O1'],
                                   'B1': c['B1'], 'N1': c['N1']} for (uf, cod), c in mun.items()}},
          open(os.path.join(D, 'comp1t.json'), 'w'), separators=(',', ':'))

# --- 2o turno (do que processar_2turno.py ja gerou) ---
m2 = {f"{m['uf']}|{m['cod']}": m for m in json.load(open(os.path.join(D, 'municipios.json')))}
est2 = json.load(open(os.path.join(D, 'estados.json')))['estados']
L1, F1, O1, B1, N1 = nat['L1'], nat['F1'], nat['O1'], nat['B1'], nat['N1']
V1 = L1 + F1 + O1; C1 = V1 + B1 + N1
L2 = sum(s['lula'] for s in est2); F2 = sum(s['flavio'] for s in est2)
B2 = sum(s['branco'] for s in est2); N2 = sum(s['nulo'] for s in est2)
V2 = L2 + F2; C2 = V2 + B2 + N2; dL = L2 - L1; dF = F2 - F1

print("===== CONTABILIDADE NACIONAL 1T -> 2T =====")
for lab, a, b in [('Lula', L1, L2), ('Flavio', F1, F2), ('Outros', O1, 0),
                  ('Brancos', B1, B2), ('Nulos', N1, N2), ('Validos', V1, V2), ('Comparec.', C1, C2)]:
    print(f"{lab:10}{a:>14,}{b:>14,}{b-a:>+14,}")
print(f"\nGanho combinado Lula+Flavio: {dL+dF:+,} = Outros {O1:,} + novos validos {V2-V1:+,}")
print(f"Checagem: {O1+(V2-V1):,} == {dL+dF:,} -> {'FECHA' if O1+(V2-V1)==dL+dF else 'ERRO'}")
print(f"Do ganho, Lula {100*dL/(dL+dF):.1f}% | Flavio {100*dF/(dL+dF):.1f}%")

# --- regressao ecologica sem intercepto: dL_i = a*O1_i + b*NV_i ---
sw = []
Soo = Son = Snn = Sol = Snl = 0.0
for k, c in mun.items():
    kk = f"{k[0]}|{k[1]}"; mm = m2.get(kk)
    if not mm: continue
    l1 = c['L1']; f1 = c['F1']; o1 = c['O1']; l2 = mm['lula']; f2 = mm['flavio']
    v1 = l1 + f1 + o1; v2 = l2 + f2; nv = v2 - v1; dl = l2 - l1
    Soo += o1*o1; Son += o1*nv; Snn += nv*nv; Sol += o1*dl; Snl += nv*dl
    sw.append({'uf': k[0], 'cod': k[1], 'nome': mm['nome'],
               'p1': round(100*l1/v1, 1) if v1 else 0, 'p2': round(100*l2/v2, 1) if v2 else 0,
               'd': round((100*l2/v2 if v2 else 0) - (100*l1/v1 if v1 else 0), 1),
               'l1': l1, 'f1': f1, 'o1': o1, 'l2': l2, 'f2': f2})
det = Soo*Snn - Son*Son
a = (Snn*Sol - Son*Snl)/det; b = (Soo*Snl - Son*Sol)/det
json.dump(sw, open(os.path.join(D, 'swings.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"\n===== MIGRACAO (regressao ecologica, {len(sw)} municipios) =====")
print(f"Votos dos ELIMINADOS p/ Lula (a): {a:.3f} | Flavio ~{1-a:.3f}")
print(f"Votos NOVOS (abstencao/branco-nulo) p/ Lula (b): {b:.3f} | Flavio ~{1-b:.3f}")
print("[inferencia ecologica: estima de totais por municipio, nao do voto individual]")

loser = [s for s in sw if s['f2'] < s['f1']]
print(f"\nMunicipios onde Flavio recuou em votos: {len(loser)} de {len(sw)} ({100*len(loser)/len(sw):.1f}%)")
print(f"  %Lula 1T medio: recuo={st.mean(s['p1'] for s in loser):.0f}% vs demais={st.mean(s['p1'] for s in sw if s['f2']>=s['f1']):.0f}%")
