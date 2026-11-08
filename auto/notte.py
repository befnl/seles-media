"""notte.py — grafiche della routine settimanale nella linea «Notte» (glow up 11/2026).

Sostituisce l'aspetto di riepilogo() e storia() di settimana.py: stessi dati Tuttocampo, nuova veste.
  riepilogo(nome_slide, partite, risultato, foto=None)  post 4:5, foto vera in testa se c'è
  storia(nome_slide, m)                                  storia 9:16 con stemmi e dati, senza foto
Le immagini usano il prefisso R/ (= cartella kit-social), come in settimana.py.
Prova: ../../../.venv-render/bin/python notte.py prova
"""
import datetime as dt
import settimana as S

ACC = {"C5": "#1898D8", "C11": "#F4F7FB", "U17": "#FF8C00", "U15": "#FFB347", "U19": "#7CD3F7"}
CAT = {"C5": "Calcio a 5", "C11": "Calcio a 11", "U17": "Under 17", "U15": "Under 15", "U19": "Juniores C5"}


def _tm(n, tid, casa):
    src, _, _ = S.stemma(tid, n)
    seles = "Seles" in n
    img = f'<img src="R/{src}" alt="">'
    nm = S.nome(n)
    txt = S.a_capo(nm) if len(nm) > 16 else nm
    cls = "tm" + (" h" if casa else "") + (" s" if seles else "")
    return f'<div class="{cls}">{txt}{img}</div>' if casa else f'<div class="{cls}">{img}{txt}</div>'


def _dove(sq, m):
    if m["seles_casa"]:
        return f"in casa, {S.campo(sq, m)}"
    c = S.campo(sq, m)
    return "in trasferta" if c == "In trasferta" else f"in trasferta, {c}"


def _periodo(partite):
    d0, d1 = (dt.datetime.fromisoformat(partite[i]["quando"]) for i in (0, -1))
    g = lambda d: "1°" if d.day == 1 else str(d.day)
    if d0.date() == d1.date():
        return f"{S.GIORNI[d0.weekday()]} {g(d0)} {S.MESI[d0.month - 1]}"
    m0 = f" {S.MESI[d0.month - 1]}" if d0.month != d1.month else ""
    return f"Dal {g(d0)}{m0} al {g(d1)} {S.MESI[d1.month - 1]}"


def riepilogo(nome_slide, partite, risultato, foto=None):
    righe = []
    for m in partite:
        sq = S.squadra_di(m)
        d = dt.datetime.fromisoformat(m["quando"])
        if risultato:
            mid = f'<div class="sc">{m["gol"][0]}<i>-</i>{m["gol"][1]}</div>'
            dx = f"{S.GIORNI[d.weekday()]} {d.day}, {_dove(sq, m)}"
        else:
            mid = f'<div class="tt"><b>{d:%H:%M}</b><span>{S.GIORNI[d.weekday()]} {d.day}</span></div>'
            dx = _dove(sq, m)
        righe.append(f'''    <div class="it" style="--acc:{ACC[m["squadra"]]}">
      <div class="cat"><span><b>{CAT[m["squadra"]]}</b>, {sq["comp"].replace(" Girone", ", girone")}</span><span>{dx}</span></div>
      <div class="ln">{_tm(m["casa"], m["casa_id"], True)}{mid}{_tm(m["ospite"], m["ospite_id"], False)}</div>
    </div>''')
    n = len(partite)
    # con la foto il titolo sta in fondo alla foto; senza, sale in alto
    if foto:
        testa = f'<img class="ph" src="R/{foto}" alt=""><div class="ph-fade"></div>'
        ttl_top, list_top = 380, 560 if n <= 4 else 540
    else:
        testa = '<div class="noph"></div>'
        ttl_top, list_top = 190, 380
    titolo = "Risultati" if risultato else "I match"
    return f'''
<div class="slide ig rec{" n5" if n > 4 else ""}{"" if foto else " big"}{" few" if n <= 3 else ""}" data-name="{nome_slide}">
  {testa}
  <img class="mk" src="R/assets/loghi/seles-trim.png" alt="">
  <div class="tr"><b>Prima squadra</b><br>e settore giovanile</div>
  <div class="ttl" style="top:{ttl_top}px"><h1>{titolo}</h1><p>{_periodo(partite)}</p></div>
  <div class="list" style="top:{list_top}px">
{chr(10).join(righe)}
  </div>
  <div class="foot"><span><b>@asdseles</b></span><span>Gioco con l'altro e non contro l'altro</span></div>
  <div class="grain"></div>
</div>
'''


