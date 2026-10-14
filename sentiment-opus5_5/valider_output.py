#!/usr/bin/env python3
"""Valider modelloutput mot inputfil.

Bruk: python3 valider_output.py <inputfil.jsonl> <modelloutput.jsonl>

Sjekker:
- gyldig JSON per linje
- nøyaktig like mange linjer i output som i input
- alle conc_id fra input finnes igjen uendret, i samme rekkefølge
- sentiment er én av de gyldige verdiene
- label er "ungdomsorg" eller null
Exit-kode 0 = OK, 1 = feil.
"""
import json
import sys

GYLDIG_SENTIMENT = {"positiv", "negativ", "nøytral", "uklart", "ikke relevant"}
GYLDIG_LABEL = {None, "ungdomsorg"}


def les_jsonl(sti):
    linjer = []
    with open(sti, encoding="utf-8") as f:
        for i, linje in enumerate(f, 1):
            linje = linje.strip()
            if not linje:
                continue
            try:
                linjer.append(json.loads(linje))
            except json.JSONDecodeError as e:
                print(f"FEIL: {sti} linje {i}: ugyldig JSON ({e})")
                sys.exit(1)
    return linjer


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    inp = les_jsonl(sys.argv[1])
    out = les_jsonl(sys.argv[2])
    feil = []

    if len(inp) != len(out):
        feil.append(f"Antall linjer: input {len(inp)}, output {len(out)}")

    for i, (a, b) in enumerate(zip(inp, out)):
        if a.get("conc_id") != b.get("conc_id"):
            feil.append(f"Posisjon {i}: conc_id input={a.get('conc_id')!r} output={b.get('conc_id')!r}")
        s = b.get("sentiment")
        if s not in GYLDIG_SENTIMENT:
            feil.append(f"conc_id {b.get('conc_id')}: ugyldig sentiment {s!r}")
        if b.get("label") not in GYLDIG_LABEL:
            feil.append(f"conc_id {b.get('conc_id')}: ugyldig label {b.get('label')!r}")
        if not b.get("begrunnelse"):
            feil.append(f"conc_id {b.get('conc_id')}: mangler begrunnelse")

    if feil:
        print(f"VALIDERING FEILET ({len(feil)} feil):")
        for f_ in feil:
            print(" -", f_)
        sys.exit(1)
    print(f"OK: {len(out)} linjer validert.")


if __name__ == "__main__":
    main()
