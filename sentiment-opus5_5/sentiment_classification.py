#!/usr/bin/env python3
"""
sentiment_classification.py – full sentimentkjøring av «ungdom»-konkordanser via Claude-API-et.

Hver batch à 10 konkordanser sendes som et eget, uavhengig (stateless) API-kall
med hele systemprompten fra prompt_sentimentanalyse_ungdom.md. Output valideres
programmatisk per batch; feilede batcher kjøres automatisk på nytt.

Oppsett (én gang):
    pip install anthropic openpyxl
    export ANTHROPIC_API_KEY=...        # settes i terminalen

Arbeidsflyt:
    python3 sentiment_classification.py forbered                  # dedupliser + del opp i deler à 5 000
    python3 sentiment_classification.py estimat                   # grovt tokenoverslag
    python3 sentiment_classification.py kalibrer                  # kjører pilotkonkordansene, sammenligner med trinn 4
    python3 sentiment_classification.py kjor --del 1              # kjør del 1 (synkront, parallelle kall)
    python3 sentiment_classification.py kjor --del 2 --modus batch   # eller via Message Batches API (billigere, asynkront)
    python3 sentiment_classification.py status                    # oversikt over deler
    python3 sentiment_classification.py samle                     # sett sammen alt → trinn6-filer + xlsx

Alle kommandoer kan gjenopptas: ferdige og validerte batcher hoppes over.
Legg til --mock for en tørrkjøring uten API (for testing av pipelinen).
"""

import argparse, collections, concurrent.futures as cf, datetime, hashlib, json, os, random, re, sys, threading, time
from pathlib import Path


ROT = Path(__file__).resolve().parent
KORPUS = ROT / "konkordanser-nettavis-ungdom-OR-ungdomm_.jsonl"
PROMPTFIL = ROT / "prompt_sentimentanalyse_ungdom.md"
PILOT_INPUT = ROT / "input-trinn4.jsonl"
PILOT_FASIT = ROT / "sentiment-ungdom-trinn4.jsonl"
T6 = ROT / "trinn6"
DELER, RAA, UT = T6 / "deler", T6 / "raa", T6 / "output"
MANIFEST, FEILET, DRIFT = T6 / "manifest.json", T6 / "feilet.jsonl", T6 / "driftrapport.csv"
AVVIKSLOGG = T6 / "avvikslogg.jsonl"

MODELL = "claude-opus-5-5"
BATCHSTR = 10
DELSTR = 5000                          # konkordanser per del (= 500 batcher)
MAKS_FORSOK = 3
KALIBRERINGSMAAL = 85.0              # % sentiment-samsvar med trinn 4; lavere samsvar logges som avvik
GYLDIG_SENTIMENT = {"positiv", "negativ", "nøytral", "uklart", "ikke relevant"}
GYLDIG_LABEL = {None, "ungdomsorg"}
FELT = ["conc_id", "sentiment", "label", "begrunnelse"]
LAAS = threading.Lock()


# Hjelpefunksjoner
def les_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def skriv_jsonl(p, rader):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def legg_til_jsonl(p, rad):
    p.parent.mkdir(parents=True, exist_ok=True)
    with LAAS, open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")

def systemprompt():
    """Alt mellom '## Systemprompt (kopier til modellen)' og første skillelinje '---'."""
    t = PROMPTFIL.read_text(encoding="utf-8")
    s = t.index("## Systemprompt (kopier til modellen)")
    e = t.index("\n---\n", s)
    sp = t[s:e].split("\n", 1)[1]
    sp = re.sub(r"<!--.*?-->", "", sp, flags=re.S)
    return sp.strip() + "\n"

def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()

def les_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

def skriv_manifest(m):
    T6.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

def batcher(rader, n=BATCHSTR):
    return [rader[i:i + n] for i in range(0, len(rader), n)]

def brukerinnhold(batch):
    return "\n".join(json.dumps({"conc_id": r["conc_id"], "dhlabid": r["dhlabid"],
                                 "concordance": r["concordance"]}, ensure_ascii=False) for r in batch)


