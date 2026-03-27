import os
import sqlite3
from pathlib import Path
from owlready2 import World, Ontology, Thing, DataProperty, ObjectProperty, AllDisjoint
import duckdb
import pandas as pd

# Target paths
TEST_DIR = Path(__file__).parent / "synthetic"
TEST_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB = TEST_DIR / "synthetic.db"
DUCKDB_DB = TEST_DIR / "synthetic.duckdb"

def generate():
    print(f"Generating synthetic ontology at {SQLITE_DB}...")
    
    # Clean up old files
    if SQLITE_DB.exists(): SQLITE_DB.unlink()
    if DUCKDB_DB.exists(): DUCKDB_DB.unlink()
    
    # 1. Create OWLReady2 Ontology
    world = World()
    world.set_backend(filename=str(SQLITE_DB), exclusive=False)
    
    onto = world.get_ontology("http://test.org/synthetic.owl")
    
    with onto:
        class Animal(Thing): pass
        class Food(Thing): pass
        
        class eats(Animal >> Food): pass
        
        from owlready2 import FunctionalProperty
        class hasWeight(Animal >> float, FunctionalProperty): pass
        class hasName(Thing >> str, FunctionalProperty): pass
        
        # Add instances
        lion = Animal("Lion")
        lion.hasName = "Leo the Lion"
        lion.hasWeight = 200.0
        
        meat = Food("Meat")
        meat.hasName = "Fresh Meat"
        lion.eats = [meat]
        
        cow = Animal("Cow")
        cow.hasName = "Bessie the Cow"
        cow.hasWeight = 500.0
        
        grass = Food("Grass")
        grass.hasName = "Green Grass"
        cow.eats = [grass]
        
    OWL_FILE = TEST_DIR / "synthetic.owl"
    onto.save(file=str(OWL_FILE), format="rdfxml")
    world.save()
    world.close()
    
    # 2. Export to DuckDB Mirror (simulate hydration output)
    print(f"Exporting to DuckDB at {DUCKDB_DB}...")
    con = duckdb.connect(str(DUCKDB_DB))
    
    # Table: Animal
    df_animals = pd.DataFrame([
        {"_id": "Lion", "hasName": "Leo the Lion", "hasWeight": 200.0},
        {"_id": "Cow", "hasName": "Bessie the Cow", "hasWeight": 500.0}
    ])
    con.register("animals_df", df_animals)
    con.execute('CREATE TABLE "Animal" AS SELECT * FROM animals_df')
    
    # Table: Food
    df_food = pd.DataFrame([
        {"_id": "Meat", "hasName": "Fresh Meat"},
        {"_id": "Grass", "hasName": "Green Grass"}
    ])
    con.register("food_df", df_food)
    con.execute('CREATE TABLE "Food" AS SELECT * FROM food_df')
    
    con.close()
    print("Synthetic ontology generated successfully.")
    print(f"SQLite: {SQLITE_DB.resolve()}")
    print(f"DuckDB: {DUCKDB_DB.resolve()}")

if __name__ == "__main__":
    generate()
