"""Testy logiki scalania danych - to ona decyduje o odpornosci portalu."""

import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collect  # noqa: E402

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
TODAY = "2026-08-30"


def raw(title="Pełnia Księżyca", starts="2026-09-07T10:00:00Z", source="sky", **kw):
    base = {
        "title": title, "starts_at": starts, "category": "sky", "importance": 3,
        "summary": "opis", "links": [{"label": "x", "url": "https://example.org"}],
        "source_id": source, "source": source,
    }
    base.update(kw)
    return base


class TestNormalize(unittest.TestCase):
    def test_ids_are_stable_across_runs(self):
        a = collect.normalize(raw(), TODAY)
        b = collect.normalize(raw(), "2026-09-01")
        self.assertEqual(a["id"], b["id"])

    def test_uid_wins_over_generated_id(self):
        ev = collect.normalize(raw(uid="ll2-abc"), TODAY)
        self.assertEqual(ev["id"], "ll2-abc")

    def test_importance_is_clamped(self):
        self.assertEqual(collect.normalize(raw(importance=99), TODAY)["importance"], 5)
        self.assertEqual(collect.normalize(raw(importance=-3), TODAY)["importance"], 1)

    def test_event_without_date_is_dropped(self):
        self.assertIsNone(collect.normalize(raw(starts=""), TODAY))
        self.assertIsNone(collect.normalize(raw(starts="kiedyś"), TODAY))

    def test_links_without_url_are_removed(self):
        ev = collect.normalize(raw(links=[{"label": "brak"}, {"label": "ok", "url": "https://a.pl"}]), TODAY)
        self.assertEqual(len(ev["links"]), 1)


class TestMerge(unittest.TestCase):
    def test_added_on_is_preserved(self):
        old = [collect.normalize(raw(), "2026-01-15")]
        merged = collect.merge(old, [raw()], [{"id": "sky", "status": "ok"}], TODAY)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["added_on"], "2026-01-15")

    def test_new_event_gets_today_as_added_on(self):
        merged = collect.merge([], [raw()], [{"id": "sky", "status": "ok"}], TODAY)
        self.assertEqual(merged[0]["added_on"], TODAY)

    def test_rescheduled_launch_is_flagged(self):
        old = [collect.normalize(raw(uid="ll2-1", starts="2026-09-14T18:22:00Z",
                                     source="launchlibrary"), "2026-08-01")]
        new = raw(uid="ll2-1", starts="2026-09-16T20:00:00Z", source="launchlibrary")
        merged = collect.merge(old, [new], [{"id": "launchlibrary", "status": "ok"}], TODAY)
        self.assertEqual(merged[0]["rescheduled_from"], "2026-09-14T18:22:00Z")
        self.assertEqual(merged[0]["updated_on"], TODAY)
        self.assertEqual(merged[0]["added_on"], "2026-08-01")

    def test_failed_source_keeps_previous_events(self):
        old = [collect.normalize(raw(uid="ll2-1", source="launchlibrary"), "2026-08-01")]
        report = [{"id": "launchlibrary", "status": "error"}, {"id": "sky", "status": "ok"}]
        merged = collect.merge(old, [raw()], report, TODAY)
        ids = {e["id"] for e in merged}
        self.assertIn("ll2-1", ids)  # start rakiety przetrwal awarie API
        self.assertEqual(len(merged), 2)

    def test_working_source_replaces_its_old_events(self):
        old = [collect.normalize(raw(title="Stary wpis", source="sky"), "2026-08-01")]
        merged = collect.merge(old, [raw(title="Nowy wpis")], [{"id": "sky", "status": "ok"}], TODAY)
        self.assertEqual([e["title"] for e in merged], ["Nowy wpis"])

    def test_ephemeral_forecasts_are_not_resurrected(self):
        old = [collect.normalize(raw(title="Burza G3", source="swpc", ephemeral=True), "2026-08-01")]
        report = [{"id": "swpc", "status": "error"}]
        self.assertEqual(collect.merge(old, [], report, TODAY), [])

    def test_result_is_sorted_by_date(self):
        events = [raw(title="B", starts="2026-12-01T00:00:00Z"),
                  raw(title="A", starts="2026-09-01T00:00:00Z")]
        merged = collect.merge([], events, [{"id": "sky", "status": "ok"}], TODAY)
        self.assertEqual([e["title"] for e in merged], ["A", "B"])


