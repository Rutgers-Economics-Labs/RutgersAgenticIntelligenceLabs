import json
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

# --- Shared constants ---
NODE_COLORS = {
    "State":        "#F5A623",  # amber
    "County":       "#4A9EDD",  # blue
    "Municipality": "#50C878",  # green
    "Individual":   "#B07FD4",  # purple
    "Measure":      "#E05C5C",  # red
}

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Ontology Explorer", "Data Analysis", "Graph Explorer"])


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

# =============================================================================
# TAB 3: Graph Explorer — full Neo4j-style graph
# =============================================================================
with tab3:
    st.header("Graph Explorer")

    # --- Sidebar controls (scoped to this tab via unique keys) ---
    c_left, c_right = st.columns([1, 4])

    with c_left:
        st.subheader("Filters")
        show_types = st.multiselect(
            "Entity types",
            list(NODE_COLORS.keys()),
            default=["State", "County", "Municipality", "Individual"],
            key="graph_types",
        )
        show_edge_labels = st.toggle("Show edge labels", value=True, key="graph_edge_labels")
        size_by_pop = st.toggle("Size nodes by population", value=True, key="graph_size_pop")

        st.markdown("**Legend**")
        for t, color in NODE_COLORS.items():
            if t in show_types:
                st.markdown(
                    f"<span style='background:{color};border-radius:50%;display:inline-block;"
                    f"width:12px;height:12px;margin-right:6px'></span>{t}",
                    unsafe_allow_html=True,
                )

    with c_right:
        # Collect instances for each selected type
        all_nodes = {}   # uri_name -> {"ind": ind, "cls": cls_name}
        for cls_name in show_types:
            cls = next((c for c in onto.classes() if c.name == cls_name), None)
            if cls is None:
                continue
            for ind in cls.instances():
                all_nodes[ind.name] = {"ind": ind, "cls": cls_name}

        if not all_nodes:
            st.info("No entities found for selected types.")
        else:
            # Pre-compute population ranges per type for size normalization
            pop_ranges = {}
            for cls_name in show_types:
                pops = [
                    getattr(v["ind"], "hasPopulation", None)
                    for v in all_nodes.values()
                    if v["cls"] == cls_name and getattr(v["ind"], "hasPopulation", None) is not None
                ]
                if pops:
                    pop_ranges[cls_name] = (min(pops), max(pops))

            def node_size(cls_name, ind):
                SIZE_RANGE = {"State": (22, 55), "County": (10, 28), "Municipality": 14, "Individual": 12, "Measure": 8}
                base = SIZE_RANGE.get(cls_name, 12)
                if not size_by_pop or isinstance(base, int):
                    return base if isinstance(base, int) else base[0]
                pop = getattr(ind, "hasPopulation", None)
                if pop is None or cls_name not in pop_ranges:
                    return base[0]
                lo, hi = pop_ranges[cls_name]
                if hi == lo:
                    return (base[0] + base[1]) // 2
                return int(base[0] + (pop - lo) / (hi - lo) * (base[1] - base[0]))

            def node_tooltip(cls_name, ind):
                color = NODE_COLORS.get(cls_name, "#aaa")
                lines = [f"<b style='color:{color}'>{cls_name}</b>"]
                for attr, label, fmt in [
                    ("hasName",       "Name",       "{}"),
                    ("hasFIPS",       "FIPS",       "{}"),
                    ("hasPopulation", "Population", "{:,}"),
                    ("hasIncome",     "Income",     "${:,.0f}"),
                    ("hasValue",      "Value",      "{:.2f}"),
                    ("hasDate",       "Date",       "{}"),
                    ("hasSeries",     "Series",     "{}"),
                ]:
                    val = getattr(ind, attr, None)
                    if val is not None:
                        lines.append(f"<span style='color:#bbb'>{label}:</span> {fmt.format(val)}")
                return "<br>".join(lines)

            # Build pyvis graph
            net = Network(
                height="700px", width="100%",
                bgcolor="#0d1117", font_color="#e6edf3",
                directed=True, notebook=False,
            )

            for name, info in all_nodes.items():
                ind, cls_name = info["ind"], info["cls"]
                label = getattr(ind, "hasName", None) or ind.name
                net.add_node(
                    name,
                    label=label,
                    color={"background": NODE_COLORS.get(cls_name, "#aaa"),
                           "border": "#ffffff33",
                           "highlight": {"background": "#ffffff", "border": "#ffffff"},
                           "hover": {"background": "#ffffffcc", "border": "#ffffff"}},
                    size=node_size(cls_name, ind),
                    title=node_tooltip(cls_name, ind),
                    group=cls_name,
                    borderWidth=1,
                    borderWidthSelected=3,
                    font={"color": "#e6edf3", "size": 11},
                )

            # Add edges only between nodes that are both in the graph
            node_set = set(all_nodes.keys())
            seen_edges = set()
            for name, info in all_nodes.items():
                ind = info["ind"]
                for prop in ind.get_properties():
                    values = prop[ind]
                    if not isinstance(values, list):
                        values = [values] if values is not None else []
                    for val in values:
                        if hasattr(val, "name") and val.name in node_set:
                            edge_key = (name, val.name, prop.python_name)
                            if edge_key not in seen_edges:
                                seen_edges.add(edge_key)
                                net.add_edge(
                                    name, val.name,
                                    label=prop.python_name if show_edge_labels else "",
                                    color={"color": "#484f58", "highlight": "#adbac7", "hover": "#adbac7"},
                                    arrows={"to": {"enabled": True, "scaleFactor": 0.5}},
                                    font={"color": "#8b949e", "size": 9, "align": "middle"},
                                    smooth={"type": "dynamic"},
                                )

            net.set_options(json.dumps({
                "physics": {
                    "solver": "barnesHut",
                    "barnesHut": {
                        "gravitationalConstant": -6000,
                        "centralGravity": 0.3,
                        "springLength": 160,
                        "springConstant": 0.04,
                        "damping": 0.09,
                        "avoidOverlap": 0.4,
                    },
                    "stabilization": {"iterations": 200, "updateInterval": 25},
                    "maxVelocity": 50,
                    "minVelocity": 0.5,
                },
                "interaction": {
                    "hover": True,
                    "tooltipDelay": 80,
                    "navigationButtons": True,
                    "keyboard": True,
                    "multiselect": True,
                    "zoomView": True,
                },
                "nodes": {
                    "shadow": {"enabled": True, "size": 6, "x": 2, "y": 2},
                    "shape": "dot",
                },
                "edges": {
                    "shadow": False,
                    "width": 1.2,
                    "selectionWidth": 2.5,
                },
            }))

            net.save_graph("graph_full.html")
            graph_html = open("graph_full.html", encoding="utf-8").read()

            st.caption(
                f"Showing **{len(all_nodes):,}** nodes · **{len(seen_edges):,}** edges "
                f"— drag to pan, scroll to zoom, click to select"
            )
            components.html(graph_html, height=720, scrolling=False)


st.markdown("---")
st.caption("Rutgers Agentic Intelligence Labs — 2026")
