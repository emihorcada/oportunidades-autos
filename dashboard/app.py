import sys
import os
import re

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.travel_cost import estimate_travel_cost
from core.analyzer import evaluate_listing, analyze_listings, find_opportunities, categorize
from core.exchange_rate import get_usd_blue_rate
from core.aging import fetch_aging_days
from db.database import get_database

BA_PATTERN = re.compile(r"buenos aires|capital federal|caba|gba|ciudad aut", re.IGNORECASE)


def _is_local(location):
    """CABA or Buenos Aires province = local, no travel cost."""
    if not location:
        return True
    return bool(BA_PATTERN.search(location))


def load_data_v2():
    try:
        db = get_database()
        db.init()
        listings = pd.DataFrame(db.get_all_listings())
        references = pd.DataFrame(db.get_market_references())
        try:
            price_history = pd.DataFrame(db.get_price_history())
        except Exception:
            price_history = pd.DataFrame()
        db.close()
    except Exception as e:
        st.error(f"Error conectando a la base de datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    if listings.empty or references.empty:
        return listings, references, pd.DataFrame(), price_history

    # Evaluate each listing with the smart analyzer (version/transmission/km aware)
    listings_dicts = listings.to_dict("records")
    eval_results = []
    for lst in listings_dicts:
        result = evaluate_listing(lst, listings_dicts)
        if result:
            eval_results.append({**lst, **result})
        else:
            eval_results.append({**lst, "median_price_usd": None, "potential_profit_usd": None,
                                 "sample_count": None, "group_level": None, "category": None})

    merged = pd.DataFrame(eval_results)

    # Drop peer_prices column (lists can't be cached by Streamlit)
    if "peer_prices" in merged.columns:
        merged = merged.drop(columns=["peer_prices"])

    # Travel costs: only for locations outside CABA/Buenos Aires
    def _get_travel(loc):
        if _is_local(loc):
            return {"total_usd": 0, "detail": "Local (CABA/Bs.As.)", "needs_travel": False}
        return estimate_travel_cost(loc)

    travel_data = merged["location"].fillna("").apply(_get_travel)
    merged["travel_cost_usd"] = travel_data.apply(lambda x: x["total_usd"])
    merged["travel_detail"] = travel_data.apply(lambda x: x["detail"])
    merged["needs_travel"] = travel_data.apply(lambda x: x["needs_travel"])

    # Net profit and suggested sale price
    merged["net_profit_usd"] = merged["potential_profit_usd"] - merged["travel_cost_usd"]
    merged["suggested_price_usd"] = (merged["median_price_usd"] * 0.95).round(0)

    # Aging: use published_days_ago from DB (fetched from ML page)
    if "published_days_ago" in merged.columns:
        merged["aging_days"] = merged["published_days_ago"]
    else:
        merged["aging_days"] = None

    return listings, references, merged, price_history


def _build_css():
    return """
    <style>
    * { font-family: Arial, Helvetica, sans-serif; }
    .opp-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 13px;
        background: #ffffff;
        color: #222;
    }
    .opp-table th {
        background: #f5f5f5;
        padding: 10px 10px;
        text-align: left;
        border-bottom: 2px solid #ddd;
        position: sticky;
        top: 0;
        z-index: 2;
        font-size: 12px;
        color: #333;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        cursor: pointer;
        user-select: none;
    }
    .opp-table th:hover {
        background: #e8e8e8;
    }
    .opp-table th .sort-arrow {
        margin-left: 4px;
        font-size: 10px;
        color: #999;
    }
    .opp-table td {
        padding: 7px 10px;
        border-bottom: 1px solid #eee;
        vertical-align: middle;
    }
    .opp-table tr:hover {
        background: #f9f9f9;
    }

    /* --- Photo thumbnail + enlarged preview --- */
    .thumb-cell {
        position: relative;
    }
    .thumb-cell img.thumb {
        width: 72px;
        height: 50px;
        object-fit: cover;
        border-radius: 4px;
        border: 1px solid #ddd;
        cursor: pointer;
    }
    .thumb-cell .thumb-big {
        display: none;
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        z-index: 99999;
        max-width: 80vw;
        max-height: 75vh;
        object-fit: contain;
        border-radius: 10px;
        box-shadow: 0 8px 40px rgba(0,0,0,0.45);
    }
    .thumb-cell .thumb-backdrop {
        display: none;
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.5);
        z-index: 99998;
    }
    .thumb-cell:hover .thumb-big,
    .thumb-cell:hover .thumb-backdrop {
        display: block;
    }

    /* --- Tooltip via CSS --- */
    .tip {
        position: relative;
        cursor: help;
        border-bottom: 1px dotted #999;
    }
    .tip .tip-box {
        display: none;
        position: fixed;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        background: #fff;
        color: #222;
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 14px 18px;
        z-index: 90000;
        font-size: 13px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.2);
        line-height: 1.7;
        max-width: 380px;
        min-width: 200px;
    }
    .tip:hover .tip-box {
        display: block;
    }

    .profit-positive { color: #1a8a4a; font-weight: bold; }
    .profit-negative { color: #cc3333; font-weight: bold; }
    .suggested-price { color: #1a6dcc; font-weight: 600; }
    .local-badge { color: #999; font-size: 11px; }
    .comp-line { margin: 2px 0; padding: 2px 0; border-bottom: 1px solid #eee; }
    .comp-header { font-weight: 700; margin-bottom: 4px; color: #555; }
    </style>
    """


def _fmt(val):
    if val is None or pd.isna(val):
        return "—"
    return f"{val:,.0f}"


def _build_median_tooltip(row, all_data):
    """Build hover content showing comparable listings above this price."""
    brand = row.get("brand", "")
    model = row.get("model", "")
    year = row.get("year")
    price = row.get("price_usd", 0)
    median = row.get("median_price_usd", 0)

    if not brand or not model or not year:
        return ""

    # Find comparable listings (same brand+model+year, priced above this one)
    comps = all_data[
        (all_data["brand"] == brand) &
        (all_data["model"] == model) &
        (all_data["year"] == year) &
        (all_data["price_usd"] > price)
    ].sort_values("price_usd").head(5)

    group_level = row.get("group_level", "")
    level_label = {
        "versión + km": "misma versión, km similares",
        "transmisión + km": "misma transmisión, km similares",
        "modelo + km": "mismo modelo, km similares",
        "modelo": "mismo modelo (cualquier km)",
    }.get(group_level, group_level or "—")

    lines = [f'<div class="comp-header">Este auto: USD {_fmt(price)}</div>']
    lines.append(f'<div class="comp-header">Referencia: USD {_fmt(median)}</div>')
    lines.append(f'<div style="color:#666;font-size:11px;margin-bottom:4px">Comparado por: {level_label}</div>')
    lines.append(f'<div style="color:#666;font-size:11px;margin-bottom:4px">Se descartó el 20% más caro</div>')
    lines.append('<div style="margin-top:4px; font-weight:600; color:#1a8a4a">Otros similares publicados:</div>')

    if comps.empty:
        lines.append('<div class="comp-line" style="color:#999">Sin datos comparables</div>')
    else:
        for _, c in comps.iterrows():
            km_str = f"{int(c['km']):,} km" if pd.notna(c.get("km")) else "s/d km"
            src = c.get("source", "")
            comp_url = c.get("url", "") or ""
            if comp_url:
                lines.append(
                    f'<div class="comp-line"><a href="{comp_url}" target="_blank" '
                    f'style="color:#1a6dcc;text-decoration:none">'
                    f'USD {_fmt(c["price_usd"])} — {km_str} — {src}</a></div>'
                )
            else:
                lines.append(
                    f'<div class="comp-line">USD {_fmt(c["price_usd"])} — {km_str} — {src}</div>'
                )

    sample = row.get("sample_count", 0)
    if sample:
        lines.append(f'<div style="margin-top:4px;color:#999;font-size:11px">Basado en {int(sample)} publicaciones</div>')

    return "".join(lines)


def _build_price_change_html(source, source_id, price_history_df):
    """Build HTML for price change indicator with hover history."""
    if price_history_df.empty:
        return '<span style="color:#999;font-size:11px">—</span>'

    history = price_history_df[
        (price_history_df["source"] == source) &
        (price_history_df["source_id"] == source_id)
    ]

    if history.empty:
        return '<span style="color:#999;font-size:11px">—</span>'

    # Latest change
    latest = history.iloc[0]
    pct = latest.get("change_pct", 0) or 0

    if pct < 0:
        color = "#1a8a4a"
        arrow = "↓"
    elif pct > 0:
        color = "#cc3333"
        arrow = "↑"
    else:
        return '<span style="color:#999;font-size:11px">—</span>'

    # Build history tooltip
    lines = []
    for _, h in history.iterrows():
        date = str(h.get("recorded_at", ""))[:10]
        old_p = h.get("price_usd_old", 0) or 0
        new_p = h.get("price_usd_new", 0) or 0
        ch = h.get("change_pct", 0) or 0
        ch_color = "#1a8a4a" if ch < 0 else "#cc3333"
        lines.append(
            f'<div style="padding:2px 0;border-bottom:1px solid #eee">'
            f'{date}: USD {old_p:,.0f} → USD {new_p:,.0f} '
            f'<span style="color:{ch_color}">({ch:+.1f}%)</span></div>'
        )
    tip_content = "".join(lines)

    label = f"{arrow} {abs(pct):.0f}%"
    return (
        f'<span class="tip" style="color:{color};font-weight:bold">{label}'
        f'<span class="tip-box">'
        f'<div style="font-weight:700;margin-bottom:4px">Historial de precio</div>'
        f'{tip_content}</span></span>'
    )


def _build_opportunities_table(df, all_data, price_history_df=None):
    if price_history_df is None:
        price_history_df = pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        img_url = row.get("image_url", "") or ""
        url = row.get("url", "") or ""
        brand = row.get("brand", "")
        model = row.get("model", "")
        version = row.get("version", "")
        year = int(row["year"]) if pd.notna(row.get("year")) else ""
        km = _fmt(row.get("km"))
        price_usd = _fmt(row.get("price_usd"))
        median_usd = _fmt(row.get("median_price_usd"))
        location = row.get("location", "")
        source = row.get("source", "")
        category = row.get("category", "")
        travel_cost = row.get("travel_cost_usd", 0)
        travel_detail = row.get("travel_detail", "")
        needs_travel = row.get("needs_travel", False)
        net_profit = row.get("net_profit_usd", 0)
        suggested = _fmt(row.get("suggested_price_usd"))

        # Photo — click goes to listing, hide if broken
        if img_url:
            photo_html = (
                f'<a href="{url}" target="_blank">'
                f'<img style="width:72px;height:50px;object-fit:cover;border-radius:4px;border:1px solid #ddd" '
                f'src="{img_url}" alt="{brand} {model}" '
                f'onerror="this.style.display=\'none\';this.parentElement.innerHTML=\'<span style=color:#aaa;font-size:11px>Ver pub.</span>\'"></a>'
            )
        else:
            photo_html = f'<a href="{url}" target="_blank" style="color:#aaa;font-size:11px;text-decoration:none">Ver pub.</a>'

        # Median with tooltip
        median_tip = _build_median_tooltip(row, all_data)
        median_html = f'<span class="tip">USD {median_usd}<span class="tip-box">{median_tip}</span></span>'

        # Travel cost
        if needs_travel and travel_cost > 0:
            travel_html = f'<span class="tip">USD {travel_cost:,.0f}<span class="tip-box">{travel_detail}</span></span>'
        else:
            travel_html = '<span class="local-badge">—</span>'

        # Net profit
        profit_class = "profit-positive" if net_profit >= 1000 else "profit-negative"
        profit_html = f'<span class="{profit_class}">USD {_fmt(net_profit)}</span>'

        # Suggested sale price
        suggested_html = f'<span class="suggested-price">USD {suggested}</span>'

        # Price change indicator
        price_change_html = _build_price_change_html(source, row.get("source_id", ""), price_history_df)

        # Aging
        aging_raw = row.get("aging_days")
        if aging_raw is None or pd.isna(aging_raw):
            aging_html = '<span style="color:#999">s/d</span>'
        else:
            aging = int(aging_raw)
            if aging <= 3:
                aging_html = f'<span style="color:#1a8a4a;font-weight:600">{aging}d</span>'
            elif aging <= 14:
                aging_html = f'<span style="color:#1a8a4a">{aging}d</span>'
            elif aging <= 45:
                aging_html = f'<span style="color:#cc8800">{aging}d</span>'
            else:
                aging_html = f'<span style="color:#cc3333">{aging}d</span>'

        # Source with link
        source_html = f'<a href="{url}" target="_blank" style="color:#1a6dcc;text-decoration:none">{source}</a>'

        # Raw values for sorting
        raw_price = row.get("price_usd", 0) or 0
        raw_median = row.get("median_price_usd", 0) or 0
        raw_suggested = row.get("suggested_price_usd", 0) or 0
        raw_profit = net_profit or 0
        raw_travel = travel_cost or 0
        raw_km = row.get("km", 0) or 0
        raw_aging = int(aging_raw) if aging_raw is not None and not pd.isna(aging_raw) else 9999

        rows.append(f"""
        <tr>
            <td data-sort="0">{photo_html}</td>
            <td data-sort="{brand}">{brand}</td>
            <td data-sort="{model} {version}">{model} {version}</td>
            <td data-sort="{year}">{year}</td>
            <td data-sort="{raw_km}">{km}</td>
            <td data-sort="{raw_price}">USD {price_usd}</td>
            <td data-sort="0">{price_change_html}</td>
            <td data-sort="{raw_median}">{median_html}</td>
            <td data-sort="{raw_suggested}">{suggested_html}</td>
            <td data-sort="{raw_profit}">{profit_html}</td>
            <td data-sort="{location}">{location}</td>
            <td data-sort="{raw_travel}">{travel_html}</td>
            <td data-sort="{raw_aging}">{aging_html}</td>
            <td data-sort="{category}">{category}</td>
            <td data-sort="{source}">{source_html}</td>
        </tr>""")

    rows_html = "".join(rows)
    html = f"""
    <div style="height: calc(100vh - 280px); overflow-y: auto; border-radius: 6px; border: 1px solid #ddd;">
    <table class="opp-table">
        <thead>
            <tr>
                <th>Foto</th>
                <th>Marca</th>
                <th>Modelo</th>
                <th>Año</th>
                <th>Km</th>
                <th>Precio</th>
                <th>Var.</th>
                <th>Mediana</th>
                <th>Venderlo a</th>
                <th>Ganancia Neta</th>
                <th>Ubicación</th>
                <th>Costo Viaje</th>
                <th>Aging</th>
                <th>Categoría</th>
                <th>Fuente</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    </div>
    """
    html += """
    <script>
    (function() {
        var table = document.querySelector('.opp-table');
        if (!table) return;
        var headers = table.querySelectorAll('th');
        var sortState = {};
        headers.forEach(function(th, colIdx) {
            th.innerHTML = th.textContent + ' <span class="sort-arrow"></span>';
            th.addEventListener('click', function() {
                var tbody = table.querySelector('tbody');
                var rows = Array.from(tbody.querySelectorAll('tr'));
                var asc = sortState[colIdx] !== 'asc';
                sortState = {};
                sortState[colIdx] = asc ? 'asc' : 'desc';
                // Update arrows
                headers.forEach(function(h) {
                    h.querySelector('.sort-arrow').textContent = '';
                });
                th.querySelector('.sort-arrow').textContent = asc ? ' ▲' : ' ▼';
                rows.sort(function(a, b) {
                    var aVal = a.cells[colIdx].getAttribute('data-sort') || a.cells[colIdx].textContent;
                    var bVal = b.cells[colIdx].getAttribute('data-sort') || b.cells[colIdx].textContent;
                    var aNum = parseFloat(aVal);
                    var bNum = parseFloat(bVal);
                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return asc ? aNum - bNum : bNum - aNum;
                    }
                    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                });
                rows.forEach(function(row) { tbody.appendChild(row); });
            });
        });
    })();
    </script>
    """
    return html


def _run_scraper():
    """Run the full scraper pipeline from the dashboard."""
    from scrapers.mercadolibre import MercadoLibreScraper
    from scrapers.autocosmos import AutocosmosScraper
    import time

    db = get_database()
    db.init()

    progress = st.progress(0, text="Obteniendo tipo de cambio...")

    try:
        usd_rate = get_usd_blue_rate()
    except Exception as e:
        st.error(f"Error obteniendo dólar: {e}")
        return

    progress.progress(10, text=f"Dólar blue: ${usd_rate:,.0f}")

    # Scrape MercadoLibre
    all_listings = []
    progress.progress(15, text="Scrapeando MercadoLibre...")
    try:
        ml = MercadoLibreScraper(usd_rate)
        ml_listings = ml.scrape_all()
        all_listings.extend(ml_listings)
    except Exception as e:
        st.warning(f"MercadoLibre falló: {e}")

    progress.progress(45, text=f"ML: {len(all_listings)} listings. Scrapeando Autocosmos...")

    # Scrape Autocosmos
    try:
        ac = AutocosmosScraper(usd_rate)
        ac_listings = ac.scrape_all()
        all_listings.extend(ac_listings)
    except Exception as e:
        st.warning(f"Autocosmos falló: {e}")

    progress.progress(70, text=f"Total: {len(all_listings)} listings. Filtrando...")

    # Filter spam
    all_listings = [l for l in all_listings if l.get("price_usd") and l["price_usd"] >= 2000]

    # Analyze
    references = analyze_listings(all_listings)
    ref_map = {(r["brand"], r["model"], r["year"]): r for r in references}

    progress.progress(75, text="Detectando cambios de precio y guardando...")

    # Save to DB with price change detection
    saved = 0
    price_changes = 0
    for listing in all_listings:
        if not listing.get("year") or not listing.get("brand") or not listing.get("model"):
            continue
        key = (listing["brand"], listing["model"], listing["year"])
        ref = ref_map.get(key)
        if ref:
            listing["category"] = categorize(ref["median_price_usd"])

        # Detect price change
        new_usd = listing.get("price_usd")
        if new_usd:
            existing = db.get_listing(listing["source"], listing["source_id"])
            if existing and existing.get("price_usd"):
                old_usd = existing["price_usd"]
                if abs(old_usd - new_usd) > 1:
                    change_pct = round((new_usd - old_usd) / old_usd * 100, 1)
                    db.log_price_change(
                        listing["source"], listing["source_id"],
                        old_usd, new_usd,
                        existing.get("price_ars"), listing.get("price_ars"),
                        change_pct,
                    )
                    price_changes += 1

        db.upsert_listing(listing)
        saved += 1

    for ref in references:
        db.save_market_reference(ref)

    progress.progress(85, text=f"Guardados {saved}. Buscando aging...")

    # Fetch aging for ML opportunities
    opportunities = find_opportunities(all_listings, min_diff_usd=1000)
    ml_opps = [o for o in opportunities if o.get("source") == "mercadolibre" and o.get("url")]
    for i, opp in enumerate(ml_opps):
        days = fetch_aging_days(opp["url"])
        if days is not None:
            db.update_aging(opp["source"], opp["source_id"], days)
        time.sleep(1.5)

    db.close()
    progress.progress(100, text=f"Listo! {saved} listings, {len(opportunities)} oportunidades, {price_changes} cambios de precio")
    time.sleep(2)
    progress.empty()


def main():
    st.set_page_config(page_title="Detector de Oportunidades", layout="wide", initial_sidebar_state="collapsed")

    # Force light theme + full width
    st.html("""
    <style>
    * { font-family: Arial, Helvetica, sans-serif !important; }
    button[data-baseweb="tab"]:hover { background-color: #f0f0f0 !important; border-radius: 4px; }
    [data-testid="stSlider"] > div > div > div > div {
        background-color: #333 !important;
    }
    div[data-baseweb="select"] > div {
        border-color: #333 !important;
    }
    .block-container { max-width: 100% !important; padding-left: 2rem !important; padding-right: 2rem !important; padding-top: 2.5rem !important; }
    [data-testid="stMultiSelect"] ul[role="listbox"] { min-width: 320px !important; }
    .sticky-filters [data-testid="stMultiSelect"] label,
    .sticky-filters [data-testid="stMultiSelect"] [data-baseweb="tag"] span,
    .sticky-filters [data-testid="stMultiSelect"] input { font-size: 11px !important; }
    .sticky-filters [data-testid="stMultiSelect"] [data-baseweb="select"] > div { min-height: 34px !important; }
    .sticky-filters {
        position: sticky;
        top: 0;
        z-index: 100;
        background: #ffffff;
        padding: 8px 0 4px 0;
        border-bottom: 1px solid #e0e0e0;
        margin-bottom: 8px;
    }
    </style>
    <script>
    (function() {
        function makeStickyFilters() {
            var rows = document.querySelectorAll('[data-testid="stHorizontalBlock"]');
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var cols = row.querySelectorAll('[data-testid="column"]');
                if (cols.length === 9 && !row.classList.contains('sticky-filters')) {
                    row.classList.add('sticky-filters');
                }
            }
        }
        var observer = new MutationObserver(function() { makeStickyFilters(); applyLocationCount(); });
        observer.observe(document.body, { childList: true, subtree: true });
        makeStickyFilters();

        function applyLocationCount() {
            var multiselects = document.querySelectorAll('[data-testid="stMultiSelect"]');
            for (var i = 0; i < multiselects.length; i++) {
                var ms = multiselects[i];
                var label = ms.querySelector('label');
                if (!label || label.textContent.trim() !== 'Ubicación') continue;
                var tags = ms.querySelectorAll('[data-baseweb="tag"]');
                var countLabel = ms.querySelector('.loc-count-label');
                if (tags.length <= 1) {
                    if (countLabel) countLabel.remove();
                    for (var t = 0; t < tags.length; t++) tags[t].style.display = '';
                    continue;
                }
                for (var t = 0; t < tags.length; t++) tags[t].style.display = 'none';
                if (!countLabel) {
                    countLabel = document.createElement('div');
                    countLabel.className = 'loc-count-label';
                    countLabel.style.cssText = 'padding: 2px 8px; font-size: 14px; color: #333; font-weight: 500; pointer-events: none; white-space: nowrap;';
                    var inputContainer = ms.querySelector('[data-baseweb="select"] > div');
                    if (inputContainer) inputContainer.prepend(countLabel);
                }
                countLabel.textContent = tags.length + ' localidades';
            }
        }
        applyLocationCount();
    })();
    </script>
    """)

    st.title("Detector de Oportunidades de Autos")

    listings_df, references_df, merged_df, price_history_df = load_data_v2()

    # --- Main tabs ---
    main_tabs = st.tabs(["Oportunidades", "Calculadora de Precio", "Análisis de Mercado", "Metodología"])

    # ================================================================
    # TAB 1: OPORTUNIDADES
    # ================================================================
    with main_tabs[0]:
        if merged_df.empty:
            st.warning("No hay datos. Clickeá 'Actualizar datos'.")
        _render_opportunities_tab(listings_df, references_df, merged_df, price_history_df)

    # ================================================================
    # TAB 2: CALCULADORA DE PRECIO
    # ================================================================
    with main_tabs[1]:
        if merged_df.empty:
            st.info("Sin datos. Actualizá primero.")
        else:
            _render_price_calculator(merged_df)

    # ================================================================
    # TAB 3: ANÁLISIS DE MERCADO
    # ================================================================
    with main_tabs[2]:
        if not references_df.empty:
            _render_market_analysis(listings_df, references_df)

    # ================================================================
    # TAB 4: METODOLOGÍA
    # ================================================================
    with main_tabs[3]:
        _render_methodology()


def _render_opportunities_tab(listings_df, references_df, merged_df, price_history_df):
    # --- Update button ---
    btn_col1, btn_col2 = st.columns([6, 1])
    with btn_col2:
        if st.button("Actualizar datos", type="primary", use_container_width=True):
            _run_scraper()
            st.cache_data.clear()
            st.rerun()

    if merged_df.empty:
        return

    # --- Filters (single row) ---
    fc1, fc2, fc3, fc4, fc5, fc6, fc7, fc8, fc9 = st.columns([1, 1, 1, 1, 2, 2, 2, 2, 2])

    with fc1:
        categories = ["Todas"] + sorted(merged_df["category"].dropna().unique().tolist())
        selected_cat = st.selectbox("Categoría", categories, key="opp_cat")

    with fc2:
        brands = ["Todas"] + sorted(merged_df["brand"].dropna().unique().tolist())
        selected_brand = st.selectbox("Marca", brands, key="opp_brand")

    with fc3:
        if selected_brand != "Todas":
            models = ["Todos"] + sorted(
                merged_df[merged_df["brand"] == selected_brand]["model"].dropna().str.strip().unique().tolist()
            )
        else:
            models = ["Todos"] + sorted(merged_df["model"].dropna().str.strip().unique().tolist())
        selected_model = st.selectbox("Modelo", models, key="opp_model")

    with fc4:
        sources = ["Todas"] + sorted(merged_df["source"].dropna().unique().tolist())
        selected_source = st.selectbox("Fuente", sources, key="opp_source")

    with fc5:
        year_min = int(merged_df["year"].min()) if not merged_df["year"].isna().all() else 2016
        year_max = int(merged_df["year"].max()) if not merged_df["year"].isna().all() else 2026
        year_range = st.slider("Año", year_min, year_max, (year_min, year_max), key="opp_year")

    with fc6:
        km_max_val = int(merged_df["km"].max()) if not merged_df["km"].isna().all() else 200000
        km_range = st.slider("Kilómetros", 0, km_max_val, (0, km_max_val), key="opp_km")

    with fc7:
        price_max_val = int(merged_df["price_usd"].max()) if not merged_df["price_usd"].isna().all() else 100000
        price_range = st.slider("Precio", 0, price_max_val, (0, price_max_val), key="opp_price", format="USD %d")

    with fc8:
        min_profit = st.slider("Ganancia mínima neta", 500, 10000, 1000, step=250, key="opp_profit", format="USD %d")

    with fc9:
        all_locations = sorted(merged_df["location"].dropna().unique().tolist())
        prev_selected = st.session_state.get("opp_loc", [])
        sorted_locations = [x for x in prev_selected if x in all_locations] + [x for x in all_locations if x not in prev_selected]
        location_filter = st.multiselect("Ubicación", sorted_locations, placeholder="Todas", key="opp_loc")

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

    if location_filter:
        df = df[df["location"].isin(location_filter)]

    # --- Opportunities (using net profit) ---
    opportunities = df[df["net_profit_usd"] >= min_profit].sort_values(
        "net_profit_usd", ascending=False
    )

    # --- Opportunities Table ---
    st.subheader(f"Oportunidades ({len(opportunities)})")

    if not opportunities.empty:
        css = _build_css()
        table_html = _build_opportunities_table(opportunities, merged_df, price_history_df)
        st.html(css + table_html)
    else:
        st.info("No se encontraron oportunidades con los filtros seleccionados.")


def _render_price_calculator(merged_df):
    import numpy as np

    st.subheader("Calculadora de Precio de Venta")
    st.write("Ingresá los datos del auto que tu cliente quiere vender para calcular el precio sugerido.")

    # --- Inputs (outside form so dropdowns update dynamically) ---
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        brands = sorted(merged_df["brand"].dropna().unique().tolist())
        calc_brand = st.selectbox("Marca", brands, key="calc_brand")

    with c2:
        brand_models = sorted(
            merged_df[merged_df["brand"] == calc_brand]["model"].dropna().str.strip().unique().tolist()
        )
        calc_model = st.selectbox("Modelo", brand_models, key="calc_model")

    with c3:
        model_versions = sorted(
            merged_df[
                (merged_df["brand"] == calc_brand) & (merged_df["model"].str.strip() == calc_model)
            ]["version"].dropna().str.strip().unique().tolist()
        )
        if model_versions:
            calc_version = st.selectbox("Versión (opcional)", ["Cualquiera"] + model_versions, key="calc_version")
        else:
            calc_version = "Cualquiera"

    with c4:
        all_years = list(range(2026, 2005, -1))
        calc_year = st.selectbox("Año", all_years, key="calc_year")

    with c5:
        km_col1, km_col2 = st.columns(2)
        with km_col1:
            calc_km_min = st.number_input("Km desde", min_value=0, max_value=500000, value=20000, step=5000, key="calc_km_min")
        with km_col2:
            calc_km_max = st.number_input("Km hasta", min_value=0, max_value=500000, value=60000, step=5000, key="calc_km_max")

    commission_options = {
        "3% del precio de venta": 0.03,
        "5% del precio de venta": 0.05,
        "7% del precio de venta": 0.07,
        "10% del precio de venta": 0.10,
        "USD 300 fijo": 300,
        "USD 500 fijo": 500,
        "USD 750 fijo": 750,
        "USD 1.000 fijo": 1000,
    }
    cc1, cc2 = st.columns([2, 5])
    with cc1:
        commission_label = st.selectbox("Tu comisión", list(commission_options.keys()), key="calc_commission")

    # Store in session state so results persist
    if st.button("Calcular precio", type="primary"):
        st.session_state["calc_submitted"] = True
        st.session_state["calc_params"] = {
            "brand": calc_brand, "model": calc_model, "version": calc_version,
            "year": calc_year, "km_min": calc_km_min, "km_max": calc_km_max,
            "commission_label": commission_label,
        }

    if not st.session_state.get("calc_submitted"):
        return

    # Use stored params
    p = st.session_state["calc_params"]
    calc_brand = p["brand"]
    calc_model = p["model"]
    calc_version = p["version"]
    calc_year = p["year"]
    calc_km_min = p["km_min"]
    calc_km_max = p["km_max"]
    commission_label = p["commission_label"]

    commission_value = commission_options[commission_label]
    is_percentage = "%" in commission_label

    # --- Progressive filtering ---
    # Step 1: All listings of this brand + model
    all_model = merged_df[
        (merged_df["brand"] == calc_brand) &
        (merged_df["model"] == calc_model) &
        (merged_df["price_usd"].notna())
    ].copy()

    if len(all_model) == 0:
        st.warning(f"No hay publicaciones de {calc_brand} {calc_model} en la base de datos.")
        return

    # Step 2: Filter by year progressively
    comps = all_model[all_model["year"] == calc_year]
    if len(comps) < 3:
        comps = all_model[abs(all_model["year"] - calc_year) <= 1]
    if len(comps) < 3:
        comps = all_model[abs(all_model["year"] - calc_year) <= 2]
    if len(comps) < 3:
        comps = all_model

    # Step 3: Filter by version if enough data
    if calc_version != "Cualquiera":
        version_comps = comps[comps["version"] == calc_version]
        if len(version_comps) >= 3:
            comps = version_comps

    # Step 4: Filter by km range (user-defined)
    km_comps = comps[
        (comps["km"].notna()) &
        (comps["km"] >= calc_km_min) &
        (comps["km"] <= calc_km_max)
    ]
    if len(km_comps) >= 2:
        comps = km_comps

    # Build filter description
    year_range_used = f"{int(comps['year'].min())}-{int(comps['year'].max())}" if len(comps['year'].unique()) > 1 else str(int(comps['year'].iloc[0]))
    km_vals = comps["km"].dropna()
    km_range_used = f"{int(km_vals.min()):,}-{int(km_vals.max()):,} km" if not km_vals.empty else "s/d"

    if len(comps) < 2:
        st.warning(f"No hay suficientes datos comparables para {calc_brand} {calc_model}. Se encontró solo {len(comps)} publicación.")
        return

    prices = sorted(comps["price_usd"].tolist())

    # Remove top 20%
    import math
    cut = max(1, math.ceil(len(prices) * 0.20))
    filtered_prices = prices[:-cut] if len(prices) > 2 else prices

    p25 = float(np.percentile(filtered_prices, 25))
    p50 = float(np.median(filtered_prices))
    p75 = float(np.percentile(filtered_prices, 75))

    scenarios = {
        "Agresivo": {"price": round(p25), "desc": "Venta rápida (percentil 25)", "color": "#cc3333"},
        "Moderado": {"price": round(p50), "desc": "Precio equilibrado (mediana)", "color": "#cc8800"},
        "Conservador": {"price": round(p75), "desc": "Maximizar precio (percentil 75)", "color": "#1a8a4a"},
    }

    st.divider()
    st.subheader("Resultado")
    st.write(f"**{calc_brand} {calc_model} {calc_year}** — entre {calc_km_min:,} y {calc_km_max:,} km")
    st.write(f"Basado en **{len(comps)}** publicaciones comparables (años: {year_range_used}, km: {km_range_used}, se descartó el 20% más caro)")

    # Cards for each scenario
    cols = st.columns(3)
    for i, (name, data) in enumerate(scenarios.items()):
        price = data["price"]
        if is_percentage:
            commission = round(price * commission_value)
        else:
            commission = commission_value
        seller_gets = price - commission

        with cols[i]:
            st.html(f"""
            <div style="background: #f9f9f9; border-radius: 10px; padding: 20px; border-left: 5px solid {data['color']}; font-family: Arial, sans-serif;">
                <div style="font-size: 14px; color: #666; margin-bottom: 4px;">{name}</div>
                <div style="font-size: 11px; color: #999; margin-bottom: 12px;">{data['desc']}</div>
                <div style="font-size: 28px; font-weight: bold; color: {data['color']};">USD {price:,}</div>
                <div style="margin-top: 12px; font-size: 13px; color: #555;">
                    <div style="display:flex; justify-content:space-between; padding: 4px 0; border-bottom: 1px solid #eee;">
                        <span>Precio de venta</span><span><b>USD {price:,}</b></span>
                    </div>
                    <div style="display:flex; justify-content:space-between; padding: 4px 0; border-bottom: 1px solid #eee;">
                        <span>Tu comisión</span><span style="color:{data['color']}"><b>USD {commission:,}</b></span>
                    </div>
                    <div style="display:flex; justify-content:space-between; padding: 4px 0;">
                        <span>El vendedor recibe</span><span><b>USD {seller_gets:,}</b></span>
                    </div>
                </div>
            </div>
            """)

    # Show comparables table as HTML with clickable links
    st.divider()
    st.write(f"**Publicaciones comparables encontradas ({len(comps)}):**")
    comp_sorted = comps.sort_values("price_usd").reset_index(drop=True)
    comp_rows = []
    for _, c in comp_sorted.iterrows():
        c_url = c.get("url", "") or ""
        c_km = f"{int(c['km']):,}" if pd.notna(c.get("km")) else "s/d"
        c_price = f"{c['price_usd']:,.0f}" if pd.notna(c.get("price_usd")) else "s/d"
        c_year = int(c["year"]) if pd.notna(c.get("year")) else ""
        link_html = f'<a href="{c_url}" target="_blank" style="color:#1a6dcc">Ver</a>' if c_url else ""
        comp_rows.append(f"""<tr>
            <td>{c.get('brand','')}</td>
            <td>{c.get('model','')} {c.get('version','')}</td>
            <td>{c_year}</td>
            <td>{c_km}</td>
            <td>USD {c_price}</td>
            <td>{c.get('location','')}</td>
            <td>{c.get('source','')}</td>
            <td>{link_html}</td>
        </tr>""")
    comp_html = f"""
    <table style="width:100%;border-collapse:collapse;font-family:Arial;font-size:13px">
        <thead><tr style="background:#f5f5f5;border-bottom:2px solid #ddd;font-size:12px;color:#333">
            <th style="padding:8px;text-align:left">Marca</th>
            <th style="padding:8px;text-align:left">Modelo</th>
            <th style="padding:8px;text-align:left">Año</th>
            <th style="padding:8px;text-align:left">Km</th>
            <th style="padding:8px;text-align:left">Precio</th>
            <th style="padding:8px;text-align:left">Ubicación</th>
            <th style="padding:8px;text-align:left">Fuente</th>
            <th style="padding:8px;text-align:left">Link</th>
        </tr></thead>
        <tbody>{"".join(comp_rows)}</tbody>
    </table>"""
    st.html(comp_html)


def _render_market_analysis(listings_df, references_df):
    tab1, tab2 = st.tabs(["Precios por Modelo", "Publicaciones por Fuente"])

    with tab1:
        ref_display = references_df.sort_values("median_price_usd", ascending=False)
        ref_display = ref_display[["brand", "model", "year", "median_price_usd", "sample_count", "min_price_usd", "max_price_usd"]]
        ref_display.columns = ["Marca", "Modelo", "Año", "Mediana USD", "Muestras", "Mín USD", "Máx USD"]
        st.dataframe(
            ref_display,
            column_config={
                "Mediana USD": st.column_config.NumberColumn(format="%.0f"),
                "Mín USD": st.column_config.NumberColumn(format="%.0f"),
                "Máx USD": st.column_config.NumberColumn(format="%.0f"),
            },
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        source_counts = listings_df["source"].value_counts()
        st.bar_chart(source_counts)


def _render_methodology():
    st.html("""
    <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.8; max-width: 800px; font-size: 14px;">

    <h4 style="margin-top: 0;">1. Fuentes de datos</h4>
    <p>Se relevan publicaciones de <b>MercadoLibre</b> y <b>Autocosmos</b> para autos desde 2016 en Argentina.
    Se descartan publicaciones con precio menor a USD 2.000 (spam o consultas).</p>

    <h4>2. Agrupación inteligente (grupo de comparación)</h4>
    <p>Cada auto se compara contra un <b>grupo de pares</b> usando una lógica en cascada:</p>
    <ol>
        <li><b>Versión + km similares</b> — Mismo modelo, misma versión exacta (ej: "XEI 1.8 CVT"),
            y kilómetros dentro de ±20.000 km. Se usa si hay al menos 3 pares.</li>
        <li><b>Transmisión + km similares</b> — Si no hay suficientes de la misma versión,
            se agrupa por tipo de caja (manual/automática) con ±20.000 km.</li>
        <li><b>Modelo + km similares</b> — Mismo modelo y año, ±20.000 km, sin filtrar por versión.</li>
        <li><b>Modelo solo</b> — Último recurso: mismo modelo y año, cualquier kilometraje.</li>
    </ol>

    <h4>3. Filtro de precios inflados</h4>
    <p>Dentro del grupo de comparación, se <b>descarta el 20% más caro</b> antes de calcular la referencia.
    Esto elimina publicaciones con precios inflados que nunca se concretan.</p>

    <h4>4. Precio de referencia (Mediana)</h4>
    <p>Se calcula la <b>mediana</b> del grupo filtrado. La mediana es más robusta que el promedio:
    no se distorsiona con valores extremos.</p>

    <h4>5. Precio sugerido de venta ("Venderlo a")</h4>
    <p>Se calcula como el <b>95% de la mediana</b>: un precio competitivo que permite venta rápida
    sin regalar ganancia. Ejemplo: si la mediana es USD 20.000, el precio sugerido es USD 19.000.</p>

    <h4>6. Costo de viaje</h4>
    <p>Para autos en <b>CABA o provincia de Buenos Aires</b>, el costo de viaje es $0 (local).</p>
    <p>Para autos en otras provincias se estima:</p>
    <ul>
        <li><b>Transporte de ida</b>: micro (hasta 800 km) o avión (más de 800 km)</li>
        <li><b>Hotel</b>: 1 noche (USD 35) si la distancia supera 400 km</li>
        <li><b>Nafta de vuelta</b>: distancia × 10L/100km × USD 1/litro</li>
    </ul>

    <h4>7. Ganancia neta</h4>
    <p><b>Ganancia neta = Mediana − Precio publicado − Costo de viaje</b></p>
    <p>Un auto es <b>oportunidad</b> si la ganancia neta es ≥ USD 1.000.</p>

    <h4>8. Categorías</h4>
    <ul>
        <li><b>Alta gama</b>: mediana del grupo > USD 30.000</li>
        <li><b>Media</b>: mediana entre USD 10.000 y USD 30.000</li>
        <li><b>Baja</b>: mediana < USD 10.000</li>
    </ul>

    <h4>9. Conversión de moneda</h4>
    <p>Precios en ARS se convierten a USD usando el <b>dólar blue</b> (venta) de
    <a href="https://dolarapi.com" target="_blank" style="color:#1a6dcc">dolarapi.com</a>,
    consultado al momento del scraping.</p>

    </div>
    """)


if __name__ == "__main__":
    main()
