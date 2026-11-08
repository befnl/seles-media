#!/usr/bin/env python3
"""
settimana.py — la routine settimanale dei social Seles, in due comandi.

  ../../../../.venv-render/bin/python settimana.py stato
      Solo controllo: in che settimana siamo, quali risultati / annunci / storie
      sono già usciti o in coda (feed Instagram + coda seles-media + registro),
      cosa manca, cosa è andato storto. Non genera e non pubblica niente.

  ../../../../.venv-render/bin/python settimana.py prepara [--oggi AAAA-MM-GG]
      Fa prima il controllo di 'stato', poi prepara SOLO quello che manca.
      Legge Tuttocampo per Calcio a 5, Calcio a 11, Under 17, Under 15 e Juniores C5 (Under 19);
      scarica gli stemmi che mancano; genera e renderizza
        · RISULTATI della settimana (post 4:5, partite degli ultimi 8 giorni)
        · MATCH della settimana     (post 4:5, partite dei prossimi 8 giorni)
        · una STORIA match day per ogni partita in arrivo
      Scrive tutto in settimana/<data>/ (html, jpg, didascalie, piano.json)
      e stampa un riepilogo da mostrare a Lorenzo. Non pubblica niente.

  ../../../../.venv-render/bin/python settimana.py vai [--data AAAA-MM-GG]
      Esegue il piano preparato (l'ultimo, o quello della data indicata), dopo
      aver ricontrollato che nel frattempo non sia già uscito niente:
        · pubblica SUBITO i risultati su Instagram + Facebook
        · mette in coda le partite per DOMANI alle 9:00 (IG + FB); subito se si gioca già domani
        · mette in coda le storie (Instagram + Facebook) alle 9:00 del giorno di ogni partita
          (stesso giorno: la partita che inizia prima esce 30' prima)
      Si lancia solo dopo il "vai" di Lorenzo.
"""
import sys, re, json, math, shutil, asyncio, argparse, subprocess, pathlib, datetime as dt, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
WS = HERE.parents[3]                                     # Claude-Workspace (kit-social → SELES → Clienti → beFNL)
PY = WS / ".venv-render/bin/python"
BUILD, SHEET = WS / "_tools/build.py", WS / "_tools/sheet.py"
MEDIA_REPO = HERE.parent / "seles-media"
OUT_ROOT = HERE / "settimana"
AVV = HERE / "assets/loghi/avversari"
TC = "https://www.tuttocampo.it/Calabria"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# ---------------------------------------------------------------- squadre
SQUADRE = [
    dict(key="C5", nome="Calcio a 5", comp="Serie C2 Girone B", base=f"{TC}/CalcioA5SerieC2/GironeBSerieC2",
         acc="#1898D8", acc_cls="a-c5", casa="Don Milani", casa_bg="don-milani.jpg", fuori_bg="futsal-arena.png",
         storia="epic", piede="Calcio a 5", glow="rgba(24,152,216,.30)", tag="#CalcioA5 #SerieC2"),
    dict(key="C11", nome="Calcio a 11", comp="Prima Categoria Girone C", base=f"{TC}/PrimaCategoria/GironeC",
         acc="#FFFFFF", acc_cls="a-c11", casa="Stadio Comunale", casa_bg="stadio-comunale.jpg", fuori_bg="stadio-notte-flux.png",
         storia="epic", piede="Calcio a 11", glow="rgba(24,152,216,.30)", tag="#PrimaCategoria #CalcioCalabrese"),
    dict(key="U17", nome="Under 17 Regionale", comp="Girone D", base=f"{TC}/AllieviRegionaliU17/GironeDRegionali",
         acc="#FF8C00", acc_cls="a-scuola", casa="Stadio Comunale", casa_bg="stadio-comunale.jpg", fuori_bg="stadio-notte-flux.png",
         storia="epic", piede="Settore giovanile", glow="rgba(255,140,0,.30)", tag="#Under17"),
    dict(key="U15", nome="Under 15 Regionale", comp="Girone D", base=f"{TC}/GiovanissimiRegionaliU15/GironeDRegionali",
         acc="#FFB347", acc_cls="a-scuola", casa="Stadio Comunale", casa_bg="stadio-comunale.jpg", fuori_bg="stadio-notte-flux.png",
         storia="epic", piede="Settore giovanile", glow="rgba(255,140,0,.30)", tag="#Under15"),
    # Juniores = calcio a 5 (audio della società, 30/10/2026); in casa domenica 17:30 al Don Milani
    dict(key="U19", nome="Juniores Calcio a 5", comp="Girone C", base=f"{TC}/CalcioA5Giovanili/GironeCJuniores",
         acc="#7CD3F7", acc_cls="a-c5", casa="Don Milani", casa_bg="don-milani.jpg", fuori_bg="futsal-arena.png",
         storia="epic", piede="Juniores Calcio a 5", glow="rgba(24,152,216,.30)", tag="#Juniores"),
]
CAMPI_ALIAS = {"saibo": "Stadio Comunale"}               # Lorenzo: mai "Saibo", sempre Stadio Comunale
NOMI_ALIAS = {
    "Polisportiva Leukos Lazzaro": "Leukos Lazzaro",
    "Polistena Calcio A 5": "Polistena Calcio a 5",
    "Città Di Guardavalle 1975": "Città di Guardavalle 1975",
    "Taurianova 1995": "Taurianova",
    "Palmese 1912": "Palmese",
    "Reggina 1914": "Reggina",
}
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
MESI_N = {m: i + 1 for i, m in enumerate(MESI)}
# Veste delle grafiche: "notte" = linea glow up 11/2026 (notte.py), "v2" = locandine a pannelli di ottobre.
STILE = "notte"
# Foto vera in testa al post dei risultati (relativa a kit-social), se Lorenzo l'ha mandata; None = solo grafica.
FOTO_SETTIMANA = None


