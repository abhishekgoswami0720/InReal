from scraper import ALL_SCRAPERS
from sites import registry


def test_sixty_sites_with_unique_keys():
    keys = [s["key"] for s in registry.SITES]
    assert len(keys) == 60
    assert len(set(keys)) == len(keys)


def test_every_site_has_a_known_region_and_status():
    regions = {r["key"] for r in registry.REGIONS}
    for s in registry.SITES:
        assert s["region"] in regions, s["key"]
        assert s["status"] in {"tested", "basic", "planned"}, s["key"]
        assert s["how"] in {"api", "rss", "page", "browser", "search"}, s["key"]


def test_live_sites_point_at_real_scrapers_and_planned_ones_at_none():
    for s in registry.SITES:
        if s["status"] == "planned":
            assert s["runs"] is None, s["key"]
        else:
            assert s["runs"] in ALL_SCRAPERS, s["key"]
            assert s["runs"] in registry.SCRAPER_LABELS, s["key"]


def test_each_scraper_runs_once_and_planned_sites_are_skipped():
    run, skipped = registry.scrapers_for(["internshala", "internshala", "usajobs", "aijobs", "nonsense"])
    assert run == ["internshala"]
    assert skipped == ["usajobs", "aijobs", "nonsense"]


def test_old_saved_scraper_names_still_work():
    run, skipped = registry.scrapers_for(["niche", "aggregators", "government"])
    assert run == ["niche", "aggregators", "government"]
    assert skipped == []


def test_public_list_hides_internal_runs():
    data = registry.public_list()
    assert all("runs" not in s for s in data["sites"])
    assert len(data["regions"]) == 5
