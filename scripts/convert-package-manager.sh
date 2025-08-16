#!/bin/bash

set -e

# Configuration
GITHUB_BASE_URL="https://raw.githubusercontent.com/livekit/livekit-cli/refs/heads/main/pkg/agentfs/examples/"
PROGRAM_MAIN="src/agent.py"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Source the parsing functions (includes detect_current_pm)
source "$(dirname "$0")/parse-dependencies.sh"

# Get the target package manager from command line
TARGET_PM="$1"

if [ -z "$TARGET_PM" ]; then
    echo -e "${RED}Error: No package manager specified${NC}"
    echo "Usage: $0 {pip|poetry|pipenv|pdm|hatch|uv}"
    exit 1
fi

# Detect current package manager
CURRENT_PM=$(detect_current_pm)

echo -e "${GREEN}✔${NC} Detected current package manager: ${YELLOW}$CURRENT_PM${NC}"

# Create backup directory
BACKUP_DIR=".backup.$CURRENT_PM"
if [ "$CURRENT_PM" = "unknown" ]; then
    BACKUP_DIR=".backup.original"
fi

echo "  Creating backup: $BACKUP_DIR/"

# Extract extra tool sections BEFORE moving files
# This ensures we capture them from pyproject.toml if it exists
extra_sections=""
if [ -f "pyproject.toml" ]; then
    extra_sections=$(extract_extra_pyproject_sections)
fi

# Create backup
mkdir -p "$BACKUP_DIR"

# Move most files to backup, but keep the source dependency file for reading
# We'll clean it up after conversion if needed
[ -f "Dockerfile" ] && mv "Dockerfile" "$BACKUP_DIR/"
[ -f ".dockerignore" ] && mv ".dockerignore" "$BACKUP_DIR/"

# Handle dependency files based on current package manager
case "$CURRENT_PM" in
    pip)
        # Keep requirements.txt for reading, move everything else
        [ -f "requirements.txt" ] && cp "requirements.txt" "$BACKUP_DIR/"
        [ -f "requirements-dev.txt" ] && mv "requirements-dev.txt" "$BACKUP_DIR/"
        [ -f "pyproject.toml" ] && mv "pyproject.toml" "$BACKUP_DIR/"
        [ -f "Pipfile" ] && mv "Pipfile" "$BACKUP_DIR/"
        ;;
    pipenv)
        # Keep Pipfile for reading, move everything else
        [ -f "Pipfile" ] && cp "Pipfile" "$BACKUP_DIR/"
        [ -f "Pipfile.lock" ] && mv "Pipfile.lock" "$BACKUP_DIR/"
        [ -f "requirements.txt" ] && mv "requirements.txt" "$BACKUP_DIR/"
        [ -f "pyproject.toml" ] && mv "pyproject.toml" "$BACKUP_DIR/"
        ;;
    poetry|pdm|hatch|uv|pyproject)
        # Keep pyproject.toml for reading, move everything else
        [ -f "pyproject.toml" ] && cp "pyproject.toml" "$BACKUP_DIR/"
        [ -f "requirements.txt" ] && mv "requirements.txt" "$BACKUP_DIR/"
        [ -f "requirements-dev.txt" ] && mv "requirements-dev.txt" "$BACKUP_DIR/"
        [ -f "Pipfile" ] && mv "Pipfile" "$BACKUP_DIR/"
        [ -f "Pipfile.lock" ] && mv "Pipfile.lock" "$BACKUP_DIR/"
        ;;
    *)
        # Unknown, just copy everything to be safe
        [ -f "pyproject.toml" ] && cp "pyproject.toml" "$BACKUP_DIR/"
        [ -f "requirements.txt" ] && cp "requirements.txt" "$BACKUP_DIR/"
        [ -f "Pipfile" ] && cp "Pipfile" "$BACKUP_DIR/"
        ;;
esac

# Always move lock files - they're never needed for reading
[ -f "poetry.lock" ] && mv "poetry.lock" "$BACKUP_DIR/"
[ -f "pdm.lock" ] && mv "pdm.lock" "$BACKUP_DIR/"
[ -f "uv.lock" ] && mv "uv.lock" "$BACKUP_DIR/"
[ -f "Pipfile.lock" ] && mv "Pipfile.lock" "$BACKUP_DIR/"

