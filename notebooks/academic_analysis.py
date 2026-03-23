"""
RAIL Academic Ontology — Jupyter Notebook Analysis
====================================================
Run this in a Jupyter notebook (each ## CELL block is one cell).

Setup:
    pip install -e packages/rail_client/
    pip install matplotlib scikit-learn pandas numpy

Usage:
    1. Trigger the academic_hydration pipeline from the Jobs page
    2. Copy the job ID from the URL (e.g. /jobs/jh7abc123...)
    3. Set JOB_ID and API_BASE below and run all cells
    4. Watch artifacts appear live on the job detail page in the UI
"""

# ── CELL 1: Connect ──────────────────────────────────────────────────────────

from rail_client import RailClient

# Paste your job ID from /jobs in the UI (or None to explore without attaching artifacts)
JOB_ID = None  # e.g. "jh7abc123def456"
API_BASE = "http://localhost:8000/api/v1"

client = RailClient(base_url=API_BASE, job_id=JOB_ID)
print("Connected to RAIL API")
print("Classes:", [c["name"] for c in client.ontology.classes()])


# ── CELL 2: Browse the ontology ───────────────────────────────────────────────

import pandas as pd

# List all classes with instance counts
classes_raw = client.ontology.classes()
classes_df = pd.DataFrame(classes_raw)
print(classes_df.to_string(index=False))


# ── CELL 3: Load faculty data ─────────────────────────────────────────────────

faculty_df = client.ontology.instances("Faculty")
print(f"Faculty loaded: {len(faculty_df)} rows")
print(faculty_df.columns.tolist())
faculty_df.head(10)


# ── CELL 4: Faculty h-index ranking ──────────────────────────────────────────

import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams["figure.facecolor"] = "#0d1117"
matplotlib.rcParams["axes.facecolor"] = "#161b22"
matplotlib.rcParams["text.color"] = "white"
matplotlib.rcParams["axes.labelcolor"] = "white"
matplotlib.rcParams["xtick.color"] = "white"
matplotlib.rcParams["ytick.color"] = "white"

# Clean and sort
faculty_plot = faculty_df[["hasName", "hasHIndex", "hasRank"]].dropna().copy()
faculty_plot["hasHIndex"] = pd.to_numeric(faculty_plot["hasHIndex"], errors="coerce")
faculty_plot = faculty_plot.dropna().sort_values("hasHIndex", ascending=True).tail(15)

fig, ax = plt.subplots(figsize=(10, 6))
colors = {
    "Full Professor": "#3fb950",
    "Associate Professor": "#58a6ff",
    "Assistant Professor": "#f0883e",
    "Emeritus": "#8b949e",
}
bar_colors = [colors.get(r, "#8b949e") for r in faculty_plot["hasRank"]]
bars = ax.barh(faculty_plot["hasName"], faculty_plot["hasHIndex"], color=bar_colors)
ax.set_xlabel("h-index")
ax.set_title("Top 15 Faculty by h-index", fontsize=13, pad=12)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Legend
for rank, color in colors.items():
    ax.barh([], [], color=color, label=rank)
ax.legend(loc="lower right", fontsize=8)

plt.tight_layout()

# Save to job — shows as image on job detail page
if JOB_ID:
    client.save_figure(fig, name="faculty_hindex_ranking")
    print("Saved figure to job")
plt.show()


# ── CELL 5: Publications by venue ────────────────────────────────────────────

pubs_df = client.ontology.instances("Publication")
print(f"Publications: {len(pubs_df)} rows")

pubs_df["hasCitationCount"] = pd.to_numeric(pubs_df.get("hasCitationCount", 0), errors="coerce").fillna(0)
pubs_df["hasYear"] = pd.to_numeric(pubs_df.get("hasYear", 0), errors="coerce").fillna(0)

venue_stats = (
    pubs_df.groupby("hasVenue")
    .agg(count=("_id", "count"), avg_citations=("hasCitationCount", "mean"))
    .sort_values("avg_citations", ascending=False)
    .reset_index()
)

fig2, ax2 = plt.subplots(figsize=(10, 5))
ax2.bar(venue_stats["hasVenue"], venue_stats["avg_citations"], color="#58a6ff", alpha=0.85)
ax2.set_xlabel("Venue")
ax2.set_ylabel("Avg Citations")
ax2.set_title("Average Citations by Publication Venue")
ax2.tick_params(axis="x", rotation=40)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)
plt.tight_layout()

if JOB_ID:
    client.save_figure(fig2, name="citations_by_venue")
plt.show()


# ── CELL 6: SQL queries ───────────────────────────────────────────────────────

