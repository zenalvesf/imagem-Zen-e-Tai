#!/usr/bin/env python3
"""Gera resultados-2026.xlsx: abas por cargo (estado e município) e comparação
Presidente x Governador por estado.

Sem argumentos, cria a planilha com a estrutura, os percentuais já divulgados
e as fórmulas, mas com as colunas de votos vazias.

Com --dir, preenche os votos a partir dos arquivos de dados abertos do TSE
(1º turno), descompactados na pasta:
  votacao_candidato_munzona_2026_BRASIL.csv   (votos por candidato e município)
  detalhe_votacao_munzona_2026_BRASIL.csv     (comparecimento, brancos e nulos)
Os zips ficam em https://cdn.tse.jus.br/estatistica/sead/odsele/
(votacao_candidato_munzona/ e detalhe_votacao_munzona/).

Uso:
  python3 planilha_resultados.py
  python3 planilha_resultados.py --dir ./tse
"""
import argparse
import csv
import glob
import os
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "resultados-2026.xlsx")

UFS = [
    ("AC", "Acre", "Norte"), ("AL", "Alagoas", "Nordeste"), ("AP", "Amapá", "Norte"),
    ("AM", "Amazonas", "Norte"), ("BA", "Bahia", "Nordeste"), ("CE", "Ceará", "Nordeste"),
    ("DF", "Distrito Federal", "Centro-Oeste"), ("ES", "Espírito Santo", "Sudeste"),
    ("GO", "Goiás", "Centro-Oeste"), ("MA", "Maranhão", "Nordeste"),
    ("MT", "Mato Grosso", "Centro-Oeste"), ("MS", "Mato Grosso do Sul", "Centro-Oeste"),
    ("MG", "Minas Gerais", "Sudeste"), ("PA", "Pará", "Norte"), ("PB", "Paraíba", "Nordeste"),
    ("PR", "Paraná", "Sul"), ("PE", "Pernambuco", "Nordeste"), ("PI", "Piauí", "Nordeste"),
    ("RJ", "Rio de Janeiro", "Sudeste"), ("RN", "Rio Grande do Norte", "Nordeste"),
    ("RS", "Rio Grande do Sul", "Sul"), ("RO", "Rondônia", "Norte"), ("RR", "Roraima", "Norte"),
    ("SC", "Santa Catarina", "Sul"), ("SP", "São Paulo", "Sudeste"), ("SE", "Sergipe", "Nordeste"),
    ("TO", "Tocantins", "Norte"),
]

