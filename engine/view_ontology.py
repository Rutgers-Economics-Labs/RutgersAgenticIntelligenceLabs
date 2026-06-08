from owlready2 import get_ontology
import sys

def main():
    if len(sys.argv) != 2:
        print("Usage: python -m engine.view_ontology <owl_path>")
        sys.exit(1)

    owl_path = sys.argv[1]
    onto = get_ontology(owl_path).load()

    print("\nMeasures found:\n")

    for measure in onto.Measure.instances():
        tag = measure.hasTag[0] if measure.hasTag else "N/A"
        value = measure.hasValue[0] if measure.hasValue else "N/A"
        unit = measure.hasUnit[0] if measure.hasUnit else "N/A"
        geo = measure.measuredFor[0].name if measure.measuredFor else "N/A"
        time = measure.measuredAt[0].timeID[0] if measure.measuredAt and measure.measuredAt[0].timeID else "N/A"
        source = measure.fromSource[0].name if measure.fromSource else "N/A"

        print(f"{geo}: {tag} = {value} {unit} | time={time} | source={source}")

if __name__ == "__main__":
    main()