#!/usr/bin/env python3
"""
risultati_auto.py — il post «Risultati» della settimana esce da solo, dopo l'ultima partita.

Gira su GitHub Actions (seles-media/.github/workflows/risultati.yml) ogni 30 minuti da domenica
a martedì, anche col Mac chiuso. A ogni giro:
  1. se il riepilogo di questa settimana è già uscito o è in coda (feed Instagram, coda/,
     in-corso/, pubblicati/) si ferma;
  2. legge Tuttocampo (le stesse funzioni di settimana.py) e prende le partite della Seles
     da mercoledì a lunedì, attorno alla domenica;
  3. aspetta finché una partita deve ancora giocarsi, è iniziata da meno di 2 ore e 15
     o non ha ancora il punteggio. Di solito l'ultima è la Juniores (domenica 17:30), a volte
     l'Under 15 di lunedì. Martedì alle 14 esce comunque, senza le partite rimaste senza punteggio;
  4. fa la grafica (notte.riepilogo, la stessa della routine) e la didascalia
     (settimana.didascalia), le mette in coda/ con l'ora di adesso e fa push:
     la sveglia su Cloudflare la pubblica su Instagram e Facebook entro un minuto.

Sorgente: kit-social/risultati_auto.py. La copia in seles-media/auto/ si aggiorna con
  ../../../../.venv-render/bin/python risultati_auto.py sincronizza
che copia anche settimana.py, notte.py, notte.css, build.py, i font e lo stemma Seles.
Dopo una modifica a settimana.py o notte.py va rilanciato, poi commit e push di seles-media.

Prova senza pubblicare niente (scrive la grafica in out-auto/):
  ../../../../.venv-render/bin/python risultati_auto.py prova [--oggi 2026-11-09T19:00]
"""
import os, sys, json, shutil, asyncio, argparse, subprocess, pathlib, datetime as dt, urllib.request, urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import settimana as S

# su GitHub lo script sta in seles-media/auto/, sul Mac in kit-social/ accanto a seles-media/
REPO = HERE.parent if (HERE.parent / "coda").is_dir() else HERE.parent / "seles-media"
BUILD = HERE / "build.py" if (HERE / "build.py").exists() else S.BUILD
ATTESA = dt.timedelta(hours=2, minutes=15)      # dal calcio d'inizio: C11 con intervallo e recupero
CHIAVE = "i risultati della settimana"           # prima riga della didascalia (settimana.didascalia)


def finestra(oggi):
    """Domenica di riferimento, inizio (mercoledì 00:00), fine (lunedì 23:59) e scadenza (martedì 14:00)."""
    wd = oggi.weekday()
    dom = (oggi + dt.timedelta(days=6 - wd if wd >= 2 else -(wd + 1))).replace(hour=0, minute=0, second=0, microsecond=0)
    return dom, dom - dt.timedelta(days=4), dom + dt.timedelta(days=2, seconds=-1), dom + dt.timedelta(days=2, hours=14)


def feed():
    """Ultimi post del feed Instagram: anche quelli fatti a mano o con la routine dal Mac."""
    tok, ig = os.environ.get("META_PAGE_TOKEN"), os.environ.get("META_IG_USER_ID")
    if tok and ig:
        q = urllib.parse.urlencode({"fields": "caption,timestamp,permalink", "limit": 30, "access_token": tok})
        with urllib.request.urlopen(f"https://graph.facebook.com/v23.0/{ig}/media?{q}", timeout=60) as r:
            dati = json.load(r).get("data", [])
    else:
        try:
            import publish                       # sul Mac: legge kit-social/.env da solo
            _, ig = publish.ids()
            dati = (publish.api("GET", f"{ig}/media", soft=True, fields="caption,timestamp,permalink", limit=30) or {}).get("data", [])
        except (ImportError, SystemExit):
            print("⚠ senza token non posso guardare il feed Instagram: controllo solo la coda")
            return []
    return [{"quando": S.locale(x["timestamp"]), "testo": x.get("caption") or "", "link": x.get("permalink")} for x in dati]


