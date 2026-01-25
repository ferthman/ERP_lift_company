import shutil
import subprocess
from pathlib import Path

import pytest


def run_node_script(script):
    if not shutil.which("node"):
        pytest.skip("node is not available for JS URL builder test")
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return result.stdout.strip().splitlines()


def test_2gis_url_builder_prefers_lon_lat_and_fallbacks():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "static" / "mobile-2gis.js"
    script = f"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("{script_path.as_posix()}", "utf8");
vm.runInThisContext(code);
    console.log(build2gisWebUrl({{ lat: 55.75, lon: 37.61, address: "Москва" }}));
    console.log(build2gisWebUrl({{ lat: null, lon: null, address: "Москва" }}));
    console.log(build2gisWebUrl({{ lat: "", lon: "", address: "Москва" }}));
"""
    lines = run_node_script(script)
    assert lines[0] == "https://2gis.kz/almaty/geo/37.61,55.75"
    assert lines[1] == "https://2gis.kz/almaty/search/%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0"
    assert lines[2] == "https://2gis.kz/almaty/search/%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0"
