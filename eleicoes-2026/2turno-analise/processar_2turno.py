#!/usr/bin/env python3
"""
Processa os Boletins de Urna (BU Web) do 2o turno de 2026 e gera os dados do site.

Entrada  : ./zips/bweb_2t_<UF>_*.zip            (baixados por baixar.sh)
Saida    : ./site/data/estados.json, municipios.json, sec_<UF>.json

Para cada secao agrega os votos de Presidente (so o cargo Presidente; estados
com 2o turno de governador tem esse cargo no mesmo arquivo e sao ignorados),
classificando por NUMERO do votavel: 13=Lula, 22=Flavio, 95=Branco, 96=Nulo.
Os cortes de horario de encerramento/recebimento sao normalizados para o
horario de Brasilia (AC +2h; AM/MT/MS/RO/RR +1h).

Uso: python3 -I processar_2turno.py [dir_zips] [dir_saida]
"""
import csv, collections, datetime, json, os, zipfile, io, sys

ZIPDIR = sys.argv[1] if len(sys.argv) > 1 else 'zips'
OUT    = sys.argv[2] if len(sys.argv) > 2 else 'site/data'
os.makedirs(OUT, exist_ok=True)

E17 = datetime.datetime(2026, 10, 25, 17, 0, 0)
# horas a somar ao horario LOCAL da urna para chegar ao horario de Brasilia
OFF = {'AC': 2, 'AM': 1, 'MT': 1, 'MS': 1, 'RO': 1, 'RR': 1}
BUCKETS = ['<17h', '17:00-17:10', '17:10-17:30', '17:30-18:00',
           '18:00-19:00', '19:00-20:00', '>20:00']

def bk(dt):
    if dt is None: return None
    if dt < E17: return 0
    d = (dt - E17).total_seconds()
    if d <= 600: return 1
    if d <= 1800: return 2
    if d <= 3600: return 3
    if d <= 7200: return 4
    if d <= 10800: return 5
    return 6

def ptime(s):
    s = s.strip().strip('"')
    try: return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except Exception: return None

def hhmm(s):
    dt = ptime(s)
    return dt.strftime('%H:%M:%S') if dt else ''