# Tolking og validering
def tolk_og_valider(tekst, batch):
    """Returnerer (rader, None) hvis gyldig, ellers (None, feilmelding)."""
    t = tekst.strip()
    t = re.sub(r"^```(?:jsonl|json)?\s*|\s*```$", "", t)          # tåler kodegjerder
    linjer = [l for l in t.splitlines() if l.strip()]
    rader = []
    for i, l in enumerate(linjer):
        try:
            rader.append(json.loads(l))
        except json.JSONDecodeError:
            return None, f"ugyldig JSON på linje {i+1}: {l[:80]!r}"
    if len(rader) != len(batch):
        return None, f"antall linjer {len(rader)} ≠ input {len(batch)}"
    ut = []
    for inn, r in zip(batch, rader):
        if not isinstance(r, dict):
            return None, "linje er ikke et JSON-objekt"
        if r.get("conc_id") != inn["conc_id"]:
            return None, f"conc_id {r.get('conc_id')!r} ≠ forventet {inn['conc_id']!r}"
        if r.get("sentiment") not in GYLDIG_SENTIMENT:
            return None, f"{inn['conc_id']}: ugyldig sentiment {r.get('sentiment')!r}"
        if r.get("label") not in GYLDIG_LABEL:
            return None, f"{inn['conc_id']}: ugyldig label {r.get('label')!r}"
        if not isinstance(r.get("begrunnelse"), str) or not r["begrunnelse"].strip():
            return None, f"{inn['conc_id']}: mangler begrunnelse"
        ut.append({k: r[k] for k in FELT})
    return ut, None


# API-utveksling
class MockKlient:
    """Tørrkjøring uten API: svarer 'nøytral' og lager av og til bevisst feil for å teste retry."""
    def __init__(self, feilrate=0.1): self.feilrate = feilrate
    def kall(self, system, bruker, **_):
        ids = [json.loads(l)["conc_id"] for l in bruker.splitlines()]
        rader = [{"conc_id": i, "sentiment": "nøytral", "label": None, "begrunnelse": "MOCK"} for i in ids]
        if random.random() < self.feilrate:
            rader = rader[:-1]                                     # simuler manglende linje
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rader), {"mock": True}

class ApiKlient:
    def __init__(self, modell, temperatur, maks_tokens):
        try:
            import anthropic
        except ImportError:
            sys.exit("Mangler pakken 'anthropic'. Kjør: pip install anthropic")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY er ikke satt. Sett den i terminalen: export ANTHROPIC_API_KEY=...")
        self.anthropic = anthropic
        self.c = anthropic.Anthropic(max_retries=8)               # SDK håndterer 429/5xx med backoff
        self.modell, self.temp, self.maks = modell, temperatur, maks_tokens

    def params(self, system, bruker):
        p = {"model": self.modell, "max_tokens": self.maks,
             "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
             "messages": [{"role": "user", "content": bruker}]}
        if self.temp is not None:
            p["temperature"] = self.temp
        return p

    def kall(self, system, bruker):
        m = self.c.messages.create(**self.params(system, bruker))
        tekst = "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
        u = m.usage
        return tekst, {"stop_reason": m.stop_reason, "input_tokens": u.input_tokens,
                       "output_tokens": u.output_tokens,
                       "cache_read": getattr(u, "cache_read_input_tokens", None),
                       "cache_write": getattr(u, "cache_creation_input_tokens", None)}

def lag_klient(a):
    if a.mock:
        return MockKlient()
    temp = None if str(a.temperatur).lower() == "none" else float(a.temperatur)
    return ApiKlient(a.modell, temp, a.maks_tokens)


# Kjøring av batcher
def ferdige_batcher(raalogg):
    ferdig = {}
    if raalogg.exists():
        for r in les_jsonl(raalogg):
            if r.get("ok"):
                ferdig[r["batch_id"]] = r["rader"]
    return ferdig