def nome(n):
    n = NOMI_ALIAS.get(n, n)
    return re.sub(r"\bDi\b", "di", re.sub(r"\bA 5\b", "a 5", n))


def a_capo(n):
    """Spezza un nome lungo su due righe, nel punto più bilanciato."""
    w = n.split()
    if len(n) <= 10 or len(w) < 2:
        return n
    best = min(range(1, len(w)), key=lambda i: abs(len(" ".join(w[:i])) - len(" ".join(w[i:]))))
    return " ".join(w[:best]) + "<br>" + " ".join(w[best:])


def campo(sq, m):
    if m["seles_casa"]:
        return sq["casa"]
    s = (m.get("stadio") or "").split(",")[0].strip()
    return CAMPI_ALIAS.get(s.lower(), s) or "In trasferta"


def g_ita(d, corto=False):
    return (f"{GIORNI[d.weekday()][:3]} {d.day}.{d.month:02d}" if corto
            else f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}")


# ---------------------------------------------------------------- Tuttocampo
async def leggi_giornata(pg, sq, g, anno):
    await pg.goto(f"{sq['base']}/Giornata{g}", wait_until="networkidle", timeout=60000)
    await pg.wait_for_timeout(1000)
    r = await pg.evaluate("""() => {
        const tr = [...document.querySelectorAll('tr')].find(r => /Seles Gioiosa/.test(r.innerText) && /Partita/.test(r.innerHTML));
        if (!tr) return null;
        const a = [...tr.querySelectorAll('a')];
        const sq = []; for (const x of a) if (/\\/Squadra\\//.test(x.href)) {
            const t = x.textContent.trim(); const e = sq.find(s => s.href === x.href);
            if (e) { if (t.length > e.nome.length) e.nome = t } else sq.push({href: x.href, nome: t}); }
        return {riga: tr.innerText.replace(/\\s+/g, ' ').trim(), squadre: sq,
                partita: (a.find(x => /\\/Partita\\//.test(x.href)) || {}).href};
    }""")
    if not r or len(r["squadre"]) < 2:
        return None                                       # la Seles riposa
    (h, a) = r["squadre"][:2]
    hid, aid = (re.search(r"/Squadra/[^/]+/(\d+)/", x["href"]).group(1) for x in (h, a))
    mid = r["riga"].split(h["nome"], 1)[-1].split(a["nome"], 1)[0]
    gol = re.findall(r"\b\d{1,2}\b", mid)
    m = dict(squadra=sq["key"], giornata=g, casa=h["nome"], casa_id=hid, ospite=a["nome"], ospite_id=aid,
             gol=[int(gol[0]), int(gol[1])] if len(gol) >= 2 else None, seles_casa="Seles" in h["nome"])
    await pg.goto(r["partita"], wait_until="networkidle", timeout=60000)
    await pg.wait_for_timeout(1200)
    t = await pg.inner_text("body")
    q = re.search(r"\d+° Giornata\s+\w+\.?\s+(\d{1,2})\s+(\w+)\s*,\s*ore\s+(\d{1,2}):(\d{2})", t)
    if not q:
        return None
    m["quando"] = dt.datetime(anno, MESI_N[q.group(2).lower()], int(q.group(1)), int(q.group(3)), int(q.group(4))).isoformat()
    s = re.search(r"STADIO:\s*([^\n]+)", t)
    m["stadio"] = s.group(1).strip().strip(",").strip() if s else ""
    return m


PREPARA_PAGINA = None      # risultati_auto.py su GitHub: fa passare Tuttocampo dal ponte Cloudflare


async def leggi_tutto(oggi):
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(locale="it-IT", user_agent=UA, viewport={"width": 1280, "height": 2000})
        if PREPARA_PAGINA:
            await PREPARA_PAGINA(pg)
        for sq in SQUADRE:
            await pg.goto(f"{sq['base']}/Risultati", wait_until="networkidle", timeout=60000)
            g0 = re.search(r"(\d+)° Giornata", await pg.inner_text("body"))
            g0 = int(g0.group(1)) if g0 else 1
            for g in range(max(1, g0 - 1), g0 + 3):
                m = await leggi_giornata(pg, sq, g, oggi.year)
                if m:
                    out.append(m)
        await b.close()
    return out


def scegli(partite, oggi):
    """Ultimo risultato degli ultimi 8 giorni e prima partita dei prossimi 8, per squadra."""
    ris, prox = {}, {}
    for m in partite:
        d = dt.datetime.fromisoformat(m["quando"])
        if m["gol"] and oggi - dt.timedelta(days=8) <= d <= oggi + dt.timedelta(hours=23):
            if m["squadra"] not in ris or d > dt.datetime.fromisoformat(ris[m["squadra"]]["quando"]):
                ris[m["squadra"]] = m
        elif not m["gol"] and d >= oggi.replace(hour=0, minute=0) and d <= oggi + dt.timedelta(days=8):
            if m["squadra"] not in prox or d < dt.datetime.fromisoformat(prox[m["squadra"]]["quando"]):
                prox[m["squadra"]] = m
    k = lambda m: m["quando"]
    return sorted(ris.values(), key=k), sorted(prox.values(), key=k)


