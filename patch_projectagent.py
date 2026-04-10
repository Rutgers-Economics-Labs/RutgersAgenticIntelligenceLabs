import re

with open('packages/api/app/routers/project_agent.py', 'r') as f:
    content = f.read()

content = content.replace(
    '''    for _turn in range(max_turns):
        role_def = ROLES.get(current_role, ROLES["planner"])''',
    '''    for _turn in range(max_turns):
        role_def = ROLES.get(current_role, ROLES["planner"])
        yield {"type": "role_change", "agentRole": current_role}'''
)

with open('packages/api/app/routers/project_agent.py', 'w') as f:
    f.write(content)
