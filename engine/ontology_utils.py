from owlready2 import get_ontology

def load_ontology(path: str = "ontology/rail_nj_skeleton.owl"):
    return get_ontology(path).load()

def get_existing_individual(onto, individual_name: str):
    return onto[individual_name]

def get_or_create_county(onto, county_fips, county_name):
    county_name_safe = str(county_name).strip().lower().replace(" ", "_")
    individual_name = f"{county_name_safe}_{county_fips}"

    county = get_existing_individual(onto, individual_name)
    if county is None:
        county = onto.County(individual_name)
        county.geoID = [str(county_fips)]
        county.geoLevel = ["county"]

    return county

def get_or_create_time_period(onto, frequency, time_value):
    safe_time_value = str(time_value).replace("-", "_").replace(" ", "_")
    individual_name = f"{frequency}_{safe_time_value}"

    tp = get_existing_individual(onto, individual_name)
    if tp is None:
        tp = onto.TimePeriod(individual_name)
        tp.timeID = [str(time_value)]
        tp.timeFrequency = [frequency]

    return tp

def get_or_create_source(onto, source_id, owl_class_name):
    source_name = f"{source_id.lower()}_source"

    src = get_existing_individual(onto, source_name)
    if src is None:
        cls = getattr(onto, owl_class_name, onto.GenericSource)
        src = cls(source_name)
        src.sourceID = [source_id]

    return src

def create_measure(onto, measure_class_name, individual_name):
    cls = getattr(onto, measure_class_name)
    return cls(individual_name)