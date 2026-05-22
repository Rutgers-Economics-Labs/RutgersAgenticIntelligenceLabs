# Research Analysis: NJ Interest Rates and Housing Affordability Study

This report analyzes how the Federal Reserve's interest rate cycle from 2015 to 2025 impacted housing affordability in New Jersey, utilizing data from the FRED API.

## Data Summary

| Metric               | Start Value (Date)  | End Value (Date)    | % Change | Data Source |
| :------------------- | :------------------ | :------------------ | :------- | :---------- |
| NJ House Price Index | 472.09 (2015-01-01) | 939.31 (2025-10-01) | +99.0%   | FRED NJSTHPI|
| Unemployment Rate    | 6.90% (2015-01-01)  | 4.70% (2026-03-01)  | -31.9%   | FRED NJURN  |
| CPI                  | 234.75 (2015-01-01) | 332.41 (2026-04-01) | +41.6%   | FRED CPIAUCSL |

---

## Analysis

Over the period spanning 2015 to 2025, New Jersey's housing market experienced significant nominal growth. The New Jersey State House Price Index (NJSTHPI) surged from 472.09 in January 2015 to 939.31 by October 2025, marking an increase of 99.0%. Concurrently, general inflation, as measured by the Consumer Price Index (CPIAUCSL), rose by 41.6% from 234.75 in January 2015 to 332.41 in April 2026. This stark difference indicates that housing price appreciation in New Jersey vastly outpaced the broader inflationary trends during this decade.

The employment landscape in New Jersey also evolved considerably during the study period. The New Jersey Unemployment Rate (NJURN) decreased from 6.90% in January 2015 to 4.70% by March 2026, representing a 31.9% reduction. This decline in unemployment suggests a strengthening labor market and increased economic stability, which typically contributes to higher housing demand. As more individuals are employed and have stable incomes, their capacity and willingness to enter the housing market tend to increase, putting upward pressure on home prices.

Computing the real (inflation-adjusted) change in housing prices reveals a substantial erosion of affordability. With nominal housing prices rising by 99.0% and general inflation by 41.6%, the real cost of housing in New Jersey increased by approximately 40.5% ((1 + 0.99) / (1 + 0.416) - 1). This significant real appreciation means that, even accounting for the general increase in prices across the economy, New Jersey housing became considerably less affordable for residents over the decade.

The pronounced trends in housing prices and inflation during this period strongly suggest the presence of structural breaks, particularly around key economic events. The rapid and disproportionate growth of NJSTHPI relative to CPIAUCSL supports the hypothesis that events like the COVID-19 pandemic and the Federal Reserve's 2022 rate-hike cycle likely introduced significant shifts in market dynamics. While the provided data only reflects aggregate changes, the substantial 99.0% increase in nominal housing prices within the context of the evolving interest rate environment and global health crises underscores the need for further granular analysis to pinpoint and quantify the exact impact of these structural breaks on housing affordability.