CITTA = S.HERE / "assets/sfondi/citta"     # foto del paese avversario: <id squadra Tuttocampo>.jpg + diritti.json
# Trattamento della foto di sfondo: "fumo" (fumo blu leggero in basso, confermato da Lorenzo l'8/11),
# alternative provate: "duotone", "retino", "bn"
FX = "fumo"


# Paese del campo (dall'indirizzo dello stadio su Tuttocampo) -> nome del file in assets/sfondi/citta/.
# Le foto sono DALL'ALTO (Lorenzo, 8/11) e le scarica lui: <paese>.jpg, per Gioiosa anche gioiosa-ionica-2.jpg, -3…
PAESE_ALIAS = {
    "reggio calabria": "reggio-calabria", "gallico": "reggio-calabria", "bocale": "reggio-calabria",
    "santa eufemia lamezia": "lamezia-terme", "caulonia marina": "caulonia", "frabotto mannesi": "montepaone",
    "sant'andrea ionio marina": "sant-andrea-apostolo-dello-ionio",
    "sant'andrea apostolo dello ionio marina": "sant-andrea-apostolo-dello-ionio",
    "sant'andrea apostolo dello ionio": "sant-andrea-apostolo-dello-ionio",
    "caraffa di catanzaro": "caraffa-di-catanzaro", "chiaravalle centrale": "chiaravalle-centrale",
    "san nicola da crissa": "san-nicola-da-crissa", "san costantino calabro": "san-costantino-calabro",
}
# squadre il cui stadio su Tuttocampo non dice il paese
PAESE_SQUADRA = {"Davoli Academy": "davoli", "Maestrelli C5": "reggio-calabria", "Union Siderno 2015": "siderno", "Virtus C5": "cinquefrondi",
                 "Accursi Football Academy": "locri"}


def paese(m):
    if m["seles_casa"]:
        return "gioiosa-ionica"
    p = PAESE_SQUADRA.get(m["casa"])
    if p:
        return p
    st = (m.get("stadio") or "")
    if "," not in st:
        return None
    import unicodedata
    t = st.rsplit(",", 1)[1].strip().lower()
    t = PAESE_ALIAS.get(t, t.replace("'", "-").replace(" ", "-"))
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()       # Dasà -> dasa


def sfondo(m):
    """Foto di sfondo della storia: la foto dall'alto del paese dove si gioca (Gioiosa in casa).
    Restituisce (percorso relativo a kit-social o None, diritti_ok, credito da stampare in piccolo).
    In casa, senza foto di Gioiosa, resta la foto del nostro campo; fuori, senza foto, fondo navy."""
    import json
    sq = S.squadra_di(m)
    p = paese(m)
    foto = sorted(CITTA.glob(f"{p}.jpg")) + sorted(CITTA.glob(f"{p}-[0-9]*.jpg")) if p else []
    if not foto:
        return (f"assets/sfondi/{sq['casa_bg']}", True, "") if m["seles_casa"] else (None, True, "")
    f = foto[int(m["giornata"]) % len(foto)]                # più foto dello stesso paese: si alternano
    d = json.loads((CITTA / "diritti.json").read_text(encoding="utf-8")) if (CITTA / "diritti.json").exists() else {}
    x = d.get(f.stem, d.get(p, {}))
    return f"assets/sfondi/citta/{f.name}", bool(x.get("ok")), x.get("credito", "")


