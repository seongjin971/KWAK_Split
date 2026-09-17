"""Keep application-owned source text in English; user filenames remain Unicode."""
import ast
from pathlib import Path
import re


def test_application_strings_do_not_contain_korean():
    root = Path(__file__).resolve().parents[1]
    paths = [root / "StemSamplePrep.py", *(root / "backend").glob("*.py"),
             *(root / "backend" / "audio_processing").glob("*.py")]
    korean = re.compile("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not korean.search(node.value), f"{path.name}:{node.lineno}: {node.value}"
