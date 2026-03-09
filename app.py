import json
import os
import re
import sys
from collections import defaultdict
from io import StringIO
import traceback

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from owlready2 import World, Thing, ObjectProperty, DataProperty
from pyvis.network import Network
from rdflib import Graph

from engine.ai_generator import generate_hydration_yaml
from engine.ai_analyst import generate_analysis_script

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
    # Find the first ontology in the world
    try:
        # Try a few common URIs or just the first one
        uri = "http://example.org/rutgers_ontology.owl"
        onto = world.get_ontology(uri).load()
    except:
        ontos = list(world.ontologies.values())
        if ontos:
            onto = ontos[0]
        else:
            owl_path = "ontology/populated_ontology.owl"
            if os.path.exists(owl_path):
                onto = world.get_ontology(f"file://{os.path.abspath(owl_path)}").load()
            else:
                raise Exception("Could not load any ontology.")
    return world, onto


_world, onto = _load_ontology(db_path)

# --- Analysis section renderer ---
def _render_section(sec):
    sec_type = sec.get("type")
    title = sec.get("title")
    if title:
        st.subheader(title)

    if sec_type == "table":
        data = sec.get("data")
        if data is not None and not data.empty:
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.caption("No data.")

    elif sec_type == "metrics":
        items = sec.get("items", [])
        cols = st.columns(max(len(items), 1))
        for col, item in zip(cols, items):
            col.metric(item.get("label", ""), item.get("value", ""))

    elif sec_type == "chart":
        data = sec.get("data")
        if data is not None and not data.empty:
            x = sec.get("x", data.columns[0])
            y = sec.get("y", data.columns[1])
            st.line_chart(data.set_index(x)[y], use_container_width=True)

    elif sec_type == "text":
        st.markdown(sec.get("content", ""))

    elif sec_type == "divider":
        st.divider()

    elif sec_type == "group":
        for item in sec.get("items", []):
            _render_section(item)


# --- Shared constants ---
NODE_COLORS = {
    "State":        "#F5A623",  # amber
    "County":       "#4A9EDD",  # blue
    "Municipality": "#50C878",  # green
    "Individual":   "#B07FD4",  # purple
    "Measure":      "#E05C5C",  # red
}

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Ontology Explorer",
    "Data Analysis",
    "Graph Explorer",
    "Analysis",
    "Data Studio",
    "Query Console",
    "AI Analyst"
])


