# Omtale av ungdom i norske nettaviser (2019-22)

Dette repoet inneholder kode som benytter Nasjonalbibliotekets DH-lab API for å:
- definere korpus,
- hente konkordanser (lister med nøkkelord i kontekst)
- beregne relativt frekvente kollokater (assosierte ord)
- klassifisere sentiment for nøkkelord med bruk av store språkmodeller (LLM)

Dette kan gjøres med to ulike verktøy:
- notebooks (brukeren kan redigere koden direkte)
- webapp (grafisk grensesnitt uten koderedigering)

## Struktur

Ressursene er organisert logisk:

```
webnews-youth-sentiment/
├── app/
│   └── ...        # Main application code
├── data/
│   └── ...        # Input datasets and intermediate files
├── drafts/
│   └── ...        # Initial notes, abstracts, etc
├── export/
│   └── ...        # Exported artifacts, visualizations, results
└── notebooks/
    └── ...        # Analysis and experimentation notebooks
```

## Målsetning

Innen feltet ungdomsstudier hevdes det ofte at ungdom portretteres negativt i media.[^1] Samtidig har tester med en leksikon-basert sentimentanalyse av tekster fra norske nettaviser indikert et mer nyansert landskap av medienarrativer: ungdom ble stadig framstilt i et mer positivt lys enn forventet, noe som utfordrer en etablert antakelse om hvordan media framstiller ungdom.

Leksikon-basert sentimentanalyse har noen kjente svakheter, siden de ikke gir mulighet for kontekst-spesifikke nyanser. For å utføre en mer nøyaktig klassifisering av hvordan "ungdom" har blitt portrettert benytter denne studien seg av store språkmodeller for sentimentklassifikasjon. Kvaliteten av resultatene vurderes deretter av menneskelige forskere, med mål om å gjøre en "skalerbar lesing"[^2] av resultatene, innenfor rammene av "computational hermeneutics".[^3]

## Metodikk

### Definere korpus
For å beskjære korpus med relevante tekster benyttes DH-lab API for innhenting av tekster som gir treff på spørringen `doctype: nettavis AND fulltext: ungdom`.

#### Håndtering av nesten-duplikater
Mange dokumenter har blitt arkivert fra samme URI, og framstår som nesten-duplikater. For å utelukke muligheten av at disse tekstene forsterker visse signaler beholdes bare den tidligste versjonen av hver unike URI, mens seinere versjoner utelates.

### Henting av konkordanser
DH-lab API tillater å hente konkordanser, noe som gir en liste med tekstvinduer for nøkkelordet "ungdom" og dets umiddelbare kontekst (opptil 12 ord før og etter).

## Kliassifisere sentiment med store språkmodeller
Konkordansene gis som input til en generative stor språkmodeller, sammen med insturksjoner for hvordan den skal klassifisere sentimentet for nøkkelordet.
Språkmodellen returnerer deretter en tabell med klassifisering ("positiv", "nøytral", "negativ") av hver enkelt konkordanse, samt en confidence score som indikerer hvor sikker språkmodellen er på sin klassifisering.
