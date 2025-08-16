# Package Manager Conversion Tool for Python LiveKit Agent
# This Makefile helps convert between different Python package managers

.PHONY: help convert-to-pip convert-to-poetry convert-to-pipenv convert-to-pdm convert-to-hatch convert-to-uv rollback list-backups clean-backups

# Default target shows help
help:
	@echo "Package Manager Conversion Tool - Python"
	@echo "========================================="
	@echo ""
	@echo "⚠️  WARNING: Converting will reset Dockerfiles to LiveKit templates"
	@echo "    Any custom Dockerfile modifications will be lost!"
	@echo ""
	@echo "Available conversion targets:"
	@echo "  make convert-to-pip      - Convert to pip (requirements.txt)"
	@echo "  make convert-to-poetry   - Convert to Poetry"
	@echo "  make convert-to-pipenv   - Convert to Pipenv"
	@echo "  make convert-to-pdm      - Convert to PDM"
	@echo "  make convert-to-hatch    - Convert to Hatch"
	@echo "  make convert-to-uv       - Convert to UV"
	@echo ""
	@echo "Backup management:"
	@echo "  make rollback           - Restore from backup (interactive if multiple)"
	@echo "  make list-backups       - Show available backups"
	@echo "  make clean-backups      - Remove all backup directories"
	@echo ""
	@echo "Notes:"
	@echo "  • Backups are saved as .backup.{package-manager}"
	@echo "  • Multiple conversions create multiple backups"
	@echo "  • Rollback is interactive when multiple backups exist"
	@echo "  • Lock files are NOT generated automatically - see instructions after conversion"

convert-to-pip:
	@bash scripts/convert-package-manager.sh pip

convert-to-poetry:
	@bash scripts/convert-package-manager.sh poetry

convert-to-pipenv:
	@bash scripts/convert-package-manager.sh pipenv

convert-to-pdm:
	@bash scripts/convert-package-manager.sh pdm

convert-to-hatch:
	@bash scripts/convert-package-manager.sh hatch

convert-to-uv:
	@bash scripts/convert-package-manager.sh uv

rollback:
	@bash scripts/rollback.sh $(PM)

list-backups:
	@echo "Available backups:"
	@for dir in .backup.*; do \
		if [ -d "$$dir" ]; then \
			echo "  $$dir"; \
		fi; \
	done 2>/dev/null || echo "  No backups found"

clean-backups:
	@echo "Removing all backup directories..."
	@rm -rf .backup.* 2>/dev/null || true
	@echo "✔ All backups removed"