# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.1",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import polars as pl
    import plotly.express as px
    from pathlib import Path

    return mo, pl, px


@app.cell
def _(DATA_DIR):
    SENTIMENT_FIL = "../../export/nettavis-ungdom-sentiment-opus5_5.xlsx"
    MEDIER_FIL = "klassifisering_av_medier_PIS.xlsx"
    KORPUS_FIL = DATA_DIR / "../../export/korpus-nettavis-ungdom_OR_ungdomm_-nob_OR_nno-limit_100000.xlsx"

    REKKEVIDDE_REKKEFOLGE = ["Nasjonal", "Regional", "Lokal"]
    SENTIMENT_REKKEFOLGE = ["positiv", "nøytral", "negativ", "uklart", "ikke relevant"]
    FARGER = {
        "positiv": "#007867",
        "nøytral": "#ececec",
        "negativ": "#DE3155",
        "uklart": "#e9c46a",
        "ikke relevant": "#6c757d",
    }
    return (
        FARGER,
        KORPUS_FIL,
        MEDIER_FIL,
        REKKEVIDDE_REKKEFOLGE,
        SENTIMENT_FIL,
        SENTIMENT_REKKEFOLGE,
    )


@app.cell
def _(KORPUS_FIL, MEDIER_FIL, SENTIMENT_FIL, pl):
    # Sentiment: én rad per konkordanse
    sentiment = pl.read_excel(SENTIMENT_FIL, sheet_name="Konkordanser").select(
        "conc_id", "dhlabid", "nøkkelord", "sentiment", "label"
    )

    # Korpus: kobler dhlabid til tittel (strip fjerner f.eks. "Ny Tid " med mellomrom)
    korpus = pl.read_excel(KORPUS_FIL, columns=["dhlabid", "title", "year"]).select(
        "dhlabid", pl.col("title").str.strip_chars().alias("tittel"), "year"
    )

    # Medier: tittel -> rekkevidde (nederst i arket ligger forklaringstekst uten klassifisering)
    medier = (
        pl.read_excel(MEDIER_FIL, sheet_name="Medier")
        .filter(pl.col("Klassifisering").is_not_null())
        .select(
            pl.col("Medium").str.strip_chars().alias("tittel"),
            pl.col("Klassifisering").str.strip_chars().alias("rekkevidde"),
        )
    )
    return korpus, medier, sentiment


@app.cell
def _(korpus, medier, sentiment):
    data = sentiment.join(korpus, on="dhlabid", how="left").join(
        medier, on="tittel", how="left"
    )
    data
    return (data,)


@app.cell
def _(data, mo, pl):
    uten_tittel = data.filter(pl.col("tittel").is_null()).height
    uten_rekkevidde = data.filter(
        pl.col("tittel").is_not_null() & pl.col("rekkevidde").is_null()
    )
    mo.md(
        f"""
        **Kobling:** {data.height:,} konkordanser ·
        {uten_tittel:,} uten treff i korpus ·
        {uten_rekkevidde.height:,} uten rekkevidde
        {"(titler: " + ", ".join(uten_rekkevidde["tittel"].unique().to_list()) + ")" if uten_rekkevidde.height else ""}
        """
    )
    return


@app.cell
def _(SENTIMENT_REKKEFOLGE, mo):
    kategorier = mo.ui.multiselect(
        options=SENTIMENT_REKKEFOLGE,
        value=["positiv", "nøytral", "negativ"],
        label="Sentimentkategorier som inngår (andeler regnes av disse)",
    )
    uten_ungdomsorg = mo.ui.checkbox(
        value=False, label="Utelat konkordanser merket label=ungdomsorg"
    )
    mo.vstack([kategorier, uten_ungdomsorg])
    return kategorier, uten_ungdomsorg


@app.cell
def _(
    REKKEVIDDE_REKKEFOLGE,
    SENTIMENT_REKKEFOLGE,
    data,
    kategorier,
    pl,
    uten_ungdomsorg,
):
    utvalg = data.filter(
        pl.col("rekkevidde").is_not_null() & pl.col("sentiment").is_in(kategorier.value)
    )
    if uten_ungdomsorg.value:
        utvalg = utvalg.filter(pl.col("label").ne("ungdomsorg") | pl.col("label").is_null())

    # Antall og andel per rekkevidde x sentiment (andel innen hver rekkevidde)
    fordeling = (
        utvalg.group_by("rekkevidde", "sentiment")
        .agg(pl.len().alias("antall"))
        .with_columns(
            (pl.col("antall") / pl.col("antall").sum().over("rekkevidde")).alias("andel")
        )
        .with_columns(
            pl.col("rekkevidde").cast(pl.Enum(REKKEVIDDE_REKKEFOLGE)),
            pl.col("sentiment").cast(pl.Enum(SENTIMENT_REKKEFOLGE)),
        )
        .sort("rekkevidde", "sentiment")
    )
    return fordeling, utvalg


@app.cell
def _(fordeling, mo, pl):
    # Bred tabell: én rad per rekkevidde, antall og andel per kategori, pluss totalt
    bred = (
        fordeling.with_columns(
            pl.format(
                "{} ({}%)", pl.col("antall"), (pl.col("andel") * 100).round(1)
            ).alias("verdi")
        )
        .pivot(on="sentiment", index="rekkevidde", values="verdi")
        .join(
            fordeling.group_by("rekkevidde").agg(pl.col("antall").sum().alias("totalt")),
            on="rekkevidde",
        )
        .sort("rekkevidde")
    )
    mo.vstack([mo.md("### Antall (andel) per rekkevidde"), bred])
    return


@app.cell
def _(FARGER, fordeling, px):
    fig_andel = px.bar(
        fordeling,
        x="andel",
        y="rekkevidde",
        color="sentiment",
        orientation="h",
        color_discrete_map=FARGER,
        text=fordeling["andel"].map_elements(lambda v: f"{v:.0%}", return_dtype=str).to_list(),
        custom_data=["antall"],
        title="Andel sentiment etter publikasjonens rekkevidde",
    )
    fig_andel.update_traces(
        hovertemplate="%{y} · %{fullData.name}<br>Andel: %{x:.1%}<br>Antall: %{customdata[0]:,}<extra></extra>"
    )
    fig_andel.update_layout(
        barmode="stack",
        xaxis_tickformat=".0%",
        xaxis_title=None,
        yaxis_title=None,
        yaxis_autorange="reversed",
        legend_title=None,
    )
    fig_andel
    return


@app.cell
def _(FARGER, fordeling, px):
    fig_antall = px.bar(
        fordeling,
        x="rekkevidde",
        y="antall",
        color="sentiment",
        barmode="group",
        color_discrete_map=FARGER,
        title="Antall konkordanser per rekkevidde og sentiment",
    )
    fig_antall.update_layout(xaxis_title=None, yaxis_title="Antall", legend_title=None)
    fig_antall
    return


@app.cell
def _(mo, pl, utvalg):
    # Bonus: hvilke titler bidrar mest innen hver rekkevidde (for å se om én avis dominerer)
    topp_titler = (
        utvalg.group_by("rekkevidde", "tittel")
        .agg(
            pl.len().alias("antall"),
            (pl.col("sentiment") == "positiv").mean().alias("andel_positiv"),
            (pl.col("sentiment") == "negativ").mean().alias("andel_negativ"),
        )
        .sort("rekkevidde", "antall", descending=[False, True])
        .group_by("rekkevidde", maintain_order=True)
        .head(10)
    )
    mo.vstack([mo.md("### Ti største titler per rekkevidde"), topp_titler])
    return


if __name__ == "__main__":
    app.run()
