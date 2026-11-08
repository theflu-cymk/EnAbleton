"""Verify release resources and run a temporary installation without touching Live."""

import json
from pathlib import Path
import tarfile
import tempfile
import zipfile
from unittest.mock import patch
from enableton import __version__
from enableton.cli import main

root = Path(__file__).resolve().parents[1]
wheels = sorted((root / "dist").glob("*.whl"))
sources = sorted((root / "dist").glob("*.tar.gz"))
if not wheels or not sources:
    raise SystemExit("Run `uv build` first; no wheel or sdist found in dist/")
wheel, source = wheels[-1], sources[-1]
forbidden = (".wav", ".aif", ".aiff", ".mp3", ".als", ".adv", ".adg", ".cfg")
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    for resource in (
        "enableton/production_recipes.json",
        "enableton/artist_methods.json",
        "enableton/remix_recipes.json",
        "enableton/remix_audio.py",
        "enableton/remix_live.py",
        "enableton/remix_preview.py",
        "enableton/remix_midi.py",
        "enableton/remix_assets.py",
        "enableton/remix_worker.py",
        "enableton/remix_arrangement.py",
        "enableton/remix_tools.py",
        "enableton/remix_cli.py",
        "enableton/jsonio.py",
        "enableton/numbers.py",
        "enableton/licenses/ableton-live-mcp-MIT.txt",
    ):
        assert resource in names, resource
    recipes = json.loads(archive.read("enableton/production_recipes.json"))["entries"]
    assert len(recipes) == 50, len(recipes)
    assert sum(1 for entry in recipes if entry.get("sources")) == 45, "sourced recipe count"
    assert len({entry["id"] for entry in recipes}) == len(recipes), "duplicate recipe id"
    assert not any(
        name.lower().endswith(forbidden) and Path(name).name != "setup.cfg" for name in names
    )
with tarfile.open(source) as archive:
    names = archive.getnames()
    for suffix in (
        "docs/INSTALLATION.md",
        "docs/TOOL_CATALOG.md",
        "docs/FEATURES.md",
        "uv.lock",
        "tests/integration/test_transport.py",
    ):
        assert any(name.endswith(suffix) for name in names), suffix
    assert not any(
        name.lower().endswith(forbidden) and Path(name).name != "setup.cfg" for name in names
    )
with tempfile.TemporaryDirectory(prefix="enableton-release-test-") as directory:
    library = Path(directory)
    with patch("pathlib.Path.home", return_value=library / "home"):
        assert main(["install", "--user-library", str(library)]) == 0
    manifest = json.loads(
        (library / "Remote Scripts" / "EnAbleton" / "ext-manifest.json").read_text()
    )
    assert manifest["enableton_version"] == __version__
print("Wheel/sdist resources and temporary User Library installation verified; no Live changes.")
