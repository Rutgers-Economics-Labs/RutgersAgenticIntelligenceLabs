import os
from collections import defaultdict

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from owlready2 import World
from pyvis.network import Network

st.set_page_config(page_title="RAIL Explorer", layout="wide")
st.title("Rutgers Agentic Intelligence Labs")

# --- Load ontology ---
db_path = "ontology/onto.db"
if not os.path.exists(db_path):
    st.error("Ontology database not found. Run: python hydrate.py")
    st.stop()


@st.cache_resource
def _load_ontology(path):
    """Open the quadstore once per server session; reused across all Streamlit reruns."""
    world = World()
    world.set_backend(filename=path)
    return world, world.get_ontology("http://example.org/rutgers_ontology.owl").load()


_world, onto = _load_ontology(db_path)

# --- Tabs ---
tab1, tab2 = st.tabs(["Ontology Explorer", "Data Analysis"])


# =============================================================================
# TAB 1: Ontology Explorer (existing behaviour, unchanged)
# =============================================================================
with tab1:
    st.sidebar.header("Search")
    search_term = st.sidebar.text_input("Search entities", placeholder="e.g. 'Alice', 'New Jersey'")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.header("Entities")
        TYPE_MAP = {
            "All": lambda: list(onto.individuals()),
            "State": lambda: list(onto.State.instances()),
            "County": lambda: list(onto.County.instances()),
            "Municipality": lambda: list(onto.Municipality.instances()),
            "Individual": lambda: list(onto.Individual.instances()),
        }
        entity_type = st.selectbox("Select Type", list(TYPE_MAP.keys()))
        entities = TYPE_MAP[entity_type]()

        if search_term:
            entities = [
                e for e in entities
                if search_term.lower() in str(e.name).lower()
                or (getattr(e, "hasName", None) and search_term.lower() in e.hasName.lower())
            ]

        selected_name = st.selectbox("Select Entity", [e.name for e in entities])
        selected = onto[selected_name] if selected_name else None

        if selected:
            st.subheader("Properties")
            st.write(f"**URI:** `{selected.iri}`")
            for attr, label, fmt in [
                ("hasName", "Name", "{}"),
                ("hasPopulation", "Population", "{:,}"),
                ("hasIncome", "Income", "${:,.2f}"),
                ("hasFIPS", "FIPS", "{}"),
            ]:
                val = getattr(selected, attr, None)
                if val:
                    st.write(f"**{label}:** {fmt.format(val)}")

            st.subheader("Relationships")
            for prop in selected.get_properties():
                for value in prop[selected]:
                    st.write(f"**{prop.python_name}:** {value.name if hasattr(value, 'name') else value}")

    with col2:
        st.header("Relationship Graph")
        if selected:
            net = Network(height="600px", width="100%", bgcolor="#1a1a2e", font_color="white", directed=True)
            net.add_node(selected.name, label=getattr(selected, "hasName", None) or selected.name,
                         color="#ff4b4b", size=30)

            for prop in selected.get_properties():
                values = prop[selected]
                if not isinstance(values, list):
                    values = [values]
                for val in values:
                    if hasattr(val, "name"):
                        net.add_node(val.name, label=getattr(val, "hasName", None) or val.name, color="#00acee")
                        net.add_edge(selected.name, val.name, label=prop.python_name)

            for prop, source in selected.get_inverse_properties():
                if hasattr(source, "name"):
                        net.add_node(source.name, label=getattr(source, "hasName", None) or source.name, color="#00acee")
                        net.add_edge(source.name, selected.name, label=prop.python_name)

            net.save_graph("graph.html")
            components.html(open("graph.html", encoding="utf-8").read(), height=600)
        else:
            st.info("Select an entity on the left to visualize its relationships.")