def kjor_en_batch(klient, system, batch_id, batch, raalogg, forsok_start=1):
    feil = None
    for forsok in range(forsok_start, MAKS_FORSOK + 1):
        try:
            tekst, bruk = klient.kall(system, brukerinnhold(batch))
        except Exception as e:                                     # nettverk/API etter SDK-retries
            feil = f"API-feil: {type(e).__name__}: {e}"
            legg_til_jsonl(raalogg, {"batch_id": batch_id, "forsok": forsok, "ok": False,
                                     "feil": feil, "tid": now()})
            if type(e).__name__ in FATALE_FEIL or isinstance(e, TypeError):                     # nytter ikke å prøve igjen
                raise FatalApiFeil(feil) from e
            time.sleep(5 * forsok)
            continue
        rader, feil = tolk_og_valider(tekst, batch)
        legg_til_jsonl(raalogg, {"batch_id": batch_id, "forsok": forsok, "ok": rader is not None,
                                 "feil": feil, "raa": tekst, "bruk": bruk, "rader": rader, "tid": now()})
        if rader is not None:
            return rader
        print(f"  – {batch_id} forsøk {forsok}: {feil}" + (f" (stop_reason={bruk.get('stop_reason')})" if isinstance(bruk, dict) and bruk.get('stop_reason') not in (None, 'end_turn') else ""))
    legg_til_jsonl(FEILET, {"batch_id": batch_id, "conc_ids": [r["conc_id"] for r in batch],
                            "siste_feil": feil, "tid": now()})
    return None

def now(): return datetime.datetime.now().isoformat(timespec="seconds")

FATALE_FEIL = {"BadRequestError", "AuthenticationError", "PermissionDeniedError", "NotFoundError"}

class FatalApiFeil(Exception):
    pass

def fatal_melding(feil):
    hint = ""
    if "temperature" in feil:
        hint = "\nTips: modellen/SDK-en støtter ikke temperatur-parameteren. Kjør uten --temperatur (standard er none)."
    elif "AuthenticationError" in feil:
        hint = "\nTips: API-nøkkelen er ugyldig. Sjekk ANTHROPIC_API_KEY."
    elif "credit" in feil.lower() or "billing" in feil.lower():
        hint = "\nTips: kontoen mangler kreditt. Fyll på under Billing i console.anthropic.com."
    elif "NotFoundError" in feil:
        hint = "\nTips: modellnavnet finnes ikke. Sjekk --modell."
    return f"\nKjøringen avbrutt på grunn av en API-feil som ikke løses ved å prøve igjen:\n  {feil}{hint}"

def logg_avvik(type_, melding, **ekstra):
    """Avvik stopper ikke kjøringen – de skrives til trinn6/avvikslogg.jsonl og vises i terminalen."""
    print(f"AVVIK ({type_}): {melding}")
    legg_til_jsonl(AVVIKSLOGG, {"tid": now(), "type": type_, "melding": melding, **ekstra})

def kjor_sync(klient, system, alle, raalogg, parallell, prefiks):
    ferdig = ferdige_batcher(raalogg)
    gjenstaar = [(f"{prefiks}-b{i:04d}", b) for i, b in enumerate(alle) if f"{prefiks}-b{i:04d}" not in ferdig]
    print(f"{len(alle)} batcher, {len(ferdig)} allerede ferdige, {len(gjenstaar)} gjenstår.")
    n = 0
    with cf.ThreadPoolExecutor(max_workers=parallell) as ex:
        fut = {ex.submit(kjor_en_batch, klient, system, bid, b, raalogg): bid for bid, b in gjenstaar}
        for f in cf.as_completed(fut):
            n += 1
            try:
                res = f.result()
            except FatalApiFeil as e:
                ex.shutdown(wait=False, cancel_futures=True)
                sys.exit(fatal_melding(str(e)))
            if res is None:
                print(f"  ! {fut[f]} feilet etter {MAKS_FORSOK} forsøk (logget i trinn6/feilet.jsonl og avvikslogg)")
            if n % 25 == 0 or n == len(gjenstaar):
                print(f"  {n}/{len(gjenstaar)} batcher behandlet")

