#!/usr/bin/env python3
"""compare_json.py

Compara dos archivos JSON (nuevo.json y viejo.json) y genera diferencias.json
con cuatro secciones:

- to_insert   : ítems que existen sólo en el JSON nuevo
- to_remove   : ítems que existen sólo en el JSON viejo
- unchanged   : ítems idénticos en ambos JSON
- anomalies   : ítems con el mismo título pero con detalles o precio distintos,
                duplicados internos o cualquier situación ambigua

Uso:
    python compare_json.py                # usa nuevo.json y viejo.json en cwd
    python compare_json.py new.json old.json [salida.json]

El algoritmo ignora mayúsculas, espacios duplicados, NBSP, tildes y separadores
al comparar textos, y normaliza precios para comparación profunda.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Utilidades de normalización
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Elimina acentos y diacríticos con NFKD."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_whitespace(text: str) -> str:
    """Reemplaza NBSP por espacio y colapsa espacios consecutivos."""
    return re.sub(r"\s+", " ", text.replace("\u00A0", " ")).strip()


def normalize_text(text: str) -> str:
    """Normaliza texto para comparación insensible a mayúsculas y acentos."""
    text = normalize_whitespace(text)
    text = _strip_accents(text.lower())
    return text


def normalize_price(price: str) -> str:
    """Convierte un precio a sólo dígitos y dos decimales para comparación."""
    s = normalize_whitespace(price.lower())
    s = s.replace("ars", "")
    # Mantén dígitos, coma y punto
    s = re.sub(r"[^0-9.,]", "", s)
    # Si hay coma decimal y ningún punto decimal, cambia a punto
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    # Quita separadores de miles dejando los decimales
    if s.count(".") > 1:
        decimal = s.split(".")[-1]
        entero = "".join(s.split(".")[:-1])
        s = f"{entero}.{decimal}"
    elif s.count(",") > 1:
        decimal = s.split(",")[-1]
        entero = "".join(s.split(",")[:-1])
        s = f"{entero}.{decimal}"
    return s


def normalize_item(item: Dict[str, Any]) -> Tuple[str, Tuple[str, ...], str]:
    """Devuelve un hashable normalizado del ítem."""
    title = normalize_text(item.get("title", ""))
    details = tuple(sorted(normalize_text(d) for d in item.get("details", [])))
    price = normalize_price(item.get("price", ""))
    return title, details, price

# ---------------------------------------------------------------------------
# Carga y validación de datos
# ---------------------------------------------------------------------------

def load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        sys.exit(f"Error: no se encontró el archivo {path}")
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("El JSON de entrada debe ser un array de objetos.")
        return data
    except json.JSONDecodeError as e:
        sys.exit(f"Error de parseo JSON en {path}: {e}")

# ---------------------------------------------------------------------------
# Lógica de comparación
# ---------------------------------------------------------------------------

def compare(new_items: List[Dict[str, Any]], old_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    to_insert: List[Dict[str, Any]] = []
    to_remove: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    anomalies: List[Dict[str, Any]] = []

    # Detectar duplicados internos en cada fuente
    def detect_duplicates(items: List[Dict[str, Any]], label: str):
        seen: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list)
        for it in items:
            key = normalize_text(it.get("title", ""))
            seen[key].append(it)
        for title, lst in seen.items():
            if len(lst) > 1:
                anomalies.append(
                    {
                        "item": lst,
                        "reason": f"'{label}' contiene {len(lst)} entradas duplicadas para el título '{title}'",
                    }
                )

    detect_duplicates(new_items, "nuevo.json")
    detect_duplicates(old_items, "viejo.json")

    new_map = {normalize_text(i["title"]): i for i in new_items}
    old_map = {normalize_text(i["title"]): i for i in old_items}

    # Ítems presentes en el nuevo JSON
    for key, new_it in new_map.items():
        if key not in old_map:
            to_insert.append(new_it)
        else:
            if normalize_item(new_it) == normalize_item(old_map[key]):
                unchanged.append(new_it)
            else:
                anomalies.append(
                    {
                        "item": {"new": new_it, "old": old_map[key]},
                        "reason": "Mismo título pero 'details' y/o 'price' difieren",
                    }
                )

    # Ítems que ya no existen en el nuevo JSON
    for key, old_it in old_map.items():
        if key not in new_map:
            to_remove.append(old_it)

    return {
        "to_insert": to_insert,
        "to_remove": to_remove,
        "unchanged": unchanged,
        "anomalies": anomalies,
    }

# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    new_path = Path(args[0]) if len(args) >= 1 else Path("nuevo.json")
    old_path = Path(args[1]) if len(args) >= 2 else Path("viejo.json")
    out_path = Path(args[2]) if len(args) >= 3 else Path("diferencias.json")

    new_items = load_json(new_path)
    old_items = load_json(old_path)
    result = compare(new_items, old_items)

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Resumen en la terminal
    print("Resultado escrito en", out_path)
    print("\nResumen de la comparación:")
    print(f"  Nuevos a insertar : {len(result['to_insert'])}")
    print(f"  Para eliminar     : {len(result['to_remove'])}")
    print(f"  Sin cambios       : {len(result['unchanged'])}")
    print(f"  Anomalías         : {len(result['anomalies'])}")


if __name__ == "__main__":
    main()
