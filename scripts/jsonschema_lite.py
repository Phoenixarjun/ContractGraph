#!/usr/bin/env python3
"""jsonschema_lite - a dependency-free validator for the JSON Schema subset that
ContractGraph node/main contracts actually use (draft 2020-12 features observed
in the bundle). PyYAML/jsonschema are not installed and CLAUDE.md forbids adding
heavy deps, so this covers exactly the keywords our contracts use and resolves
local $refs across files.

Supported: type (incl unions like ["string","null"]), required, properties,
additionalProperties (bool | schema), items, enum, const, minItems, maxItems,
minLength, maxLength, minimum, maximum, uniqueItems, format (uri/date/date-time),
allOf/anyOf/oneOf, and $ref (internal "#/..." + external "file#/pointer",
resolved relative to the referring file's directory).

NOT a general-purpose validator: no pattern, dependentSchemas, if/then/else,
$dynamicRef, etc. Those never appear in our contracts. Errors are path-specific:
[{"path": "data.business.products[0].name", "message": "..."}].
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


class Validator:
    def __init__(self):
        self._docs = {}

    def _load(self, path: Path):
        ap = str(path.resolve())
        if ap not in self._docs:
            self._docs[ap] = json.loads(path.read_text(encoding="utf-8"))
        return self._docs[ap]

    @staticmethod
    def _pointer(doc, pointer: str):
        cur = doc
        for part in pointer.split("/"):
            if part == "":
                continue
            part = part.replace("~1", "/").replace("~0", "~")
            cur = cur[int(part)] if isinstance(cur, list) else cur[part]
        return cur

    def _resolve_ref(self, ref: str, base_dir: Path, root_doc):
        file_part, _, ptr = ref.partition("#")
        if file_part == "":
            target_doc, new_base = root_doc, base_dir
        else:
            target_path = base_dir / file_part
            target_doc = self._load(target_path)
            new_base = target_path.parent
        return self._pointer(target_doc, ptr), new_base, target_doc

    @staticmethod
    def _typename(v):
        if isinstance(v, bool):
            return "boolean"
        if v is None:
            return "null"
        if isinstance(v, str):
            return "string"
        if isinstance(v, int):
            return "integer"
        if isinstance(v, float):
            return "number"
        if isinstance(v, list):
            return "array"
        if isinstance(v, dict):
            return "object"
        return type(v).__name__

    def _type_ok(self, v, t) -> bool:
        types = t if isinstance(t, list) else [t]
        name = self._typename(v)
        for want in types:
            if want == name:
                return True
            if want == "number" and name in ("integer", "number"):
                return True
        return False

    @staticmethod
    def _format_err(v, fmt):
        if fmt == "uri" and not _URI.match(v):
            return f"not a valid uri: {v!r}"
        if fmt == "date" and not _DATE.match(v):
            return f"not a valid date (YYYY-MM-DD): {v!r}"
        if fmt == "date-time" and not _DATETIME.match(v):
            return f"not a valid date-time: {v!r}"
        return None

    def validate(self, instance, schema, base_dir: Path, root_doc=None):
        errors = []
        self._v(instance, schema, base_dir, root_doc if root_doc is not None else schema, "$", errors)
        return errors

    def _v(self, inst, schema, base_dir, root_doc, path, errors):
        if schema is True or schema == {}:
            return
        if schema is False:
            errors.append({"path": path, "message": "schema is false; no value allowed"})
            return
        if not isinstance(schema, dict):
            return

        if "$ref" in schema:
            sub, nb, nd = self._resolve_ref(schema["$ref"], base_dir, root_doc)
            self._v(inst, sub, nb, nd, path, errors)
            return

        for key in ("allOf", "anyOf", "oneOf"):
            if key not in schema:
                continue
            subs = schema[key]
            passes = []
            for s in subs:
                e = []
                self._v(inst, s, base_dir, root_doc, path, e)
                passes.append(not e)
            if key == "allOf" and not all(passes):
                errors.append({"path": path, "message": "failed allOf"})
            if key == "anyOf" and not any(passes):
                errors.append({"path": path, "message": "matched none of anyOf"})
            if key == "oneOf" and sum(passes) != 1:
                errors.append({"path": path, "message": f"matched {sum(passes)} of oneOf (need exactly 1)"})

        if "type" in schema and not self._type_ok(inst, schema["type"]):
            errors.append({"path": path, "message": f"expected type {schema['type']}, got {self._typename(inst)}"})
            return
        if "const" in schema and inst != schema["const"]:
            errors.append({"path": path, "message": f"expected const {schema['const']!r}, got {inst!r}"})
        if "enum" in schema and inst not in schema["enum"]:
            errors.append({"path": path, "message": f"{inst!r} not in enum {schema['enum']}"})
        if "format" in schema and isinstance(inst, str):
            fe = self._format_err(inst, schema["format"])
            if fe:
                errors.append({"path": path, "message": fe})

        if isinstance(inst, str):
            if "minLength" in schema and len(inst) < schema["minLength"]:
                errors.append({"path": path, "message": f"string shorter than minLength {schema['minLength']}"})
            if "maxLength" in schema and len(inst) > schema["maxLength"]:
                errors.append({"path": path, "message": f"string longer than maxLength {schema['maxLength']}"})

        if isinstance(inst, (int, float)) and not isinstance(inst, bool):
            if "minimum" in schema and inst < schema["minimum"]:
                errors.append({"path": path, "message": f"less than minimum {schema['minimum']}"})
            if "maximum" in schema and inst > schema["maximum"]:
                errors.append({"path": path, "message": f"greater than maximum {schema['maximum']}"})

        if isinstance(inst, list):
            if "minItems" in schema and len(inst) < schema["minItems"]:
                errors.append({"path": path, "message": f"fewer than minItems {schema['minItems']} (got {len(inst)})"})
            if "maxItems" in schema and len(inst) > schema["maxItems"]:
                errors.append({"path": path, "message": f"more than maxItems {schema['maxItems']} (got {len(inst)})"})
            if schema.get("uniqueItems"):
                seen = []
                for it in inst:
                    if it in seen:
                        errors.append({"path": path, "message": "items are not unique"})
                        break
                    seen.append(it)
            if "items" in schema:
                for i, it in enumerate(inst):
                    self._v(it, schema["items"], base_dir, root_doc, f"{path}[{i}]", errors)

        if isinstance(inst, dict):
            props = schema.get("properties", {})
            for req in schema.get("required", []):
                if req not in inst:
                    errors.append({"path": f"{path}.{req}", "message": "required property missing"})
            ap = schema.get("additionalProperties", True)
            for k, val in inst.items():
                if k in props:
                    self._v(val, props[k], base_dir, root_doc, f"{path}.{k}", errors)
                elif ap is False:
                    errors.append({"path": f"{path}.{k}", "message": "additional property not allowed"})
                elif isinstance(ap, dict):
                    self._v(val, ap, base_dir, root_doc, f"{path}.{k}", errors)


def validate_instance(instance, schema_path: Path):
    """Validate an instance against a schema file; return path-specific errors."""
    schema_path = Path(schema_path)
    v = Validator()
    root = v._load(schema_path)
    return v.validate(instance, root, schema_path.parent, root)


def validate_subschema(instance, schema_path: Path, pointer: str):
    """Validate against a JSON pointer inside a schema file (e.g. /properties/data)."""
    schema_path = Path(schema_path)
    v = Validator()
    root = v._load(schema_path)
    sub = v._pointer(root, pointer)
    return v.validate(instance, sub, schema_path.parent, root)