# ---------------------------------------------------------------- stemmi
def riempi_interno(im):
    """Le zone trasparenti chiuse dentro lo stemma diventano bianche (su Tuttocampo si vedono su bianco:
    Audax Locri, 19/10/2026). Resta trasparente solo l'esterno collegato ai bordi."""
    from PIL import Image, ImageDraw, ImageFilter
    a = im.split()[3]
    fuori = a.point(lambda v: 255 if v < 128 else 0).convert("L")
    W, H = fuori.size
    for xy in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
        if fuori.getpixel(xy) == 255:
            ImageDraw.floodfill(fuori, xy, 128)
    fuori = fuori.point(lambda v: 255 if v == 128 else 0).filter(ImageFilter.MaxFilter(5))
    out = Image.new("RGBA", im.size, (255, 255, 255, 255)); out.alpha_composite(im)
    out.putalpha(Image.composite(a, Image.new("L", im.size, 255), fuori))
    return out


def stemma(tid, nome_sq):
    """Restituisce (percorso relativo, altezza bilanciata, scuro?) dello stemma; lo scarica se manca."""
    from PIL import Image
    if "Seles" in nome_sq:
        return "assets/loghi/seles-trim.png", 1.0, False
    trim = AVV / f"tc-{tid}-trim.png"
    if not trim.exists():
        raw = AVV / f"tc-{tid}.png"
        req = urllib.request.Request(f"https://b2-content.tuttocampo.it/Teams/Original/{tid}.png?v=3", headers={"User-Agent": UA})
        raw.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        im = Image.open(raw).convert("RGBA")
        if im.width < 600:
            im = im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
        im = riempi_interno(im)
        bb = im.split()[3].point(lambda v: 255 if v > 12 else 0).getbbox()
        (im.crop(bb) if bb else im).save(trim)
        print(f"  ↓ nuovo stemma: {nome_sq} → {trim.name}")
    im = Image.open(trim).convert("RGBA")
    r = im.width / im.height
    px = [p for p in im.resize((64, 64)).getdata() if p[3] > 200]
    lum = sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px) / max(1, len(px))
    # stesso peso visivo dello scudo Seles (rapporto 0.64): altezza ∝ √(0.64 / rapporto)
    return f"assets/loghi/avversari/{trim.name}", min(1.0, math.sqrt(0.64 / r)), lum < 75


# ---------------------------------------------------------------- html
TOP = '''    <div class="top">
      <div class="lock"><img src="R/assets/loghi/seles.png" alt=""><div><div class="w">SELES</div><div class="s">Gioiosa Ionica</div></div></div>
      <div class="right"><div class="lab">Società affiliata<br>Empoli FC Academy</div><img src="R/assets/loghi/empoli-academy.png" alt=""></div>
    </div>'''
DARK = "filter:drop-shadow(0 0 2px rgba(255,255,255,.9)) drop-shadow(0 18px 40px rgba(0,0,0,.7))"


def img(src, h, dark):
    return f'<img src="R/{src}" alt="" style="--h:{h}px;{DARK if dark else ""}">'


def squadra_di(m):
    return next(s for s in SQUADRE if s["key"] == m["squadra"])


def sfondo(sq, m):
    bg = sq["casa_bg"] if m["seles_casa"] else sq["fuori_bg"]
    return bg, bg in ("don-milani.jpg", "stadio-comunale.jpg")


def pannello(m, risultato):
    sq = squadra_di(m)
    d = dt.datetime.fromisoformat(m["quando"])
    bg, _ = sfondo(sq, m)
    def lato(n, tid, away):
        src, k, dark = stemma(tid, n)
        return (f'<div class="side{" away" if away else ""}"><div class="cb">{img(src, round(104 * k), dark)}</div>'
                f'<div class="n">{a_capo(nome(n))}</div></div>')
    mid = (f'<div class="sc">{m["gol"][0]}<i>–</i>{m["gol"][1]}</div>' if risultato else
           f'<div class="when"><div class="d">{g_ita(d)}</div><div class="t">{d:%H:%M}</div></div>')
    dove = campo(sq, m) + (", Gioiosa Ionica" if m["seles_casa"] and not risultato else "")
    r = f"{g_ita(d, True)}, {dove if m['seles_casa'] else 'in trasferta'}" if risultato else \
        (dove if m["seles_casa"] else f"In trasferta, {dove}" if dove != "In trasferta" else dove)
    return f'''    <div class="pn" style="--pacc:{sq["acc"]};--pos:50% 58%">
      <div class="bg"><img src="R/assets/sfondi/{bg}" alt=""><div class="tone"></div><div class="tint"></div></div>
      <div class="in">
        <div class="lab"><div class="l"><b>{sq["nome"]}</b>&nbsp; {sq["comp"]}, {m["giornata"]}ª giornata</div><div class="r">{r}</div></div>
        <div class="row">{lato(m["casa"], m["casa_id"], False)}{mid}{lato(m["ospite"], m["ospite_id"], True)}</div>
      </div>
    </div>
'''


def riepilogo(nome_slide, partite, risultato):
    d0, d1 = (dt.datetime.fromisoformat(partite[i]["quando"]) for i in (0, -1))
    g1 = "1°" if d1.day == 1 else str(d1.day)
    m0 = f" {MESI[d0.month - 1]}" if d0.month != d1.month else ""
    periodo = f"dal {d0.day}{m0} al {g1} {MESI[d1.month - 1]}" if d0.date() != d1.date() else f"{g1 if d0.day == 1 else d0.day} {MESI[d0.month - 1]}"
    titolo = "Risultati" if risultato else "Match"
    return f'''
<div class="slide ig t-dark tex recap compact{" cinque" if len(partite) > 4 else ""} a-c5" data-name="{nome_slide}">
  <div class="glow" style="position:absolute;inset:0;background:radial-gradient(700px 420px at 20% 10%,rgba(24,152,216,.22),transparent 70%)"></div>
  <div class="frame">
{TOP}
    <div class="kicker" style="margin-top:34px"><b>Prima squadra e giovanili</b>&nbsp; {periodo}</div>
    <div class="h1" style="font-size:{84 if len(partite) > 4 else 98}px;margin-top:6px;line-height:.84">{titolo}<em>della settimana</em></div>
  </div>
  <div class="panels">
{"".join(pannello(m, risultato) for m in partite)}  </div>
  <div class="foot"><div class="h">@asdseles</div><div class="r">Gioco con l’altro e non contro l’altro</div></div>
</div>
'''


