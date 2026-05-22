### 1. How did the percentage change in unemployment rates for New Jersey and the U.S. compare specifically during the pre-COVID (2015-early 2020), COVID shock (early 2020-mid 2020), and recovery (mid 2020-2026) periods?
- Classification: `answerable_after_requery`
- Rationale: The data for both NJURN and UNRATE is already available in DuckDB for the entire period. This question requires re-running queries with specific date filters for sub-periods and calculating percentage changes within those periods.

### 2. What were the key sector-specific unemployment rates or labor force participation rates in New Jersey during 2015-2026 that could contribute to the persistent higher absolute unemployment rate compared to the national average?
- Classification: `requires_expansion`
- Rationale: The current ontology only includes aggregate NJURN and UNRATE. Answering this would require identifying and adding new FRED data series related to specific industries or labor force participation, thereby expanding the data ontology.

### 3. What additional FRED economic indicators, such as GDP growth or wage growth, show significant correlation with New Jersey's relatively stronger percentage reduction in unemployment compared to the national average?
- Classification: `requires_expansion`
- Rationale: The current data is limited to unemployment rates. To explore correlations with other economic indicators, new FRED series (e.g., NJGDP, NJWAGE) would need to be integrated into the ontology.

### 4. What was the maximum absolute difference between New Jersey's and the national unemployment rates, and on what dates did these maximum differences occur, between 2015 and 2025?
- Classification: `answerable_now`
- Rationale: This question can be directly answered by querying the existing NJURN and UNRATE time series data already stored in DuckDB and performing basic comparative analysis.

### 5. What role did state-level economic development policies or specific demographic shifts in New Jersey play in its unemployment trajectory, particularly during the post-COVID recovery?
- Classification: `requires_expansion`
- Rationale: The current data focuses solely on FRED unemployment statistics. Answering this would necessitate integrating new types of data (e.g., policy documents, demographic statistics from Census Bureau or other state-level sources) that are not part of the existing FRED ontology.
