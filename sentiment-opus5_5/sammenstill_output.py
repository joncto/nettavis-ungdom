#!/usr/bin/env python3
"""Sammenstill modelloutput med kildetekst til valideringsfil.

Bruk: python3 sammenstill_output.py <inputfil.jsonl> <modelloutput.jsonl> <resultatfil.jsonl>

Henter concordance og dhlabid regelbasert fra inputfila via conc_id, slik at
teksten holdes identisk med kilden. Varsler dersom en conc_id mangler i input,
eller dersom modellen likevel har levert en avvikende tekst.

Feltrekkefølge i resultat: conc_id, dhlabid, concordance, sentiment, label, begrunnelse.
"""
import json
import sys


def les_jsonl(sti):
    with open(sti, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    inp = {r["conc_id"]: r for r in les_jsonl(sys.argv[1])}
    out = les_jsonl(sys.argv[2])
    resultat = []
    feil = 0

    for r in out:
        cid = r.get("conc_id")
        kilde = inp.get(cid)
        if kilde is None:
            print(f"ADVARSEL: conc_id {cid!r} finnes ikke i inputfila – hoppet over.")
            feil += 1
            continue
        if "concordance" in r and r["concordance"] != kilde["concordance"]:
            print(f"ADVARSEL: conc_id {cid}: modellen leverte avvikende concordance-tekst; kildeteksten brukes.")
        resultat.append({
            "conc_id": cid,
            "dhlabid": kilde["dhlabid"],
            "concordance": kilde["concordance"],
            "sentiment": r.get("sentiment"),
            "label": r.get("label"),
            "begrunnelse": r.get("begrunnelse"),
        })

    with open(sys.argv[3], "w", encoding="utf-8") as f:
        for r in resultat:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Skrev {len(resultat)} linjer til {sys.argv[3]}" + (f" ({feil} hoppet over)" if feil else ""))
    sys.exit(1 if feil else 0)


if __name__ == "__main__":
    main()
