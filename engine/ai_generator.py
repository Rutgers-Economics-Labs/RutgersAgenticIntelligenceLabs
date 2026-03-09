"""
AI-assisted YAML generation using Gemini API.
"""
import os
import re
import yaml
import json
import google.generativeai as genai
from pathlib import Path

def generate_hydration_yaml(content, content_type, ontology_spec, api_key=None):
    """
    Generate a hydration YAML based on data sample/docs and ontology schema.
    """
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        return "Error: GOOGLE_API_KEY not found in environment."

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
You are an expert data engineer for the RAIL (Rutgers Agentic Intelligence Labs) system.
RAIL uses YAML configurations to hydrate an OWL ontology from various data sources.

### Task
Generate a RAIL API config YAML based on the provided {content_type} information and the target ontology schema.

### Ontology Schema (YAML)
```yaml
{ontology_spec}
```

### {content_type} Content/Documentation
```
{content}
```

### Output Requirement
Return ONLY a JSON object with two keys:
1. 'api_config': The full YAML for the API configuration.
2. 'pipeline_step': The YAML snippet for the pipeline step.

Wrap the JSON in a ```json ... ``` block.
"""

    response = model.generate_content(prompt)
    text = response.text

    # Robust extraction
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()
