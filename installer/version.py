"""Read the application version without importing Qt or application code."""
import ast
from pathlib import Path

source = Path(__file__).resolve().parent.parent / "main.py"
for node in ast.parse(source.read_text(encoding="utf-8")).body:
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets
    ):
        version = ast.literal_eval(node.value)
        if not isinstance(version, str) or not version:
            raise SystemExit("VERSION must be a nonempty string")
        print(version)
        break
else:
    raise SystemExit("VERSION was not found in main.py")