# =============================================================================
# TAB 1: Ontology Explorer (Palantir style)
# =============================================================================
with tab1:
    st.sidebar.header("Search & Filter")
    search_term = st.sidebar.text_input("Global Search", placeholder="e.g. 'Alice', 'New Jersey'")

    # Advanced Filtering
    with st.sidebar.expander("Advanced Filters"):
        all_classes = [c.name for c in onto.classes()]
        filter_class = st.multiselect("Filter by Class", all_classes, default=all_classes)

        # Numeric range filters (e.g., Population)
        min_pop = st.number_input("Min Population", value=0)
        max_pop = st.number_input("Max Population", value=20000000)

    col1, col2 = st.columns([1, 2])

    with col1:
        st.header("Object Explorer")

        # Get all individuals filtered
        entities = list(onto.individuals())
        if filter_class:
            entities = [e for e in entities if any(isinstance(e, getattr(onto, c, type(None))) for c in filter_class)]

        if search_term:
            entities = [
                e for e in entities
                if search_term.lower() in str(e.name).lower()
                or (getattr(e, "hasName", None) and search_term.lower() in str(e.hasName).lower())
            ]

        # Pop filter
        entities = [e for e in entities if (getattr(e, "hasPopulation", None) is None or (min_pop <= (getattr(e, "hasPopulation", 0) or 0) <= max_pop))]

        st.write(f"Showing **{len(entities)}** objects")

        sorted_entities = sorted(entities, key=lambda x: str(getattr(x, "hasName", x.name)) or "")
        selected_name = st.selectbox("Select Object", [e.name for e in sorted_entities])
        selected = onto[selected_name] if selected_name else None

        if selected:
            st.divider()
            st.subheader(f"Object View: {getattr(selected, 'hasName', selected.name)}")
            st.caption(f"Type: {selected.__class__.name}")
            st.write(f"**URI:** `{selected.iri}`")

            # Group properties into Data and Object
            data_props = []
            obj_props = []
            for prop in selected.get_properties():
                if issubclass(prop, DataProperty):
                    data_props.append(prop)
                elif issubclass(prop, ObjectProperty):
                    obj_props.append(prop)

            with st.expander("Data Properties", expanded=True):
                for prop in data_props:
                    val = getattr(selected, prop.python_name)
                    st.write(f"**{prop.python_name}:** {val}")

            with st.expander("Relationships", expanded=True):
                for prop in obj_props:
                    vals = getattr(selected, prop.python_name)
                    if not isinstance(vals, list): vals = [vals]
                    for val in vals:
                        if hasattr(val, "name"):
                            st.write(f"**{prop.python_name}:** {val.name} ({val.__class__.name})")

    with col2:
        st.header("Interactions & Context")
        if selected:
            # mini graph for selected object
            net = Network(height="500px", width="100%", bgcolor="#0d1117", font_color="white", directed=True)
            net.add_node(selected.name, label=getattr(selected, "hasName", None) or selected.name,
                         color="#ff4b4b", size=25, title=f"Selected: {selected.name}")

            for prop in selected.get_properties():
                values = prop[selected]
                if not isinstance(values, list):
                    values = [values]
                for val in values:
                    if hasattr(val, "name"):
                        net.add_node(val.name, label=getattr(val, "hasName", None) or val.name,
                                     color=NODE_COLORS.get(val.__class__.name, "#00acee"), size=20)
                        net.add_edge(selected.name, val.name, label=getattr(prop, "python_name", prop.name))

            for prop, source in selected.get_inverse_properties():
                if hasattr(source, "name"):
                    net.add_node(source.name, label=getattr(source, "hasName", None) or source.name,
                                 color=NODE_COLORS.get(source.__class__.name, "#00acee"), size=20)
                    net.add_edge(source.name, selected.name, label=getattr(prop, "python_name", prop.name))

            net.save_graph("graph.html")
            components.html(open("graph.html", encoding="utf-8").read(), height=550)

            # Class-specific views (e.g. State overview)
            if selected.__class__.name == "State":
                st.subheader("State Statistics")
                if hasattr(onto, "County"):
                    counties = [c for c in onto.County.instances() if getattr(c, "isPartOf", None) == selected]
                    st.metric("Total Counties", len(counties))
                    if counties:
                        pop_df = pd.DataFrame([{
                            "County": getattr(c, "hasName", c.name),
                            "Population": getattr(c, "hasPopulation", 0)
                        } for c in counties]).sort_values("Population", ascending=False)
                        st.bar_chart(pop_df.set_index("County")["Population"])


# =============================================================================
# TAB 2: Generalized Data Analysis
# =============================================================================
with tab2:
    st.header("Dynamic Indicator Analysis")

    # Auto-detect all instances with numeric values or time-series data
    measure_cls = getattr(onto, "Measure", None)
    all_measures = list(measure_cls.instances()) if measure_cls else []

    if not all_measures:
        st.info("No numeric measure data found.")
    else:
        # Group measures by 'hasSeries' or similar categorization
        series_map = defaultdict(list)
        for m in all_measures:
            sid = getattr(m, "hasSeries", "General")
            series_map[sid].append(m)

        selected_series = st.selectbox("Select Indicator Series", sorted(series_map.keys()))

        measures = sorted(series_map[selected_series], key=lambda x: getattr(x, "hasDate", "") or "")

        # Prepare Dataframe
        data_list = []
        for m in measures:
            target = getattr(m, "measuredFor", None)
            if isinstance(target, list): target = target[0] if target else None
            data_list.append({
                "Date": getattr(m, "hasDate", "N/A"),
                "Value": getattr(m, "hasValue", 0),
                "Entity": getattr(target, "hasName", target.name) if target else "Unknown"
            })

        df = pd.DataFrame(data_list)

        entities = df["Entity"].unique()
        selected_entity = st.multiselect("Filter by Entity", entities, default=entities[:5])

        filtered_df = df[df["Entity"].isin(selected_entity)]

        if not filtered_df.empty:
            st.line_chart(filtered_df.pivot_table(index="Date", columns="Entity", values="Value"))
            st.dataframe(filtered_df)
        else:
            st.write("No data for selected filters.")


