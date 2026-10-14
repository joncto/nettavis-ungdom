[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/notebooks/nb_SKvjqFZBJr7tYf7qSDf6xG)

# Omtale av ungdom i norske nettaviser (2019-22)

Dette repoet inneholder kode som benytter Nasjonalbibliotekets DH-lab API for å:
- definere korpus,
- hente konkordanser (lister med nøkkelord i kontekst)
- beregne relativt frekvente kollokater (assosierte ord)

Repoet har også kode for å:
- klassifisere sentiment for nøkkelord med bruk av store språkmodeller (Anthropic Opus 5.5)
- beregne og visualisere resultaterfor sentimentklassifisering

## Struktur

Ressursene er organisert logisk:

```
nettavis-ungdom/
├── export/
│   └── ...        # Output fra korpusdefinisjon, konkordanser og sentimentanalyse
└── notebooks/     # Notebook for analyse og eksperimenter
    └── 1_korpus_konkordanser_kollokasjoner
        └── ...        
    └── 2_sentimentklassifisering
        └── ...        
└── sentiment-opus5_5/
    └── ...        # Script for prompting av Opus 5.5 for sentimentanalyse
```

## Målsetning

Innen feltet ungdomsstudier hevdes det ofte at ungdom portretteres negativt i media.[^1] Samtidig har tidligere tester med en leksikon-basert sentimentanalyse av tekster fra norske nettaviser indikert et mer nyansert landskap av medienarrativer: ungdom ble stadig framstilt i et mer positivt lys enn forventet, noe som utfordrer en etablert antakelse om hvordan media framstiller ungdom.

Ved å analysere en samling av tekst publisert av norske nettaviser, tilgjengeliggjort gjennom Nasjonalbibliotekets (NB) DH-lab [^2], ønsker dette prosjektet å måle hvilken andel av disse tekstene som omtaler ungdom enten positivt, negativt eller nøytralt. Målet er å gjøre en skalerbar lesing som kombinerer fjernlesing og maskinell klassifikasjon med nærlesing av et utvalg data, både for kvalitetssikring og hjelp til tolkning av store datamengder, det vil si en form for "computational hermeneutics".[^3]

## Metodikk

### Definere korpus
For å beskjære korpus med relevante tekster benyttes DH-lab API for innhenting av tekster som gir treff på spørringen `doctype: nettavis AND fulltext: ungdom`.

#### Håndtering av nesten-duplikater
Mange dokumenter har blitt arkivert fra samme URI, og framstår som nesten-duplikater. For å utelukke muligheten av at disse tekstene forsterker visse signaler beholdes bare den tidligste versjonen av hver unike URI, mens seinere versjoner utelates.

### Henting av konkordanser
DH-lab API tillater å hente konkordanser, noe som gir en liste med tekstvinduer for nøkkelordet "ungdom" og dets umiddelbare kontekst (opptil 12 ord før og etter).

## Klassifisere sentiment med store språkmodeller
Konkordansene gis som input til en generative stor språkmodeller, sammen med insturksjoner for hvordan den skal klassifisere sentimentet for nøkkelordet.
Språkmodellen returnerer deretter en tabell med klassifisering ("positiv", "nøytral", "negativ") av hver enkelt konkordanse, samt en confidence score som indikerer hvor sikker språkmodellen er på sin klassifisering.




### Referanser
[^1]: Se f.eks. Seland & Hyggen (2022): "The digital generation: Representations of a generational digital divide". In *Generational Tensions and Solidarity Within Advanced Welfare States* (1st ed., Vol. 1, pp. 133–152). Routledge. [DOI:10.4324/9781003129592-11](https://doi.org/10.4324/9781003129592-11)
[^2]: Nasjonalbiblioteket (2026): *DH-lab*. [https://www.nb.no/dh-lab/digital-tekstanalyse/](https://www.nb.no/dh-lab/digital-tekstanalyse/)
[^3]: Armaselu & Fickers (2024): *Zoomland*. [DOI:10.1515/9783111317779](https://doi.org/10.1515/9783111317779)