def kjor_batch_api(a, system, alle, raalogg, prefiks):
    """Message Batches API: alle gjenstående batcher sendes som én asynkron jobb; feilede valideringer kjøres synkront på nytt."""
    klient = lag_klient(a)
    if a.mock:
        return kjor_sync(klient, system, alle, raalogg, a.parallell, prefiks)
    ferdig = ferdige_batcher(raalogg)
    idx = {f"{prefiks}-b{i:04d}": b for i, b in enumerate(alle)}
    gjenstaar = {bid: b for bid, b in idx.items() if bid not in ferdig}
    if not gjenstaar:
        print("Alle batcher er ferdige."); return
    m = les_manifest(); jobbnokkel = f"batchjobb_{prefiks}"
    jobb_id = m.get(jobbnokkel)
    if not jobb_id:
        req = [{"custom_id": bid, "params": klient.params(system, brukerinnhold(b))} for bid, b in gjenstaar.items()]
        jobb = klient.c.messages.batches.create(requests=req)
        jobb_id = jobb.id; m[jobbnokkel] = jobb_id; skriv_manifest(m)
        print(f"Sendt {len(req)} forespørsler som batchjobb {jobb_id}.")
    else:
        print(f"Gjenopptar batchjobb {jobb_id}.")
    while True:
        j = klient.c.messages.batches.retrieve(jobb_id)
        print(f"  status: {j.processing_status}  {j.request_counts}")
        if j.processing_status == "ended":
            break
        time.sleep(60)
    omkjor = []
    for res in klient.c.messages.batches.results(jobb_id):
        bid = res.custom_id
        if bid not in gjenstaar:
            continue
        if res.result.type == "succeeded":
            msg = res.result.message
            tekst = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            rader, feil = tolk_og_valider(tekst, gjenstaar[bid])
            legg_til_jsonl(raalogg, {"batch_id": bid, "forsok": 1, "ok": rader is not None, "feil": feil,
                                     "raa": tekst, "bruk": {"input_tokens": msg.usage.input_tokens,
                                     "output_tokens": msg.usage.output_tokens}, "rader": rader,
                                     "tid": now(), "kilde": "batch-api"})
            if rader is None:
                omkjor.append(bid)
        else:
            legg_til_jsonl(raalogg, {"batch_id": bid, "forsok": 1, "ok": False,
                                     "feil": f"batch-api: {res.result.type}", "tid": now()})
            omkjor.append(bid)
    m.pop(jobbnokkel, None); skriv_manifest(m)
    if omkjor:
        print(f"{len(omkjor)} batcher feilet validering/kjøring – kjøres synkront på nytt.")
        for bid in omkjor:
            try:
                kjor_en_batch(klient, system, bid, gjenstaar[bid], raalogg, forsok_start=2)
            except FatalApiFeil as e:
                sys.exit(fatal_melding(str(e)))

def samle_rader(alle, raalogg, prefiks):
    ferdig = ferdige_batcher(raalogg)
    ut, mangler = [], []
    for i, b in enumerate(alle):
        bid = f"{prefiks}-b{i:04d}"
        if bid in ferdig:
            ut.extend(ferdig[bid])
        else:
            mangler.append(bid)
    return ut, mangler


# Rapportering
def fordeling(rader):
    n = len(rader) or 1
    c = collections.Counter(r["sentiment"] for r in rader)
    d = {k: round(100 * c.get(k, 0) / n, 1) for k in ["positiv", "negativ", "nøytral", "uklart", "ikke relevant"]}
    d["ungdomsorg"] = round(100 * sum(r["label"] == "ungdomsorg" for r in rader) / n, 1)
    return d