def storia(nome_slide, m):
    sq = squadra_di(m)
    d = dt.datetime.fromisoformat(m["quando"])
    bg, day = sfondo(sq, m)
    (cs, ck, cd), (os_, ok, od) = stemma(m["casa_id"], m["casa"]), stemma(m["ospite_id"], m["ospite"])
    kicker = (f"<b>{sq['comp'].replace(' Girone', '</b>&nbsp; Girone')}, {m['giornata']}ª giornata" if sq["key"] == "C11"   # nome+campionato non sta su una riga
              else f"<b>{sq['nome']}</b>&nbsp; {sq['comp']}, {m['giornata']}ª giornata")
    dove = campo(sq, m)
    cella = (f"{dove}<br>Gioiosa Ionica" if m["seles_casa"] else
             "In trasferta" if dove == "In trasferta" else f"{dove}<br>In trasferta")
    tone = '<div class="tone"></div>' if day else ""
    barra = f'''  <div class="bar">
    <div class="cells">
      <div class="c"><div class="k" style="visibility:hidden">·</div><div class="v">Oggi</div></div>
      <div class="c"><div class="k">Calcio d’inizio</div><div class="v">{d:%H:%M}</div></div>
      <div class="c"><div class="k" style="visibility:hidden">·</div><div class="v"><small>{cella}</small></div></div>
    </div>
    <div class="foot"><div class="h">@asdseles</div><div class="r">{sq["piede"]}</div></div>
  </div>
  <div class="safe"></div>'''
    if sq["storia"] == "clash":
        def riga(src, n, dark):
            return f'<div class="row"><img src="R/{src}" alt="" style="object-fit:contain;{DARK if dark else ""}"><div class="tm">{a_capo(nome(n))}</div></div>'
        return f'''
<div class="slide t-dark clash{" day" if day else ""} story {sq["acc_cls"]} ph-full" data-name="{nome_slide}">
  <div class="photo"><img src="R/assets/sfondi/{bg}" alt="">{tone}<div class="tint"></div></div>
  <div class="glow"></div>
  <div class="frame">
{TOP}
    <div class="kicker" style="margin-top:56px">{sq["comp"]}, {m["giornata"]}ª giornata</div>
    <div class="h1" style="font-size:150px;margin-top:10px;line-height:.84">Match day</div>
    <div class="grow"></div>
    {riga(cs, m["casa"], cd)}
    <div class="sep"><i></i><b>VS</b><i></i></div>
    {riga(os_, m["ospite"], od)}
    <div class="grow"></div>
  </div>
{barra}
</div>
'''
    gl = sq["glow"]
    away_gl = "rgba(200,200,200,.18)"
    gl_l, gl_r = (gl, away_gl) if m["seles_casa"] else (away_gl, gl)
    return f'''
<div class="slide t-dark epic story{" day" if day else ""} {sq["acc_cls"]} ph-full" data-name="{nome_slide}">
  <div class="photo"><img src="R/assets/sfondi/{bg}" alt="">{tone}<div class="tint"></div></div>
  <div class="glow" style="background:radial-gradient(560px 560px at 4% 50%,{gl_l},transparent 68%),radial-gradient(560px 560px at 96% 50%,{gl_r},transparent 68%)"></div>
  <div class="frame">
{TOP}
    <div class="kicker" style="margin-top:56px">{kicker}</div>
    <div class="h1" style="font-size:184px;margin-top:10px;line-height:.84">Match<em>day</em></div>
    <div class="grow"></div>
    <div class="duel">
      <div class="side"><div class="cr">{img(cs, round(320 * ck), cd)}</div><div class="nm">{a_capo(nome(m["casa"]))}</div></div>
      <div class="mid"><div class="vsbig">VS</div></div>
      <div class="side"><div class="cr">{img(os_, round(320 * ok), od)}</div><div class="nm">{a_capo(nome(m["ospite"]))}</div></div>
    </div>
    <div class="grow"></div>
  </div>
{barra}
</div>
'''


# ---------------------------------------------------------------- didascalie
HASHTAG = "#SelesGioiosa #CalcioA5 #PrimaCategoria #SettoreGiovanile #GioiosaIonica #EmpoliAcademy @empoli_fc_official"


def didascalia(partite, risultato):
    righe = ["I risultati della settimana" if risultato else "I match della settimana", ""]
    for m in partite:
        sq = squadra_di(m)
        d = dt.datetime.fromisoformat(m["quando"])
        righe.append(f"{sq['nome']}, {sq['comp']}")
        if risultato:
            righe.append(f"{nome(m['casa'])} – {nome(m['ospite'])} {m['gol'][0]}-{m['gol'][1]}")
        else:
            righe.append(f"{nome(m['casa'])} – {nome(m['ospite'])}")
            righe.append(f"{g_ita(d)}, ore {d:%H:%M}, {campo(sq, m)}")
        righe.append("")
    righe.append(HASHTAG)
    return "\n".join(righe)


# ---------------------------------------------------------------- stato: cosa è già uscito
REGISTRO = HERE / "registro.jsonl"          # pubblicazioni dirette (publish.py e 'vai'): le storie l'API le mostra solo 24 ore
GENERICHE = {"calcio", "futsal", "sporting", "academy", "gioiosa", "seles", "citta", "real", "atletico",
             "polisportiva", "associazione", "oratorio", "sport", "football", "club", "nuova"}


