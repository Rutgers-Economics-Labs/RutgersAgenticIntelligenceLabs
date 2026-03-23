from owlready2 import *
onto = get_ontology("http://example.org/rail_nj.owl")

with onto:

    #Geography classes
    class State(Thing):
        pass
    class County(Thing):
        pass
    class Municipality(Thing):
        pass
    class CensusTract(Thing):
        pass
    class ZipCode(Thing):
        pass
    
    #Entity classes
    class Person(Thing): pass
    class Establishment(Thing): pass
    class Household(Thing): pass
    class Utility(Thing): pass
    class Plant(Thing): pass
    
    #Measure classes
    class Measure(Thing): pass
    class LaborIndicator(Measure): pass
    class DemographicIndicator(Measure): pass
    class HousingIndicator(Measure): pass
    class EconomicIndicator(Measure): pass
    class EnergyIndicator(Measure): pass
    class EnvironmentIndicator(Measure): pass
    class TransportationIndicator(Measure): pass

    #Source classes
    class Source(Thing): pass
    class ACS(Source): pass
    class QCEW(Source): pass
    class LAUS(Source): pass

    #Time class
    class TimePeriod(Thing): pass

    #Object properties
    class locatedIn(ObjectProperty): pass
    class measuredFor(ObjectProperty):
        domain = [Measure]
    class fromSource(ObjectProperty):
        domain = [Measure]
        range = [Source]
    class measuredAt(ObjectProperty):
        domain = [Measure]
        range = [TimePeriod]

    #Data properties
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
    class geoID(DataProperty):
        range = [str]
    class dataVintage(DataProperty):
        domain = [Measure]
        range = [str]
    class timeID(DataProperty):
        domain = [TimePeriod]
        range = [str]

       
onto.save(file="rail_nj_skeleton.owl", format="rdfxml")
print("Skeleton ontology saved!")