from owlready2 import *

onto = get_ontology("http://example.org/rail_nj.owl")

with onto:

    # Geography classes
    class Geography(Thing):
        pass

    class State(Geography):
        pass

    class County(Geography):
        pass

    class Municipality(Geography):
        pass

    class CensusTract(Geography):
        pass

    class ZipCode(Geography):
        pass

    # Entity classes
    class Entity(Thing):
        pass

    class Person(Entity):
        pass

    class Establishment(Entity):
        pass

    class Household(Entity):
        pass

    class Utility(Entity):
        pass

    class Plant(Entity):
        pass

    # Time class
    class TimePeriod(Thing):
        pass

    # Source classes
    class Source(Thing):
        pass

    class ACS(Source):
        pass

    class QCEW(Source):
        pass

    class LAUS(Source):
        pass

    class GenericSource(Source):
        pass

    # Measure classes
    class Measure(Thing):
        pass

    class LaborIndicator(Measure):
        pass

    class DemographicIndicator(Measure):
        pass

    class HousingIndicator(Measure):
        pass

    class EconomicIndicator(Measure):
        pass

    class EnergyIndicator(Measure):
        pass

    class EnvironmentIndicator(Measure):
        pass

    class TransportationIndicator(Measure):
        pass

    # Object properties
    class locatedIn(ObjectProperty):
        pass

    class measuredFor(ObjectProperty):
        domain = [Measure]

    class fromSource(ObjectProperty):
        domain = [Measure]
        range = [Source]

    class measuredAt(ObjectProperty):
        domain = [Measure]
        range = [TimePeriod]

    # Data properties
    class hasValue(DataProperty):
        domain = [Measure]
        range = [float]

    class hasUnit(DataProperty):
        domain = [Measure]
        range = [str]

    class hasTag(DataProperty):
        domain = [Measure]
        range = [str]

    class priceBasis(DataProperty):
        domain = [Measure]
        range = [str]

    class dataVintage(DataProperty):
        domain = [Measure]
        range = [str]

    class sourceID(DataProperty):
        domain = [Source]
        range = [str]

    class geoID(DataProperty):
        range = [str]

    class geoLevel(DataProperty):
        range = [str]

    class timeID(DataProperty):
        domain = [TimePeriod]
        range = [str]

    class timeFrequency(DataProperty):
        domain = [TimePeriod]
        range = [str]

    class suppressed(DataProperty):
        domain = [Measure]
        range = [bool]

    class rawField(DataProperty):
        domain = [Measure]
        range = [str]

    class baseYear(DataProperty):
        domain = [Measure]
        range = [str]

    class deflatorSource(DataProperty):
        domain = [Measure]
        range = [str]

onto.save(file="ontology/rail_nj_skeleton.owl", format="rdfxml")
print("Skeleton ontology saved to ontology/rail_nj_skeleton.owl")