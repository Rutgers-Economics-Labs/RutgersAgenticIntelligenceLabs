"""
Census data cleaning transforms.

These clean DataFrames *before* they are mapped to the ontology.
Reference in pipeline YAML as:
    transform: "census_clean::strip_state_suffix"

DataFrame transform signature:
    def my_transform(df: pd.DataFrame, **kwargs) -> pd.DataFrame
"""


def strip_state_suffix(df, **kwargs):
    """
    Census county names arrive as "Essex County, New Jersey".
    Strip the ", State Name" suffix to get just "Essex County".
    """
    if "name" in df.columns:
        df = df.copy()
        df["name"] = df["name"].str.split(",").str[0].str.strip()
    return df


def strip_municipality_name(df, **kwargs):
    """
    Census county subdivision names: 'Hoboken city, Hudson County, New Jersey'
    -> 'Hoboken city'
    Also removes "County subdivisions not defined" placeholder rows.
    """
    if "raw_name" not in df.columns:
        return df
    df = df.copy()
    df = df[~df["raw_name"].str.startswith("County subdivisions not defined")]
    df["name"] = df["raw_name"].str.split(",").str[0].str.strip()
    return df.reset_index(drop=True)


def normalize_fips(df, pad_width=2, **kwargs):
    """
    Ensure FIPS codes are zero-padded strings (e.g. "4" -> "04").
    Set pad_width in transform_config: {pad_width: 3} for county FIPS.
    """
    if "fips" in df.columns:
        df = df.copy()
        df["fips"] = df["fips"].astype(str).str.zfill(pad_width)
    return df
