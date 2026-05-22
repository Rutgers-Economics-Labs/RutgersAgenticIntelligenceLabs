# Source Registry

This document registers the data sources used in the "NJ Labor Market Literature and Data Synthesis" project. Each source is listed with its key details and a justification for its inclusion.

## Registered Sources

### 1. New Jersey Unemployment Rate (NJURN)

*   **Source Key:** `NJURN`
*   **Type:** API
*   **Title:** New Jersey Unemployment Rate
*   **Origin:** FRED (Federal Reserve Economic Data)
*   **Access Method:** REST API
*   **Justification for Inclusion:** This series is critical for directly addressing the first objective of the research brief: "Characterize the NJ unemployment trajectory." As the official unemployment rate for New Jersey provided by FRED, it offers reliable and consistent historical data for the specified period (2015-2025), enabling a precise analysis of state-specific labor market conditions.

### 2. National Unemployment Rate (UNRATE)

*   **Source Key:** `UNRATE`
*   **Type:** API
*   **Title:** National Unemployment Rate
*   **Origin:** FRED (Federal Reserve Economic Data)
*   **Access Method:** REST API
*   **Justification for Inclusion:** The national unemployment rate is essential for placing New Jersey's labor market trajectory "in national context," as required by the second objective of the research brief. By comparing NJURN with UNRATE, the study can identify whether New Jersey's trends are part of broader national patterns or if they reflect unique state-level dynamics, particularly during periods like pre-COVID, COVID shock, and recovery. This comparative analysis is fundamental to understanding NJ's relative labor market resilience.

## Summary

Two critical data sources, NJURN and UNRATE, have been registered. Both are from FRED and accessed via REST API. Their inclusion is justified by their direct relevance to the core research objectives of characterizing NJ's unemployment trajectory and placing it within a national context to assess labor market resilience.