# =============================================================================
# TAB 2: Data Analysis
# =============================================================================
with tab2:
    st.header("Economic Indicators")

    # Find the Measure class (dynamically — works whether built from YAML or OWL)
    measure_class = next((c for c in onto.classes() if c.name == "Measure"), None)
    measures = list(measure_class.instances()) if measure_class else []

    if not measures:
        st.info("No indicator data found. Make sure the FRED steps ran in hydrate.py.")
        st.stop()

    # Group observations by series ID
    series_data = defaultdict(list)
    for m in measures:
        sid = getattr(m, "hasSeries", None)
        if sid:
            series_data[sid].append(m)

    SERIES_META = {
        "NJURN":            {"label": "NJ Unemployment Rate",       "unit": "%",      "freq": "Monthly"},
        "NJSTHPI":          {"label": "NJ House Price Index",        "unit": "Index",  "freq": "Quarterly"},
        "MEHOINUSNJA646N":  {"label": "NJ Median Household Income",  "unit": "$",      "freq": "Annual"},
    }

    # --- Summary cards (one per series) ---
    st.subheader("Overview")
    cols = st.columns(len(series_data))
    for col, sid in zip(cols, sorted(series_data)):
        ms = sorted(series_data[sid], key=lambda m: getattr(m, "hasDate", "") or "")
        vals = [m.hasValue for m in ms if m.hasValue is not None]
        meta = SERIES_META.get(sid, {"label": sid, "unit": "", "freq": ""})
        if vals:
            latest = vals[-1]
            prev   = vals[-2] if len(vals) > 1 else latest
            delta  = latest - prev
            col.metric(
                label=f"{meta['label']} ({meta['freq']})",
                value=f"{meta['unit']}{latest:,.2f}" if meta["unit"] == "$" else f"{latest:.2f}{meta['unit']}",
                delta=f"{delta:+.2f}",
            )

    st.divider()

    # --- Detailed view ---
    st.subheader("Series Detail")
    selected_sid = st.selectbox(
        "Select series",
        sorted(series_data.keys()),
        format_func=lambda x: SERIES_META.get(x, {}).get("label", x),
    )

    ms = sorted(series_data[selected_sid], key=lambda m: getattr(m, "hasDate", "") or "")
    df = pd.DataFrame(
        [{"Date": m.hasDate, "Value": m.hasValue} for m in ms if m.hasDate and m.hasValue is not None]
    )

    if df.empty:
        st.warning("No data points found for this series.")
    else:
        meta = SERIES_META.get(selected_sid, {"label": selected_sid, "unit": "", "freq": ""})
        values = df["Value"]

        # Stats row
        total_chg = ((values.iloc[-1] - values.iloc[0]) / values.iloc[0]) * 100
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Latest",        f"{values.iloc[-1]:.2f}")
        c2.metric("Mean",          f"{values.mean():.2f}")
        c3.metric("Min",           f"{values.min():.2f}")
        c4.metric("Max",           f"{values.max():.2f}")
        c5.metric("Total Change",  f"{total_chg:+.1f}%")

        # Chart
        st.line_chart(df.set_index("Date")["Value"], use_container_width=True)

        # Descriptive stats
        with st.expander("Descriptive Statistics"):
            desc = df["Value"].describe().rename("Value").to_frame()
            desc.index.name = "Stat"
            st.dataframe(desc.style.format("{:.4f}"), use_container_width=True)

        # Raw data table
        with st.expander("Raw Data"):
            st.dataframe(
                df.rename(columns={"Value": f"{meta['label']} ({meta['unit']})"}),
                use_container_width=True,
                height=300,
            )

    st.divider()

    # --- Cross-series comparison ---
    st.subheader("Compare Series")
    compare_sids = st.multiselect(
        "Select series to overlay",
        sorted(series_data.keys()),
        default=sorted(series_data.keys()),
        format_func=lambda x: SERIES_META.get(x, {}).get("label", x),
    )

    if compare_sids:
        frames = []
        for sid in compare_sids:
            ms2 = sorted(series_data[sid], key=lambda m: getattr(m, "hasDate", "") or "")
            tmp = pd.DataFrame(
                [{"Date": m.hasDate, SERIES_META.get(sid, {}).get("label", sid): m.hasValue}
                 for m in ms2 if m.hasDate and m.hasValue is not None]
            ).set_index("Date")
            frames.append(tmp)

        if frames:
            merged = pd.concat(frames, axis=1).sort_index()
            # Normalize to 100 at start for fair comparison
            normalized = (merged / merged.iloc[0]) * 100
            st.caption("Normalized to 100 at start date for comparability")
            st.line_chart(normalized, use_container_width=True)

st.markdown("---")
st.caption("Rutgers Agentic Intelligence Labs — 2026")