# Percentuais de votos válidos divulgados pela imprensa (apuração do TSE, 100%).
# (vencedor, % Flávio, % Lula); None = não divulgado.
PRES_PCT = {
    "AC": (64.56, None), "DF": (51.31, None), "ES": (54.78, None), "MT": (65.15, None),
    "MS": (58.60, None), "PR": (59.91, None), "RJ": (53.01, None), "RS": (55.64, None),
    "RO": (67.45, None), "RR": (71.06, None), "SC": (66.65, None), "SP": (51.93, None),
    "GO": (53.61, 31.06), "TO": (50.44, 43.42), "MG": (48.24, 43.33),
    "AL": (None, 54.73), "BA": (None, 66.17), "CE": (31.27, 63.29), "MA": (30.90, 63.96),
    "PB": (33.07, 61.31), "PE": (None, 63.45), "PI": (None, 70.99), "RN": (34.77, 59.75),
    "SE": (None, 62.75), "AP": (45.67, 45.71), "AM": (45.00, 48.16), "PA": (44.50, 49.91),
}
# (situação, [(candidato, partido, %), ...])
GOV = {
    "SP": ("Eleito", [("Tarcísio de Freitas", "Republicanos", 62.65)]),
    "MG": ("Eleito", [("Cleitinho Azevedo", "Republicanos", 55.40)]),
    "RS": ("Eleito", [("Luciano Zucco", "PL", 58.05)]),
    "SC": ("Eleito", [("Jorginho Mello", "PL", 68.98)]),
    "PR": ("Eleito", [("Sergio Moro", "PL", 50.10)]),
    "MS": ("Eleito", [("Eduardo Riedel", "PP", 67.07)]),
    "GO": ("Eleito", [("Daniel Vilela", "MDB", 59.17)]),
    "MT": ("Eleito", [("Otaviano Pivetta", "Republicanos", 60.77)]),
    "CE": ("Eleito", [("Elmano de Freitas", "PT", 53.19)]),
    "PI": ("Eleito", [("Rafael Fonteles", "PT", 70.90)]),
    "BA": ("Eleito", [("Jerônimo Rodrigues", "PT", 55.80)]),
    "MA": ("Eleito", [("Eduardo Braide", "PSD", 54.02)]),
    "SE": ("Eleito", [("Fábio Mitidieri", "PSD", 59.27)]),
    "PE": ("Eleito", [("Raquel Lyra", "PSD", 53.27)]),
    "PB": ("Eleito", [("Lucas Ribeiro", "PP", 64.30)]),
    "RO": ("Eleito", [("Marcos Rogério", "PL", 56.86)]),
    "RR": ("Eleito", [("Arthur Henrique", "PL", 69.13)]),
    "PA": ("Eleito", [("Dr. Daniel", "Podemos", 51.75)]),
    "AL": ("Eleito", [("JHC", "PSDB", 52.19)]),
    "AP": ("Eleito", [("Dr. Furlan", "PSD", 62.75)]),
    "AC": ("2º turno", [("Mailza Assis", "PP", None), ("Alan Rick", "Republicanos", None)]),
    "AM": ("2º turno", [("Omar Aziz", "PSD", 40.38), ("Professora Maria do Carmo", "PL", 24.72)]),
    "DF": ("2º turno", [("Celina Leão", "PP", 49.93), ("Leandro Grass", "PT", 34.48)]),
    "ES": ("2º turno", [("Lorenzo Pazolini", "Republicanos", 49.65), ("Ricardo Ferraço", "MDB", 34.06)]),
    "RJ": ("2º turno", [("Douglas Ruas", "PL", 49.27), ("Eduardo Paes", "PSD", 42.76)]),
    "RN": ("2º turno", [("Allyson", "União", 36.83), ("Cadu de Lula", "PT", 36.21)]),
    "TO": ("2º turno", [("Professora Dorinha", "União", 45.52), ("Vicentinho Júnior", "PSDB", None)]),
}
FONTE = ("Fonte: apuração do TSE (100%) divulgada por Metrópoles, Gazeta do Povo, TV Senado, "
         "Exame e Agência Brasil, 05/10/2026. Pode diferir em centésimos do TSE.")

FONT = "Arial"
F_BASE = Font(name=FONT, size=10)
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_INPUT = Font(name=FONT, size=10, color="0000FF")
F_LINK = Font(name=FONT, size=10, color="008000")
F_TITLE = Font(name=FONT, size=14, bold=True)
F_NOTE = Font(name=FONT, size=9, italic=True, color="555555")
FILL_HEAD = PatternFill("solid", fgColor="1F3A5F")
FILL_INPUT = PatternFill("solid", fgColor="FFFF00")
FILL_EX = PatternFill("solid", fgColor="EEEEEE")
LINHA = Border(bottom=Side(style="thin", color="CCCCCC"))
NUM = '#,##0;-#,##0;"-"'
PCT = '0.00%;-0.00%;"-"'


def cabecalho(ws, linha, titulos, larguras):
    for i, (t, w) in enumerate(zip(titulos, larguras), start=1):
        c = ws.cell(row=linha, column=i, value=t)
        c.font, c.fill = F_HEAD, FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[linha].height = 32
    ws.freeze_panes = ws.cell(row=linha + 1, column=3)


def entrada(c, valor=None, fmt=NUM):
    c.value = valor
    c.font, c.fill, c.number_format = F_INPUT, FILL_INPUT, fmt


