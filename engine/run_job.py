import sys
from engine.config_loader import load_yaml
from engine.hydrator import hydrate_source

def main():
    if len(sys.argv) != 2:
        print("Usage: python engine/run_job.py <job_yaml_path>")
        sys.exit(1)

    job_path = sys.argv[1]
    job_cfg = load_yaml(job_path)

    source_config_path = job_cfg["source_config"]
    output_owl_path = job_cfg["output_owl"]

    hydrate_source(source_config_path, output_owl_path)

if __name__ == "__main__":
    main()