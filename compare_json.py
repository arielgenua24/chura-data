#!/usr/bin/env python3
"""compare_json.py

Compara dos archivos JSON (nuevo.json y viejo.json) y genera:

1. **diferencias.json** – objeto con cuatro secciones:
   - `to_insert`   : ítems que existen sólo en el JSON nuevo
   - `to_remove`   : ítems que existen sólo en el JSON viejo
   - `unchanged`   : ítems idénticos en ambos JSON
   - `anomalies`   : diagnóstico completo (duplicados, diferencias, etc.)

2. **anomalies.json** – lista plana con **sólo los ítems del JSON nuevo** que
   presentan anomalías.

3. **ready_to_upsert.json** – unión de:
   - `to_insert`
   - `anomalies.json` (ya normalizado, sin claves auxiliares)

   Se eliminan duplicados de título (preferencia al primer elemento).

Regla extra: cualquier ítem cuyo `details` consista únicamente en “AGOTADO” se
ignora por completo y no aparece en ningún archivo.

Uso por defecto:
    python compare_json.py

Uso avanzado:
    python compare_json.py <new.json> <old.json> [diferencias.json] [anomalies.json] [ready.json]

El algoritmo ignora mayúsculas, tildes, espacios duplicados, NBSP y normaliza
precios para comparación exhaustiva.
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
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00A0", " ")).strip()


def normalize_text(text: str) -> str:
    return _strip_accents(normalize_whitespace(text).lower())


def normalize_price(price: str) -> str:
    s = normalize_whitespace(price.lower()).replace("ars", "")
    s = re.sub(r"[^0-9.,]", "", s)
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    if s.count(".") > 1:
        dec = s.split(".")[-1]
        ent = "".join(s.split(".")[:-1])
        s = f"{ent}.{dec}"
    elif s.count(",") > 1:
        dec = s.split(",")[-1]
        ent = "".join(s.split(",")[:-1])
        s = f"{ent}.{dec}"
    return s


def normalize_item(item: Dict[str, Any]) -> Tuple[str, Tuple[str, ...], str]:
    title = normalize_text(item.get("title", ""))
    details = tuple(sorted(normalize_text(d) for d in item.get("details", [])))
    price = normalize_price(item.get("price", ""))
    return title, details, price

# ---------------------------------------------------------------------------
# Filtro de "AGOTADO"
# ---------------------------------------------------------------------------

def is_sold_out(item: Dict[str, Any]) -> bool:
    details = item.get("details", [])
    if len(details) != 1:
        return False
    text = normalize_text(details[0]).replace("*", "").strip()
    return text == "agotado"


def filter_sold_out(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [it for it in items if not is_sold_out(it)]

# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        sys.exit(f"Error: no se encontró el archivo {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("El JSON de entrada debe ser un array de objetos.")
        return filter_sold_out(data)
    except json.JSONDecodeError as e:
        sys.exit(f"Error de parseo JSON en {path}: {e}")

# ---------------------------------------------------------------------------
# Comparación principal
# ---------------------------------------------------------------------------

def compare(new_items: List[Dict[str, Any]], old_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    to_insert, to_remove, unchanged, anomalies = [], [], [], []

    def detect_duplicates(items: List[Dict[str, Any]], label: str):
        grouped: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list)
        for it in items:
            grouped[normalize_text(it.get("title", ""))].append(it)
        for title, lst in grouped.items():
            if len(lst) > 1:
                anomalies.append({
                    "item": lst,
                    "source": label,
                    "reason": f"{label} contiene {len(lst)} entradas duplicadas para el título '{title}'"
                })

    detect_duplicates(new_items, "nuevo.json")
    detect_duplicates(old_items, "viejo.json")

    new_map = {normalize_text(i["title"]): i for i in new_items}
    old_map = {normalize_text(i["title"]): i for i in old_items}

    for key, new_it in new_map.items():
        if key not in old_map:
            to_insert.append(new_it)
        else:
            if normalize_item(new_it) == normalize_item(old_map[key]):
                unchanged.append(new_it)
            else:
                anomalies.append({
                    "item": {"new": new_it, "old": old_map[key]},
                    "source": "both",
                    "reason": "Mismo título pero 'details' y/o 'price' difieren"
                })

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
# Anomalías planas (solo new) y unión final
# ---------------------------------------------------------------------------

def flatten_new_anomalies(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for entry in anomalies:
        item = entry.get("item")
        if isinstance(item, list):
            if entry.get("source") == "nuevo.json":
                flat.extend(item)
        elif isinstance(item, dict) and "new" in item:
            flat.append(item["new"])
    seen = set()
    uniq = []
    for it in flat:
        k = normalize_text(it.get("title", ""))
        if k not in seen:
            uniq.append(it)
            seen.add(k)
    return uniq


def build_ready_list(to_insert: List[Dict[str, Any]], anomalies_new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined = []
    seen = set()
    for it in to_insert + anomalies_new:
        k = normalize_text(it.get("title", ""))
        if k not in seen:
            combined.append(it)
            seen.add(k)
    return combined

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    new_path = Path(args[0]) if len(args) >= 1 else Path("nuevo.json")
    old_path = Path(args[1]) if len(args) >= 2 else Path("viejo.json")
    diff_path = Path(args[2]) if len(args) >= 3 else Path("diferencias.json")
    anomalies_path = Path(args[3]) if len(args) >= 4 else Path("anomalies.json")
    ready_path = Path(args[4]) if len(args) >= 5 else Path("ready_to_upsert.json")

    new_items = load_json(new_path)
    old_items = load_json(old_path)

    result = compare(new_items, old_items)
    anomalies_only_new = flatten_new_anomalies(result["anomalies"])
    ready_items = build_ready_list(result["to_insert"], anomalies_only_new)

    # Salidas
    diff_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    anomalies_path.write_text(json.dumps(anomalies_only_new, ensure_ascii=False, indent=2), encoding="utf-8")
    ready_path.write_text(json.dumps(ready_items, ensure_ascii=False, indent=2), encoding="utf-8")

    # Resumen
    print("Resultados escritos en:")
    print(f"  {diff_path}")
    print(f"  {anomalies_path}")
    print(f"  {ready_path}\n")

    def p(label, value):
        print(f"  {label:<28}: {value}")

    print("Resumen de la comparación:")
    p("Nuevos a insertar", len(result["to_insert"]))
    p("Para eliminar", len(result["to_remove"]))
    p("Sin cambios", len(result["unchanged"]))
    p("Anomalías totales", len(result["anomalies"]))
    p("Anomalías (solo new)", len(anomalies_only_new))
    p("READY total", len(ready_items))


if __name__ == "__main__":
    main()
