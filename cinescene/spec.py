"""Scene spec loading and validation (no third-party dependencies).

Implements the subset of JSON Schema used by ``schema/scene_spec.schema.json``:
type, enum, minimum, maximum, pattern, required, properties,
additionalProperties=false and default. Defaults are filled in, so code
downstream can rely on every field being present.
"""

import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "scene_spec.schema.json"

_TYPES = {
    "object": dict, "string": str, "boolean": bool, "array": list,
    "integer": int, "number": (int, float),
}


class SpecError(ValueError):
    """Raised with *all* problems found, one per line."""


def _check(value, schema, path, errors):
    t = schema.get("type")
    if t:
        ok = isinstance(value, _TYPES[t])
        if t in ("integer", "number") and isinstance(value, bool):
            ok = False  # bool is an int subclass in Python; reject it
        if not ok:
            errors.append(f"{path}: expected {t}, got {type(value).__name__} ({value!r})")
            return value
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} < minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: {value} > maximum {schema['maximum']}")
    if "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if t == "object":
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}.{req}: required field missing")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errors.append(f"{path}.{k}: unknown field (allowed: {sorted(props)})")
        for k, sub in props.items():
            if k not in value and "default" in sub:
                value[k] = copy.deepcopy(sub["default"])
            if k in value:
                value[k] = _check(value[k], sub, f"{path}.{k}", errors)
    return value


def load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(spec: dict) -> dict:
    """Return a new spec with defaults filled in, or raise SpecError."""
    errors = []
    out = _check(copy.deepcopy(spec), load_schema(), "spec", errors)
    if not errors:
        from . import recipes
        recipes.apply_defaults(out)
        errors += recipes.check_spec_against_recipe(out)
    if errors:
        raise SpecError("\n".join(errors))
    return out


def load(path) -> dict:
    with open(path, encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise SpecError(f"{path}: not valid JSON ({e})")
    return validate(raw)


def main(argv=None):
    """CLI: ``python3 -m cinescene.spec examples/foo.json`` -> prints the filled spec."""
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python3 -m cinescene.spec SPEC.json [...]")
        return 2
    code = 0
    for p in args:
        try:
            print(json.dumps(load(p), indent=2, ensure_ascii=False))
            print(f"OK  {p}", file=sys.stderr)
        except SpecError as e:
            print(f"FAIL {p}\n{e}", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