estados = []; municipios = []; NAT = collections.Counter(); mun_names = {}
files = sorted(f for f in os.listdir(ZIPDIR) if f.endswith('.zip'))
for zf in files:
    uf = zf.split('_')[2]
    secs = {}; munc = collections.defaultdict(collections.Counter)
    tzoff = datetime.timedelta(hours=OFF.get(uf, 0))
    with zipfile.ZipFile(os.path.join(ZIPDIR, zf)) as z:
        csvname = [n for n in z.namelist() if n.lower().endswith('.csv')][0]
        with z.open(csvname) as raw:
            r = csv.reader(io.TextIOWrapper(raw, encoding='latin-1', newline=''), delimiter=';')
            h = next(r); idx = {n: i for i, n in enumerate(h)}
            iCg = idx['DS_CARGO_PERGUNTA']; iNR = idx['NR_VOTAVEL']; iQ = idx['QT_VOTOS']
            iM = idx['CD_MUNICIPIO']; iNM = idx['NM_MUNICIPIO']; iZ = idx['NR_ZONA']; iS = idx['NR_SECAO']
            iL = idx['NR_LOCAL_VOTACAO']; iU = idx['NR_URNA_EFETIVADA']
            iAp = idx['QT_APTOS']; iCp = idx['QT_COMPARECIMENTO']
            iAb = idx['DT_ABERTURA']; iEnc = idx['DT_ENCERRAMENTO']
            iEm = idx['DT_EMISSAO_BU']; iRec = idx['DT_BU_RECEBIDO']
            for row in r:
                if row[iCg] != 'Presidente': continue
                key = (row[iM], row[iZ], row[iS])
                d = secs.get(key)
                if d is None:
                    d = secs[key] = {'m': row[iM], 'z': row[iZ], 's': row[iS], 'loc': row[iL],
                        'urna': row[iU], 'apt': row[iAp], 'cmp': row[iCp],
                        'ab': row[iAb].strip('"'), 'en': row[iEnc].strip('"'),
                        'em': row[iEm].strip('"'), 're': row[iRec].strip('"'),
                        'L': 0, 'F': 0, 'N': 0, 'B': 0}
                    mun_names[(uf, row[iM])] = row[iNM]
                q = int(row[iQ]); nr = row[iNR]
                if nr == '13': d['L'] += q; munc[row[iM]]['L'] += q
                elif nr == '22': d['F'] += q; munc[row[iM]]['F'] += q
                elif nr == '95': d['B'] += q; munc[row[iM]]['B'] += q
                elif nr == '96': d['N'] += q; munc[row[iM]]['N'] += q
    sl = sf = sn = sb = 0
    enc_b = [0]*7; rec_b = [0]*7; encL = [0]*7; encF = [0]*7
    enc_vals = []; rec_vals = []; rows_out = []
    for key, d in secs.items():
        sl += d['L']; sf += d['F']; sn += d['N']; sb += d['B']
        edt = ptime(d['en']); rdt = ptime(d['re'])
        edt_b = (edt + tzoff) if edt else None
        rdt_b = (rdt + tzoff) if rdt else None
        be = bk(edt_b); br = bk(rdt_b)
        if be is not None: enc_b[be] += 1; encL[be] += d['L']; encF[be] += d['F']
        if br is not None: rec_b[br] += 1
        if edt_b: enc_vals.append(edt_b)
        if rdt_b: rec_vals.append(rdt_b)
        rows_out.append([d['m'], int(d['z']), int(d['s']), d['loc'], d['urna'],
            int(d['apt']), int(d['cmp']), hhmm(d['ab']), hhmm(d['en']),
            hhmm(d['em']), hhmm(d['re']), d['L'], d['F'], d['N'], d['B']])
    NAT['L'] += sl; NAT['F'] += sf; NAT['N'] += sn; NAT['B'] += sb
    val = sl + sf
    estados.append({'uf': uf, 'lula': sl, 'flavio': sf, 'nulo': sn, 'branco': sb,
        'validos': val, 'pct_lula': round(100*sl/val, 2) if val else 0, 'n_secoes': len(secs),
        'enc_min': min(enc_vals).strftime('%H:%M:%S') if enc_vals else '',
        'enc_max': max(enc_vals).strftime('%H:%M:%S') if enc_vals else '',
        'rec_min': min(rec_vals).strftime('%H:%M:%S') if rec_vals else '',
        'rec_max': max(rec_vals).strftime('%H:%M:%S') if rec_vals else '',
        'tz_off': OFF.get(uf, 0), 'enc_b': enc_b, 'rec_b': rec_b, 'encL': encL, 'encF': encF})
    for m, c in munc.items():
        v = c['L'] + c['F']
        municipios.append({'uf': uf, 'cod': m, 'nome': mun_names[(uf, m)],
            'lula': c['L'], 'flavio': c['F'], 'nulo': c['N'], 'branco': c['B'],
            'validos': v, 'pct_lula': round(100*c['L']/v, 2) if v else 0})
    json.dump({'cols': ['cod_mun','zona','secao','local','urna','aptos','comp','abertura',
        'encerr','emissao','recebido','lula','flavio','nulo','branco'], 'rows': rows_out},
        open(os.path.join(OUT, f'sec_{uf}.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f"{uf}: secoes={len(secs):>6} lula={sl:>10,} flavio={sf:>10,}", flush=True)

json.dump({'buckets': BUCKETS, 'estados': estados},
          open(os.path.join(OUT, 'estados.json'), 'w'), ensure_ascii=False)
json.dump(municipios, open(os.path.join(OUT, 'municipios.json'), 'w'),
          ensure_ascii=False, separators=(',', ':'))
TL, TF = NAT['L'], NAT['F']
print(f"\nNACIONAL  Lula {TL:,} ({100*TL/(TL+TF):.2f}%) | Flavio {TF:,} ({100*TF/(TL+TF):.2f}%)")
print("Oficial   Lula 64.256.232 (51,79%) | Flavio 59.826.041 (48,21%)")
print(f"Municipios (incl. exterior): {len(municipios)}")
