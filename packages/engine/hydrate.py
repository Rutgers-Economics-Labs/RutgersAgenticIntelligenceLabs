"""
RAIL Hydration Engine
Usage:
  python hydrate.py
  python hydrate.py --pipeline configs/pipelines/nj_hydration.yaml
"""
import argparse
from engine.pipeline_runner import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="RAIL YAML-driven ontology hydration")
    parser.add_argument(
        "--pipeline",
        default="configs/pipelines/nj_hydration.yaml",
        help="Path to pipeline YAML (default: configs/pipelines/nj_hydration.yaml)",
    )
    args = parser.parse_args()
    run_pipeline(args.pipeline)


if __name__ == "__main__":
    main()
