#!/usr/bin/env python3
"""Codebase audit script for Tomorrow.io Weather Data Pipeline.

Checks for:
- Required files existence
- Import cycles
- Test coverage
- Documentation completeness
- Configuration validation

Usage:
    python scripts/audit.py
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Set, Tuple

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_status(message: str, status: str = "info"):
    """Print status message with color."""
    if status == "ok":
        print(f"{GREEN}✓{RESET} {message}")
    elif status == "error":
        print(f"{RED}✗{RESET} {message}")
    elif status == "warning":
        print(f"{YELLOW}!{RESET} {message}")
    else:
        print(f"  {message}")


def check_required_files() -> bool:
    """Check that all required files exist."""
    print("\n=== Checking Required Files ===")

    required_files = [
        "tomorrow/__init__.py",
        "tomorrow/__main__.py",
        "tomorrow/config.py",
        "tomorrow/models.py",
        "tomorrow/db.py",
        "tomorrow/client.py",
        "tomorrow/etl.py",
        "tomorrow/scheduler.py",
        "tomorrow/observability.py",
        "tomorrow/migrations.py",
        "migrations/001_create_locations_table.sql",
        "migrations/002_insert_default_locations.sql",
        "migrations/003_create_weather_data_table.sql",
        "tests/test_config.py",
        "tests/test_models.py",
        "tests/test_db.py",
        "tests/test_client.py",
        "tests/test_etl.py",
        "tests/test_scheduler.py",
        "tests/test_main.py",
        "tests/test_observability.py",
        "tests/test_migrations.py",
        "tests/test_locations_migration.py",
        "tests/test_weather_data_migration.py",
        "tests/test_e2e.py",
        "Dockerfile",
        "docker-compose.yaml",
        ".env.example",
        ".github/workflows/ci.yml",
        ".github/workflows/docker.yml",
        ".pre-commit-config.yaml",
    ]

    all_exist = True
    for file in required_files:
        path = Path(file)
        if path.exists():
            print_status(f"{file}", "ok")
        else:
            print_status(f"{file} - MISSING", "error")
            all_exist = False

    return all_exist


def check_no_import_cycles() -> bool:
    """Check for import cycles in tomorrow package."""
    print("\n=== Checking Import Cycles ===")

    # Build import graph
    imports: dict[str, Set[str]] = {}

    for py_file in Path("tomorrow").glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        module_name = f"tomorrow.{py_file.stem}"
        imports[module_name] = set()

        try:
            with open(py_file) as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("tomorrow."):
                        imports[module_name].add(node.module)
        except Exception as e:
            print_status(f"Error parsing {py_file}: {e}", "error")
            continue

    # Check for cycles using DFS
    def has_cycle(node: str, visited: Set[str], path: Set[str]) -> bool:
        if node in path:
            return True
        if node in visited:
            return False

        visited.add(node)
        path.add(node)

        for neighbor in imports.get(node, set()):
            if has_cycle(neighbor, visited, path):
                return True

        path.remove(node)
        return False

    no_cycles = True
    for module in imports:
        if has_cycle(module, set(), set()):
            print_status(f"Import cycle detected involving {module}", "error")
            no_cycles = False

    if no_cycles:
        print_status("No import cycles detected", "ok")

    return no_cycles


def count_tests() -> Tuple[int, int]:
    """Count total tests and check coverage."""
    print("\n=== Test Count ===")

    test_files = list(Path("tests").glob("test_*.py"))
    total_tests = 0

    for test_file in test_files:
        try:
            with open(test_file) as f:
                tree = ast.parse(f.read())

            test_count = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith("test_"):
                        test_count += 1

            total_tests += test_count
            print_status(f"{test_file.name}: {test_count} tests", "ok")
        except Exception as e:
            print_status(f"Error parsing {test_file}: {e}", "warning")

    print_status(f"Total: {total_tests} tests", "ok")
    return total_tests, len(test_files)


def check_code_quality() -> bool:
    """Check code quality with ruff."""
    print("\n=== Code Quality (Ruff) ===")

    result = os.system("ruff check tomorrow/ --ignore E501 > /dev/null 2>&1")

    if result == 0:
        print_status("No linting errors", "ok")
        return True
    else:
        print_status(
            "Linting errors found - run 'ruff check tomorrow/ --ignore E501'", "error"
        )
        return False


def check_formatting() -> bool:
    """Check code formatting with ruff."""
    print("\n=== Code Formatting (Ruff) ===")

    result = os.system("ruff format tomorrow/ --check > /dev/null 2>&1")

    if result == 0:
        print_status("Code is properly formatted", "ok")
        return True
    else:
        print_status("Formatting issues - run 'ruff format tomorrow/'", "error")
        return False


def check_docker_compose() -> bool:
    """Validate docker-compose.yaml."""
    print("\n=== Docker Compose Validation ===")

    result = os.system("docker compose config > /dev/null 2>&1")

    if result == 0:
        print_status("docker-compose.yaml is valid", "ok")
        return True
    else:
        print_status("docker-compose.yaml has errors", "error")
        return False


def check_environment_variables() -> bool:
    """Check environment variable documentation."""
    print("\n=== Environment Variables ===")

    required_vars = [
        "TOMORROW_API_KEY",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "LOG_LEVEL",
    ]

    # Check .env.example
    if not Path(".env.example").exists():
        print_status(".env.example not found", "error")
        return False

    with open(".env.example") as f:
        env_content = f.read()

    all_documented = True
    for var in required_vars:
        if var in env_content:
            print_status(f"{var} documented", "ok")
        else:
            print_status(f"{var} not in .env.example", "warning")
            all_documented = False

    return all_documented


def generate_summary(
    files_ok: bool,
    cycles_ok: bool,
    quality_ok: bool,
    format_ok: bool,
    docker_ok: bool,
    env_ok: bool,
    total_tests: int,
) -> bool:
    """Generate audit summary."""
    print("\n" + "=" * 50)
    print("AUDIT SUMMARY")
    print("=" * 50)

    checks = [
        ("Required Files", files_ok),
        ("Import Cycles", cycles_ok),
        ("Code Quality", quality_ok),
        ("Code Formatting", format_ok),
        ("Docker Compose", docker_ok),
        ("Environment Variables", env_ok),
    ]

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    for name, ok in checks:
        if ok:
            print_status(name, "ok")
        else:
            print_status(name, "error")

    print(f"\nTotal Tests: {total_tests}")
    print(f"Checks Passed: {passed}/{total}")

    return passed == total


def main():
    """Run complete audit."""
    print("=" * 50)
    print("Tomorrow.io Weather Pipeline - Codebase Audit")
    print("=" * 50)

    files_ok = check_required_files()
    cycles_ok = check_no_import_cycles()
    total_tests, _ = count_tests()
    quality_ok = check_code_quality()
    format_ok = check_formatting()
    docker_ok = check_docker_compose()
    env_ok = check_environment_variables()

    all_ok = generate_summary(
        files_ok,
        cycles_ok,
        quality_ok,
        format_ok,
        docker_ok,
        env_ok,
        total_tests,
    )

    print()
    if all_ok:
        print_status("All checks passed! ✨", "ok")
        return 0
    else:
        print_status("Some checks failed. Please review above.", "error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
