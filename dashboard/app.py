import sqlite3
import streamlit as st
import pandas as pd

DB_PATH = "autos.db"


@st.cache_data(ttl=60)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    listings = pd.read_sql_query("SELECT * FROM listings", conn)
    references = pd.read_sql_query("SELECT * FROM market_reference", conn)
    conn.close()

    if listings.empty or references.empty:
        return listings, references, pd.DataFrame()

    merged = listings.merge(
        references[["brand", "model", "year", "median_price_usd", "sample_count"]],
        on=["brand", "model", "year"],
        how="left",
    )
    merged["potential_profit_usd"] = merged["median_price_usd"] - merged["price_usd"]
    return listings, references, merged


def main():
    st.set_page_config(page_title="Detector de Oportunidades", layout="wide")
    st.title("Detector de Oportunidades de Autos")

    listings_df, references_df, merged_df = load_data()

    if merged_df.empty:
        st.warning("No hay datos. Ejecuta `python run_scraper.py` primero.")
        return

    # --- Sidebar Filters ---
    st.sidebar.header("Filtros")

    categories = ["Todas"] + sorted(merged_df["category"].dropna().unique().tolist())
    selected_cat = st.sidebar.selectbox("Categoría", categories)

    brands = ["Todas"] + sorted(merged_df["brand"].dropna().unique().tolist())
    selected_brand = st.sidebar.selectbox("Marca", brands)

    if selected_brand != "Todas":
        models = ["Todos"] + sorted(
            merged_df[merged_df["brand"] == selected_brand]["model"].dropna().unique().tolist()
        )
    else:
        models = ["Todos"] + sorted(merged_df["model"].dropna().unique().tolist())
    selected_model = st.sidebar.selectbox("Modelo", models)

    year_min = int(merged_df["year"].min()) if not merged_df["year"].isna().all() else 2016
    year_max = int(merged_df["year"].max()) if not merged_df["year"].isna().all() else 2026
    year_range = st.sidebar.slider("Año", year_min, year_max, (year_min, year_max))

    km_max_val = int(merged_df["km"].max()) if not merged_df["km"].isna().all() else 200000
    km_range = st.sidebar.slider("Kilómetros", 0, km_max_val, (0, km_max_val))

    price_max_val = int(merged_df["price_usd"].max()) if not merged_df["price_usd"].isna().all() else 100000
    price_range = st.sidebar.slider("Precio USD", 0, price_max_val, (0, price_max_val))

    min_profit = st.sidebar.slider("Ganancia mínima USD", 500, 10000, 1000, step=250)

    sources = ["Todas"] + sorted(merged_df["source"].dropna().unique().tolist())
    selected_source = st.sidebar.selectbox("Fuente", sources)

    location_filter = st.sidebar.radio("Ubicación", ["Todas", "Buenos Aires", "Otras provincias"])

    # --- Apply Filters ---
    df = merged_df.copy()

    if selected_cat != "Todas":
        df = df[df["category"] == selected_cat.lower()]
    if selected_brand != "Todas":
        df = df[df["brand"] == selected_brand]
    if selected_model != "Todos":
        df = df[df["model"] == selected_model]
    if selected_source != "Todas":
        df = df[df["source"] == selected_source]

    df = df[
        (df["year"] >= year_range[0]) & (df["year"] <= year_range[1]) &
        (df["km"].fillna(0) >= km_range[0]) & (df["km"].fillna(0) <= km_range[1]) &
        (df["price_usd"].fillna(0) >= price_range[0]) & (df["price_usd"].fillna(0) <= price_range[1])
    ]

    if location_filter == "Buenos Aires":
        df = df[df["location"].str.contains("Buenos Aires|Capital Federal|CABA|GBA", case=False, na=False)]
    elif location_filter == "Otras provincias":
        df = df[~df["location"].str.contains("Buenos Aires|Capital Federal|CABA|GBA", case=False, na=False)]

    # --- Opportunities ---
    opportunities = df[df["potential_profit_usd"] >= min_profit].sort_values(
        "potential_profit_usd", ascending=False
    )

    # --- Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Publicaciones", f"{len(listings_df):,}")
    col2.metric("Oportunidades", f"{len(opportunities):,}")

    if not opportunities.empty:
        best = opportunities.iloc[0]
        col3.metric(
            "Mejor Oportunidad",
            f"USD {best['potential_profit_usd']:,.0f}",
            f"{best['brand']} {best['model']} {best['year']}"
        )
    else:
        col3.metric("Mejor Oportunidad", "—")

    last_scrape = listings_df["scraped_at"].max() if "scraped_at" in listings_df.columns else "—"
    col4.metric("Último Scraping", str(last_scrape)[:16] if last_scrape != "—" else "—")

    # --- Opportunities Table ---
    st.subheader(f"Oportunidades ({len(opportunities)})")

    if not opportunities.empty:
        display_cols = [
            "brand", "model", "version", "year", "km",
            "price_usd", "price_ars", "median_price_usd",
            "potential_profit_usd", "location", "source",
            "transmission", "fuel", "category", "url",
        ]
        display_df = opportunities[
            [c for c in display_cols if c in opportunities.columns]
        ].reset_index(drop=True)

        display_df.columns = [
            "Marca", "Modelo", "Versión", "Año", "Km",
            "Precio USD", "Precio ARS", "Mediana USD",
            "Ganancia USD", "Ubicación", "Fuente",
            "Transmisión", "Combustible", "Categoría", "Link",
        ][:len(display_df.columns)]

        st.dataframe(
            display_df,
            column_config={
                "Link": st.column_config.LinkColumn("Link"),
                "Precio USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Precio ARS": st.column_config.NumberColumn(format="$%,.0f"),
                "Mediana USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Ganancia USD": st.column_config.NumberColumn(format="$%,.0f"),
                "Km": st.column_config.NumberColumn(format="%,d"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No se encontraron oportunidades con los filtros seleccionados.")

    # --- Market Analysis Tab ---
    st.subheader("Análisis de Mercado")

    if not references_df.empty:
        tab1, tab2 = st.tabs(["Precios por Modelo", "Publicaciones por Fuente"])

        with tab1:
            ref_display = references_df.sort_values("median_price_usd", ascending=False)
            ref_display = ref_display[["brand", "model", "year", "median_price_usd", "sample_count", "min_price_usd", "max_price_usd"]]
            ref_display.columns = ["Marca", "Modelo", "Año", "Mediana USD", "Muestras", "Mín USD", "Máx USD"]
            st.dataframe(
                ref_display,
                column_config={
                    "Mediana USD": st.column_config.NumberColumn(format="$%,.0f"),
                    "Mín USD": st.column_config.NumberColumn(format="$%,.0f"),
                    "Máx USD": st.column_config.NumberColumn(format="$%,.0f"),
                },
                use_container_width=True,
                hide_index=True,
            )

        with tab2:
            source_counts = listings_df["source"].value_counts()
            st.bar_chart(source_counts)


if __name__ == "__main__":
    main()
