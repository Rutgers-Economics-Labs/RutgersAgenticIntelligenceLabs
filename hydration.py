from owlready2 import *
onto = get_ontology("file://rail_nj_skeleton.owl").load()
print("Classes in ontology: ")
for cls in onto.classes():
    print(cls)
print("\n")
print("Object properties: ")
for prop in onto.object_properties():
    print(prop)

with onto:
    #Geography individual
    nj_state = onto.State("new_jersey")
    nj_state.geoID = ["34"]
    nj_county = onto.County("essex_county")
    nj_county.geoID = ["34013"]
    nj_county.locatedIn = [nj_state]

    #Time individual
    year_2024 = onto.TimePeriod("year_2024")
    year_2024.timeID = ["2024"]

    #Source individual
    laus_source = onto.LAUS("laus_source")

    #Measure individual from imaginary dataset A
    unem_rate = onto.LaborIndicator("essex_unemployment_2024")
    unem_rate.hasValue = [4.2]
    unem_rate.hasUnit = ["Percent"]
    unem_rate.hasTag = ["labor.unemployment.rate"]
    unem_rate.measuredFor = [nj_county]
    unem_rate.fromSource = [laus_source]
    unem_rate.dataVintage = ["2024-01-01"]
    unem_rate.measuredAt = [year_2024]

    #Measure individual from imaginary dataset B
    electricity = onto.EnergyIndicator("essex_electricity_2024")
    electricity.hasValue = [5000000]  
    electricity.hasUnit = ["kWh"]
    electricity.measuredFor = [nj_county]
    electricity.hasTag = ["energy.electricity.consumption_kwh"]
    electricity.fromSource = [laus_source]
    electricity.dataVintage = ["2024-01-01"]
    electricity.measuredAt = [year_2024]

print("\nLabor indicators:")
for measure in onto.LaborIndicator.instances():
    for geo in measure.measuredFor:
        print(
            f"{geo.name}: {measure.hasValue[0]} {measure.hasUnit[0]} "
            f"(tag={measure.hasTag[0]}, year={measure.measuredAt[0].timeID[0]})"
        )

print("\nAll measures:")
for measure in onto.Measure.instances():
    for geo in measure.measuredFor:
        print(
            f"{geo.name}: {measure.name} = {measure.hasValue[0]} {measure.hasUnit[0]} "
            f"[tag={measure.hasTag[0]}, year={measure.measuredAt[0].timeID[0]}]"
        )

onto.save(file="rail_nj_populated.owl", format="rdfxml")
print("\nPopulated ontology saved!")