# =============================================================================
# TAB 3: Graph Explorer
# =============================================================================
with tab3:
    st.header("Graph Explorer")

    c_left, c_right = st.columns([1, 4])

    def _first(val):
        if isinstance(val, list):
            return val[0] if val else None
        return val

    with c_left:
        st.subheader("Filters")
        show_types = st.multiselect(
            "Entity types",
            list(NODE_COLORS.keys()),
            default=["State", "County", "Municipality", "Individual"],
            key="graph_types",
        )

        focus_state_ind = None
        if any(t in show_types for t in ("County", "Municipality")):
            state_cls = next((c for c in onto.classes() if c.name == "State"), None)
            if state_cls:
                state_opts = sorted(
                    [(ind, getattr(ind, "hasName", None) or ind.name)
                     for ind in state_cls.instances()],
                    key=lambda x: str(x[1]),
                )
                state_labels = ["— All states (no municipalities) —"] + [str(lbl) for _, lbl in state_opts]
                state_inds   = [None] + [ind for ind, _ in state_opts]
                nj_default = next(
                    (i for i, lbl in enumerate(state_labels) if "New Jersey" in lbl), 0
                )
                focus_idx = st.selectbox(
                    "Focus on state",
                    range(len(state_labels)),
                    format_func=lambda i: state_labels[i],
                    index=nj_default,
                    key="graph_state_filter",
                )
                focus_state_ind = state_inds[focus_idx]

        show_edge_labels = st.toggle("Show edge labels", value=True, key="graph_edge_labels")
        size_by_pop = st.toggle("Size nodes by population", value=True, key="graph_size_pop")

    with c_right:
        focus_county_set = None
        if focus_state_ind is not None:
            county_cls = next((c for c in onto.classes() if c.name == "County"), None)
            if county_cls:
                focus_county_set = {
                    ind for ind in county_cls.instances()
                    if _first(getattr(ind, "isPartOf", None)) == focus_state_ind
                }

        all_nodes = {}
        for cls_name in show_types:
            cls = getattr(onto, cls_name, None)
            if cls is None: continue
            for ind in cls.instances():
                if focus_state_ind is not None:
                    if cls_name == "County":
                        if _first(getattr(ind, "isPartOf", None)) != focus_state_ind: continue
                    elif cls_name == "Municipality":
                        if focus_county_set is None or _first(getattr(ind, "isPartOf", None)) not in focus_county_set: continue
                elif cls_name == "Municipality": continue
                all_nodes[ind.name] = {"ind": ind, "cls": cls_name}

        if all_nodes:
            net = Network(height="700px", width="100%", bgcolor="#0d1117", font_color="#e6edf3", directed=True)
            for name, info in all_nodes.items():
                label = getattr(info["ind"], "hasName", None) or name
                net.add_node(name, label=label, color=NODE_COLORS.get(info["cls"], "#aaa"))

            node_set = set(all_nodes.keys())
            for name, info in all_nodes.items():
                ind = info["ind"]
                for prop in ind.get_properties():
                    values = prop[ind]
                    if not isinstance(values, list): values = [values]
                    for val in values:
                        if hasattr(val, "name") and val.name in node_set:
                            net.add_edge(name, val.name, label=prop.python_name if show_edge_labels else "")

            net.save_graph("graph_full.html")
            components.html(open("graph_full.html", encoding="utf-8").read(), height=720)


# =============================================================================
# TAB 4: Analysis Plugins
# =============================================================================
with tab4:
    from engine.analysis_runner import discover as _discover_analyses
    st.header("Analysis Plugins")
    modules = _discover_analyses()
    if modules:
        selected_mod = st.selectbox("Module", list(modules.keys()))
        if st.button("Run Plugin"):
            result = modules[selected_mod].analyze(onto)
            for sec in result.get("sections", []):
                _render_section(sec)