def storia(nome_slide, m):
    sq = S.squadra_di(m)
    d = dt.datetime.fromisoformat(m["quando"])
    (cs, _, _), (os_, _, _) = S.stemma(m["casa_id"], m["casa"]), S.stemma(m["ospite_id"], m["ospite"])
    dove = S.campo(sq, m)
    luogo = f"{dove}, Gioiosa Ionica" if m["seles_casa"] else ("In trasferta" if dove == "In trasferta" else f"{dove}, in trasferta")
    comp = sq["comp"].replace(" Girone", ", girone")
    # una riga sola, grande: il campionato se ha un nome (Prima Categoria, Serie C2), altrimenti la categoria
    camp = (f'<b>{comp.split(", ")[0]}</b>, {", ".join(comp.split(", ")[1:])}, giornata {m["giornata"]}' if not comp.startswith("Girone")
            else f'<b>{sq["nome"]}</b>, {comp.replace("Girone", "girone")}, giornata {m["giornata"]}')
    bg, ok, credito = sfondo(m)
    if bg and not ok:
        print(f"  ⚠ {nome_slide}: foto del paese senza diritti confermati (assets/sfondi/citta/diritti.json) — non pubblicare")
    fx = FX
    if bg and fx == "retino":
        import fx as F
        bg = F.retino(bg)
    fumo = (f'<img class="fumo" src="R/assets/sfondi/fumo-vero-{1 + int(m["giornata"]) % 2}.png" alt="">'
            if fx == "fumo" else "")                       # fumo vero (Unsplash), lato alternato
    bgh = (f'<div class="bgp"><img src="R/{bg}" alt=""></div><div class="bgv"></div>{fumo}'
           if bg else f'<div class="glow"></div>{fumo}')
    oc, oo = ("", " o") if "Seles" in m["casa"] else (" o", "")
    return f'''
<div class="slide st md fx-{FX}" data-name="{nome_slide}" style="--acc:{ACC[m["squadra"]]}">
  {bgh}
  <img class="mk" src="R/assets/loghi/seles-trim.png" alt="" style="top:150px">
  <div class="tr" style="top:162px">Oggi si gioca</div>
  <div class="cat">{camp}</div>
  <div class="acc" style="top:470px"></div>
  <div class="duo">
    <div class="sd{oc}"><img src="R/{cs}" alt=""><span>{S.a_capo(S.nome(m["casa"]))}</span></div>
    <i>vs</i>
    <div class="sd{oo}"><img src="R/{os_}" alt=""><span>{S.a_capo(S.nome(m["ospite"]))}</span></div>
  </div>
  <div class="dt"><b>{d:%H:%M}</b>{luogo}</div>
  <div class="foot"><span><b>@asdseles</b></span><span>Gioco con l'altro e non contro l'altro</span></div>
  {f'<div class="cred">{credito}</div>' if credito else ""}
  <div class="grain"></div>
</div>
'''


def documento(html, rel):
    """rel = percorso dalla cartella dell'html a kit-social (es. '../../')."""
    return ('<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>SELES settimana</title>'
            f'<link rel="stylesheet" href="{rel}notte.css"></head><body>{html}</body></html>').replace('src="R/', f'src="{rel}')


if __name__ == "__main__":
    import sys, json, subprocess
    if sys.argv[1:] == ["prova"]:
        # dati veri già letti da Tuttocampo nel piano del 2/11 (risultati 31/10–1/11, partite 7–9/11)
        p = json.loads((S.OUT_ROOT / "2026-11-02/piano.json").read_text(encoding="utf-8"))
        cart = S.OUT_ROOT / "prova-notte"; cart.mkdir(exist_ok=True)
        html = riepilogo("prova-risultati-foto", p["risultati"]["match"], True, foto="assets/foto/settimana/2026-11-07-c5.jpg")
        html += riepilogo("prova-risultati", p["risultati"]["match"], True)
        html += riepilogo("prova-partite", p["partite"]["match"], False)
        for m in p["partite"]["match"]:
            html += storia(f"prova-storia-{m['squadra'].lower()}", m)
        (cart / "prova.html").write_text(documento(html, "../../"), encoding="utf-8")
        subprocess.run([str(S.PY), str(S.BUILD), str(cart / "prova.html"), str(cart / "out"), "1080", "1920", "1", "92"], check=True)