# Top universities by number of faculty
top_unis = client.sql("""
    SELECT
        u.hasName AS university,
        COUNT(f._id) AS faculty_count,
        ROUND(AVG(CAST(f.hasHIndex AS DOUBLE)), 1) AS avg_h_index,
        MAX(CAST(f.hasHIndex AS INTEGER)) AS max_h_index
    FROM "Faculty" f
    JOIN "University" u ON f._id LIKE u._id || '%'
    GROUP BY u.hasName
    ORDER BY faculty_count DESC
""")
print("Faculty per university:")
print(top_unis.to_string(index=False))


# ── CELL 7: Publication trends over time ─────────────────────────────────────

pub_trends = client.sql("""
    SELECT
        hasYear AS year,
        COUNT(*) AS publications,
        ROUND(AVG(CAST(hasCitationCount AS DOUBLE)), 1) AS avg_citations
    FROM "Publication"
    WHERE hasYear IS NOT NULL AND CAST(hasYear AS INTEGER) > 2010
    GROUP BY hasYear
    ORDER BY hasYear
""")

fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

pub_trends["year"] = pub_trends["year"].astype(int)

ax3a.bar(pub_trends["year"], pub_trends["publications"], color="#3fb950", alpha=0.8)
ax3a.set_ylabel("Publications")
ax3a.set_title("Publication Output Over Time")
ax3a.spines["top"].set_visible(False)
ax3a.spines["right"].set_visible(False)

ax3b.plot(pub_trends["year"], pub_trends["avg_citations"], color="#f0883e", marker="o", linewidth=2)
ax3b.set_xlabel("Year")
ax3b.set_ylabel("Avg Citations")
ax3b.set_title("Average Citations by Year")
ax3b.spines["top"].set_visible(False)
ax3b.spines["right"].set_visible(False)

plt.tight_layout()
if JOB_ID:
    client.save_figure(fig3, name="publication_trends")
plt.show()


# ── CELL 8: ML model — predict h-index from rank + pub count ─────────────────

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import numpy as np

# Build features
model_df = faculty_df[["hasRank", "hasPublicationCount", "hasHIndex", "hasJoinYear"]].dropna().copy()
model_df["hasPublicationCount"] = pd.to_numeric(model_df["hasPublicationCount"], errors="coerce")
model_df["hasHIndex"] = pd.to_numeric(model_df["hasHIndex"], errors="coerce")
model_df["hasJoinYear"] = pd.to_numeric(model_df["hasJoinYear"], errors="coerce")
model_df = model_df.dropna()

# Years of experience proxy
model_df["years_experience"] = 2025 - model_df["hasJoinYear"]

# Encode rank
rank_map = {"Assistant Professor": 1, "Associate Professor": 2, "Full Professor": 3, "Emeritus": 4}
model_df["rank_encoded"] = model_df["hasRank"].map(rank_map).fillna(1)

X = model_df[["rank_encoded", "hasPublicationCount", "years_experience"]].values
y = model_df["hasHIndex"].values

if len(X) >= 10:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    reg = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    reg.fit(X_train, y_train)

    y_pred = reg.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)

    print(f"R² = {r2:.3f}  |  MAE = {mae:.2f} h-index points")

    # Feature importance plot
    fig4, ax4 = plt.subplots(figsize=(7, 4))
    features = ["Faculty Rank", "Publication Count", "Years Experience"]
    importances = reg.feature_importances_
    ax4.barh(features, importances, color="#a371f7")
    ax4.set_xlabel("Feature Importance")
    ax4.set_title("h-index Predictor — Feature Importance")
    ax4.spines["top"].set_visible(False)
    ax4.spines["right"].set_visible(False)
    plt.tight_layout()

    if JOB_ID:
        client.save_figure(fig4, name="feature_importance")
        client.save_model(reg, name="hindex_predictor")
        print("Saved model to job")
    plt.show()
else:
    print(f"Not enough data for ML ({len(X)} rows). Run the hydration pipeline to populate more data.")


# ── CELL 9: Save text summary ─────────────────────────────────────────────────

summary = f"""# Academic Ontology Analysis Summary

## Dataset
- Faculty: {len(faculty_df)} records
- Publications: {len(pubs_df)} records

## Key Findings

### Faculty h-index Distribution
- Mean h-index: {pd.to_numeric(faculty_df.get('hasHIndex', pd.Series()), errors='coerce').mean():.1f}
- Top venue by avg citations: {venue_stats.iloc[0]['hasVenue'] if len(venue_stats) > 0 else 'N/A'}

### Universities
{top_unis.to_string(index=False) if len(top_unis) > 0 else 'No data'}

## ML Model (h-index Predictor)
- R² = {r2:.3f}
- MAE = {mae:.2f} h-index points
- Most important feature: {features[importances.argmax()]}

Generated by rail_client SDK
"""

print(summary)
if JOB_ID:
    client.save_text(summary, name="analysis_summary.md")
    print(f"\nAll artifacts saved — view at: http://localhost:3000/jobs/{JOB_ID}")