def driftkontroll(navn, rader):
    ref = fordeling(les_jsonl(PILOT_FASIT)) if PILOT_FASIT.exists() else None
    d = fordeling(rader)
    advarsler = []
    if ref:
        for k in ["positiv", "negativ", "nøytral", "uklart", "ikke relevant"]:
            if abs(d[k] - ref[k]) > 10:
                advarsler.append(f"{k} {d[k]} % vs pilot {ref[k]} %")
    if d["uklart"] > 10: advarsler.append(f"uklart {d['uklart']} % > 10 %")
    if not 3 <= d["ungdomsorg"] <= 15: advarsler.append(f"ungdomsorg {d['ungdomsorg']} % utenfor 3–15 %")
    ny = not DRIFT.exists()
    with open(DRIFT, "a", encoding="utf-8") as f:
        if ny: f.write("del;n;" + ";".join(d.keys()) + ";advarsler;tid\n")
        f.write(f"{navn};{len(rader)};" + ";".join(str(v) for v in d.values()) + f";{' | '.join(advarsler)};{now()}\n")
    print(f"Fordeling {navn} (%): {d}")
    if ref: print(f"Pilot (trinn 4) (%):  {ref}")
    if advarsler:
        logg_avvik("drift", " | ".join(advarsler), del_=navn, fordeling=d)
    else:
        print("Ingen driftavvik.")

def skriv_xlsx(sti, rader, kolonner, bredder=None, ark="data"):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    wb = Workbook(write_only=False); ws = wb.active; ws.title = ark
    ws.append(kolonner)
    for r in rader:
        ws.append([r.get(k) for k in kolonner])
    for c in ws[1]: c.font = Font(name="Arial", size=10, bold=True)
    for i, k in enumerate(kolonner, 1):
        ws.column_dimensions[get_column_letter(i)].width = (bredder or {}).get(k, 14)
    for i, k in enumerate(kolonner, 1):
        if "conc_id" in k:
            for c in ws[get_column_letter(i)]: c.number_format = "@"
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    wb.save(sti)

def skriv_duplikatliste(korpus, kart):
    """Alle rader som deler tekst med minst én annen rad, gruppert. Brukes til å se om duplikatene
    kommer fra samme eller ulike nettsteder (slå opp dhlabid i metadata)."""
    grupper = collections.defaultdict(list)
    for r in korpus:
        grupper[kart[r["conc_id"]]].append(r)
    rader, g = [], 0
    for rep_id, medl in grupper.items():
        if len(medl) < 2:
            continue
        g += 1
        for r in medl:
            rader.append({"gruppe": g, "antall_i_gruppe": len(medl), "representant_conc_id": rep_id,
                          "conc_id": r["conc_id"], "dhlabid": r["dhlabid"],
                          "ulike_dhlabid_i_gruppe": len({x["dhlabid"] for x in medl}),
                          "concordance": r["concordance"]})
    skriv_jsonl(ROT / "duplikater-trinn6.jsonl", rader)
    skriv_xlsx(ROT / "duplikater-trinn6.xlsx", rader, list(rader[0].keys()),
               {"gruppe": 8, "antall_i_gruppe": 10, "representant_conc_id": 12, "conc_id": 10,
                "dhlabid": 12, "ulike_dhlabid_i_gruppe": 12, "concordance": 90}, "duplikater")
    print(f"Duplikatliste: {len(rader)} rader i {g} grupper → duplikater-trinn6.jsonl / .xlsx")


