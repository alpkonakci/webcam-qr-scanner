"""Inventory the actual PyInstaller inputs and copy missing distribution notices.

Build-time only; this module is not imported by the application.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil


def input_files(value):
    if isinstance(value, (tuple, list)):
        if len(value) == 3 and all(isinstance(item, str) for item in value):
            if value[2] in {"PYMODULE", "PYSOURCE", "BINARY", "EXTENSION", "DATA"}:
                yield Path(value[1]).resolve()
        for item in value:
            yield from input_files(item)


def inventory(analysis: Path):
    files = set(input_files(ast.literal_eval(analysis.read_text(encoding="utf-8"))))
    rows = []
    mapped = set()
    for dist in metadata.distributions():
        owned = {Path(dist.locate_file(file)).resolve() for file in dist.files or []}
        included_set = files & owned
        # comtypes generates this package initializer locally; it is not in
        # the wheel RECORD but is part of comtypes, not an unknown dependency.
        if dist.metadata["Name"].lower() == "comtypes":
            generated = Path(dist.locate_file("comtypes/gen/__init__.py")).resolve()
            included_set.update(files & {generated})
        included = sorted(included_set)
        if not included:
            continue
        mapped.update(included)
        license_files = []
        for file in dist.files or []:
            path = Path(dist.locate_file(file))
            if ".dist-info" in str(file) and any(
                part.lower().startswith(("license", "copying", "notice", "authors"))
                for part in Path(str(file)).parts[1:]
            ) and path.is_file():
                if path.stat().st_size == 0:
                    raise ValueError(f"Empty license material: {path}")
                license_files.append(path)
        if not license_files:
            raise ValueError(f"No license material for {dist.metadata['Name']}")
        rows.append({
            "name": dist.metadata["Name"], "version": dist.version,
            "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "see notices"),
            "files": [str(file) for file in included],
            "license_files": license_files,
        })
    unknown = [str(file) for file in files - mapped if "site-packages" in str(file).lower()]
    if unknown:
        raise ValueError(f"Unmapped third-party build inputs: {sorted(unknown)}")
    return sorted(rows, key=lambda row: row["name"].lower())


def copy_material(rows, destination: Path):
    for row in rows:
        target = destination / "INVENTORY_LICENSES" / row["name"]
        target.mkdir(parents=True, exist_ok=True)
        for source in row["license_files"]:
            # Preserve nested license trees; paths begin at their dist-info root.
            parts = source.parts
            index = next(i for i, part in enumerate(parts) if part.endswith(".dist-info"))
            output = target.joinpath(*parts[index + 1:])
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
    public_rows = [{key: value for key, value in row.items() if key not in {"files", "license_files"}}
                   | {"input_count": len(row["files"])} for row in rows]
    (destination / "DEPENDENCY_INVENTORY.json").write_text(
        json.dumps(public_rows, indent=2) + "\n", encoding="utf-8")


def verify_sources(source_directory: Path):
    manifest = json.loads((source_directory / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest:
        filename = row["filename"]
        if Path(filename).name != filename:
            raise ValueError("Source file must be directly inside source directory")
        actual = hashlib.sha256((source_directory / filename).read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ValueError(f"Source archive checksum mismatch: {filename}")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--sources", type=Path)
    args = parser.parse_args()
    rows = inventory(args.analysis)
    if args.destination:
        copy_material(rows, args.destination)
    if args.sources:
        verify_sources(args.sources)
        if args.destination:
            shutil.copytree(args.sources, args.destination / "SOURCES", dirs_exist_ok=True)
    print(json.dumps([{key: value for key, value in row.items()
                       if key not in {"files", "license_files"}} for row in rows], indent=2))


if __name__ == "__main__":
    main()
