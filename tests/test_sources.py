"""Testy parserow zrodel zewnetrznych - na zapisanych odpowiedziach API.

Dzieki fixture'om testy dzialaja bez sieci i bez kluczy API, a jednoczesnie
pilnuja, ze zmiana w kodzie nie rozjedzie sie ze schematem odpowiedzi.
"""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.http import FetchError  # noqa: E402
from sources import apod, launches, neo, spaceweather  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestLaunches(unittest.TestCase):
    def collect(self):
        with mock.patch.object(launches, "get_json", return_value=fixture("launchlibrary.json")):
            return launches.collect(NOW)

    def test_parses_both_launches(self):
        events = self.collect()
        self.assertEqual(len(events), 2)
        crew = events[0]
        self.assertEqual(crew["starts_at"], "2026-09-14T18:22:00Z")
        self.assertEqual(crew["category"], "launch")
        self.assertEqual(crew["location"], "Kennedy Space Center, FL, USA")
        self.assertIn("SpaceX", crew["tags"])
        self.assertIn("Falcon 9 Block 5", crew["summary"])
        self.assertIn("potwierdzony", crew["summary"])
        self.assertIn("Międzynarodową Stację", crew["summary"])

    def test_crewed_flight_outranks_starlink(self):
        crew, starlink = self.collect()
        self.assertEqual(crew["importance"], 5)
        self.assertEqual(starlink["importance"], 1)

    def test_links_include_webcast(self):
        crew = self.collect()[0]
        labels = [l["label"] for l in crew["links"]]
        self.assertIn("Transmisja na żywo", labels)
        self.assertTrue(all(l["url"].startswith("http") for l in crew["links"]))

    def test_missing_optional_fields_do_not_crash(self):
        starlink = self.collect()[1]
        self.assertTrue(starlink["summary"])
        self.assertEqual(starlink["extra"]["status"], "termin do potwierdzenia")

    def test_uid_is_stable(self):
        first, second = self.collect(), self.collect()
        self.assertEqual([e["uid"] for e in first], [e["uid"] for e in second])

    def test_falls_back_to_older_api_version(self):
        calls = []

        def fake(url, **kwargs):
            calls.append(url)
            if "2.3.0" in url:
                raise FetchError("404")
            return fixture("launchlibrary.json")

        with mock.patch.object(launches, "get_json", side_effect=fake):
            events = launches.collect(NOW)
        self.assertEqual(len(events), 2)
        self.assertEqual(len(calls), 2)

    def test_all_endpoints_down_raises(self):
        with mock.patch.object(launches, "get_json", side_effect=FetchError("down")):
            with self.assertRaises(FetchError):
                launches.collect(NOW)


class TestSpaceWeather(unittest.TestCase):
    def collect(self):
        with mock.patch.object(spaceweather, "get_json", return_value=fixture("swpc_kp.json")):
            return spaceweather.collect(NOW)

    def test_only_storm_days_become_events(self):
        events = self.collect()
        self.assertEqual(len(events), 1)  # tylko doba z Kp >= 5
        self.assertEqual(events[0]["starts_at"][:10], "2026-08-31")

    def test_takes_daily_maximum_and_maps_noaa_scale(self):
        event = self.collect()[0]
        self.assertIn("G3", event["title"])
        self.assertEqual(event["extra"]["kp"], 7.0)
        self.assertEqual(event["importance"], 5)
        self.assertIn("Polski", event["summary"])

    def test_marked_as_ephemeral(self):
        # prognozy sa krotkoterminowe - nie chcemy ich archiwizowac
        self.assertTrue(self.collect()[0]["ephemeral"])

    def test_empty_forecast_raises(self):
        with mock.patch.object(spaceweather, "get_json", return_value=[["time_tag", "kp"]]):
            with self.assertRaises(FetchError):
                spaceweather.collect(NOW)


class TestNeo(unittest.TestCase):
    def collect(self):
        with mock.patch.object(neo, "get_json", return_value=fixture("neows.json")):
            return neo.collect(NOW)

    def test_filters_out_distant_small_rocks(self):
        titles = [e["title"] for e in self.collect()]
        self.assertEqual(len(titles), 2)
        self.assertFalse(any("2019 AB" in t for t in titles))

    def test_close_pass_gets_top_importance(self):
        close = [e for e in self.collect() if "2026 QQ1" in e["title"]][0]
        self.assertEqual(close["importance"], 5)  # blizej niz Ksiezyc
        self.assertAlmostEqual(close["extra"]["lunar_distances"], 0.68, places=2)
        self.assertEqual(close["starts_at"], "2026-09-02T21:05:00Z")

    def test_hazardous_flag_is_explained_not_alarmist(self):
        pk9 = [e for e in self.collect() if "2010 PK9" in e["title"]][0]
        self.assertIn("potencjalnie niebezpieczna", pk9["tags"])
        self.assertIn("Żaden znany obiekt nie zagraża", pk9["summary"])

    def test_links_point_to_jpl(self):
        for e in self.collect():
            self.assertTrue(any("jpl.nasa.gov" in l["url"] for l in e["links"]))


class TestApod(unittest.TestCase):
    def test_parses_picture_of_the_day(self):
        with mock.patch.object(apod, "get_json", return_value=fixture("apod.json")):
            pic = apod.collect()
        self.assertEqual(pic["title"], "Mgławica Wschodnia Veil")
        self.assertTrue(pic["image"].endswith(".jpg"))
        self.assertEqual(pic["credit"], "Jan Kowalski")
        self.assertEqual(pic["link"], "https://apod.nasa.gov/apod/ap260830.html")

    def test_video_entry_uses_thumbnail(self):
        data = dict(fixture("apod.json"), media_type="video",
                    thumbnail_url="https://img.youtube.com/vi/x/0.jpg")
        with mock.patch.object(apod, "get_json", return_value=data):
            pic = apod.collect()
        self.assertEqual(pic["image"], "https://img.youtube.com/vi/x/0.jpg")


if __name__ == "__main__":
    unittest.main(verbosity=2)
