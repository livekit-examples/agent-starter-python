#!/bin/bash

# Parsing functions for Python dependency files
# Can be sourced by conversion scripts or used standalone for testing

# Source the detect script for package manager detection
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/detect-package-manager.sh"

# Function to parse dependencies from pyproject.toml
parse_pyproject_dependencies() {
    local dep_type="$1"  # "main" or "dev"
    
    if [ ! -f "pyproject.toml" ]; then
        return
    fi
    
    python3 -c "
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(1)

with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)

dep_type = '$dep_type'

# Check for different dependency locations based on the tool
dependencies = []

if dep_type == 'main':
    # Standard location
    if 'project' in data and 'dependencies' in data['project']:
        dependencies.extend(data['project']['dependencies'])
    # Poetry
    if 'tool' in data and 'poetry' in data['tool'] and 'dependencies' in data['tool']['poetry']:
        deps = data['tool']['poetry']['dependencies']
        for pkg, ver in deps.items():
            if pkg != 'python':
                if isinstance(ver, dict):
                    if 'extras' in ver:
                        extras = ','.join(ver['extras'])
                        version = ver.get('version', '*')
                        dependencies.append(f'{pkg}[{extras}]{version}')
                    else:
                        version = ver.get('version', '*')
                        dependencies.append(f'{pkg}{version}')
                else:
                    dependencies.append(f'{pkg}{ver}')
    # PDM
    if 'tool' in data and 'pdm' in data['tool'] and 'dependencies' in data['tool']['pdm']:
        dependencies.extend(data['tool']['pdm']['dependencies'])
elif dep_type == 'dev':
    # Standard location
    if 'project' in data and 'optional-dependencies' in data['project']:
        for group_deps in data['project']['optional-dependencies'].values():
            dependencies.extend(group_deps)
    # Poetry
    if 'tool' in data and 'poetry' in data['tool']:
        poetry = data['tool']['poetry']
        if 'group' in poetry:
            for group in poetry['group'].values():
                if 'dependencies' in group:
                    for pkg, ver in group['dependencies'].items():
                        if isinstance(ver, dict):
                            version = ver.get('version', '*')
                            dependencies.append(f'{pkg}{version}')
                        else:
                            dependencies.append(f'{pkg}{ver}')
        # Legacy dev-dependencies
        if 'dev-dependencies' in poetry:
            for pkg, ver in poetry['dev-dependencies'].items():
                if isinstance(ver, dict):
                    version = ver.get('version', '*')
                    dependencies.append(f'{pkg}{version}')
                else:
                    dependencies.append(f'{pkg}{ver}')
    # PDM
    if 'tool' in data and 'pdm' in data['tool'] and 'dev-dependencies' in data['tool']['pdm']:
        for group_deps in data['tool']['pdm']['dev-dependencies'].values():
            dependencies.extend(group_deps)
    # Hatch
    if 'tool' in data and 'hatch' in data['tool'] and 'envs' in data['tool']['hatch']:
        if 'default' in data['tool']['hatch']['envs'] and 'dependencies' in data['tool']['hatch']['envs']['default']:
            dependencies.extend(data['tool']['hatch']['envs']['default']['dependencies'])
    # UV
    if 'dependency-groups' in data:
        for group_deps in data['dependency-groups'].values():
            dependencies.extend(group_deps)

for dep in dependencies:
    print(dep)
" 2>/dev/null
}

# Function to parse dependencies from requirements.txt files
parse_requirements_dependencies() {
    local dep_type="$1"
    
    if [ "$dep_type" = "main" ]; then
        if [ -f "requirements.txt" ]; then
            grep -v '^#' requirements.txt 2>/dev/null | grep -v '^$' || true
        fi
    elif [ "$dep_type" = "dev" ]; then
        for dev_file in "requirements-dev.txt" "requirements.dev.txt" "dev-requirements.txt"; do
            if [ -f "$dev_file" ]; then
                grep -v '^#' "$dev_file" 2>/dev/null | grep -v '^$' || true
                return
            fi
        done
    fi
}