def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def cita(testo, n):
    """Il testo nomina la squadra n? Nome completo, oppure la sua parola più caratteristica."""
    t = norm(testo)
    if norm(nome(n)) in t or norm(n) in t:
        return True
    w = [x for x in re.findall(r"[a-z]{5,}", norm(nome(n))) if x not in GENERICHE]
    return bool(w) and max(w, key=len) in t


def avversario(m):
    return m["ospite"] if m["seles_casa"] else m["casa"]


def locale(ts):
    """'2026-10-06T07:01:57+0000' o '…+02:00' → datetime locale senza fuso."""
    try:
        d = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def leggi_stato():
    """Feed Instagram (verità, anche i post fatti a mano), coda/in-corso/pubblicati di seles-media, registro locale."""
    st = {"feed": [], "coda": [], "pubblicati": [], "registro": [], "avvisi": []}
    sys.path.insert(0, str(HERE))
    try:
        import publish
        _, ig = publish.ids()
        r = publish.api("GET", f"{ig}/media", soft=True, fields="caption,timestamp,permalink", limit=40) or {}
        st["feed"] = [{"quando": locale(x["timestamp"]), "testo": x.get("caption") or "", "link": x.get("permalink")}
                      for x in r.get("data", [])]
        if not r:
            st["avvisi"].append("non riesco a leggere il feed Instagram (token?): la verifica dei post è incompleta")
    except SystemExit:
        st["avvisi"].append("token Meta mancante: non posso verificare cosa è già sul feed")
    p = subprocess.run(["git", "-C", str(MEDIA_REPO), "pull", "--rebase", "-q"], capture_output=True)
    if p.returncode:
        st["avvisi"].append("git pull di seles-media fallito: la coda potrebbe non essere aggiornata")
    for cart, chiave in (("coda", "coda"), ("in-corso", "coda"), ("pubblicati", "pubblicati")):
        for f in sorted((MEDIA_REPO / cart).glob("*.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                st[chiave].append({**j, "file": f.name, "cartella": cart, "q": locale(j["quando"])})
            except Exception:
                st["avvisi"].append(f"non leggo {cart}/{f.name}")
    if REGISTRO.exists():
        for riga in REGISTRO.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                j = json.loads(riga); j["q"] = locale(j["quando"]); st["registro"].append(j)
    return st


def e_storia(x):
    return any("story" in d for d in x.get("dove", []))


def storie_note(st):
    """Tutte le storie pubblicate o in coda: (data, testo per riconoscere la squadra, stato, voce)."""
    out = []
    for x in st["coda"]:
        if e_storia(x):
            out.append((x, "in coda"))
    for x in st["pubblicati"] + st["registro"]:
        if e_storia(x):
            ok = not any(str(v).startswith("ERRORE") for v in (x.get("esiti") or {}).values())
            out.append((x, "pubblicata" if ok else "errore"))
    return out


def storia_di(m, st, partite):
    """La storia match day di m, se è pubblicata o in coda (la cerca per giorno partita e squadra)."""
    d = dt.datetime.fromisoformat(m["quando"])
    stessa_data = [p for p in partite if p["quando"][:10] == m["quando"][:10]]
    trovate = []
    for x, stato in storie_note(st):
        if x["q"].date() != d.date():
            continue
        meta = x.get("partita") or {}
        chiave = (meta.get("squadra") or "").lower()
        testo = norm(" ".join([x.get("file", ""), x.get("img", "")] + list(x.get("immagini", []))))
        if chiave == m["squadra"].lower() or re.search(rf"(^|[-_/]){m['squadra'].lower()}([-_.]|$)", testo) \
                or (not chiave and len(stessa_data) == 1):
            trovate.append((x, stato))
    return trovate


def annuncio_di(m, st):
    """Post del feed (o in coda) che annuncia m: nomina l'avversario e il giorno, uscito prima del fischio."""
    d = dt.datetime.fromisoformat(m["quando"])
    giorno = norm(f"{d.day} {MESI[d.month - 1]}")
    for x in st["feed"]:
        if d - dt.timedelta(days=9) <= x["quando"] <= d and cita(x["testo"], avversario(m)) \
                and (giorno in norm(x["testo"]) or x["quando"].date() == d.date()):
            return ("pubblicato", x["quando"], x["link"])
    for x in st["coda"]:
        if not e_storia(x) and x["q"] <= d and cita(x.get("didascalia", ""), avversario(m)) and giorno in norm(x.get("didascalia", "")):
            return ("in coda", x["q"], x["file"])
    return None


def risultato_di(m, st):
    """Post del feed (o in coda) che riporta il risultato di m: avversario + punteggio, dopo il fischio."""
    d = dt.datetime.fromisoformat(m["quando"])
    a, b = m["gol"]
    pat = re.compile(rf"(?<!\d)({a}\s*[–\-:]\s*{b}|{b}\s*[–\-:]\s*{a})(?!\d)")
    for x in st["feed"]:
        if x["quando"] >= d and cita(x["testo"], avversario(m)) and pat.search(x["testo"]):
            return ("pubblicato", x["quando"], x["link"])
    for x in st["coda"]:
        t = x.get("didascalia", "")
        if not e_storia(x) and x["q"] >= d and cita(t, avversario(m)) and pat.search(t):
            return ("in coda", x["q"], x["file"])
    return None


def quando_txt(q):
    return f"{g_ita(q, True)} {q:%H:%M}"


def controlla(oggi, tutte, st):
    """Confronta Tuttocampo con quello che è uscito / è in coda. Stampa la situazione e restituisce cosa manca."""
    ris, prox = scegli(tutte, oggi)
    lun = (oggi - dt.timedelta(days=oggi.weekday())).date()
    dom = lun + dt.timedelta(days=6)
    print(f"\nSETTIMANA: lun {lun.day} – dom {dom.day} {MESI[dom.month - 1]}  (oggi {g_ita(oggi, True)} {oggi:%H:%M})")
    problemi = list(st["avvisi"])
    manca = {"risultati": [], "partite": [], "storie": []}

    def riga(m, x):
        sq = squadra_di(m); d = dt.datetime.fromisoformat(m["quando"])
        return f"{g_ita(d, True):10} {sq['key']:4} {nome(m['casa'])} {x} {nome(m['ospite'])}"

    print("\nRISULTATI (ultimi 8 giorni):" if ris else "\nRISULTATI: nessuna partita giocata negli ultimi 8 giorni")
    for m in ris:
        c = risultato_di(m, st)
        print(f"  {'✓' if c else '✗'} {riga(m, f'{m['gol'][0]}–{m['gol'][1]}')}  · "
              + (f"{c[0]} {quando_txt(c[1])}" if c else "NON ancora pubblicato"))
        if not c:
            manca["risultati"].append(m)

    print("\nPARTITE IN ARRIVO (prossimi 8 giorni):" if prox else "\nPARTITE IN ARRIVO: nessuna nei prossimi 8 giorni")
    for m in prox:
        d = dt.datetime.fromisoformat(m["quando"])
        a = annuncio_di(m, st)
        s = storia_di(m, st, prox)
        sa = (f"annuncio {a[0]} {quando_txt(a[1])}" if a else "annuncio MANCA")
        ok_st = [x for x, k in s if k != "errore"]
        ss = (f"storia {s[0][1]} {quando_txt(s[0][0]['q'])}" if ok_st else "storia MANCA")
        print(f"  {'✓' if a and ok_st else '✗'} {riga(m, f'{d:%H:%M}')}  · {sa} · {ss}")
        if not a:
            manca["partite"].append(m)
        if not ok_st:
            manca["storie"].append(m)
        for x, k in s:
            meta = x.get("partita") or {}
            if meta.get("quando") and meta["quando"] != m["quando"]:
                problemi.append(f"{squadra_di(m)['key']} {g_ita(d, True)}: la storia in coda ({x['file']}) dice "
                                f"{meta['quando'][11:16]}, Tuttocampo ora {d:%H:%M} → va rifatta")
            if len(ok_st) > 1:
                problemi.append(f"{squadra_di(m)['key']} {g_ita(d, True)}: {len(ok_st)} storie per la stessa partita "
                                f"({', '.join(x.get('file') or x.get('img', '?') for x in ok_st)})")
                break

    # match day mancati: partite già giocate (ultimi 8 giorni) senza storia né post il giorno stesso
    for m in ris:
        d = dt.datetime.fromisoformat(m["quando"])
        if not storia_di(m, st, ris) and not any(x["quando"].date() == d.date() and x["quando"] <= d and cita(x["testo"], avversario(m)) for x in st["feed"]):
            problemi.append(f"{squadra_di(m)['key']} {g_ita(d, True)} vs {nome(avversario(m))}: non trovo il match day "
                            "(né storia registrata né post quel giorno) — se è stata fatta a mano dal telefono, ignora")

    # coda ferma o andata in errore
    adesso = dt.datetime.now()
    for x in st["coda"]:
        if x["q"] < adesso - dt.timedelta(minutes=20):
            problemi.append(f"in {x['cartella']}/ c'è {x['file']} previsto {quando_txt(x['q'])}: la sveglia non l'ha pubblicato")
    for x in st["pubblicati"]:
        err = [k for k, v in (x.get("esiti") or {}).items() if str(v).startswith("ERRORE")]
        if err and x["q"] > adesso - dt.timedelta(days=10):
            problemi.append(f"{x['file']} ({quando_txt(x['q'])}): errore su {', '.join(err)}")

    futuri = sorted((x for x in st["coda"] if x["q"] >= adesso - dt.timedelta(minutes=20)), key=lambda x: x["q"])
    print("\nIN CODA:" if futuri else "\nIN CODA: niente")
    for x in futuri:
        print(f"  ⏳ {quando_txt(x['q'])} · {'storia' if e_storia(x) else 'post'} · {x['file']}")

    if problemi:
        print("\n⚠ DA GUARDARE:")
        for p_ in problemi:
            print("  ·", p_)
    return manca


# ---------------------------------------------------------------- comandi
def prepara(oggi, ignora_stato=False):
    import notte                                          # veste «Notte» (import qui: notte importa settimana)
    print(f"Leggo Tuttocampo (oggi = {oggi:%d/%m/%Y})…")
    tutte = asyncio.run(leggi_tutto(oggi))
    if ignora_stato:
        ris, prox = scegli(tutte, oggi)
        manca = {"risultati": ris, "partite": prox, "storie": prox}
    else:
        print("Controllo cosa è già uscito e cosa è in coda…")
        manca = controlla(oggi, tutte, leggi_stato())
    ris, prox, mds = manca["risultati"], manca["partite"], manca["storie"]
    cart = OUT_ROOT / f"{oggi:%Y-%m-%d}"
    if cart.exists() and (cart / "piano.json").exists():
        vecchio = json.loads((cart / "piano.json").read_text(encoding="utf-8"))
        if vecchio.get("eseguito"):
            cart = OUT_ROOT / f"{oggi:%Y-%m-%d-%H%M}"              # non sovrascrivere un piano già eseguito
    if not (ris or prox or mds):
        if (cart / "piano.json").exists():                 # un piano rimasto lì non deve poter partire per sbaglio
            (cart / "piano.json").write_text(json.dumps({"data": f"{oggi:%Y-%m-%d}", "eseguito": "niente da fare (tutto già coperto)"},
                                                        ensure_ascii=False), encoding="utf-8")
        print("\n✓ NIENTE DA FARE: tutto quello che serve è già pubblicato o in coda.")
        return
    shutil.rmtree(cart / "out", ignore_errors=True)
    (cart / "out").mkdir(parents=True, exist_ok=True)
    piano = {"data": f"{oggi:%Y-%m-%d}", "preparato": dt.datetime.now().isoformat(timespec="minutes"),
             "risultati": None, "partite": None, "storie": []}
    html = ""
    if ris:
        n = f"risultati-{oggi:%Y%m%d}"
        html += notte.riepilogo(n, ris, True, foto=FOTO_SETTIMANA) if STILE == "notte" else riepilogo(n, ris, True)
        (cart / f"{n}.txt").write_text(didascalia(ris, True), encoding="utf-8")
        piano["risultati"] = {"img": f"out/{n}.jpg", "caption": f"{n}.txt", "match": ris}
    if prox:
        n = f"partite-{oggi:%Y%m%d}"
        html += notte.riepilogo(n, prox, False) if STILE == "notte" else riepilogo(n, prox, False)
        (cart / f"{n}.txt").write_text(didascalia(prox, False), encoding="utf-8")
        primo = dt.datetime.fromisoformat(prox[0]["quando"]).date()
        piano["partite"] = {"img": f"out/{n}.jpg", "caption": f"{n}.txt", "match": prox,
                            "subito": primo <= (oggi + dt.timedelta(days=1)).date()}   # partita domani: domani alle 9 è tardi
    for m in mds:
        d = dt.datetime.fromisoformat(m["quando"])
        n = f"storia-{m['squadra'].lower()}-{d:%Y%m%d}"
        html += notte.storia(n, m) if STILE == "notte" else storia(n, m)
        piano["storie"].append({"img": f"out/{n}.jpg", "partita": m["quando"], "squadra": m["squadra"], "match": m})
    doc = ('<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>SELES — settimana</title>'
           f'<link rel="stylesheet" href="../../{"notte.css" if STILE == "notte" else "brand.css"}"></head><body>' + html + "</body></html>")
    (cart / "settimana.html").write_text(doc.replace('src="R/', 'src="../../'), encoding="utf-8")
    subprocess.run([str(PY), str(BUILD), str(cart / "settimana.html"), str(cart / "out"), "1080", "1920", "1", "92"],
                   check=True, stdout=subprocess.DEVNULL)
    storie = cart / "out-storie"
    shutil.rmtree(storie, ignore_errors=True); storie.mkdir()
    for s in piano["storie"]:
        shutil.copy2(cart / s["img"], storie)
    (cart / "anteprima-storie.jpg").unlink(missing_ok=True)
    if piano["storie"]:
        subprocess.run([str(PY), str(SHEET), str(storie), str(cart / "anteprima-storie.jpg"), "4", "420"],
                       check=True, stdout=subprocess.DEVNULL)
    shutil.rmtree(storie, ignore_errors=True)
    (cart / "piano.json").write_text(json.dumps({**piano, "partite_lette": tutte}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✓ preparato SOLO quello che manca, in {cart.relative_to(HERE)}/")
    print("\nANTEPRIME:")
    for k in ("risultati", "partite"):
        if piano[k]:
            print(f"  {(cart / piano[k]['img']).relative_to(HERE)}")
    if piano["storie"]:
        print(f"  {(cart / 'anteprima-storie.jpg').relative_to(HERE)}  ({len(piano['storie'])} storie)")
    azioni = []
    if piano["risultati"]:
        azioni.append(f"risultati subito ({len(ris)})")
    if piano["partite"]:
        azioni.append(f"partite {'subito' if piano['partite']['subito'] else 'domani 9:00'} ({len(prox)})")
    if piano["storie"]:
        azioni.append(f"{len(mds)} storie alle 9:00 del giorno partita")
    print("\nCon 'vai': " + " · ".join(azioni) + ".")


def orari_storie(storie):
    """9:00 del giorno partita; se più partite lo stesso giorno, scaglionate di 30' in ordine di calcio d'inizio."""
    per_giorno = {}
    for s in sorted(storie, key=lambda s: s["partita"]):
        per_giorno.setdefault(s["partita"][:10], []).append(s)
    for g, el in per_giorno.items():
        for i, s in enumerate(el):
            t = dt.datetime.fromisoformat(f"{g}T09:00:00") - dt.timedelta(minutes=30 * (len(el) - 1 - i))
            s["quando"] = max(t, dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=1))
    return storie


def registra(dove, img, esiti):
    with REGISTRO.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"quando": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "dove": dove,
                            "img": pathlib.Path(img).name, "esiti": esiti}, ensure_ascii=False) + "\n")