# Kommandoer for CLI
def cmd_forbered(a):
    korpus = les_jsonl(KORPUS)
    ids = [r["conc_id"] for r in korpus]
    assert len(ids) == len(set(ids)), "duplikate conc_id i korpus!"
    if a.ingen_dedup:
        unike, kart = korpus, {r["conc_id"]: r["conc_id"] for r in korpus}
    else:
        forste, kart, unike = {}, {}, []
        for r in korpus:
            rep = forste.setdefault(r["concordance"], r["conc_id"])
            kart[r["conc_id"]] = rep
            if rep == r["conc_id"]:
                unike.append(r)
    antall_deler = (len(unike) + DELSTR - 1) // DELSTR
    gamle = [p for p in DELER.glob("del_*.jsonl") if int(p.stem[4:]) > antall_deler]
    if gamle:
        sys.exit(f"Mappa trinn6/deler har overflødige delfiler fra en tidligere oppdeling: {[p.name for p in gamle]}. Slett dem og kjør på nytt.")
    for i in range(0, len(unike), DELSTR):
        skriv_jsonl(DELER / f"del_{i // DELSTR + 1:03d}.jsonl", unike[i:i + DELSTR])
    (T6 / "dedup_kart.json").write_text(json.dumps(kart), encoding="utf-8")
    skriv_duplikatliste(korpus, kart)
    sp = systemprompt()
    m = les_manifest()
    m.update({"korpus": KORPUS.name, "korpus_rader": len(korpus), "unike_tekster": len(unike),
              "dedup": not a.ingen_dedup, "deler": (len(unike) + DELSTR - 1) // DELSTR, "delstr": DELSTR,
              "batchstr": BATCHSTR, "systemprompt_sha256": sha(sp), "forberedt": now()})
    skriv_manifest(m)
    (T6 / "systemprompt-brukt.txt").write_text(sp, encoding="utf-8")
    print(f"Korpus: {len(korpus)} rader, {len(unike)} unike tekster → {m['deler']} deler à inntil {DELSTR} "
          f"({(len(unike) + BATCHSTR - 1) // BATCHSTR} batcher à {BATCHSTR}).")

def cmd_estimat(a):
    sp = systemprompt()
    unike = sum(len(les_jsonl(p)) for p in sorted(DELER.glob("del_*.jsonl"))) or len(les_jsonl(KORPUS))
    nb = (unike + BATCHSTR - 1) // BATCHSTR
    inn_tegn = sum(len(brukerinnhold([r])) for p in sorted(DELER.glob("del_*.jsonl")) for r in les_jsonl(p))
    ut_tegn = sum(len(json.dumps(r, ensure_ascii=False)) for r in les_jsonl(PILOT_FASIT)) / 200 * unike
    tpt = 3.5  # tegn per token, grovt for norsk
    print(f"Batcher: {nb}")
    print(f"Systemprompt: ~{len(sp)/tpt:,.0f} tokens per kall → ~{nb*len(sp)/tpt/1e6:,.1f} M tokens totalt (mest cache-treff)")
    print(f"Konkordanser inn: ~{inn_tegn/tpt/1e6:,.1f} M tokens")
    print(f"Output: ~{ut_tegn/tpt/1e6:,.1f} M tokens")
    print("Grovt anslag – sjekk gjeldende priser for valgt modell. Batch-API gir rabatt; prompt-caching reduserer systemprompt-kostnaden.")