echo ""
echo -e "${GREEN}✔${NC} Fetching $TARGET_PM templates from GitHub"

# Download Dockerfile and dockerignore
DOCKERFILE_URL="$GITHUB_BASE_URL/python.$TARGET_PM.Dockerfile"
DOCKERIGNORE_URL="$GITHUB_BASE_URL/python.$TARGET_PM.dockerignore"

curl -sL "$DOCKERFILE_URL" -o Dockerfile.tmp
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to download Dockerfile${NC}"
    exit 1
fi

curl -sL "$DOCKERIGNORE_URL" -o .dockerignore
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to download .dockerignore${NC}"
    exit 1
fi

# Replace template variable in Dockerfile
sed "s|{{\.ProgramMain}}|$PROGRAM_MAIN|g" Dockerfile.tmp > Dockerfile
rm Dockerfile.tmp

echo "  Downloaded: Dockerfile (from LiveKit template)"
echo "  Downloaded: .dockerignore (from LiveKit template)"
echo ""
echo -e "${YELLOW}⚠️  Note: Dockerfile has been reset to LiveKit template version${NC}"
echo "    Any custom modifications have been backed up"

# Generate package manager specific files
echo ""
echo -e "${GREEN}✔${NC} Generating $TARGET_PM configuration"

case "$TARGET_PM" in
    pip)
        # Generate requirements.txt from current project
        # Get main dependencies
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        if [ ! -z "$main_deps" ]; then
            # Process each dependency to fix version specifiers for requirements.txt format
            while IFS= read -r dep; do
                # Fix Poetry-style version specifiers
                if [[ "$dep" == *"~"[0-9]* ]]; then
                    # Convert ~1.2 to ~=1.2
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    # Convert ^1.2 to ~=1.2
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                # Remove trailing * for any version
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi
                echo "$dep"
            done <<< "$main_deps" > requirements.txt

            # Add dev dependencies as comments
            dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")
            if [ ! -z "$dev_deps" ]; then
                echo "" >> requirements.txt
                echo "# Development dependencies:" >> requirements.txt
                while IFS= read -r dep; do
                    # Fix version specifiers for dev deps too
                    if [[ "$dep" == *"~"[0-9]* ]]; then
                        dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                    fi
                    # Convert Poetry's caret operator ^ to ~=
                    if [[ "$dep" == *"^"* ]]; then
                        dep=$(echo "$dep" | sed 's/\^/~=/')
                    fi
                    if [[ "$dep" == *"*" ]]; then
                        dep=$(echo "$dep" | sed 's/\*$//')
                    fi
                    echo "# $dep" >> requirements.txt
                done <<< "$dev_deps"
            fi

            echo "  Generated: requirements.txt"

            # Preserve tool configurations in a minimal pyproject.toml
            # (using pre-extracted sections from before files were moved)
            if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
                # Create minimal pyproject.toml with just tool configs
                echo "[tool]" > pyproject.toml
                format_preserved_toml_sections "$extra_sections" >> pyproject.toml
                echo "  Preserved: pyproject.toml (tool configurations)"
            else
                # Clean up pyproject.toml if no tool configs to preserve
                rm -f pyproject.toml
            fi
        else
            echo -e "${YELLOW}Warning: No dependencies found to convert${NC}"
        fi
        ;;

    poetry)
        # Parse dependencies BEFORE overwriting the file!
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")

        # Generate pyproject.toml for Poetry
        cat > pyproject.toml << 'EOF'
[tool.poetry]
name = "livekit-agent"
version = "0.1.0"
description = "LiveKit Agent"
authors = ["Your Name <you@example.com>"]

