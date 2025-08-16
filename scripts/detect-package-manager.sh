#!/bin/bash

# Detect the current Python package manager based on existing files

detect_current_pm() {
    # Check for various package manager files in order of specificity

    # UV (check for uv.lock, tool.uv, or dependency-groups in pyproject.toml)
    if [ -f "uv.lock" ]; then
        echo "uv"
        return
    fi
    
    # UV also uses [dependency-groups] or [tool.uv] in pyproject.toml
    if [ -f "pyproject.toml" ]; then
        if grep -q "\[tool\.uv\]" pyproject.toml 2>/dev/null || grep -q "\[dependency-groups\]" pyproject.toml 2>/dev/null; then
            echo "uv"
            return
        fi
    fi

    # Poetry (check for poetry.lock or poetry sections in pyproject.toml)
    if [ -f "poetry.lock" ] || ([ -f "pyproject.toml" ] && grep -q "\[tool\.poetry\]" pyproject.toml 2>/dev/null); then
        echo "poetry"
        return
    fi

    # PDM (check for pdm.lock or pdm sections in pyproject.toml)
    if [ -f "pdm.lock" ] || ([ -f "pyproject.toml" ] && grep -q "\[tool\.pdm\]" pyproject.toml 2>/dev/null); then
        echo "pdm"
        return
    fi

    # Hatch (check for hatch sections in pyproject.toml)
    if [ -f "pyproject.toml" ] && grep -q "\[tool\.hatch\]" pyproject.toml 2>/dev/null; then
        echo "hatch"
        return
    fi

    # Pipenv (check for Pipfile)
    if [ -f "Pipfile" ]; then
        echo "pipenv"
        return
    fi

    # Pip (check for requirements.txt)
    if [ -f "requirements.txt" ]; then
        echo "pip"
        return
    fi

    # Default to unknown if we have pyproject.toml but can't identify the tool
    if [ -f "pyproject.toml" ]; then
        echo "pyproject"
        return
    fi

    echo "unknown"
}

# If script is executed directly, print the detected package manager
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    detect_current_pm
fi