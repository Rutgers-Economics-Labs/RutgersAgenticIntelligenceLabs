import time
import random
from typing import List

# This would ideally import from the api side, but for engine standalone 
# we simulate the update loop.

def run_stream_simulation(uri_list: List[str], property_name: str, interval: float = 2.0):
    """
    Simulates a real-time data stream (e.g., sensor data) and pushes updates
    to the active ontology individuals.
    """
    print(f"[stream] Starting simulation on {len(uri_list)} entities for property '{property_name}'")
    
    try:
        while True:
            for uri in uri_list:
                # Simulate a value (e.g., Temperature, Price, or AQI)
                new_value = round(random.uniform(50, 100), 2)
                
                # In a real setup, this would call the API's update endpoint 
                # or modify the quadstore directly if running inside the engine process.
                print(f"[stream] PUSH -> {uri}.{property_name} = {new_value}")
                
                # Mock update (In production, this triggers a quadstore hit)
                # update_entity_property(uri, property_name, new_value)
                
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[stream] Simulation stopped.")

if __name__ == "__main__":
    # Example usage: simulate real-time sensors for NJ counties
    counties = ["County_34013", "County_34017", "County_34031"]
    run_stream_simulation(counties, "hasValue")