def vai(data):
    cart = OUT_ROOT / data if data else max((p for p in OUT_ROOT.iterdir() if (p / "piano.json").exists()),
                                            key=lambda p: (p / "piano.json").stat().st_mtime)
    piano = json.loads((cart / "piano.json").read_text(encoding="utf-8"))
    if piano.get("eseguito"):
        print(f"✗ il piano del {piano['data']} è già stato eseguito il {piano['eseguito']}: niente da fare.")
        return
    if not piano.get("preparato") or dt.datetime.now() - dt.datetime.fromisoformat(piano["preparato"]) > dt.timedelta(hours=24):
        print(f"✗ il piano in {cart.name}/ è vecchio (formato senza controllo o preparato da più di 24 ore): rilancia 'prepara'.")
        return
    # ricontrollo all'ultimo momento: nel frattempo qualcuno può aver pubblicato o messo in coda
    st = leggi_stato()
    for a in st["avvisi"]:
        print("⚠", a)
    if piano["risultati"] and "match" in piano["risultati"]:
        gia = [m for m in piano["risultati"]["match"] if risultato_di(m, st)]
        if len(gia) == len(piano["risultati"]["match"]):
            print("· risultati: già pubblicati nel frattempo, salto"); piano["risultati"] = None
        elif gia:
            print(f"✗ {len(gia)} risultati su {len(piano['risultati']['match'])} sono usciti nel frattempo: rilancia 'prepara'.")
            return
    if piano["partite"] and "match" in piano["partite"]:
        gia = [m for m in piano["partite"]["match"] if annuncio_di(m, st)]
        if len(gia) == len(piano["partite"]["match"]):
            print("· partite: già annunciate nel frattempo, salto"); piano["partite"] = None
        elif gia:
            print(f"✗ {len(gia)} partite su {len(piano['partite']['match'])} sono state annunciate nel frattempo: rilancia 'prepara'.")
            return
    tutte_storie = [s["match"] for s in piano["storie"] if "match" in s]
    resto = []
    for s in piano["storie"]:
        if "match" in s and storia_di(s["match"], st, tutte_storie):
            print(f"· storia {s['squadra']} {s['partita'][:10]}: già in coda o pubblicata, salto")
        else:
            resto.append(s)
    piano["storie"] = resto

    sys.path.insert(0, str(HERE))
    import publish
    tz = dt.datetime.now().astimezone().tzinfo
    adesso = [("risultati", piano["risultati"])] if piano["risultati"] else []
    coda = []
    if piano["partite"]:
        p = piano["partite"]
        if p.get("subito"):
            adesso.append(("partite", p))
        else:
            dom = (dt.datetime.now() + dt.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            coda.append((dom, ["ig", "fb"], cart / p["img"], (cart / p["caption"]).read_text(encoding="utf-8").strip(), None))
    for etichetta, p in adesso:
        cap = (cart / p["caption"]).read_text(encoding="utf-8").strip()
        url = publish.upload(str(cart / p["img"]))
        esiti = {"ig": publish.ig_publish([url], cap)}
        print(f"✓ {etichetta} · Instagram:", esiti["ig"])
        esiti["fb"] = publish.fb_publish([url], cap)
        print(f"✓ {etichetta} · Facebook:", esiti["fb"])
        registra(["ig", "fb"], cart / p["img"], esiti)
    for s in orari_storie(piano["storie"]):
        meta = {"squadra": s["squadra"], "quando": s["partita"]}
        if "match" in s:
            meta.update(casa=s["match"]["casa"], ospite=s["match"]["ospite"])
        coda.append((s["quando"], ["ig_story", "fb_story"], cart / s["img"], "", meta))
    segna = lambda: (cart / "piano.json").write_text(json.dumps({**piano, "eseguito": dt.datetime.now().isoformat(timespec="minutes")},
                                                                  ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    def sul_sito():  # calendario sul sito Mondo Seles: se fallisce, i social sono già a posto
        try:
            import sito
            sito.dopo_vai(piano)
        except (Exception, SystemExit) as e:
            print(f"⚠ sito non aggiornato: {e}  → rilancia: ../../../../.venv-render/bin/python sito.py partite --data {cart.name}")

    if not coda:
        segna(); sul_sito(); print("✓ fatto."); return
    subprocess.run(["git", "-C", str(MEDIA_REPO), "pull", "--rebase", "-q"], check=True)
    for quando, dove, img, cap, meta in coda:
        q = quando.replace(tzinfo=tz)
        nome_f = f"{q:%Y%m%d-%H%M}-{img.stem}"
        shutil.copy2(img, MEDIA_REPO / "media" / f"{nome_f}.jpg")
        post = {"quando": q.isoformat(), "dove": dove, "immagini": [f"media/{nome_f}.jpg"], "didascalia": cap}
        if meta:
            post["partita"] = meta                       # serve al controllo: squadra e orario della partita
        (MEDIA_REPO / "coda" / f"{nome_f}.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ in coda: {g_ita(q, True)} {q:%H:%M} · {'storia IG+FB' if 'ig_story' in dove else 'post IG+FB'} · {img.stem}")
    subprocess.run(["git", "-C", str(MEDIA_REPO), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(MEDIA_REPO), "commit", "-q", "-m", f"In coda: settimana del {piano['data']}"], check=True)
    subprocess.run(["git", "-C", str(MEDIA_REPO), "push", "-q"], check=True)
    segna()
    print("✓ coda aggiornata: la sveglia pubblica ogni post al minuto previsto.")
    sul_sito()


def stato(oggi):
    print(f"Leggo Tuttocampo (oggi = {oggi:%d/%m/%Y})…")
    tutte = asyncio.run(leggi_tutto(oggi))
    manca = controlla(oggi, tutte, leggi_stato())
    n = sum(len(v) for v in manca.values())
    print("\n✓ tutto coperto." if not n else
          f"\nMancano: {len(manca['risultati'])} risultati · {len(manca['partite'])} annunci · {len(manca['storie'])} storie → 'prepara'.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stato", "prepara", "vai"])
    ap.add_argument("--oggi", help="AAAA-MM-GG (solo per prove)")
    ap.add_argument("--data", help="cartella settimana/<data> da eseguire (default: l'ultima preparata)")
    ap.add_argument("--ignora-stato", action="store_true", help="prepara tutto come se non fosse uscito niente (prove)")
    a = ap.parse_args()
    oggi = dt.datetime.fromisoformat(a.oggi) if a.oggi else dt.datetime.now().replace(second=0, microsecond=0)
    if a.cmd == "prepara":
        prepara(oggi, a.ignora_stato)
    elif a.cmd == "stato":
        stato(oggi)
    else:
        vai(a.data)
