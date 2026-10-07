#!/usr/bin/env python3
"""Gera a página HTML do relatório de auditoria (log x BU x TSE) a partir dos
arquivos resumo_*.json de auditar_urnas.py, para um ou vários estados.

Uso:
  python3 relatorio_auditoria.py --saida-auditoria ./auditoria --html auditoria-urnas.html \\
      [--ufs AC,BA,CE] [--resumo-estado ./dados/resumo_estado.csv]

--resumo-estado (de consolidar_tse.py) acrescenta a conferência do comparecimento
somado dos BUs com o comparecimento oficial do TSE em cada estado.
"""
import argparse
import csv
import glob
import html
import json
import os
from collections import Counter, defaultdict

NOMES = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
         "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
         "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
         "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
         "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
         "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
ORDEM = ["AC", "BA", "CE", "PE", "MA", "PB", "RN", "AL", "PI", "SE", "MG", "SP"]
EXPLICA = {
    "ALERTA: Identificador do eleitor digitado inválido": "Mesário digitou título/CPF errado e corrigiu.",
    "ALERTA: Mesário indagado se eleitor está votando": "Eleitor demorou; a urna perguntou ao mesário se ele ainda votava.",
    "ALERTA: O eleitor identificado já votou": "A urna bloqueou uma segunda tentativa de voto do mesmo eleitor.",
    "Eleitor suspenso pelo mesário (não concluiu o voto)": "Eleitor saiu sem terminar; os cargos que faltavam viraram nulo.",
    "ALERTA: Habilitação cancelada durante reconhecimento biométrico": "Leitura da digital cancelada e refeita.",
    "ALERTA: Eleitor já justificou": "Eleitor tinha justificado ausência e foi votar mesmo assim.",
    "Urna travou logo após o eleitor confirmar o último cargo (voto gravado no BU)":
        "A urna travou no fim do voto; o BU mostra que o voto foi gravado.",
    "Urna travou logo após o eleitor confirmar o último cargo (voto não gravado)":
        "A urna travou no fim do voto e não gravou esse voto; o BU confirma.",
    "Voto interrompido (urna desligada/reiniciada) e refeito pelo eleitor":
        "Urna desligada no meio de um voto; o voto parcial foi descartado e o eleitor votou de novo.",
}


def nf(n):
    return f"{n:,}".replace(",", ".")