def cmd_kalibrer(a):
    klient, sp = lag_klient(a), systemprompt()
    inn = les_jsonl(PILOT_INPUT); fasit = {r["conc_id"]: r for r in les_jsonl(PILOT_FASIT)}
    kdir = T6 / "kalibrering" / ("mock" if a.mock else a.modell); raalogg = kdir / "raa.jsonl"
    alle = batcher(inn)
    kjor_sync(klient, sp, alle, raalogg, a.parallell, "kal")
    ut, mangler = samle_rader(alle, raalogg, "kal")
    if mangler:
        print(f"Mangler {len(mangler)} batcher – kjør kalibrer på nytt."); return
    skriv_jsonl(kdir / "output.jsonl", ut)
    enig = sum(fasit[r["conc_id"]]["sentiment"] == r["sentiment"] for r in ut)
    lab = sum(fasit[r["conc_id"]]["label"] == r["label"] for r in ut)
    matrise = collections.Counter((fasit[r["conc_id"]]["sentiment"], r["sentiment"]) for r in ut)
    print(f"\nSentiment-samsvar med trinn 4: {enig}/{len(ut)} = {100*enig/len(ut):.1f} %  (mål ≥ 85 %)")
    print(f"Label-samsvar: {lab}/{len(ut)} = {100*lab/len(ut):.1f} %")
    if 100*enig/len(ut) < KALIBRERINGSMAAL:
        logg_avvik("kalibrering", f"sentiment-samsvar {100*enig/len(ut):.1f} % er under {KALIBRERINGSMAAL} %")
    print("Avvik (trinn4 → API):", {f"{a_}→{b_}": n for (a_, b_), n in matrise.items() if a_ != b_})
    kilde = {r["conc_id"]: r for r in inn}
    avvik = [{"conc_id": r["conc_id"], "concordance": kilde[r["conc_id"]]["concordance"],
              "trinn4_sentiment": fasit[r["conc_id"]]["sentiment"], "api_sentiment": r["sentiment"],
              "trinn4_label": fasit[r["conc_id"]]["label"], "api_label": r["label"],
              "trinn4_begrunnelse": fasit[r["conc_id"]]["begrunnelse"], "api_begrunnelse": r["begrunnelse"]}
             for r in ut if fasit[r["conc_id"]]["sentiment"] != r["sentiment"] or fasit[r["conc_id"]]["label"] != r["label"]]
    if avvik:
        skriv_xlsx(kdir / "kalibrering-avvik.xlsx", avvik, list(avvik[0].keys()),
                   {"concordance": 70, "trinn4_begrunnelse": 45, "api_begrunnelse": 45})
        print(f"Avvik skrevet til {(kdir / 'kalibrering-avvik.xlsx').relative_to(ROT)}")
    m = les_manifest(); m["kalibrering"] = {"modell": "mock" if a.mock else a.modell, "sentiment_samsvar": round(100*enig/len(ut), 1),
                                            "label_samsvar": round(100*lab/len(ut), 1), "tid": now()}
    skriv_manifest(m)

def cmd_kjor(a):
    m = les_manifest()
    if not m.get("deler"): sys.exit("Kjør 'forbered' først.")
    sp = systemprompt()
    if sha(sp) != m["systemprompt_sha256"]:
        sys.exit("Systemprompten er endret siden 'forbered'. Kjør 'forbered' på nytt før du fortsetter, "
                 "ellers blir deler av korpuset annotert med ulike prompter.")
    navn = f"del_{a.del_:03d}"
    if not a.mock:
        k = m.get("kalibrering")
        if not k or k.get("modell") != a.modell:
            logg_avvik("kalibrering", f"kalibrering er ikke kjørt for modellen {a.modell}", del_=navn)
        elif k["sentiment_samsvar"] < KALIBRERINGSMAAL:
            logg_avvik("kalibrering", f"kalibreringssamsvar {k['sentiment_samsvar']} % er under {KALIBRERINGSMAAL} %", del_=navn)
    inn = les_jsonl(DELER / f"{navn}.jsonl")
    alle = batcher(inn); raalogg = RAA / f"{navn}.jsonl"
    m.setdefault("kjoringer", []).append({"del": navn, "modell": "mock" if a.mock else a.modell,
                                          "temperatur": a.temperatur, "modus": a.modus, "start": now()})
    skriv_manifest(m)
    if a.modus == "batch":
        kjor_batch_api(a, sp, alle, raalogg, navn)
    else:
        kjor_sync(lag_klient(a), sp, alle, raalogg, a.parallell, navn)
    ut, mangler = samle_rader(alle, raalogg, navn)
    if mangler:
        logg_avvik("manglende batcher", f"{navn}: {len(mangler)} batcher feilet etter {MAKS_FORSOK} forsøk", batcher=mangler)
        print(f"\n{len(mangler)} batcher mangler fortsatt ({', '.join(mangler[:5])}…). Kjør samme kommando på nytt."); return
    skriv_jsonl(UT / f"{navn}.jsonl", ut)
    print(f"\n{navn}: {len(ut)} konkordanser ferdig og validert → trinn6/output/{navn}.jsonl")
    driftkontroll(navn, ut)

