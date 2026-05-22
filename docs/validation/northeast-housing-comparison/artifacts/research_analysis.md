# Research Analysis: Northeast State Housing Price Comparison (2015-2025)

This analysis examines the housing price index (HPI) trajectories for New Jersey (NJSTHPI), New York (NYSTHPI), and Connecticut (CTSTHPI) from January 2015 to October 2025, utilizing data from the FRED API. The primary objective is to compare the performance of these states, identify the strongest post-COVID surge, normalize indices for fair comparison, and observe patterns of convergence or divergence. All three states experienced substantial growth in housing prices over the decade, reflecting broader market trends, but with distinct magnitudes.

To facilitate a comparative understanding, each state's HPI series was normalized to a 2015 baseline (2015-01-01 = 100). By October 2025, New Jersey's normalized HPI reached 198.96, indicating a near-doubling of prices. New York followed very closely with a normalized HPI of 198.44, also representing a significant surge. Connecticut's housing market, while also growing, lagged behind its neighbors, reaching a normalized HPI of 183.50. This suggests that New Jersey experienced a marginally stronger overall percentage increase (99.0%) compared to New York (98.4%) and Connecticut (83.5%), positioning it as the state with the highest growth from the baseline period.

The period saw both New Jersey and New York exhibit remarkably similar growth patterns, almost perfectly converging in terms of their percentage increases from the 2015 baseline. Both states saw their HPIs nearly double by October 2025. This close alignment in relative growth suggests similar market dynamics or demand pressures influenced these two states. In contrast, Connecticut's slower growth rate (83.5%) indicates a clear divergence from the more rapid appreciation seen in New Jersey and New York, suggesting differing regional economic or demographic factors.

In summary, while New York maintained the highest absolute HPI values throughout the period (starting at 579.72 and ending at 1150.44), New Jersey showed the strongest relative growth, increasing by 99.0% from 472.09 to 939.31. Connecticut's market, starting at 386.30 and ending at 708.82, grew at a comparatively slower rate of 83.5%. The data clearly points to a strong post-COVID surge in housing prices across the Northeast, with New Jersey and New York leading the charge and demonstrating a notable convergence in their relative price trajectories, while Connecticut followed a more moderate path.

## Data Summary Table (Source: FRED API)

| State | Initial HPI (2015-01-01) | Final HPI (2025-10-01) | % Change (2015-2025) | Normalized HPI (2025, 2015=100) |
| :---- | :----------------------- | :--------------------- | :------------------- | :-------------------------------- |
| NJ    | 472.09                   | 939.31                 | 99.0%                | 198.96                            |
| NY    | 579.72                   | 1150.44                | 98.4%                | 198.44                            |
| CT    | 386.30                   | 708.82                 | 83.5%                | 183.50                            |