def ler_estado(pasta, uf, casos, casos_sa):
    muns, eventos, hora = [], Counter(), Counter()
    tot = Counter()
    for f in sorted(glob.glob(os.path.join(pasta, f"resumo_{uf.lower()}[0-9]*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        m = Counter()
        for s in d["secoes"]:
            if s.get("log_bate_bu") == "agregada":
                m["agregadas"] += 1
                continue
            if s.get("log_bate_bu") == "SA":
                m["sa"] += 1
                m["comparecimento"] += int(s.get("comparecimento_bu") or 0)
                m["aptos"] += int(s.get("aptos_bu") or 0)
                casos_sa.append((uf, d["municipio"].title(), s))
                continue
            if "comparecimento_bu" not in s:
                m["sem_arquivo"] += 1
                continue
            m["urnas"] += 1
            m["ok"] += s.get("log_bate_bu") == "OK"
            if s.get("log_bate_bu") != "OK":
                casos.append((uf, d["municipio"].title(), s))
            m["comparecimento"] += int(s.get("comparecimento_bu") or 0)
            m["aptos"] += int(s.get("aptos_bu") or 0)
            m["trocas"] += int(s.get("urnas_no_log") or 1) > 1
            for k, v in json.loads(s.get("votos_por_hora") or "{}").items():
                hora[k] += v
            for item in (s.get("eventos_log") or "").split("; "):
                if item:
                    nome, _, n = item.rpartition(" (")
                    n = int(n.rstrip(")"))
                    eventos[nome] += n
                    if nome.startswith("Eleitor suspenso"):
                        m["suspensos"] += n
                    if nome.startswith("Voto interrompido"):
                        m["interrompidos"] += n
                    if nome.startswith("Urna travou logo após") and "voto gravado" in nome:
                        m["travou_gravado"] += n
                    if nome.startswith("Urna travou logo após") and "não gravado" in nome:
                        m["travou_perdido"] += n
        comp = d["comparacao"]
        m["totais"] = len(comp)
        m["totais_ok"] = sum(c["bate"] == "OK" for c in comp)
        m["tecnicos"] = sum(int(c["candidato"].split("inclui ")[1].split(" ")[0])
                            for c in comp if "nulo(s) técnico" in c["candidato"])
        for k, v in m.items():
            tot[k] += v
        muns.append((d["municipio"].title(), m))
    muns.sort(key=lambda x: (x[1]["ok"] == x[1]["urnas"] and x[1]["totais_ok"] == x[1]["totais"], -x[1]["urnas"]))
    return muns, tot, eventos, hora


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saida-auditoria", required=True)
    p.add_argument("--html", required=True)
    p.add_argument("--ufs", help="lista separada por vírgula; padrão: todos os estados com resultado")
    p.add_argument("--resumo-estado", help="resumo_estado.csv de consolidar_tse.py")
    a = p.parse_args()

    achados = {os.path.basename(f)[7:9].upper() for f in glob.glob(os.path.join(a.saida_auditoria, "resumo_*.json"))}
    ufs = [u.strip().upper() for u in a.ufs.split(",")] if a.ufs else \
        sorted(achados, key=lambda u: (ORDEM.index(u) if u in ORDEM else 99, u))
    oficial = {}
    if a.resumo_estado:
        with open(a.resumo_estado, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r["cargo"] == "Presidente":
                    oficial[r["uf"]] = int(r["comparecimento"])

    estados, tot, eventos, hora = [], Counter(), Counter(), defaultdict(Counter)
    casos, casos_sa = [], []
    for uf in ufs:
        muns, t, ev, h = ler_estado(a.saida_auditoria, uf, casos, casos_sa)
        if not muns:
            continue
        t["municipios"] = len(muns)
        estados.append((uf, muns, t))
        tot.update(t)
        eventos.update(ev)
        hora[uf] = h
    if not estados:
        raise SystemExit("Nenhum resultado encontrado")

    comp_ok = all(oficial.get(uf) in (None, t["comparecimento"]) for uf, _m, t in estados)
    tudo_ok = tot["ok"] == tot["urnas"] and tot["totais_ok"] == tot["totais"] and comp_ok and not tot["sem_arquivo"]
    nomes_ufs = ", ".join(NOMES.get(uf, uf) for uf, _m, _t in estados)

    hsum = Counter()
    for h in hora.values():
        hsum.update(h)
    hmax = max(hsum.values()) if hsum else 1
    barras = "".join(
        f'<div class="b" style="--h:{100 * v / hmax:.1f}%" tabindex="0" aria-label="{h}h: {nf(v)} votos">'
        f'<span class="tip">{h}h · {nf(v)} votos</span></div>' for h, v in sorted(hsum.items()))
    eixos = "".join(f"<span>{h}h</span>" for h, _ in sorted(hsum.items()))

    def cls(ok):
        return "ok" if ok else "x"

    linhas_uf = ""
    for uf, _m, t in estados:
        of = oficial.get(uf)
        linhas_uf += (
            f"<tr><td>{NOMES.get(uf, uf)}</td><td>{t['municipios']}</td><td>{nf(t['urnas'])}</td>"
            f"<td>{nf(t['agregadas'])}</td>"
            f"<td class='{cls(t['ok'] == t['urnas'])}'>{nf(t['ok'])} de {nf(t['urnas'])}</td>"
            f"<td class='{cls(t['totais_ok'] == t['totais'])}'>{nf(t['totais_ok'])} de {nf(t['totais'])}</td>"
            f"<td>{nf(t['comparecimento'])}</td>"
            f"<td class='{cls(of in (None, t['comparecimento']))}'>{'-' if of is None else ('igual' if of == t['comparecimento'] else nf(of))}</td>"
            f"<td>{nf(t['trocas'])}</td><td>{nf(t['interrompidos'])}</td><td>{nf(t['suspensos'])}</td></tr>")

    detalhes = ""
    for uf, muns, t in estados:
        com_dif = [x for x in muns if x[1]["ok"] != x[1]["urnas"] or x[1]["totais_ok"] != x[1]["totais"]]
        linhas = "".join(
            f"<tr><td>{html.escape(n)}</td><td>{nf(m['urnas'])}</td><td>{m['agregadas']}</td>"
            f"<td>{nf(m['comparecimento'])}</td>"
            f"<td class='{cls(m['ok'] == m['urnas'])}'>{m['ok']} de {m['urnas']}</td>"
            f"<td class='{cls(m['totais_ok'] == m['totais'])}'>{m['totais_ok']} de {m['totais']}</td>"
            f"<td>{m['trocas']}</td><td>{m['suspensos']}</td></tr>" for n, m in muns)
        resumo = (f"{len(com_dif)} com diferença" if com_dif else "todos conferem")
        detalhes += f"""<details><summary><b>{NOMES.get(uf, uf)}</b> · {t['municipios']} municípios · {resumo}</summary>
<div class="tbl"><table><thead><tr><th>Município</th><th>Urnas</th><th>Agregadas</th><th>Comparecimento</th>
<th>Log = BU</th><th>BUs = TSE</th><th>Urnas trocadas</th><th>Voto não concluído</th></tr></thead>
<tbody>{linhas}</tbody></table></div></details>"""

    linhas_casos = "".join(
        f"<tr><td>{NOMES.get(uf, uf)}</td><td>{html.escape(mun)}</td><td>{c['zona']}</td><td>{c['secao']}</td>"
        f"<td>{nf(int(c.get('comparecimento_bu') or 0))}</td><td>{nf(int(c.get('votos_computados_log') or 0))}</td>"
        f"<td class='muted'>{html.escape('; '.join(e for e in (c.get('eventos_log') or '').split('; ') if not e.startswith('ALERTA')))}</td></tr>"
        for uf, mun, c in casos)
    bloco_casos = "" if not casos else f"""<section>
    <h2>Casos a examinar ({len(casos)})</h2>
    <p class="muted" style="margin-bottom:10px">Urnas em que o log publicado não confere com o BU. {'A soma dos BUs bate com o TSE em todos os municípios, inclusive nesses: a diferença está no registro (log), não nos votos.' if tot['totais_ok'] == tot['totais'] else 'Há também municípios em que a soma dos BUs difere do TSE; veja a lista por estado.'}</p>
    <div class="tbl"><table>
      <thead><tr><th>Estado</th><th>Município</th><th>Zona</th><th>Seção</th><th>Eleitores no BU</th><th>Eleitores no log</th><th style="text-align:left">O que o log mostra</th></tr></thead>
      <tbody>{linhas_casos}</tbody>
    </table></div>
  </section>"""
    li_sa = "" if not casos_sa else (
        f"<li><b>{len(casos_sa)} seções apuradas pelo Sistema de Apuração (SA).</b> Quando a urna não pode ser usada "
        "até o fim, os votos são apurados pelo SA, por exemplo com cédulas de papel. Não há log de votação para comparar, "
        "e o BU do SA entra na soma, que bate com o TSE. Casos: "
        + "; ".join(f"{html.escape(mun)} ({uf}), zona {c['zona']}, seção {c['secao']}: "
                    f"{html.escape(c.get('eventos_log', '').replace('Apurada pelo SA: ', '').rsplit(' (1)', 1)[0])}"
                    for uf, mun, c in casos_sa) + ".</li>")
    linhas_ev = "".join(
        f"<tr><td>{html.escape(k.replace('ALERTA: ', '').replace('ERRO: ', 'Erro: ')[:110])}</td>"
        f"<td>{nf(v)}</td><td class='muted'>{html.escape(EXPLICA.get(k, ''))}</td></tr>"
        for k, v in eventos.most_common(16) if not k.startswith(("Urna substituída", "Log publicado traz", "Apurada pelo SA")))

    titulo = "Auditoria de Urnas" if len(estados) > 1 else f"Auditoria de Urnas {estados[0][0]}"
    pagina = f"""<title>{titulo}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
/* Layout: veredito no topo, três conferências, tabela por estado, explicações, gráfico por hora e detalhes por município */
:root{{--bg:#f3f1ea;--panel:#fffdf7;--fg:#1d1c19;--muted:#6b675c;--line:#dcd7c9;--ok:#1f8a4c;--warn:#b5481d;--bar:#2a78d6;
--display:"Archivo",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#17171a;--panel:#202024;--fg:#ecebe6;--muted:#a19d92;--line:#34343a;--ok:#4cc27f;--warn:#f0a05a;--bar:#3987e5;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#17171a;--panel:#202024;--fg:#ecebe6;--muted:#a19d92;--line:#34343a;--ok:#4cc27f;--warn:#f0a05a;--bar:#3987e5;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--display);font-size:15px;line-height:1.5}}
.wrap{{max-width:1040px;margin:0 auto;padding-inline:16px;padding-block:20px 48px;display:grid;gap:22px}}
.wrap>*{{min-width:0}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
h1{{font-size:28px;font-weight:800;margin:2px 0 4px;text-wrap:balance}}
h2{{font-size:13px;font-family:var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px;font-weight:600}}
p{{margin:0;max-width:70ch}}
.muted{{color:var(--muted)}}
.veredito{{border-left:4px solid var(--ok);background:var(--panel);padding:12px 16px;border-radius:4px;font-size:16px}}
.veredito.x{{border-left-color:var(--warn)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px;display:grid;gap:6px;align-content:start;min-width:0}}
.card .n{{font-family:var(--mono);font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}}
ul.exp{{margin:0;padding-left:18px;display:grid;gap:8px;max-width:74ch}}
.chart{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}}
.bars{{display:flex;align-items:flex-end;gap:4px;height:180px;border-bottom:1px solid var(--line)}}
.b{{flex:1;height:var(--h);background:var(--bar);border-radius:4px 4px 0 0;position:relative;min-height:2px}}
.b:hover,.b:focus{{filter:brightness(1.15);outline:none}}
.tip{{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:var(--fg);color:var(--bg);font-family:var(--mono);font-size:12px;padding:3px 7px;border-radius:4px;white-space:nowrap;z-index:2}}
.b:hover .tip,.b:focus .tip{{display:block}}
.ax{{display:flex;gap:4px;font-family:var(--mono);font-size:11px;color:var(--muted)}} .ax span{{flex:1;text-align:center}}
.tbl{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:6px}}
table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
th{{font-weight:600;color:var(--muted);font-size:12px}}
td.ok{{color:var(--ok);font-weight:600}} td.x{{color:var(--warn);font-weight:600}}
td.muted{{white-space:normal;text-align:left;min-width:220px}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px 12px}}
details+details{{margin-top:8px}}
details summary{{cursor:pointer}}
details .tbl{{border:0;margin-top:8px;max-height:480px;overflow:auto}}
code{{font-family:var(--mono);font-size:13px}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Eleições 2026 · 1º turno · Arquivos de urna do TSE</div>
    <h1>Auditoria de urnas</h1>
    <p class="muted">Conferência, seção por seção, entre o log de cada urna, o boletim de urna (BU) e o resultado oficial do TSE. Estados auditados: {nomes_ufs}. São {nf(tot['urnas'] + tot['agregadas'] + tot['sem_arquivo'] + tot['sa'])} seções em {nf(tot['municipios'])} municípios.</p>
  </header>

  <div class="veredito {'' if tudo_ok else 'x'}">{'<b>Tudo bateu.</b> Nenhuma diferença sem explicação entre log, BU e resultado oficial.' if tudo_ok else '<b>Há diferenças a examinar.</b> Veja as células em laranja e os municípios marcados abaixo.'}</div>

  <section class="cards">
    <div class="card"><h2>1 · Log x BU</h2><div class="n">{nf(tot['ok'])} de {nf(tot['urnas'])}</div>
      <p class="muted">urnas em que o log e o BU têm o mesmo número de eleitores e os mesmos votos em cada cargo.</p></div>
    <div class="card"><h2>2 · Soma dos BUs x TSE</h2><div class="n">{nf(tot['totais_ok'])} de {nf(tot['totais'])}</div>
      <p class="muted">totais por município (cada candidato a Presidente, Governador e Senador, brancos e nulos) iguais ao publicado pelo TSE.</p></div>
    <div class="card"><h2>3 · Comparecimento</h2><div class="n">{nf(tot['comparecimento'])}</div>
      <p class="muted">eleitores que votaram, somando todos os BUs. {'Igual ao número oficial do TSE em cada estado.' if oficial and comp_ok else ('Há estado com diferença; veja a tabela.' if oficial else '')}</p></div>
  </section>

  <section>
    <h2>Por estado</h2>
    <div class="tbl"><table>
      <thead><tr><th>Estado</th><th>Municípios</th><th>Urnas</th><th>Agregadas</th><th>Log = BU</th><th>BUs = TSE</th><th>Comparecimento (BUs)</th><th>TSE</th><th>Urnas trocadas</th><th>Votos interrompidos</th><th>Voto não concluído</th></tr></thead>
      <tbody>{linhas_uf}</tbody>
    </table></div>
  </section>

  {bloco_casos}

  <section>
    <h2>O que parecia diferença, mas é previsto</h2>
    <ul class="exp">
      {li_sa}
      <li><b>{nf(tot['agregadas'])} seções agregadas.</b> Seções pequenas cujos eleitores votam na urna de outra seção. Não têm arquivo próprio, e os votos estão no BU da seção principal.</li>
      <li><b>{nf(tot['trocas'])} urnas substituídas durante a votação.</b> O log da urna com defeito vem dentro do arquivo de log, e somando os logs o total bate com o BU.</li>
      <li><b>{nf(tot['interrompidos'])} votos interrompidos.</b> A urna foi desligada ou reiniciada no meio do voto de um eleitor. O voto parcial foi descartado, o eleitor votou de novo desde o início, e só o voto completo entra no BU.</li>
      <li><b>{nf(tot['travou_gravado'] + tot['travou_perdido'])} vezes a urna travou logo depois de o eleitor confirmar o último cargo</b>, antes de registrar "O voto do eleitor foi computado". O BU mostra o que aconteceu: em {nf(tot['travou_gravado'])} o voto foi gravado e em <b>{nf(tot['travou_perdido'])} o voto não foi gravado</b>. Nesses casos o log não permite saber se o eleitor votou de novo depois que a urna voltou.</li>
      <li><b>{nf(tot['suspensos'])} eleitores não concluíram o voto.</b> O mesário suspendeu, e a urna registrou "voto nulo por suspensão" nos cargos que faltavam.</li>
      <li><b>{nf(tot['tecnicos'])} "nulos técnicos".</b> Votos digitados para um número de candidato fora da lista válida do TSE. O BU registra o número, e o TSE conta como nulo.</li>
    </ul>
  </section>

  <section class="chart" aria-label="Votos por hora">
    <h2>Votos computados por hora (horário local de cada estado)</h2>
    <div class="bars">{barras}</div>
    <div class="ax">{eixos}</div>
  </section>

  <section>
    <h2>Municípios, por estado</h2>
    <p class="muted" style="margin-bottom:10px">Toque no estado para abrir a lista. Municípios com alguma diferença aparecem primeiro.</p>
    {detalhes}
  </section>

  <section>
    <h2>Ocorrências registradas nos logs</h2>
    <p class="muted" style="margin-bottom:10px">Alertas são avisos normais de operação. Os números de título de eleitor que aparecem em alguns registros foram removidos.</p>
    <div class="tbl"><table>
      <thead><tr><th>Registro</th><th>Vezes</th><th style="text-align:left">O que significa</th></tr></thead>
      <tbody>{linhas_ev}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Como foi feito</h2>
    <p class="muted">Arquivos de resultados.tse.jus.br (Arquivos de Urna, pleito 3220): BU (<code>bu.dat</code>, ASN.1) e log (<code>log.jez</code>) de cada seção, conferidos com a totalização oficial por município. No log, só contam os votos de eleitores com registro "O voto do eleitor foi computado". Script: <code>eleicoes-2026/auditar_urnas.py</code>.</p>
  </section>
</div>
"""
    with open(a.html, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"Gerado: {a.html} ({', '.join(uf for uf, _m, _t in estados)})")


if __name__ == "__main__":
    main()