def ler_tse(pasta):
    """Lê os CSVs do TSE e devolve totais por UF/município para presidente e governador."""
    def abrir(padrao):
        arqs = sorted(glob.glob(os.path.join(pasta, padrao)))
        for arq in arqs:
            with open(arq, encoding="latin-1", newline="") as f:
                yield from csv.DictReader(f, delimiter=";")

    def col(linha, *nomes):
        for n in nomes:
            if n in linha and linha[n] not in ("", None):
                return linha[n]
        return "0"

    cand = {"PRESIDENTE": defaultdict(int), "GOVERNADOR": defaultdict(int)}
    nomes_mun = {}
    for l in abrir("votacao_candidato_munzona_2026*.csv"):
        cargo = l.get("DS_CARGO", "").upper()
        if cargo not in cand or l.get("NR_TURNO", "1") != "1" or l.get("SG_UF") in ("ZZ", "BR", "VT"):
            continue
        chave = (l["SG_UF"], l["CD_MUNICIPIO"], l.get("NM_URNA_CANDIDATO", ""), l.get("SG_PARTIDO", ""))
        nomes_mun[(l["SG_UF"], l["CD_MUNICIPIO"])] = l["NM_MUNICIPIO"]
        cand[cargo][chave] += int(col(l, "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS", "QT_VOTOS"))

    det = {"PRESIDENTE": defaultdict(lambda: [0, 0, 0]), "GOVERNADOR": defaultdict(lambda: [0, 0, 0])}
    for l in abrir("detalhe_votacao_munzona_2026*.csv"):
        cargo = l.get("DS_CARGO", "").upper()
        if cargo not in det or l.get("NR_TURNO", "1") != "1" or l.get("SG_UF") in ("ZZ", "BR", "VT"):
            continue
        d = det[cargo][l["SG_UF"]]
        d[0] += int(col(l, "QT_COMPARECIMENTO"))
        d[1] += int(col(l, "QT_VOTOS_BRANCOS"))
        d[2] += int(col(l, "QT_TOTAL_VOTOS_NULOS", "QT_VOTOS_NULOS"))
    return cand, det, nomes_mun


def aba_leiame(wb):
    ws = wb.active
    ws.title = "Leia-me"
    ws.column_dimensions["A"].width = 110
    linhas = [
        ("Eleições Gerais 2026 · 1º turno (04/10/2026)", F_TITLE),
        ("", F_BASE),
        ("Abas", Font(name=FONT, size=11, bold=True)),
        ("Presidente / Governador: totais por estado (votos por candidato, brancos, nulos, comparecimento).", F_BASE),
        ("Presidente - Municípios / Governador - Municípios: votos por candidato em cada município.", F_BASE),
        ("Comparação: confere, estado a estado, se os números de Governador e Presidente batem.", F_BASE),
        ("", F_BASE),
        ("Legenda", Font(name=FONT, size=11, bold=True)),
        ("Células amarelas com texto azul: dados a preencher (ou já preenchidos pelo script).", F_BASE),
        ("Texto azul sem fundo: percentuais divulgados (fonte no comentário da célula).", F_BASE),
        ("Texto preto: fórmulas. Não edite.", F_BASE),
        ("", F_BASE),
        ("Como preencher", Font(name=FONT, size=11, bold=True)),
        ("1. Baixe do TSE os zips votacao_candidato_munzona_2026 e detalhe_votacao_munzona_2026 em "
         "https://cdn.tse.jus.br/estatistica/sead/odsele/ e descompacte numa pasta.", F_BASE),
        ("2. Rode: python3 eleicoes-2026/planilha_resultados.py --dir <pasta>", F_BASE),
        ("", F_BASE),
        ("Por que Presidente e Governador podem não bater", Font(name=FONT, size=11, bold=True)),
        ("O comparecimento deve ser igual nos dois cargos (o eleitor vota nos dois na mesma urna). "
         "Votos válidos, brancos e nulos variam: quem vota em presidente pode anular para governador. "
         "No DF a comparação é igual à dos estados; votos do exterior só existem para presidente e ficam fora.", F_BASE),
        ("", F_BASE),
        (FONTE, F_NOTE),
    ]
    for i, (t, f) in enumerate(linhas, start=1):
        c = ws.cell(row=i, column=1, value=t)
        c.font = f
        c.alignment = Alignment(wrap_text=True, vertical="top")


