export type AnalysisTemplate = {
  id: string;
  label: string;
  category: "descriptive" | "regression" | "causal" | "timeseries" | "clustering";
  description: string;
  prompt: string;
  code?: string;
};

export const ANALYSIS_TEMPLATES: AnalysisTemplate[] = [
  {
    id: "describe-table",
    label: "Describe a table",
    category: "descriptive",
    description: "Summarize columns, missingness, and distribution.",
    prompt: "Describe the most relevant table in the schema, summarize its columns, missing values, and key descriptive statistics, and use execute_python if useful.",
  },
  {
    id: "top-n",
    label: "Top N entities",
    category: "descriptive",
    description: "Rank entities by a meaningful numeric column.",
    prompt: "Find the most relevant entity table and rank the top 10 rows by an important numeric column. Explain the result and use SQL or execute_python as needed.",
  },
  {
    id: "correlation-matrix",
    label: "Correlation matrix",
    category: "descriptive",
    description: "Compute correlations across numeric features.",
    prompt: "Identify a table with multiple numeric columns and compute a correlation matrix. Use execute_python and explain which relationships stand out.",
  },
  {
    id: "ols-regression",
    label: "OLS regression",
    category: "regression",
    description: "Run a simple linear model with interpretation.",
    prompt: "Choose a sensible outcome and predictors from the schema, run an OLS regression with execute_python, and interpret the coefficients in plain English.",
  },
  {
    id: "panel-fe",
    label: "Panel regression (FE)",
    category: "regression",
    description: "Set up a fixed-effects style panel model.",
    prompt: "If the schema supports repeated observations over time, build a panel dataset and run a fixed-effects style regression with execute_python. Explain assumptions and limitations.",
  },
  {
    id: "did-basic",
    label: "Difference-in-differences",
    category: "causal",
    description: "Draft a basic DiD analysis from available panel data.",
    prompt: "If the schema supports treatment timing and repeated outcomes, set up a basic difference-in-differences analysis with execute_python and discuss parallel trends requirements.",
  },
  {
    id: "event-study",
    label: "Event study plot",
    category: "causal",
    description: "Estimate dynamic effects around an event.",
    prompt: "If the data supports it, build an event-study style analysis around a plausible intervention date using execute_python and produce a plot.",
  },
  {
    id: "time-series-plot",
    label: "Time-series line chart",
    category: "timeseries",
    description: "Visualize a relevant series over time.",
    prompt: "Find a time-indexed table or series and create a clear time-series plot with execute_python. Summarize the main trend and any structural breaks.",
  },
  {
    id: "yoy-growth",
    label: "Year-over-year growth",
    category: "timeseries",
    description: "Compute growth rates from time-indexed data.",
    prompt: "Find a time series with a meaningful value column, compute year-over-year growth rates with execute_python, and summarize the strongest increases and declines.",
  },
  {
    id: "kmeans-cluster",
    label: "K-means clustering",
    category: "clustering",
    description: "Cluster entities by numeric features.",
    prompt: "Choose a table with several numeric features, run a k-means clustering analysis with execute_python, and explain what separates the clusters.",
  },
];