[tool.poetry.dependencies]
python = "^3.9"
EOF

        # Add main dependencies
        if [ -n "$main_deps" ]; then
            while IFS= read -r dep; do
                # Handle dependencies with extras
                if [[ "$dep" == *"["*"]"* ]]; then
                    pkg_name=$(echo "$dep" | sed 's/\[.*//')
                    extras=$(echo "$dep" | sed 's/.*\[\(.*\)\].*/\1/')
                    version=$(echo "$dep" | grep -oE '(~=|>=|<=|==|>|<)[0-9.]+' || echo "*")

                    # Format for Poetry in pyproject.toml
                    if [ "$version" != "*" ]; then
                        # Convert ~= to ^ for Poetry
                        if [[ "$version" == "~="* ]]; then
                            version="^$(echo "$version" | sed 's/~=//')"
                        fi
                        # Format extras with proper quoting for Poetry
                        formatted_extras=$(echo "$extras" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed 's/.*/"&"/' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
                        echo "$pkg_name = {extras = [$formatted_extras], version = \"$version\"}" >> pyproject.toml
                    else
                        formatted_extras=$(echo "$extras" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed 's/.*/"&"/' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
                        echo "$pkg_name = {extras = [$formatted_extras]}" >> pyproject.toml
                    fi
                else
                    # Regular dependencies
                    if [[ "$dep" =~ (~=?|>=?|<=?|==?|!=|\^)[0-9.] ]] || [[ "$dep" == *"*"* ]]; then
                        pkg_name=$(echo "$dep" | sed -E 's/(~=?|>=?|<=?|==?|!=|\^|\*).*//')
                        version=$(echo "$dep" | sed -E "s/^${pkg_name}//")

                        # Convert version specifiers for Poetry
                        if [[ "$version" == "~="* ]]; then
                            version="^$(echo "$version" | sed 's/~=//')"
                        elif [[ "$version" == "~"* ]]; then
                            version="^$(echo "$version" | sed 's/~//')"
                        fi

                        if [[ "$version" == "*" ]] || [ -z "$version" ]; then
                            echo "$pkg_name = \"*\"" >> pyproject.toml
                        else
                            echo "$pkg_name = \"$version\"" >> pyproject.toml
                        fi
                    else
                        echo "$dep = \"*\"" >> pyproject.toml
                    fi
                fi
            done <<< "$main_deps"
        fi

        # Add dev dependencies (already parsed above)
        echo "" >> pyproject.toml
        echo "[tool.poetry.group.dev.dependencies]" >> pyproject.toml
        if [ -n "$dev_deps" ]; then
            while IFS= read -r dep; do
                if [[ "$dep" =~ (~=?|>=?|<=?|==?|!=|\^)[0-9.] ]] || [[ "$dep" == *"*"* ]]; then
                    pkg_name=$(echo "$dep" | sed -E 's/(~=?|>=?|<=?|==?|!=|\^|\*).*//')
                    version=$(echo "$dep" | sed -E "s/^${pkg_name}//")

                    if [[ "$version" == "~="* ]]; then
                        version="^$(echo "$version" | sed 's/~=//')"
                    elif [[ "$version" == "~"* ]]; then
                        version="^$(echo "$version" | sed 's/~//')"
                    fi

                    if [[ "$version" == "*" ]] || [ -z "$version" ]; then
                        echo "$pkg_name = \"*\"" >> pyproject.toml
                    else
                        echo "$pkg_name = \"$version\"" >> pyproject.toml
                    fi
                else
                    echo "$dep = \"*\"" >> pyproject.toml
                fi
            done <<< "$dev_deps"
        fi

        # Add build system
        echo "" >> pyproject.toml
        echo "[build-system]" >> pyproject.toml
        echo 'requires = ["poetry-core"]' >> pyproject.toml
        echo 'build-backend = "poetry.core.masonry.api"' >> pyproject.toml

        # Add preserved extra tool sections
        if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
            format_preserved_toml_sections "$extra_sections" >> pyproject.toml
        fi

        echo "  Generated: pyproject.toml (Poetry format)"
        ;;

    pipenv)
        # Parse dependencies BEFORE overwriting the file!
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")

        # Generate Pipfile from current project
        # Start building the Pipfile
        cat > Pipfile << 'EOF'
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
EOF

        # Add main dependencies (already parsed above)
        if [ -n "$main_deps" ]; then
            while IFS= read -r dep; do
                # Handle dependencies with extras (e.g., livekit-agents[openai,silero])
                if [[ "$dep" == *"["*"]"* ]]; then
                    # Extract package name and extras
                    pkg_name=$(echo "$dep" | sed 's/\[.*//')
                    extras=$(echo "$dep" | sed 's/.*\[\(.*\)\].*/\1/')
                    # Look for version after the closing bracket - handle both ~= and ~ formats and ^
                    version=$(echo "$dep" | grep -oE '(\^|~=?|>=|<=|==|>|<)[0-9.]+' || echo "*")

                    if [ "$version" != "*" ]; then
                        # Handle Poetry's ~ format (convert to ~= for Pipfile)
                        if [[ "$version" == "~"* ]] && [[ "$version" != "~="* ]]; then
                            version=$(echo "$version" | sed 's/^~/~=/')
                        fi
                        # Convert Poetry's caret operator ^ to ~=
                        if [[ "$version" == "^"* ]]; then
                            version=$(echo "$version" | sed 's/^\^/~=/')
                        fi
                        # Format extras properly: split by comma, trim spaces, quote each
                        formatted_extras=$(echo "$extras" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed 's/.*/"&"/' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
                        echo "$pkg_name = {extras = [$formatted_extras], version = \"$version\"}" >> Pipfile
                    else
                        formatted_extras=$(echo "$extras" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed 's/.*/"&"/' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
                        echo "$pkg_name = {extras = [$formatted_extras]}" >> Pipfile
                    fi
                else
                    # Handle regular dependencies
                    # Check for version specifiers (with or without =)
                    if [[ "$dep" =~ (~=?|>=?|<=?|==?|!=|\^)[0-9.] ]] || [[ "$dep" == *"*"* ]]; then
                        # Extract package name (everything before version specifier)
                        pkg_name=$(echo "$dep" | sed -E 's/(~=?|>=?|<=?|==?|!=|\^|\*).*//')
                        # Extract version (everything after package name)
                        version=$(echo "$dep" | sed -E "s/^${pkg_name}//")

                        # Normalize version specifiers for Pipfile format
                        if [[ "$version" == "~"* ]] && [[ "$version" != "~="* ]]; then
                            # Convert ~1.2 to ~=1.2
                            version=$(echo "$version" | sed 's/^~/~=/')
                        fi
                        # Convert Poetry's caret operator ^ to ~=
                        if [[ "$version" == "^"* ]]; then
                            version=$(echo "$version" | sed 's/^\^/~=/')
                        fi

                        # Ensure no double equals (fix ~==)
                        version=$(echo "$version" | sed 's/~==/~=/')

                        if [[ "$version" == "*" ]] || [ -z "$version" ]; then
                            echo "$pkg_name = \"*\"" >> Pipfile
                        else
                            echo "$pkg_name = \"$version\"" >> Pipfile
                        fi
                    else
                        # No version specified
                        echo "$dep = \"*\"" >> Pipfile
                    fi
                fi
            done <<< "$main_deps"
        fi

        # Add dev dependencies (already parsed above)
        echo "" >> Pipfile
        echo "[dev-packages]" >> Pipfile
        if [ -n "$dev_deps" ]; then
            while IFS= read -r dep; do
                # Check for version specifiers (with or without =)
                if [[ "$dep" =~ (~=?|>=?|<=?|==?|!=|\^)[0-9.] ]] || [[ "$dep" == *"*"* ]]; then
                    # Extract package name (everything before version specifier)
                    pkg_name=$(echo "$dep" | sed -E 's/(~=?|>=?|<=?|==?|!=|\^|\*).*//')
                    # Extract version (everything after package name)
                    version=$(echo "$dep" | sed -E "s/^${pkg_name}//")

                    # Normalize version specifiers for Pipfile format
                    if [[ "$version" == "~"* ]] && [[ "$version" != "~="* ]]; then
                        # Convert ~1.2 to ~=1.2
                        version=$(echo "$version" | sed 's/^~/~=/')
                    fi
                    # Convert Poetry's caret operator ^ to ~=
                    if [[ "$version" == "^"* ]]; then
                        version=$(echo "$version" | sed 's/^\^/~=/')
                    fi

                    # Ensure no double equals (fix ~==)
                    version=$(echo "$version" | sed 's/~==/~=/')

                    if [[ "$version" == "*" ]] || [ -z "$version" ]; then
                        echo "$pkg_name = \"*\"" >> Pipfile
                    else
                        echo "$pkg_name = \"$version\"" >> Pipfile
                    fi
                else
                    # No version specified
                    echo "$dep = \"*\"" >> Pipfile
                fi
            done <<< "$dev_deps"
        fi

        # Add Python version requirement
        # For now, use a sensible default - could be enhanced to detect from current Python
        python_version="3.9"
        echo "" >> Pipfile
        echo "[requires]" >> Pipfile
        echo "python_version = \"$python_version\"" >> Pipfile

        echo "  Generated: Pipfile"

        # Preserve tool configurations in a minimal pyproject.toml
        # (using pre-extracted sections from before files were moved)
        if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
            # Create minimal pyproject.toml with just tool configs
            echo "[tool]" > pyproject.toml
            format_preserved_toml_sections "$extra_sections" >> pyproject.toml
            echo "  Preserved: pyproject.toml (tool configurations)"
        else
            # Clean up pyproject.toml if no tool configs to preserve
            rm -f pyproject.toml
        fi
        ;;

    pdm)
        # Parse dependencies BEFORE overwriting the file!
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")

        # Generate pyproject.toml for PDM
        cat > pyproject.toml << 'EOF'
[project]
name = "livekit-agent"
version = "0.1.0"
description = "LiveKit Agent"
requires-python = ">=3.9"
dependencies = [
EOF

        # Add main dependencies
        if [ -n "$main_deps" ]; then
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                # Convert Poetry's ~1.2 to ~=1.2 for PDM
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                # Remove trailing * for any version
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$main_deps"
            echo "" >> pyproject.toml
        fi

        echo "]" >> pyproject.toml
        echo "" >> pyproject.toml
        echo "[tool.pdm]" >> pyproject.toml
        echo "distribution = false" >> pyproject.toml

        # Add dev dependencies (already parsed above)
        if [ -n "$dev_deps" ]; then
            echo "" >> pyproject.toml
            echo "[tool.pdm.dev-dependencies]" >> pyproject.toml
            echo "dev = [" >> pyproject.toml
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$dev_deps"
            echo "" >> pyproject.toml
            echo "]" >> pyproject.toml
        fi

        # Add build system
        echo "" >> pyproject.toml
        echo "[build-system]" >> pyproject.toml
        echo 'requires = ["pdm-backend"]' >> pyproject.toml
        echo 'build-backend = "pdm.backend"' >> pyproject.toml

        # Add preserved extra tool sections
        if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
            format_preserved_toml_sections "$extra_sections" >> pyproject.toml
        fi

        echo "  Generated: pyproject.toml (PDM format)"
        ;;

    hatch)
        # Parse dependencies BEFORE overwriting the file!
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")

        # Generate pyproject.toml for Hatch
        cat > pyproject.toml << 'EOF'
[project]
name = "livekit-agent"
version = "0.1.0"
description = "LiveKit Agent"
requires-python = ">=3.9"
dependencies = [
EOF

        # Add main dependencies
        if [ -n "$main_deps" ]; then
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                # Convert Poetry's ~1.2 to ~=1.2 for Hatch
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                # Remove trailing * for any version
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$main_deps"
            echo "" >> pyproject.toml
        fi

        echo "]" >> pyproject.toml
        echo "" >> pyproject.toml
        echo "[tool.hatch]" >> pyproject.toml
        echo 'build.targets.wheel.packages = ["src"]' >> pyproject.toml

        # Add dev dependencies (already parsed above)
        if [ -n "$dev_deps" ]; then
            echo "" >> pyproject.toml
            echo "[tool.hatch.envs.default]" >> pyproject.toml
            echo "dependencies = [" >> pyproject.toml
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$dev_deps"
            echo "" >> pyproject.toml
            echo "]" >> pyproject.toml
        fi

        # Add build system
        echo "" >> pyproject.toml
        echo "[build-system]" >> pyproject.toml
        echo 'requires = ["hatchling"]' >> pyproject.toml
        echo 'build-backend = "hatchling.build"' >> pyproject.toml

        # Add preserved extra tool sections
        if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
            format_preserved_toml_sections "$extra_sections" >> pyproject.toml
        fi

        echo "  Generated: pyproject.toml (Hatch format)"
        ;;

    uv)
        # Parse dependencies BEFORE overwriting the file!
        main_deps=$(parse_dependencies "main" "$CURRENT_PM")
        dev_deps=$(parse_dependencies "dev" "$CURRENT_PM")

        # Generate pyproject.toml for UV
        cat > pyproject.toml << 'EOF'
[project]
name = "livekit-agent"
version = "0.1.0"
description = "LiveKit Agent"
requires-python = ">=3.9"
dependencies = [
EOF

        # Add main dependencies
        if [ -n "$main_deps" ]; then
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                # Convert Poetry's ~1.2 to ~=1.2 for UV
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                # Remove trailing * for any version
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$main_deps"
            echo "" >> pyproject.toml
        fi

        echo "]" >> pyproject.toml

        # Add dev dependencies (already parsed above)
        if [ -n "$dev_deps" ]; then
            echo "" >> pyproject.toml
            echo "[dependency-groups]" >> pyproject.toml
            echo "dev = [" >> pyproject.toml
            first=true
            while IFS= read -r dep; do
                # Clean up the dependency format
                if [[ "$dep" == *"~"[0-9]* ]] && [[ "$dep" != *"~="* ]]; then
                    dep=$(echo "$dep" | sed 's/\(~\)\([0-9]\)/~=\2/')
                fi
                # Convert Poetry's caret operator ^ to ~=
                if [[ "$dep" == *"^"* ]]; then
                    dep=$(echo "$dep" | sed 's/\^/~=/')
                fi
                if [[ "$dep" == *"*" ]]; then
                    dep=$(echo "$dep" | sed 's/\*$//')
                fi

                if [ "$first" = true ]; then
                    echo -n "    \"$dep\"" >> pyproject.toml
                    first=false
                else
                    echo "," >> pyproject.toml
                    echo -n "    \"$dep\"" >> pyproject.toml
                fi
            done <<< "$dev_deps"
            echo "" >> pyproject.toml
            echo "]" >> pyproject.toml
        fi

        # Add UV-specific configuration
        echo "" >> pyproject.toml
        echo "[tool.uv]" >> pyproject.toml
        echo "package = false" >> pyproject.toml

        # Add preserved extra tool sections
        if [ -n "$extra_sections" ] && [ "$extra_sections" != "{}" ]; then
            format_preserved_toml_sections "$extra_sections" >> pyproject.toml
        fi

        echo "  Generated: pyproject.toml (UV format)"
        ;;
esac

echo "  Entry point: $PROGRAM_MAIN"

# Display instructions based on package manager
echo ""
echo "Next steps:"
echo "  › Install $TARGET_PM:"

case "$TARGET_PM" in
    pip)
        echo "    # pip is usually pre-installed with Python"
        echo ""
        echo "  › Install dependencies:"
        echo "    pip install -r requirements.txt"
        echo ""
        echo "  › For reproducible builds, generate lock file:"
        echo "    pip freeze > requirements.lock"
        ;;
    poetry)
        echo "    curl -sSL https://install.python-poetry.org | python3 -"
        echo ""
        echo "  › Generate lock file:"
        echo "    poetry lock"
        echo ""
        echo "  › Install dependencies:"
        echo "    poetry install"
        ;;
    pipenv)
        echo "    pip install pipenv"
        echo ""
        echo "  › Generate lock file:"
        echo "    pipenv lock"
        echo ""
        echo "  › Install dependencies:"
        echo "    pipenv install"
        ;;
    pdm)
        echo "    pip install pdm"
        echo ""
        echo "  › Generate lock file:"
        echo "    pdm lock"
        echo ""
        echo "  › Install dependencies:"
        echo "    pdm install"
        ;;
    hatch)
        echo "    pip install hatch"
        echo ""
        echo "  › Create environment:"
        echo "    hatch env create"
        echo ""
        echo "  › Install dependencies:"
        echo "    hatch env run pip install -e ."
        ;;
    uv)
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo ""
        echo "  › Generate lock file:"
        echo "    uv lock"
        echo ""
        echo "  › Install dependencies:"
        echo "    uv sync"
        ;;
esac

# Clean up source dependency files that are no longer needed
case "$TARGET_PM" in
    pip|pipenv)
        # These use requirements.txt/Pipfile, don't need the source pyproject.toml
        # (unless it has tool configs, which we've already preserved above)
        ;;
    poetry|pdm|hatch|uv)
        # These use pyproject.toml, clean up old pip/pipenv files
        rm -f requirements.txt requirements-dev.txt Pipfile
        ;;
esac

echo ""
echo "  › Test locally:"
echo "    python $PROGRAM_MAIN dev"
echo ""
echo "  › Build Docker image:"
echo "    docker build -t my-agent ."
echo ""
echo "To rollback: make rollback"

# List existing backups
BACKUP_COUNT=$(ls -d .backup.* 2>/dev/null | wc -l)
if [ $BACKUP_COUNT -gt 0 ]; then
    echo "Existing backups: $(ls -d .backup.* | tr '\n' ' ')"
fi