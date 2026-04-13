from pathlib import Path
from typing import Any, Dict, List

from app.services.yaml_service import validate_agent_runnable, validate, parse
from app.services.policy_resolver import RuntimePolicy

class VerificationResult:
    def __init__(self, passed: bool, errors: List[str] = None):
        self.passed = passed
        self.errors = errors or []

def verify_config(config_type: str, content: str, project_root: Path = None) -> VerificationResult:
    try:
        parsed = parse(content)
        if not isinstance(parsed, dict):
            return VerificationResult(False, [f"{config_type.capitalize()} config must be an object (dict)"])
    except ValueError as e:
        return VerificationResult(False, [str(e)])

    if config_type == "agent":
        if project_root is None:
            return VerificationResult(False, ["project_root is required for agent config verification"])
        errors = validate_agent_runnable(content, project_root)
    else:
        errors = validate(config_type, content)
    return VerificationResult(len(errors) == 0, errors)

def verify_path_policy(modified_paths: List[str], policy: RuntimePolicy) -> VerificationResult:
    errors = []

    writes = policy.paths.write
    denies = policy.paths.deny

    for path in modified_paths:
        # Check denies first
        is_denied = False
        for deny in denies:
            if path == deny or path.startswith(f"{deny}/"):
                errors.append(f"Path modified in denied location: {path}")
                is_denied = True
                break

        if is_denied:
            continue

        # Check writes
        is_allowed = False
        for write in writes:
            if path == write or path.startswith(f"{write}/"):
                is_allowed = True
                break

        if not is_allowed and writes:
            errors.append(f"Path modified outside allowed write locations: {path}")

    return VerificationResult(len(errors) == 0, errors)


def verify_execution(script_path: str, output_paths: List[str], project_root: Path, policy: RuntimePolicy) -> VerificationResult:
    # This is a stub for Execution Verification
    # Coding agent tasks require checking that expected output files exist
    # and paths match policy. The actual script execution success is checked
    # during the task run, but this verifies the final state.
    errors = []

    # Verify outputs exist
    for path in output_paths:
        full_path = project_root / path
        if not full_path.exists():
            errors.append(f"Expected output file not found: {path}")

    # Verify outputs respect policy
    path_check = verify_path_policy(output_paths, policy)
    if not path_check.passed:
        errors.extend(path_check.errors)

    return VerificationResult(len(errors) == 0, errors)

def verify_artifact(artifact_paths: List[str], project_root: Path, policy: RuntimePolicy) -> VerificationResult:
    # Stub for Artifact Verification
    errors = []

    for path in artifact_paths:
        full_path = project_root / path
        if not full_path.exists():
            errors.append(f"Required artifact file not found: {path}")

    path_check = verify_path_policy(artifact_paths, policy)
    if not path_check.passed:
        errors.extend(path_check.errors)

    return VerificationResult(len(errors) == 0, errors)