class TestPrune(unittest.TestCase):
    def test_old_events_move_to_archive(self):
        old_date = (NOW - timedelta(days=200)).isoformat().replace("+00:00", "Z")
        events = [collect.normalize(raw(starts=old_date), TODAY),
                  collect.normalize(raw(title="Nadchodzące"), TODAY)]
        keep, archived = collect.prune(events, NOW)
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(archived), 1)
        self.assertEqual(keep[0]["title"], "Nadchodzące")

    def test_recent_past_events_stay_visible(self):
        yesterday = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        keep, archived = collect.prune([collect.normalize(raw(starts=yesterday), TODAY)], NOW)
        self.assertEqual(len(keep), 1)
        self.assertEqual(archived, [])

    def test_ephemeral_events_are_never_archived(self):
        old_date = (NOW - timedelta(days=200)).isoformat().replace("+00:00", "Z")
        ev = collect.normalize(raw(starts=old_date, ephemeral=True), TODAY)
        keep, archived = collect.prune([ev], NOW)
        self.assertEqual((keep, archived), ([], []))


class TestFeed(unittest.TestCase):
    def build(self):
        events = [collect.normalize(raw(title="Zaćmienie Słońca & Księżyca"), TODAY)]
        return collect.build_feed(events, NOW)

    def test_feed_is_valid_xml(self):
        root = ET.fromstring(self.build())
        self.assertEqual(root.tag, "rss")
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].find("title").text, "Zaćmienie Słońca & Księżyca")

    def test_special_characters_are_escaped(self):
        xml = self.build()
        self.assertIn("&amp;", xml)
        self.assertNotIn("Słońca & Księżyca", xml)

    def test_newest_entries_come_first(self):
        events = [collect.normalize(raw(title="Stare"), "2026-01-01"),
                  collect.normalize(raw(title="Nowe", starts="2026-10-01T00:00:00Z"), "2026-08-30")]
        root = ET.fromstring(collect.build_feed(events, NOW))
        titles = [i.find("title").text for i in root.findall("./channel/item")]
        self.assertEqual(titles, ["Nowe", "Stare"])


class TestSlug(unittest.TestCase):
    def test_polish_characters_are_transliterated(self):
        self.assertEqual(collect.slugify("Zaćmienie Księżyca"), "zacmienie-ksiezyca")

    def test_empty_input_has_fallback(self):
        self.assertEqual(collect.slugify("***"), "wydarzenie")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestRescheduleDetection(unittest.TestCase):
    """Plakietka „termin przesunięty" ma dotyczyć realnych zmian, nie szumu."""

    def make(self, starts, source="launchlibrary"):
        return collect.normalize(raw(uid="e-1", starts=starts, source=source), TODAY)

    def test_real_launch_delay_is_flagged(self):
        old = self.make("2026-09-14T18:22:00Z")
        new = self.make("2026-09-16T20:00:00Z")
        self.assertTrue(collect.is_rescheduled(old, new))

    def test_shift_of_a_few_seconds_is_ignored(self):
        old = self.make("2026-09-14T18:22:00Z")
        new = self.make("2026-09-14T18:22:41Z")
        self.assertFalse(collect.is_rescheduled(old, new))

    def test_computed_sky_events_are_never_flagged(self):
        old = self.make("2026-10-04T11:56:00Z", source="sky")
        new = self.make("2026-10-04T13:30:00Z", source="sky")
        self.assertFalse(collect.is_rescheduled(old, new))

    def test_merge_does_not_flag_stable_sky_events(self):
        old = [collect.normalize(raw(source="sky"), "2026-08-01")]
        merged = collect.merge(old, [raw(source="sky")], [{"id": "sky", "status": "ok"}], TODAY)
        self.assertNotIn("rescheduled_from", merged[0])
