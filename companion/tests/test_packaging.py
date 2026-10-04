"""The AddOn's file list and version live in four places (two TOCs, the wheel's force-include, the Lua test).
A file added to one and not the others gives someone a broken AddOn; this is the check."""
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).parents[2]
ADDON = REPO / "addon" / "Rambleon"
GENERATED = {"Chapters.lua"}          # written by `ramble publish`; listed in the TOCs, never shipped


def toc_files(name: str) -> list[str]:
    return [ln.strip() for ln in (ADDON / name).read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def toc_version(name: str) -> str:
    return re.search(r"^## Version:\s*(\S+)", (ADDON / name).read_text(), re.M).group(1)


def test_addon_file_lists_agree():
    lua = {p.name for p in ADDON.glob("*.lua")} - GENERATED
    camelot = toc_files("Rambleon_Camelot.toc")
    assert set(camelot) - GENERATED == lua
    assert [f for f in camelot if f != "Forever.lua"] == toc_files("Rambleon.toc")     # same files, same order
    project = tomllib.loads((REPO / "companion" / "pyproject.toml").read_text())
    shipped = {Path(src).name for src in project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]}
    assert shipped == lua | {"Rambleon.toc", "Rambleon_Camelot.toc", "Bindings.xml"}
    tested = re.search(r"local files = \{(.*?)\}", (REPO / "addon" / "tests" / "run.lua").read_text()).group(1)
    assert set(re.findall(r'"([^"]+)"', tested)) == lua
    assert "Bindings.xml" not in camelot                # loaded by name; listing it loads it twice


def test_versions_agree():
    from rambleon import __version__
    project = tomllib.loads((REPO / "companion" / "pyproject.toml").read_text())
    assert project["project"]["version"] == __version__ == toc_version("Rambleon.toc") == toc_version("Rambleon_Camelot.toc")