# Function to parse dependencies from Pipfile
parse_pipfile_dependencies() {
    local dep_type="$1"
    
    if [ ! -f "Pipfile" ]; then
        return
    fi
    
    python3 -c "
import re

with open('Pipfile', 'r') as f:
    content = f.read()

dep_type = '$dep_type'
section = '[packages]' if dep_type == 'main' else '[dev-packages]'

# Find the section
pattern = re.escape(section) + r'(.*?)(?:\n\[|\Z)'
match = re.search(pattern, content, re.DOTALL)
if not match:
    exit(0)

section_content = match.group(1)

# Parse dependencies
for line in section_content.strip().split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    
    # Parse different formats
    if '=' in line:
        parts = line.split('=', 1)
        pkg_name = parts[0].strip()
        version_part = parts[1].strip()
        
        # Handle extras format: {extras = [...], version = ...}
        if '{' in version_part:
            extras_match = re.search(r'extras\s*=\s*\[(.*?)\]', version_part)
            version_match = re.search(r'version\s*=\s*\"(.*?)\"', version_part)
            
            if extras_match:
                extras = re.sub(r'[\"\\']', '', extras_match.group(1))
                extras = ','.join([e.strip() for e in extras.split(',')])
                if version_match:
                    print(f'{pkg_name}[{extras}]{version_match.group(1)}')
                else:
                    print(f'{pkg_name}[{extras}]')
            elif version_match:
                print(f'{pkg_name}{version_match.group(1)}')
        else:
            # Simple version string
            version = version_part.strip('\"\\' ')
            if version == '*':
                print(pkg_name)
            else:
                print(f'{pkg_name}{version}')
" 2>/dev/null
}

# Main router function that detects the file type and delegates to the appropriate parser
parse_dependencies() {
    local dep_type="$1"  # "main" or "dev"
    local force_pm="$2"  # Optional: force a specific package manager detection
    
    local current_pm
    if [ -n "$force_pm" ]; then
        current_pm="$force_pm"
    else
        current_pm=$(detect_current_pm)
    fi
    
    case "$current_pm" in
        pip)
            parse_requirements_dependencies "$dep_type"
            ;;
        pipenv)
            parse_pipfile_dependencies "$dep_type"
            ;;
        poetry|pdm|hatch|uv|pyproject)
            parse_pyproject_dependencies "$dep_type"
            ;;
        *)
            # Fallback: try each parser in order of likelihood
            if [ -f "pyproject.toml" ]; then
                parse_pyproject_dependencies "$dep_type"
            elif [ -f "requirements.txt" ] || [ -f "requirements-dev.txt" ]; then
                parse_requirements_dependencies "$dep_type"
            elif [ -f "Pipfile" ]; then
                parse_pipfile_dependencies "$dep_type"
            fi
            ;;
    esac
}

# Function to extract non-package-manager sections from pyproject.toml
# This preserves ALL tool configurations except package-manager specific ones
extract_extra_pyproject_sections() {
    if [ ! -f "pyproject.toml" ]; then
        return
    fi
    
    python3 -c "
import sys
import json

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(1)

with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)

# Define package-manager specific tool names that should NOT be preserved
# Everything else will be preserved
package_manager_tools = {
    'poetry',
    'pdm', 
    'hatch',
    'uv',
    'pipenv',
}

# Extract sections to preserve
preserved = {}

# Preserve all tool sections except package manager ones
if 'tool' in data:
    for tool_name, tool_config in data['tool'].items():
        if tool_name not in package_manager_tools:
            if 'tool' not in preserved:
                preserved['tool'] = {}
            preserved['tool'][tool_name] = tool_config

# Output as JSON for easy parsing in bash
print(json.dumps(preserved))
" 2>/dev/null
}

# Function to format preserved sections back into TOML format
format_preserved_toml_sections() {
    local json_data="$1"
    
    if [ -z "$json_data" ] || [ "$json_data" = "{}" ]; then
        return
    fi
    
    python3 -c "
import sys
import json

# Read JSON from stdin to avoid shell escaping issues
json_input = '''$json_data'''
data = json.loads(json_input)

def format_value(value):
    if isinstance(value, str):
        # Check if string contains quotes or special characters
        if '\"' in value or '\\n' in value or '\\\\' in value:
            return f'\"\"\"\\n{value}\\n\"\"\"'
        else:
            return f'\"{value}\"'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = [format_value(item) for item in value]
        return '[' + ', '.join(items) + ']'
    elif isinstance(value, dict):
        # This is a table, handle separately
        return None
    else:
        return f'\"{value}\"'

def has_non_dict_values(data):
    \"\"\"Check if a dictionary has any non-dict values\"\"\"
    for value in data.values():
        if not isinstance(value, dict):
            return True
    return False

def print_table(data, prefix='', section_header_printed=False):
    # First, check if this table has any direct values
    if has_non_dict_values(data):
        # Print section header if not already printed
        if not section_header_printed and prefix:
            print(f'\\n[{prefix.rstrip(\".\")}]')
        
        # Print all non-dict values at this level
        for key, value in data.items():
            if not isinstance(value, dict):
                formatted = format_value(value)
                if formatted is not None:
                    # Handle empty string keys specially
                    if key == '':
                        print(f'\"\" = {formatted}')
                    else:
                        print(f'{key} = {formatted}')
    
    # Then handle nested tables
    for key, value in data.items():
        if isinstance(value, dict) and value:  # Only process non-empty dicts
            # Check if the nested table has any content worth printing
            if has_non_dict_values(value) or any(isinstance(v, dict) and v for v in value.values()):
                print_table(value, f'{prefix}{key}.', False)

# Print tool sections
if 'tool' in data:
    for tool_name, tool_config in data['tool'].items():
        # Only process tool if it has actual content
        if tool_config:
            print_table(tool_config, f'tool.{tool_name}.', False)
" 2>/dev/null
}