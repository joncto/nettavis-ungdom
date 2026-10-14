# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "dhlab==2.43",
#     "marimo",
#     "pandas",
#     "numpy",
#     "plotly",
#     "openpyxl",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", css_file="custom.css", auto_download=["html"])


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Korpusanalyse: Nettavis-tekst om ungdom

    Denne kodeboka lar deg arbeide programmatisk med Nasjonalbibliotekets (NB) samling av nettavis-tekster (2019-22):
    - definere [tekstkorpus](https://no.wikipedia.org/wiki/Tekstkorpus)
    - visualisere statistikk om korpuset
    - hente lister med [nøkkelord i kontekst (konkordanser)](https://en.wikipedia.org/wiki/Key_Word_in_Context)
    - beregne relativfrekvens for [kollokasjoner](https://en.wikipedia.org/wiki/Collocation)

    For mer informasjon, se informasjon om [NBs samling av nettavis-tekst](https://www.nb.no/samlingen/nettarkivet/forskning/korpus-med-nettaviser/) eller [kontakt DH-lab](https://www.nb.no/dh-lab/kontakt/).

    ___
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # 0. Importere pakker

    Først importerer vi nødvendige python-pakker.
    """)
    return


@app.cell
def _():
    import dhlab as dh
    from dhlab import Corpus, totals, Collocations, Ngram
    from urllib.parse import urlparse
    import plotly.express as px
    import numpy as np
    import pandas as pd
    import json

    return dh, np, pd, px, totals, urlparse


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # 1. Korpus

    Koden nedenfor definerer et [korpus](https://no.wikipedia.org/wiki/Tekstkorpus) med tekster fra norske nettaviser.

    Definisjonen presenteres som en tabell med metadata[^1] om hvert dokument:

    | Attributt | Forklaring |
    |:-------|:------------|
    | dhlabid | Unik, persistent identifikator for teksten |
    | title    | Tittel på nettavis |
    | lang  | Tekstens språk |
    | timestamp    | Dato for arkivering (ikke nødv. publ.dato) |
    | oaiid  | Opprinnelig URI for dokumentet |
    | city  | Redaksjonssted |
    | publisher  | Domenenavn |

    [^1]: For en oversikt over alle attributter, slik de eksponeres gjennom DH-labs API, se [listen over skjema-attributter](https://www.nb.no/samlingen/nettarkivet/forskning/korpus-med-nettaviser/#hvilke-skjema-attributter-kan-jeg-benytte-mot-apiet?).*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1.1 Definere korpus

    Kodecellen nedenfor definerer et korpus med tekster:
    - fra **nettaviser**,
    - på **bokmål** eller **nynorsk**,
    - som inneholder **nøkkelordet "ungdom"**
    """)
    return


@app.cell
def _(dh):
    corpus = dh.Corpus(
        doctype="nettavis",
        fulltext="ungdom OR ungdomm*",
        lang="nob OR nno",
        limit=100_000)
    corpus
    return (corpus,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1.2 Deduplisering

    NBs nettarkiv dedupliserer nettdokumenter som er identiske. Likevel finnes det mange nettdokumenter i samlingen som er nær identiske, f.eks. sider som er arkivert flere ganger og der annonser eller menyer har mindre endringer over tid. Disse nesten-duplikatene er inkludert i DHlabs samling med nettavis-dokumenter for å tillate ulike forskningsspørsmål, f.eks. analyse av tekstendring over tid. Men for formålet i denne studien ønsker vi å utelukke slike nesten-duplikater.

    Kodecellen nedenfor:
    - normaliserer URIer (fjerne protokoll og queryparametre)
    - sammenlikner URIer,
    - beholder bare den første versjonen der flere tekster har samme URI
    """)
    return


@app.cell
def _(corpus, urlparse):
    def normalise_uri(uri):
        p = urlparse(uri)
        return f"{p.netloc}{p.path}"

    df = corpus.frame
    uri_keys = df["oaiid"].apply(normalise_uri)

    corpus.frame = df[~uri_keys.duplicated(keep="first")].reset_index(drop=True)

    print(f"Deduplisering reduserte korpuset til {len(corpus.frame)} tekster.")

    corpus
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1.3 Visualisere statistikk for korpus

    For å få innsikt i korpuset kan vi visualisere generell statistikk for distribusjon av publikasjonstitler, arkiveringstidspunkt og språk/målform.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.3.1 Distribusjon per tittel
    """)
    return


@app.cell
def _(corpus, px):
    telle_titler = corpus['title'].value_counts()

    fig_title = px.treemap(
        path=[telle_titler.index],
        values=telle_titler.values,
        title='Fordeling av tekster etter publikasjonsnavn',
        hover_data={'Antall tekster': telle_titler.values}
    )

    fig_title.show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.3.2 Distribusjon etter arkivdato
    """)
    return


@app.cell
def _(corpus, np, pd, px):
    hoestetid = pd.to_datetime(corpus['timestamp'], format='%Y%m%d')

    y_spredning = np.random.uniform(0, 1, size=len(hoestetid))

    # Tilfeldig justering langs y-aksen
    x_jitter = hoestetid + pd.to_timedelta(np.random.uniform(-2, 2, size=len(hoestetid)), unit='D')

    fig_timestamps = px.scatter(
        x=x_jitter,
        y=y_spredning,
        labels={'x': 'Høstetidspunkt', 'y': 'Spredning'},
        title='Fordeling etter arkivdato',
        opacity=0.5,
        size_max=5
    )

    fig_timestamps.show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.3.3 Fordeling etter språk/målform
    """)
    return


@app.cell
def _(corpus, px):
    språkfordeling = corpus['langs'].value_counts()

    fig_langs = px.pie(
        values=språkfordeling.values,
        names=språkfordeling.index,
        title='Fordeling etter språk/målform',
        labels={'names': 'Språk/målform', 'values': 'Antall forekomster'}
    )

    fig_langs.show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1.4 Eksporter korpusdefinisjon

    Når vi er fornøyd med korpuset kan vi eksportere korpusdefinisjonen.

    Ved å kjøre kodecellen nedenfor genereres det to filer (Excel og JSONL) under mappen "export".

    Excel-fila kan gjenbrukes i enkelte av [DH-labs apper](https://www.nb.no/dh-lab/apper/). Den fungerer også som en dokumentasjon for [håndtering av forskningsdata (RDM)](https://bibliotek.usn.no/forskerstotte/forskningsdata/retningslinjer-for-handtering-av-forskningsdata/).

    JSONL-fila er ment for programmatisk prosessering.
    """)
    return


@app.cell
def _(corpus):
    # Eksporter korpus til Excel (endre filnavn og filsti)
    corpus.frame.to_excel('../../export/korpus-nettavis-ungdom_OR_ungdomm_-nob_OR_nno-limit_100000.xlsx', index=False)

    # Eksportere korpus til JSONL (endre filnavn og filsti)
    corpus.frame.to_json('../../export/korpus-nettavis-ungdom_OR_ungdomm_-nob_OR_nno-limit_100000.jsonl', orient='records', lines=True, force_ascii=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
 
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # 2. Konkordanser (nøkkelord i kontekst)

    Basert på korpuset vi har definert kan vi hente ut forskjellig informasjon.

    Kodecellen nedenfor lar oss hente ut konkordanser for nøkkelordet **ungdom**. Dette er lister med [nøkkelord i kontekst](https://en.wikipedia.org/wiki/Key_Word_in_Context), og kan brukes til raskt å få en forståelse for hvilken kontekst nøkkelordet står i.

    (Tekstvinduet kan ha inntil 12 ord før/etter nøkkelordet, men kan aldri krysse avsnitt. Nøkkelordet fremheves i fet skrift.)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2.1 Hente konkordanser
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **2.1.1 Segmentering**

    For større korpus – slik som dette korpuset på nær 40 000 tekster – kan man oppleve sampling i DHlabs backend, uten at dette nødvendigvis framgår av resultatet.

    For å sikre at prosessen kan reproduseres fra start til slutt – og unngå sampling – velger vi å stykke opp korpusdefinisjonen i delsett à 10 000 dokumenter. Dette gjør at vi kan hente ut samtlige konkordanser.
    """)
    return


@app.cell
def _(corpus, dh):
    chunk = 10_000
    corpus_sets = [
        dh.Corpus.from_df(corpus.frame.iloc[i:i + chunk])
        for i in range(0, len(corpus.frame), chunk)
    ]
    return (corpus_sets,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **2.1.2 Hente og kombinere konkordanser**

    Konkordanser hentes for hvert av delsettene, før disse kombineres.
    """)
    return


@app.cell
def _(corpus_sets, pd):
    concs = []
    for n, c in enumerate(corpus_sets, start=1):
        conc = c.conc(words="ungdom OR ungdomm*", limit=100_000)
        print(f"Set {n}: {len(c.frame)} documents -> {len(conc.frame)} concordances")
        concs.append(conc)

    conc_ungdom = pd.concat([c.frame for c in concs], ignore_index=True)
    conc_ungdom
    return (conc_ungdom,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2.2 Eksportere konkordanser

    På samme måte som med korpusdefinisjonen kan konkordansene eksporteres.

    Innholdet kan brukes for videre automatisk analyse, samt dokumentasjon for [håndtering av forskningsdata (RDM)](https://bibliotek.usn.no/forskerstotte/forskningsdata/retningslinjer-for-handtering-av-forskningsdata/).

    Kodecellen nedenfor genererer en Excel-fil og en JSONL-fil. Disse kan lastes ned ved å trykke "Download".

    *(Dersom nettleseren navngir filen med en tilfeldig, meningsløs tekststreng, husk å døp om filnavnet ved nedlasting, f.eks. "konkordanser-nettavis-ungdom_OR_ungdomm_.xlsx")*
    """)
    return


@app.cell
def _(conc_ungdom):
    conc_ungdom["conc_id"] = conc_ungdom.index.astype(str).str.zfill(5)
    cols = ["conc_id", "dhlabid", "concordance"]

    conc_ungdom[cols].to_excel('../../export/konkordanser-nettavis-ungdom_OR_ungdomm_.xlsx', index=False)
    conc_ungdom[cols].to_json('../../export/konkordanser-nettavis-ungdom-OR-ungdomm_.jsonl', orient='records', lines=True)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # 3. Kollokasjoner med relativtfreks
    Kollokasjoner er ordpar som forekommer sammen. Ved å telle kollokasjoner for et gitt basisord kan vi si noe om hvor hyppig/sjelden ulike ord forekommer sammen med hverandre.

    En del ord alltid vil forekomme hyppig i alle tekster, slik som `og`, `han` og `hun`. For å finne ord som er signifikante innen en gitt kontekst kan vi beregne den relative frekvensen, der vi sammenlikner råfrekvensen i vårt eget korpus med frekvensen i et allment referansekorpus.

    Cellen under lister ordene med høyest relativfrekvens, gitt et nøkkelord i korpuset.
    """)
    return


@app.cell
def _(corpus, totals):
    tot = totals(75000) # Henter referansekorpus for å sammenlikne relativfrekvens
    coll = corpus.coll(
        words="ungdom",
        before=6,
        after=6,
        samplesize=75000
    ).frame.sort_values(by="counts", ascending=False) # Beregner kollokasjoner for basisordet "ungdom"
    (coll.counts / tot.freq).sort_values(ascending = False).head(40) # Beregner relativfrekvens for kollokasjoner ved å dele råfrekvensen i korpuset på råfrekvens i referansekorpuset
    return


if __name__ == "__main__":
    app.run()
