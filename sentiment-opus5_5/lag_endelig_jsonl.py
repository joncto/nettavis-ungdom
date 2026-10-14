#!/usr/bin/env python3
"""
Lag den endelige JSONL-leveransen fra resultatet av trinn 6.

Bruk: uv run lag_endelig_jsonl.py

Leser (kun lesing): sentiment-ungdom-trinn6-validering.jsonl
Skriver:            nettavis-ungdom-sentiment-opus5_5.jsonl

Én linje per konkordanse med nøklene:
  conc_id, dhlabid, konkordanse, nøkkelord, sentiment, label, begrunnelse
«konkordanse» er kildeteksten uendret, med <b>…</b> rundt nøkkelordet.
«nøkkelord» er de uthevede ordene, unike og i rekkefølge, skilt med komma
(samme verdi som i nettavis-ungdom-sentiment-opus5_5.xlsx).
"""
import json
import re
from pathlib import Path

ROT = Path(__file__).resolve().parent
KILDE = ROT / "sentiment-ungdom-trinn6-validering.jsonl"
UT = ROT / "nettavis-ungdom-sentiment-opus5_5.jsonl"

n = 0
with open(KILDE, encoding="utf-8") as inn, open(UT, "w", encoding="utf-8") as ut:
    for linje in inn:
        if not linje.strip():
            continue
        r = json.loads(linje)
        nokkel = list(dict.fromkeys(re.findall(r"<b>(.*?)</b>", r["concordance"], re.S)))
        ut.write(json.dumps({
            "conc_id": r["conc_id"],
            "dhlabid": r["dhlabid"],
            "konkordanse": r["concordance"],
            "nøkkelord": ", ".join(nokkel),
            "sentiment": r["sentiment"],
            "label": r["label"],
            "begrunnelse": r["begrunnelse"],
        }, ensure_ascii=False) + "\n")
        n += 1
print(f"Skrev {n} linjer til {UT.name}")
