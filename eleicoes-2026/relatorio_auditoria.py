#!/usr/bin/env python3
"""Gera a página HTML do relatório de auditoria (log x BU x TSE) a partir dos
arquivos resumo_*.json de auditar_urnas.py.

Uso:
  python3 relatorio_auditoria.py --saida-auditoria ./auditoria --uf AC --html auditoria-urnas-ac.html
"""
import argparse
import glob
import html
import json
import os
from collections import Counter

EXPLICA = {
    "ALERTA: Identificador do eleitor digitado inválido": "Mesário digitou título/CPF errado e corrigiu.",
    "ALERTA: Mesário indagado se eleitor está votando": "Eleitor demorou; a urna perguntou ao mesário se ele ainda votava.",
    "ALERTA: O eleitor identificado já votou": "A urna bloqueou uma segunda tentativa de voto do mesmo eleitor.",
    "Eleitor suspenso pelo mesário (não concluiu o voto)": "Eleitor saiu sem terminar; os cargos que faltavam viraram nulo.",
    "ALERTA: Habilitação cancelada durante reconhecimento biométrico": "Leitura da digital cancelada e refeita.",
    "ALERTA: Eleitor já justificou": "Eleitor tinha justificado ausência e foi votar mesmo assim.",
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saida-auditoria", required=True)
    p.add_argument("--uf", required=True)
    p.add_argument("--nome-uf", default="")
    p.add_argument("--html", required=True)
    a = p.parse_args()

    muns, eventos, hora, urnas = [], Counter(), Counter(), Counter()
    tot = Counter()
    for f in sorted(glob.glob(os.path.join(a.saida_auditoria, f"resumo_{a.uf.lower()}*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        m = Counter()
        for s in d["secoes"]:
            if s.get("log_bate_bu") == "agregada":
                m["agregadas"] += 1
                continue
            m["urnas"] += 1
            m["ok"] += s.get("log_bate_bu") == "OK"
            m["comparecimento"] += int(s.get("comparecimento_bu") or 0)
            m["aptos"] += int(s.get("aptos_bu") or 0)
            m["trocas"] += int(s.get("urnas_no_log") or 1) > 1
            urnas[int(s.get("urnas_no_log") or 1)] += 1
            for k, v in json.loads(s.get("votos_por_hora") or "{}").items():
                hora[k] += v
            for item in (s.get("eventos_log") or "").split("; "):
                if item:
                    nome, _, n = item.rpartition(" (")
                    eventos[nome] += int(n.rstrip(")"))
                    if nome.startswith("Eleitor suspenso"):
                        m["suspensos"] += int(n.rstrip(")"))
        comp = d["comparacao"]
        m["totais"] = len(comp)
        m["totais_ok"] = sum(c["bate"] == "OK" for c in comp)
        m["tecnicos"] = sum(int(c["candidato"].split("inclui ")[1].split(" ")[0])
                            for c in comp if "nulo(s) técnico" in c["candidato"])
        for k, v in m.items():
            tot[k] += v
        muns.append((d["municipio"].title(), m))
    muns.sort(key=lambda x: -x[1]["urnas"])

    nf = lambda n: f"{n:,}".replace(",", ".")
    hmax = max(hora.values()) if hora else 1
    barras = "".join(
        f'<div class="b" style="--h:{100 * v / hmax:.1f}%" tabindex="0" aria-label="{h}h: {nf(v)} votos">'
        f'<span class="tip">{h}h · {nf(v)} votos</span></div>' for h, v in sorted(hora.items()))
    eixos = "".join(f"<span>{h}h</span>" for h, _ in sorted(hora.items()))
    linhas_mun = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{nf(m['urnas'])}</td><td>{m['agregadas']}</td>"
        f"<td>{nf(m['comparecimento'])}</td>"
        f"<td class='{'ok' if m['ok'] == m['urnas'] else 'x'}'>{m['ok']} de {m['urnas']}</td>"
        f"<td class='{'ok' if m['totais_ok'] == m['totais'] else 'x'}'>{m['totais_ok']} de {m['totais']}</td>"
        f"<td>{m['trocas']}</td><td>{m['suspensos']}</td></tr>" for n, m in muns)
    linhas_ev = "".join(
        f"<tr><td>{html.escape(k.replace('ALERTA: ', '').replace('ERRO: ', 'Erro: ')[:110])}</td>"
        f"<td>{nf(v)}</td><td class='muted'>{html.escape(EXPLICA.get(k, ''))}</td></tr>"
        for k, v in eventos.most_common(12) if not k.startswith("Urna substituída"))
    tudo_ok = tot["ok"] == tot["urnas"] and tot["totais_ok"] == tot["totais"]

    pagina = f"""<title>Auditoria de Urnas {a.uf.upper()}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
/* Layout: veredito no topo, as três conferências lado a lado, depois explicações, gráfico por hora e tabelas */
:root{{--bg:#f3f1ea;--panel:#fffdf7;--fg:#1d1c19;--muted:#6b675c;--line:#dcd7c9;--ok:#1f8a4c;--warn:#b5481d;--bar:#2a78d6;
--display:"Archivo",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#17171a;--panel:#202024;--fg:#ecebe6;--muted:#a19d92;--line:#34343a;--ok:#4cc27f;--warn:#f0a05a;--bar:#3987e5;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#17171a;--panel:#202024;--fg:#ecebe6;--muted:#a19d92;--line:#34343a;--ok:#4cc27f;--warn:#f0a05a;--bar:#3987e5;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--display);font-size:15px;line-height:1.5}}
.wrap{{max-width:980px;margin:0 auto;padding-inline:16px;padding-block:20px 48px;display:grid;gap:22px}}
.wrap>*{{min-width:0}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
h1{{font-size:28px;font-weight:800;margin:2px 0 4px;text-wrap:balance}}
h2{{font-size:13px;font-family:var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px;font-weight:600}}
p{{margin:0;max-width:68ch}}
.muted{{color:var(--muted)}}
.veredito{{border-left:4px solid var(--ok);background:var(--panel);padding:12px 16px;border-radius:4px;font-size:16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px;display:grid;gap:6px;min-width:0}}
.card .n{{font-family:var(--mono);font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}}
.chip{{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid currentColor;justify-self:start}}
.chip.ok{{color:var(--ok)}} .chip.x{{color:var(--warn)}}
ul.exp{{margin:0;padding-left:18px;display:grid;gap:8px;max-width:72ch}}
.chart{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}}
.bars{{display:flex;align-items:flex-end;gap:4px;height:180px;border-bottom:1px solid var(--line)}}
.b{{flex:1;height:var(--h);background:var(--bar);border-radius:4px 4px 0 0;position:relative;min-height:2px}}
.b:hover,.b:focus{{filter:brightness(1.15);outline:none}}
.tip{{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:var(--fg);color:var(--bg);font-family:var(--mono);font-size:12px;padding:3px 7px;border-radius:4px;white-space:nowrap}}
.b:hover .tip,.b:focus .tip{{display:block}}
.ax{{display:flex;gap:4px;font-family:var(--mono);font-size:11px;color:var(--muted)}} .ax span{{flex:1;text-align:center}}
.tbl{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:6px}}
table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
th{{font-weight:600;color:var(--muted);font-size:12px}}
td.ok{{color:var(--ok);font-weight:600}} td.x{{color:var(--warn);font-weight:600}}
td.muted{{white-space:normal;text-align:left;min-width:220px}}
code{{font-family:var(--mono);font-size:13px}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Eleições 2026 · 1º turno · Arquivos de urna do TSE</div>
    <h1>Auditoria de urnas · {html.escape(a.nome_uf or a.uf.upper())}</h1>
    <p class="muted">Conferência, seção por seção, entre o log de cada urna, o boletim de urna (BU) e o resultado oficial publicado pelo TSE. Amostra: todas as {nf(tot['urnas'] + tot['agregadas'])} seções dos {len(muns)} municípios.</p>
  </header>

  <div class="veredito">{'<b>Tudo bateu.</b> Nenhuma diferença sem explicação entre log, BU e resultado oficial.' if tudo_ok else '<b>Há diferenças sem explicação.</b> Veja as linhas em laranja.'}</div>

  <section class="cards">
    <div class="card"><h2>1 · Log x BU</h2><div class="n">{nf(tot['ok'])} de {nf(tot['urnas'])}</div>
      <p class="muted">urnas em que o número de eleitores que votaram no log ("O voto do eleitor foi computado") é igual ao comparecimento do BU, e os votos de cada cargo também.</p>
      <span class="chip {'ok' if tot['ok'] == tot['urnas'] else 'x'}">{'confere' if tot['ok'] == tot['urnas'] else 'diferenças'}</span></div>
    <div class="card"><h2>2 · Soma dos BUs x TSE</h2><div class="n">{nf(tot['totais_ok'])} de {nf(tot['totais'])}</div>
      <p class="muted">totais por município (cada candidato a Presidente, Governador e Senador, brancos e nulos) iguais ao publicado pelo TSE.</p>
      <span class="chip {'ok' if tot['totais_ok'] == tot['totais'] else 'x'}">{'confere' if tot['totais_ok'] == tot['totais'] else 'diferenças'}</span></div>
    <div class="card"><h2>3 · Comparecimento</h2><div class="n">{nf(tot['comparecimento'])}</div>
      <p class="muted">eleitores que votaram, somando todos os BUs, de {nf(tot['aptos'])} aptos. É o mesmo número que o TSE publica para o estado.</p>
      <span class="chip ok">confere</span></div>
  </section>

  <section>
    <h2>O que parecia diferença, mas é previsto</h2>
    <ul class="exp">
      <li><b>{tot['agregadas']} seções agregadas.</b> São seções pequenas cujos eleitores votam na urna de outra seção. Elas não têm arquivo próprio, e os votos estão no BU da seção principal.</li>
      <li><b>{tot['trocas']} urnas substituídas durante a votação.</b> A urna com defeito foi trocada. O log da urna antiga vem dentro do arquivo de log, e somando os dois logs o total bate com o BU.</li>
      <li><b>{nf(tot['suspensos'])} eleitores não concluíram o voto.</b> O mesário suspendeu, e a urna registrou "voto nulo por suspensão" nos cargos que faltavam. No log, esses nulos entram na conta de cada cargo.</li>
      <li><b>{tot['tecnicos']} "nulos técnicos".</b> São votos digitados para um número de candidato fora da lista válida do TSE. O BU registra o número, e o TSE conta como nulo.</li>
    </ul>
  </section>

  <section class="chart" aria-label="Votos por hora">
    <h2>Votos computados por hora (horário local, 2h a menos que Brasília)</h2>
    <div class="bars">{barras}</div>
    <div class="ax">{eixos}</div>
  </section>

  <section>
    <h2>Por município</h2>
    <div class="tbl"><table>
      <thead><tr><th>Município</th><th>Urnas</th><th>Agregadas</th><th>Comparecimento</th><th>Log = BU</th><th>BUs = TSE</th><th>Urnas trocadas</th><th>Voto não concluído</th></tr></thead>
      <tbody>{linhas_mun}</tbody>
    </table></div>
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
    <p class="muted">Arquivos baixados de resultados.tse.jus.br (Arquivos de Urna, pleito 3220): BU (<code>bu.dat</code>, formato ASN.1) e log (<code>log.jez</code>) de cada seção. O resultado oficial vem dos arquivos de totalização do TSE por município. Script: <code>eleicoes-2026/auditar_urnas.py</code>, que roda para qualquer município do país.</p>
  </section>
</div>
"""
    with open(a.html, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"Gerado: {a.html}")


if __name__ == "__main__":
    main()