def aba_presidente(wb, cand, det):
    ws = wb.create_sheet("Presidente")
    tit = ["UF", "Estado", "Região", "Votos Flávio Bolsonaro (PL)", "Votos Lula (PT)",
           "Votos demais candidatos", "Votos válidos", "Brancos", "Nulos", "Comparecimento",
           "% Flávio (calculado)", "% Lula (calculado)", "% Flávio (divulgado)", "% Lula (divulgado)",
           "Vencedor"]
    cabecalho(ws, 1, tit, [6, 20, 13, 16, 16, 16, 16, 13, 13, 16, 13, 13, 13, 13, 18])
    tot = defaultdict(lambda: [0, 0, 0])
    for (uf, _m, nome, _p), v in cand.get("PRESIDENTE", {}).items():
        i = 0 if "FLÁVIO" in nome.upper() or "FLAVIO" in nome.upper() else 1 if "LULA" in nome.upper() else 2
        tot[uf][i] += v
    for r, (uf, nome, reg) in enumerate(UFS, start=2):
        ws.cell(row=r, column=1, value=uf).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r, column=2, value=nome).font = F_BASE
        ws.cell(row=r, column=3, value=reg).font = F_BASE
        t = tot.get(uf)
        d = det.get("PRESIDENTE", {}).get(uf)
        for col, val in zip((4, 5, 6), t or (None, None, None)):
            entrada(ws.cell(row=r, column=col), val)
        for col, val in zip((8, 9, 10), (d[1], d[2], d[0]) if d else (None, None, None)):
            entrada(ws.cell(row=r, column=col), val)
        ws.cell(row=r, column=7, value=f'=IF(COUNT(D{r}:F{r})=0,"",SUM(D{r}:F{r}))')
        ws.cell(row=r, column=11, value=f'=IF(N(G{r})=0,"",D{r}/G{r})')
        ws.cell(row=r, column=12, value=f'=IF(N(G{r})=0,"",E{r}/G{r})')
        pf, pl = PRES_PCT[uf]
        for col, val in ((13, pf), (14, pl)):
            c = ws.cell(row=r, column=col, value=None if val is None else val / 100)
            c.font, c.number_format = F_INPUT, PCT
        ws.cell(row=r, column=15, value=(
            f'=IF(N(G{r})>0,IF(D{r}>E{r},"Flávio","Lula"),'
            f'IF(N(M{r})+N(N{r})=0,"",IF(N(M{r})>N(N{r}),"Flávio","Lula")))'))
        for col in range(1, 16):
            c = ws.cell(row=r, column=col)
            c.border = LINHA
            if col in (7,):
                c.number_format, c.font = NUM, F_BASE
            elif col in (11, 12):
                c.number_format, c.font = PCT, F_BASE
            elif col == 15:
                c.font = F_BASE
    ws.cell(row=2, column=13).comment = Comment(FONTE, "Claude")
    tr = len(UFS) + 2
    ws.cell(row=tr, column=1, value="Total").font = Font(name=FONT, size=10, bold=True)
    ws.cell(row=tr, column=2, value="27 UFs (sem exterior)").font = F_BASE
    for col in range(4, 11):
        L = get_column_letter(col)
        c = ws.cell(row=tr, column=col, value=f"=SUM({L}2:{L}{tr-1})")
        c.font, c.number_format = Font(name=FONT, size=10, bold=True), NUM
    br = tr + 2
    ws.cell(row=br, column=1, value="Brasil (TSE, inclui exterior)").font = Font(name=FONT, size=10, bold=True)
    for col, val in ((4, 56104503), (5, 53879538)):
        c = ws.cell(row=br, column=col, value=val)
        c.font, c.number_format = F_INPUT, NUM
    ws.cell(row=br, column=4).comment = Comment(FONTE, "Claude")
    ws.cell(row=br + 1, column=1, value=FONTE).font = F_NOTE