def cmd_status(a):
    m = les_manifest()
    print(f"Modellprompt SHA-256: {m.get('systemprompt_sha256', '-')[:12]}…  Kalibrering: {m.get('kalibrering', 'ikke kjørt')}")
    for p in sorted(DELER.glob("del_*.jsonl")):
        n = len(les_jsonl(p)); nb = (n + BATCHSTR - 1) // BATCHSTR
        ferdig = len(ferdige_batcher(RAA / p.name))
        st = "FERDIG" if (UT / p.name).exists() else ("pågår" if ferdig else "ikke startet")
        print(f"  {p.stem}: {ferdig}/{nb} batcher  {st}")
    if FEILET.exists(): print(f"Feillogg: {len(les_jsonl(FEILET))} oppføringer i trinn6/feilet.jsonl")

def cmd_samle(a):
    korpus = les_jsonl(KORPUS)
    kart = json.loads((T6 / "dedup_kart.json").read_text(encoding="utf-8"))
    vurd = {}
    for p in sorted(DELER.glob("del_*.jsonl")):
        if not (UT / p.name).exists():
            sys.exit(f"{p.stem} er ikke ferdig. Alle deler må være ferdige før 'samle'.")
        for r in les_jsonl(UT / p.name):
            vurd[r["conc_id"]] = r
    ut = []
    for r in korpus:
        v = vurd[kart[r["conc_id"]]]
        ut.append({"conc_id": r["conc_id"], "sentiment": v["sentiment"], "label": v["label"], "begrunnelse": v["begrunnelse"]})
    rå = ROT / "sentiment-ungdom-trinn6.jsonl"
    skriv_jsonl(rå, ut)
    # full validering + sammenstilling med de eksisterende skriptene
    os.system(f'"{sys.executable}" "{ROT/"valider_output.py"}" "{KORPUS}" "{rå}"')
    os.system(f'"{sys.executable}" "{ROT/"sammenstill_output.py"}" "{KORPUS}" "{rå}" "{ROT/"sentiment-ungdom-trinn6-validering.jsonl"}"')
    skriv_xlsx(ROT / "sentiment-ungdom-trinn6.xlsx", ut, FELT, {"conc_id": 10, "sentiment": 14, "label": 14, "begrunnelse": 90}, "trinn6")
    print("Skrev sentiment-ungdom-trinn6.xlsx")
    driftkontroll("TOTAL", ut)
    m = les_manifest(); m["samlet"] = now(); skriv_manifest(m)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kommando", choices=["forbered", "estimat", "kalibrer", "kjor", "status", "samle"])
    ap.add_argument("--del", dest="del_", type=int, help="delnummer for 'kjor' (1, 2, …)")
    ap.add_argument("--modus", choices=["sync", "batch"], default="sync")
    ap.add_argument("--modell", default=MODELL)
    ap.add_argument("--temperatur", default="none", help="'none' (standard: sendes ikke – Opus 5.5 og gjeldende SDK støtter ikke parameteren) eller et tall, f.eks. 0, for modeller som støtter det")
    ap.add_argument("--maks-tokens", type=int, default=4000)
    ap.add_argument("--parallell", type=int, default=4, help="samtidige kall i sync-modus")
    ap.add_argument("--ingen-dedup", action="store_true", help="annoter alle rader, også identiske tekster")
    ap.add_argument("--mock", action="store_true", help="tørrkjøring uten API")
    a = ap.parse_args()
    if a.kommando == "kjor" and not a.del_:
        ap.error("'kjor' krever --del N")
    {"forbered": cmd_forbered, "estimat": cmd_estimat, "kalibrer": cmd_kalibrer, "kjor": cmd_kjor,
     "status": cmd_status, "samle": cmd_samle}[a.kommando](a)

if __name__ == "__main__":
    main()
