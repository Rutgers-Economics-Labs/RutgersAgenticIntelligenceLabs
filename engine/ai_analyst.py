"""
AI Analyst: Natural language to Python analysis script.
"""
import os
import re
import google.generativeai as genai

def generate_analysis_script(question, ontology_spec, api_key=None):
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        return "print('Error: GOOGLE_API_KEY not found in environment.')"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
You are an AI Data Analyst for the RAIL (Rutgers Agentic Intelligence Labs) system.
RAIL uses owlready2 for ontology management.

### Ontology Schema (YAML)
```yaml
{ontology_spec}
```

### User Question
"{question}"

### Task
Generate a Python script that uses the `onto` object (already provided in the environment) to answer the user's question.
The script should:
1. Use owlready2 API to query the ontology.
2. Perform necessary calculations using pandas (`pd`).
3. Print the final answer or a summary table.
4. If appropriate, use `st.write()` or `st.dataframe()` since it runs in a Streamlit environment.

### Constraints
- Return ONLY the Python code. Wrap it in ```python ... ``` blocks.
- Assume `onto`, `pd`, and `st` are already available.
- Be careful with owlready2 syntax (e.g., `onto.ClassName.instances()`, `individual.propertyName`).
"""

    response = model.generate_content(prompt)
    text = response.text

    # Robustly extract code block
    match = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback if no block found but code is present
    return text.strip()