def aba_governador(wb, cand, det):
    ws = wb.create_sheet("Governador")
    tit = ["UF", "Estado", "Situação", "1º colocado", "Partido", "Votos 1º", "% 1º (divulgado)",
           "2º colocado", "Partido", "Votos 2º", "% 2º (divulgado)", "Votos demais candidatos",
           "Votos válidos", "Brancos", "Nulos", "Comparecimento", "% 1º (calculado)"]
    cabecalho(ws, 1, tit, [6, 20, 11, 24, 13, 15, 12, 26, 13, 15, 12, 16, 16, 13, 13, 16, 12])
    porcand = defaultdict(lambda: defaultdict(int))
    for (uf, _m, nome, partido), v in cand.get("GOVERNADOR", {}).items():
        porcand[uf][(nome, partido)] += v
    for r, (uf, nome, _reg) in enumerate(UFS, start=2):
        ws.cell(row=r, column=1, value=uf).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r, column=2, value=nome).font = F_BASE
        sit, cands = GOV[uf]
        ws.cell(row=r, column=3, value=sit).font = F_BASE
        ranking = sorted(porcand.get(uf, {}).items(), key=lambda x: -x[1])
        for k, (cn, cp, cpct) in enumerate((cands + [(None, None, None)])[:2]):
            base = 4 + k * 4
            if ranking and k < len(ranking) and cn is None:
                cn, cp = ranking[k][0]
            ws.cell(row=r, column=base, value=cn).font = F_BASE
            ws.cell(row=r, column=base + 1, value=cp).font = F_BASE
            votos = porcand.get(uf, {}).get((cn, cp)) if cn else None
            if votos is None and ranking and cn:
                votos = next((v for (n, _p), v in ranking if n.upper() == cn.upper()), None)
            entrada(ws.cell(row=r, column=base + 2), votos)
            c = ws.cell(row=r, column=base + 3, value=None if cpct is None else cpct / 100)
            c.font, c.number_format = F_INPUT, PCT
        if ranking:
            usados = sum(ws.cell(row=r, column=c).value or 0 for c in (6, 10))
            demais = sum(v for _k, v in ranking) - usados
        else:
            demais = None
        entrada(ws.cell(row=r, column=12), demais)
        d = det.get("GOVERNADOR", {}).get(uf)
        for col, val in zip((14, 15, 16), (d[1], d[2], d[0]) if d else (None, None, None)):
            entrada(ws.cell(row=r, column=col), val)
        ws.cell(row=r, column=13, value=f'=IF(COUNT(F{r},J{r},L{r})=0,"",SUM(F{r},J{r},L{r}))')
        ws.cell(row=r, column=17, value=f'=IF(N(M{r})=0,"",F{r}/M{r})')
        for col in range(1, 18):
            c = ws.cell(row=r, column=col)
            c.border = LINHA
            if col == 13:
                c.number_format, c.font = NUM, F_BASE
            elif col == 17:
                c.number_format, c.font = PCT, F_BASE
    ws.cell(row=2, column=7).comment = Comment(FONTE, "Claude")
    tr = len(UFS) + 2
    ws.cell(row=tr, column=1, value="Total").font = Font(name=FONT, size=10, bold=True)
    for col in (6, 10, 12, 13, 14, 15, 16):
        L = get_column_letter(col)
        c = ws.cell(row=tr, column=col, value=f"=SUM({L}2:{L}{tr-1})")
        c.font, c.number_format = Font(name=FONT, size=10, bold=True), NUM
    ws.cell(row=tr + 1, column=1, value=FONTE).font = F_NOTE


def aba_municipios(wb, nome, cargo, cand, nomes_mun):
    ws = wb.create_sheet(nome)
    cabecalho(ws, 1, ["UF", "Cód. município (TSE)", "Município", "Candidato", "Partido", "Votos", "Observação"],
              [6, 14, 28, 28, 13, 14, 30])
    linhas = sorted(
        ((uf, m, nomes_mun.get((uf, m), ""), n, p, v) for (uf, m, n, p), v in cand.get(cargo, {}).items()),
        key=lambda x: (x[0], x[2], -x[5]))
    if not linhas:
        ex = ("SP", "71072", "SÃO PAULO", "Nome do candidato", "PARTIDO", 0)
        for col, val in enumerate(ex, start=1):
            c = ws.cell(row=2, column=col, value=val)
            c.font, c.fill = F_INPUT, FILL_EX
        ws.cell(row=2, column=6).number_format = NUM
        ws.cell(row=2, column=7, value="Linha de exemplo do formato. Apague ao preencher.").font = F_NOTE
        return
    for r, row in enumerate(linhas, start=2):
        for col, val in enumerate(row, start=1):
            c = ws.cell(row=r, column=col, value=val)
            c.font = F_INPUT if col == 6 else F_BASE
        ws.cell(row=r, column=6).number_format = NUM
    ws.auto_filter.ref = f"A1:G{len(linhas) + 1}"