# =============================================================================
# TAB 5: Data Studio (AI-Assisted Hydration)
# =============================================================================
with tab5:
    st.header("Data Studio")
    st.write("Onboard new data sources using AI. Upload a file or provide documentation.")

    source_type = st.radio("Source Type", ["CSV/Excel", "API Documentation"])
    content = ""
    content_type = ""

    if source_type == "CSV/Excel":
        uploaded_file = st.file_uploader("Upload sample data", type=["csv", "xlsx"])
        if uploaded_file:
            if uploaded_file.name.endswith('.csv'):
                sample_df = pd.read_csv(uploaded_file, nrows=10)
            else:
                sample_df = pd.read_excel(uploaded_file, nrows=10)
            st.write("Data Sample:")
            st.dataframe(sample_df)
            content = sample_df.to_csv(index=False)
            content_type = "csv"
    else:
        api_docs = st.text_area("Paste API Documentation or JSON Response Sample")
        content = api_docs
        content_type = "api_docs"

    if st.button("Generate RAIL Configuration"):
        if not content:
            st.error("Please provide data content.")
        else:
            with st.spinner("AI is analyzing and generating YAML..."):
                with open("configs/ontology/core.yaml") as f:
                    onto_spec = f.read()

                try:
                    result_raw = generate_hydration_yaml(content, content_type, onto_spec)
                    json_str = result_raw.strip()
                    if json_str.startswith("```json"): json_str = json_str[7:]
                    if json_str.endswith("```"): json_str = json_str[:-3]

                    res_obj = json.loads(json_str)

                    st.success("Configuration Generated!")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.subheader("API Config")
                        st.code(res_obj['api_config'], language='yaml')
                    with col_b:
                        st.subheader("Pipeline Step")
                        st.code(res_obj['pipeline_step'], language='yaml')
                except Exception as e:
                    st.error(f"Generation failed: {e}")
                    st.write(result_raw)


# =============================================================================
# TAB 6: Query Console
# =============================================================================
with tab6:
    st.header("Query Console")

    mode = st.radio("Engine Mode", ["Analysis Mode (Read-Only)", "Cleaning Mode (Read-Write)"])
    lang = st.radio("Language", ["Python", "SPARQL"])

    query = st.text_area("Enter your query", height=200, placeholder="Python: [i.name for i in onto.individuals()]\nSPARQL: SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10")

    if st.button("Execute Query"):
        if lang == "Python":
            try:
                context = {"onto": onto, "_world": _world, "pd": pd, "st": st}
                old_stdout = sys.stdout
                sys.stdout = StringIO()

                try:
                    res = eval(query, context)
                    st.write("Result:")
                    st.write(res)
                except SyntaxError:
                    exec(query, context)
                    st.write("Execution complete.")

                out = sys.stdout.getvalue()
                sys.stdout = old_stdout
                if out:
                    st.subheader("Standard Output:")
                    st.text(out)

                if mode == "Cleaning Mode (Read-Write)":
                    _world.save()
                    st.success("Changes saved.")
            except Exception:
                st.error("Execution Error")
                st.code(traceback.format_exc())
        else:
            try:
                graph = _world.as_rdflib_graph()
                qres = graph.query(query)
                df_res = pd.DataFrame([list(r) for r in qres], columns=[str(var) for var in qres.vars])
                st.write("SPARQL Results:")
                st.dataframe(df_res)
            except Exception:
                st.error("SPARQL Error")
                st.code(traceback.format_exc())


# =============================================================================
# TAB 7: AI Analyst
# =============================================================================
with tab7:
    st.header("AI Analyst")
    st.write("Ask questions about the data in natural language.")

    user_q = st.text_input("Question", placeholder="How many municipalities have a population over 100,000?")

    if st.button("Analyze"):
        if user_q:
            with st.spinner("AI Analyst is thinking..."):
                with open("configs/ontology/core.yaml") as f:
                    onto_spec = f.read()

                try:
                    script = generate_analysis_script(user_q, onto_spec)
                    st.subheader("Generated Analysis Script")
                    st.code(script, language='python')

                    st.subheader("Analysis Results")
                    context = {"onto": onto, "_world": _world, "pd": pd, "st": st}
                    exec(script, context)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    st.code(traceback.format_exc())

st.markdown("---")
st.caption("Rutgers Agentic Intelligence Labs — 2026")
