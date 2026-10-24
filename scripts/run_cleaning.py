"""Ejecutar desde cualquier carpeta: python scripts/run_cleaning.py."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qfire_cusco.cleaning import CleaningConfig, clean_source, export_result


def main():
    parser = argparse.ArgumentParser(description="Limpiar historial de incendios de Cusco.")
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/incendios_Cusco_2022_2026.csv")
    args = parser.parse_args()
    result = clean_source(args.input, CleaningConfig())
    export_result(result, ROOT)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
