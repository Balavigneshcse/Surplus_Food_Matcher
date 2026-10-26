"""The Phase 2 pages are served without login, and every API call in the page scripts exists in the real app
(same path and method), so a renamed endpoint cannot silently break a page."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main

STATIC = Path(main.STATIC_DIR)
PAGES = {  # page -> its own script
    "optout.html": "/js/optout.js",
    "kitchen/plan.html": "/js/plan.js",
    "kitchen/cookcard.html": "/js/cookcard.js",
    "kitchen/setup.html": "/js/setup.js",
}
METHODS = {"get": "get", "post": "post", "put": "put", "del": "delete"}
CALL = re.compile(r"api\.(get|post|put|del)\(\s*[`'\"]([^`'\"]+)[`'\"]")


def canonical(path: str) -> str:
    """'/api/kitchen/meals/${m.id}?x=1' and '/api/kitchen/meals/{meal_id}' -> '/api/kitchen/meals/{}'."""
    path = path.split("?")[0]
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    return re.sub(r"\{[^}]*\}", "{}", path)


@pytest.mark.parametrize("page, script", PAGES.items())
def test_page_is_served_and_loads_its_module(page, script):
    res = TestClient(main.app).get(f"/{page}")
    assert res.status_code == 200
    assert f'<script type="module" src="{script}"></script>' in res.text
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in res.text
    assert TestClient(main.app).get(script).status_code == 200


def test_cook_card_has_a_print_stylesheet():
    html = (STATIC / "kitchen" / "cookcard.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/css/print.css" media="print">' in html


def test_every_api_call_in_the_page_scripts_exists():
    spec = main.app.openapi()
    known = {(method, canonical(path)) for path, ops in spec["paths"].items() for method in ops}
    calls = set()
    for script in ["optout.js", "plan.js", "cookcard.js", "setup.js"]:
        source = (STATIC / "js" / script).read_text(encoding="utf-8")
        for method, path in CALL.findall(source):
            calls.add((METHODS[method], canonical(path)))
    assert calls, "no API calls found: did the call style change?"
    assert calls - known == set()
    # the calls this phase's pages are built on
    assert {("get", "/api/public/kitchens/{}/open-meals"), ("post", "/api/public/opt-outs"),
            ("post", "/api/public/opt-outs/cancel"), ("get", "/api/kitchen/meals"), ("post", "/api/kitchen/meals"),
            ("get", "/api/kitchen/meals/{}"), ("put", "/api/kitchen/meals/{}"),
            ("post", "/api/kitchen/meals/{}/override"), ("post", "/api/kitchen/meals/{}/issue-cook-card"),
            ("post", "/api/kitchen/meals/{}/live-count"), ("get", "/api/kitchen/slots"), ("put", "/api/kitchen/slots/{}"),
            ("get", "/api/kitchen/dishes"), ("post", "/api/kitchen/dishes"), ("put", "/api/kitchen/dishes/{}")} <= calls


@pytest.mark.parametrize("page, script", PAGES.items())
def test_every_element_id_the_script_looks_up_is_in_its_page(page, script):
    """$('#some-id') in a page script must find that id in the page's HTML, or the page breaks at runtime.
    (Ids built at runtime, like `#tab-${day}`, are listed by hand below.)"""
    built_at_runtime = {"/js/plan.js": ["tab-today", "tab-tomorrow"],
                        "/js/setup.js": ["tab-slots", "tab-dishes", "panel-slots", "panel-dishes"]}
    html = (STATIC / page).read_text(encoding="utf-8")
    source = (STATIC / script.lstrip("/")).read_text(encoding="utf-8")
    ids = set(re.findall(r"\$\('#([\w-]+)'\)", source)) | set(built_at_runtime.get(script, []))
    assert ids, f"no element lookups found in {script}"
    missing = sorted(i for i in ids if f'id="{i}"' not in html)
    assert missing == [], f"{script} looks up ids that {page} does not have: {missing}"


def test_public_opt_out_answer_has_no_state_of_other_students():
    """The opt-out answer must not reveal whether the hostel ID had opted out before (anyone can type any ID)."""
    fields = set(main.app.openapi()["components"]["schemas"]["OptOutResult"]["properties"])
    assert fields == {"kitchenCode", "date", "slot", "optedOut", "cutoffAt", "serverNow"}


def test_tamil_labels_cover_every_english_label():
    source = (STATIC / "js" / "i18n.js").read_text(encoding="utf-8")
    en_block = source.split("  en: {")[1].split("\n  },\n  ta: {")[0]
    ta_block = source.split("  ta: {")[1].split("\n  },\n};")[0]
    key = re.compile(r"^\s{4}(\w+):", re.MULTILINE)
    assert set(key.findall(en_block)) == set(key.findall(ta_block))