def aba_comparacao(wb):
    ws = wb.create_sheet("Comparação")
    ws.cell(row=1, column=1, value="Presidente x Governador por estado").font = F_TITLE
    ws.cell(row=2, column=1, value=(
        "Comparecimento deve ser igual. Brancos, nulos e válidos podem variar entre cargos. "
        "A soma dos municípios deve bater com o total do estado.")).font = F_NOTE
    tit = ["UF", "Estado",
           "Comparecimento Presidente", "Comparecimento Governador", "Diferença", "Comparecimento bate?",
           "Válidos Presidente", "Válidos Governador", "Diferença", "Diferença %",
           "Brancos+Nulos Presidente", "Brancos+Nulos Governador", "Diferença",
           "Soma municípios Presidente", "Bate com estado?", "Soma municípios Governador", "Bate com estado?"]
    cabecalho(ws, 4, tit, [6, 20, 16, 16, 12, 14, 16, 16, 12, 11, 16, 16, 12, 16, 12, 16, 12])
    pm, gm = "'Presidente - Municípios'", "'Governador - Municípios'"
    for i, (uf, nome, _reg) in enumerate(UFS):
        r, s = 5 + i, 2 + i  # s = linha da UF nas abas Presidente/Governador
        ws.cell(row=r, column=1, value=uf).font = Font(name=FONT, size=10, bold=True)
        ws.cell(row=r, column=2, value=nome).font = F_BASE
        f = {
            3: f"=IF(Presidente!J{s}=\"\",\"\",Presidente!J{s})",
            4: f"=IF(Governador!P{s}=\"\",\"\",Governador!P{s})",
            5: f'=IF(COUNT(C{r}:D{r})<2,"",D{r}-C{r})',
            6: f'=IF(COUNT(C{r}:D{r})<2,"Sem dados",IF(D{r}=C{r},"OK","Não bate"))',
            7: f"=IF(Presidente!G{s}=\"\",\"\",Presidente!G{s})",
            8: f"=IF(Governador!M{s}=\"\",\"\",Governador!M{s})",
            9: f'=IF(COUNT(G{r}:H{r})<2,"",H{r}-G{r})',
            10: f'=IF(N(G{r})=0,"",IF(I{r}="","",I{r}/G{r}))',
            11: f'=IF(COUNT(Presidente!H{s}:I{s})=0,"",SUM(Presidente!H{s}:I{s}))',
            12: f'=IF(COUNT(Governador!N{s}:O{s})=0,"",SUM(Governador!N{s}:O{s}))',
            13: f'=IF(COUNT(K{r}:L{r})<2,"",L{r}-K{r})',
            14: f"=IF(COUNTIF({pm}!A:A,A{r})=0,\"\",SUMIFS({pm}!F:F,{pm}!A:A,A{r}))",
            15: f'=IF(COUNT(N{r},G{r})<2,"Sem dados",IF(N{r}=G{r},"OK","Não bate"))',
            16: f"=IF(COUNTIF({gm}!A:A,A{r})=0,\"\",SUMIFS({gm}!F:F,{gm}!A:A,A{r}))",
            17: f'=IF(COUNT(P{r},H{r})<2,"Sem dados",IF(P{r}=H{r},"OK","Não bate"))',
        }
        for col, formula in f.items():
            c = ws.cell(row=r, column=col, value=formula)
            c.font = F_LINK if col in (3, 4, 7, 8, 11, 12) else F_BASE
            c.number_format = PCT if col == 10 else NUM
            c.border = LINHA
        ws.cell(row=r, column=1).border = ws.cell(row=r, column=2).border = LINHA
    fim = 5 + len(UFS)
    ws.cell(row=fim, column=1, value="Total").font = Font(name=FONT, size=10, bold=True)
    for col in (3, 4, 5, 7, 8, 9, 11, 12, 13, 14, 16):
        L = get_column_letter(col)
        c = ws.cell(row=fim, column=col, value=f"=SUM({L}5:{L}{fim-1})")
        c.font, c.number_format = Font(name=FONT, size=10, bold=True), NUM
    ws.cell(row=fim + 1, column=1, value="Estados que não batem (comparecimento):").font = F_BASE
    ws.cell(row=fim + 1, column=6, value=f'=COUNTIF(F5:F{fim-1},"Não bate")').font = Font(name=FONT, size=10, bold=True)
    ws.freeze_panes = "C5"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", help="pasta com os CSVs do TSE descompactados")
    p.add_argument("--saida", default=SAIDA)
    a = p.parse_args()
    cand, det, nomes = ler_tse(a.dir) if a.dir else ({}, {}, {})
    wb = Workbook()
    aba_leiame(wb)
    aba_presidente(wb, cand, det)
    aba_governador(wb, cand, det)
    aba_municipios(wb, "Presidente - Municípios", "PRESIDENTE", cand, nomes)
    aba_municipios(wb, "Governador - Municípios", "GOVERNADOR", cand, nomes)
    aba_comparacao(wb)
    wb.save(a.saida)
    print(f"Gerado: {a.saida}")


if __name__ == "__main__":
    main()