def gia_uscito(inizio):
    for cart in ("coda", "in-corso", "pubblicati"):
        for f in sorted((REPO / cart).glob("*.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (j.get("didascalia") or "").strip().lower().startswith(CHIAVE) and S.locale(j["quando"]) >= inizio:
                return f"{cart}/{f.name}"
    for x in feed():
        if x["testo"].strip().lower().startswith(CHIAVE) and x["quando"] >= inizio:
            return x["link"]
    return None


def grafica(ris, out, nome):
    import notte
    out.mkdir(parents=True, exist_ok=True)
    html = notte.riepilogo(nome, ris, True, foto=None)
    doc = (f'<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>Risultati</title>'
           f'<link rel="stylesheet" href="{(HERE / "notte.css").as_uri()}"></head><body>{html}</body></html>')
    (out / f"{nome}.html").write_text(doc.replace('src="R/', f'src="{HERE.as_uri()}/'), encoding="utf-8")
    subprocess.run([sys.executable, str(BUILD), str(out / f"{nome}.html"), str(out), "1080", "1920", "1", "92"],
                   check=True, stdout=subprocess.DEVNULL)
    return out / f"{nome}.jpg"


def git(*a, check=True):
    return subprocess.run(["git", "-C", str(REPO), *a], check=check, capture_output=True, text=True)


def metti_in_coda(img, cap, ris):
    git("pull", "--rebase", "-q")
    q = dt.datetime.now().astimezone().replace(second=0, microsecond=0)
    nome = f"{q:%Y%m%d-%H%M}-risultati-settimana"
    shutil.copy2(img, REPO / "media" / f"{nome}.jpg")
    post = {"quando": q.isoformat(), "dove": ["ig", "fb"], "immagini": [f"media/{nome}.jpg"], "didascalia": cap,
            "da": "risultati_auto.py",
            "match": [{k: m[k] for k in ("squadra", "quando", "casa", "ospite", "gol")} for m in ris]}
    (REPO / "coda" / f"{nome}.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    git("add", "media", "coda")
    git("commit", "-q", "-m", f"Risultati della settimana in coda ({len(ris)} partite)")
    for _ in range(3):                           # la sveglia scrive sulla stessa repo: riprova dopo un rebase
        if git("push", "-q", check=False).returncode == 0:
            print(f"✓ in coda: coda/{nome}.json, la sveglia lo pubblica entro un minuto")
            return
        git("pull", "--rebase", "-q")
    raise SystemExit("✗ push non riuscito")


def giro(oggi, prova):
    dom, inizio, fine, scad = finestra(oggi)
    print(f"Settimana della domenica {dom:%d/%m} (partite dal {inizio:%d/%m} al {fine:%d/%m}), adesso {oggi:%a %d/%m %H:%M}")
    g = gia_uscito(inizio)
    if g:
        print("✓ il riepilogo di questa settimana è già uscito o in coda:", g)
        return
    S.AVV.mkdir(parents=True, exist_ok=True)
    for tentativo in range(3):                   # Tuttocampo a volte non risponde: riprova due volte
        try:
            tutte = asyncio.run(S.leggi_tutto(oggi))
            break
        except Exception as e:
            print(f"⚠ Tuttocampo non risponde ({type(e).__name__}), tentativo {tentativo + 1} di 3")
            if tentativo == 2:
                raise
    q = lambda m: dt.datetime.fromisoformat(m["quando"])
    sett = sorted((m for m in tutte if inizio <= q(m) <= fine), key=q)
    if not sett:
        print("· nessuna partita della Seles in questa settimana: niente da pubblicare")
        return
    attesa = []
    for m in sett:
        finita = m["gol"] and oggi >= q(m) + ATTESA
        stato = (f"{m['gol'][0]}-{m['gol'][1]}" if finita else
                 "da giocare" if oggi < q(m) else "in corso o appena finita" if oggi < q(m) + ATTESA else "senza punteggio")
        print(f"  {'✓' if finita else '…'} {S.g_ita(q(m), True)} {q(m):%H:%M} {m['squadra']:4} "
              f"{S.nome(m['casa'])} – {S.nome(m['ospite'])}: {stato}")
        if not finita:
            attesa.append(m)
    if attesa and oggi < scad:
        print(f"· aspetto: {len(attesa)} {'partita ancora aperta' if len(attesa) == 1 else 'partite ancora aperte'} (esce comunque martedì alle 14 con quelle che ci sono)")
        if not prova:
            return
        print("  (prova: preparo lo stesso la grafica con le partite già chiuse)")
    per = {}
    for m in sett:
        if m["gol"] and oggi >= q(m) + ATTESA:
            per[m["squadra"]] = m                # una per squadra: l'ultima giocata
    ris = sorted(per.values(), key=q)
    if not ris:
        print("· nessun risultato su Tuttocampo: niente da pubblicare")
        return
    nome = f"risultati-{dom:%Y%m%d}"
    out = HERE / ("out-auto" if prova else "out")
    img = grafica(ris, out, nome)
    cap = S.didascalia(ris, True)
    (out / f"{nome}.txt").write_text(cap, encoding="utf-8")
    print(f"✓ grafica: {img}\n--- didascalia ---\n{cap}\n------------------")
    if prova:
        print("prova: non metto in coda niente")
        return
    metti_in_coda(img, cap, ris)


def controllo(oggi):
    """Solo libreria standard, prima di installare il browser: scrive fatto=true per GitHub se è già uscito."""
    g = gia_uscito(finestra(oggi)[1])
    print("✓ già uscito o in coda:", g) if g else print("· non ancora uscito: si legge Tuttocampo")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"fatto={'true' if g else 'false'}\n")


def sincronizza():
    """Copia in seles-media/auto/ quello che serve a GitHub per fare la grafica."""
    dst = HERE.parent / "seles-media" / "auto"
    file = ["risultati_auto.py", "settimana.py", "notte.py", "notte.css", "assets/loghi/seles-trim.png"] + \
           [f"assets/fonts/{f}" for f in ("Viga-Regular.ttf", "Poppins-Regular.ttf", "Poppins-Medium.ttf",
                                          "Poppins-SemiBold.ttf", "Poppins-Bold.ttf")]
    for f in file:
        (dst / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / f, dst / f)
    shutil.copy2(S.BUILD, dst / "build.py")
    (dst / ".gitignore").write_text("assets/loghi/avversari/\nout/\nout-auto/\n__pycache__/\n", encoding="utf-8")
    print(f"✓ copiati {len(file) + 1} file in {dst}: ora commit e push di seles-media")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["giro", "prova", "controllo", "sincronizza"])
    ap.add_argument("--oggi", help="AAAA-MM-GGTHH:MM (solo per le prove)")
    a = ap.parse_args()
    if a.cmd == "sincronizza":
        sincronizza()
    else:
        oggi = dt.datetime.fromisoformat(a.oggi) if a.oggi else dt.datetime.now().replace(second=0, microsecond=0)
        controllo(oggi) if a.cmd == "controllo" else giro(oggi, a.cmd == "prova")
