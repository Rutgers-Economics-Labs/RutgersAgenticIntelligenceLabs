"""Subprocess entry point for the hydration worker."""
import sys
from engine.pipeline_runner import run_pipeline

if __name__ == "__main__":
    run_pipeline(sys.argv[1])
