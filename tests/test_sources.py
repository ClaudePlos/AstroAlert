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

    def test_parses_all_launches(self):
        events = self.collect()
        self.assertEqual(len(events), 3)
        crew = events[0]
        self.assertEqual(crew["starts_at"], "2026-09-14T18:22:00Z")
        self.assertEqual(crew["category"], "launch")
        self.assertEqual(crew["location"]["pl"], "Kennedy Space Center, FL, USA")
        self.assertIn("SpaceX", [t["pl"] for t in crew["tags"]])
        self.assertIn("Falcon 9 Block 5", crew["summary"]["pl"])
        self.assertIn("potwierdzony", crew["summary"]["pl"])
        self.assertIn("confirmed", crew["summary"]["en"])

    def test_crewed_flight_outranks_starlink(self):
        crew, starlink, _ = self.collect()
        self.assertEqual(crew["importance"], 5)
        self.assertEqual(starlink["importance"], 1)

    def test_links_include_webcast(self):
        crew = self.collect()[0]
        labels = [l["label"]["pl"] for l in crew["links"]]
        self.assertIn("Transmisja na żywo", labels)
        self.assertIn("Live webcast", [l["label"]["en"] for l in crew["links"]])
        self.assertTrue(all(l["url"].startswith("http") for l in crew["links"]))

    def test_missing_optional_fields_do_not_crash(self):
        starlink = self.collect()[1]
        self.assertTrue(starlink["summary"]["pl"])
        # w extra trzymamy surowy status z API (dane maszynowe),
        # a przetlumaczony trafia do opisu
        self.assertEqual(starlink["extra"]["status"], "To Be Confirmed")
        self.assertIn("termin do potwierdzenia", starlink["summary"]["pl"])
        self.assertIn("date to be confirmed", starlink["summary"]["en"])

    def test_unknown_provider_does_not_leak_into_text(self):
        # API bez pelnych danych zwraca rekord bez operatora - opis ma zostac
        # poprawnym zdaniem, a nie "firmy/agencji nieznany operator"
        pallas = self.collect()[2]
        self.assertEqual(pallas["summary"]["pl"].split(".")[0], "Start rakiety Pallas-1")
        self.assertEqual(pallas["summary"]["en"].split(".")[0], "Launch of Pallas-1")
        self.assertNotIn("nieznany operator", pallas["summary"]["pl"])
        self.assertEqual([t["pl"] for t in pallas["tags"]], ["start rakiety"])

    def test_provider_named_when_present(self):
        crew = self.collect()[0]
        self.assertIn("Start rakiety Falcon 9 Block 5 – SpaceX.", crew["summary"]["pl"])
        self.assertIn("Launch of Falcon 9 Block 5, operated by SpaceX.", crew["summary"]["en"])

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
        self.assertEqual(len(events), 3)
        self.assertEqual(len(calls), 2)

    def test_requests_full_records_not_list_mode(self):
        # tryb "list" gubi operatora, kosmodrom i opis misji
        self.assertTrue(all("mode=list" not in url for url in launches.ENDPOINTS))

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
        self.assertIn("G3", event["title"]["pl"])
        self.assertIn("G3", event["title"]["en"])
        self.assertEqual(event["extra"]["kp"], 7.0)
        self.assertEqual(event["importance"], 5)
        self.assertIn("Polski", event["summary"]["pl"])
        self.assertIn("central Europe", event["summary"]["en"])

    def test_marked_as_ephemeral(self):
        # prognozy sa krotkoterminowe - nie chcemy ich archiwizowac
        self.assertTrue(self.collect()[0]["ephemeral"])

    def test_empty_forecast_raises(self):
        with mock.patch.object(spaceweather, "get_json", return_value=[["time_tag", "kp"]]):
            with self.assertRaises(FetchError):
                spaceweather.collect(NOW)

    def test_handles_list_of_objects_shape(self):
        # NOAA serwuje ten produkt jako tablicę tablic, ale bywa też listą
        # obiektów - na tym wywracał się pierwszy przebieg produkcyjny
        with mock.patch.object(spaceweather, "get_json",
                               return_value=fixture("swpc_kp_objects.json")):
            events = spaceweather.collect(NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["extra"]["kp"], 7.0)
        self.assertIn("G3", events[0]["title"]["pl"])

    def test_unknown_shape_reports_what_arrived(self):
        with mock.patch.object(spaceweather, "get_json", return_value={"error": "nope"}):
            with self.assertRaises(FetchError) as ctx:
                spaceweather.collect(NOW)
        self.assertIn("dict", str(ctx.exception))

    def test_unparsable_rows_are_skipped_not_fatal(self):
        rows = [["time_tag", "kp"], ["nie-data", "5.0"], ["2026-08-31 00:00:00", "6.0"]]
        with mock.patch.object(spaceweather, "get_json", return_value=rows):
            events = spaceweather.collect(NOW)
        self.assertEqual(len(events), 1)


class TestNeo(unittest.TestCase):
    def collect(self):
        with mock.patch.object(neo, "get_json", return_value=fixture("neows.json")):
            return neo.collect(NOW)

    def test_small_distant_rock_is_dropped(self):
        titles = [e["title"]["pl"] for e in self.collect()]
        # 60 m w odległości 104 odległości księżycowych to nie jest wydarzenie
        self.assertFalse(any("2019 AB" in t for t in titles))

    def test_close_approaches_are_always_kept(self):
        events = self.collect()
        close = [e for e in events if e["extra"]["lunar_distances"] <= neo.CLOSE_LD]
        self.assertEqual(len(close), 2)  # 2026 QQ1 i 2010 PK9
        for e in close:
            self.assertTrue(e["title"]["pl"].startswith("Bliski przelot planetoidy"), e["title"])
            self.assertTrue(e["title"]["en"].startswith("Close approach of asteroid"), e["title"])

    def test_distant_list_is_capped_by_ranking(self):
        # w oknie jest 8 dalszych kandydatów; pokazujemy tylko najciekawsze
        events = self.collect()
        far = [e for e in events if e["extra"]["lunar_distances"] > neo.CLOSE_LD]
        self.assertEqual(len(far), neo.MAX_RANKED)

    def test_ranking_prefers_large_and_nearby(self):
        far = [e["title"]["pl"] for e in self.collect()
               if e["extra"]["lunar_distances"] > neo.CLOSE_LD]
        self.assertTrue(any("2020 XR" in t for t in far))    # 690 m z 12 LD
        self.assertTrue(any("2012 LE11" in t for t in far))  # 1406 m, 68 LD
        self.assertFalse(any("2007 PB8" in t for t in far))  # 318 m, 81 LD

    def test_distant_pass_is_not_called_close(self):
        xr = [e for e in self.collect() if "2020 XR" in e["title"]["pl"]][0]
        self.assertTrue(xr["title"]["pl"].startswith("Przelot planetoidy"))
        self.assertTrue(xr["title"]["en"].startswith("Asteroid 2020 XR"))
        self.assertIn("To nie jest bliskie spotkanie", xr["summary"]["pl"])
        self.assertIn("not a close encounter", xr["summary"]["en"])
        self.assertAlmostEqual(xr["extra"]["lunar_distances"], 12.0, places=1)

    def test_events_are_sorted_by_date(self):
        dates = [e["starts_at"] for e in self.collect()]
        self.assertEqual(dates, sorted(dates))

    def test_catalogue_name_keeps_both_parentheses(self):
        # obj["name"].strip("()") ucinało tylko domykający nawias
        close = [e for e in self.collect() if "QQ1" in e["title"]["pl"]][0]
        self.assertEqual(close["title"]["pl"], "Bliski przelot planetoidy 2026 QQ1")
        self.assertEqual(close["title"]["en"], "Close approach of asteroid 2026 QQ1")
        self.assertNotIn("(", close["title"]["pl"])

    def test_close_pass_is_described_as_such(self):
        close = [e for e in self.collect() if "2026 QQ1" in e["title"]["pl"]][0]
        self.assertIn("To jedno z bliższych zbliżeń w tym tygodniu", close["summary"]["pl"])
        self.assertIn("one of the closer approaches", close["summary"]["en"])

    def test_close_pass_gets_top_importance(self):
        close = [e for e in self.collect() if "2026 QQ1" in e["title"]["pl"]][0]
        self.assertEqual(close["importance"], 5)  # blizej niz Ksiezyc
        self.assertAlmostEqual(close["extra"]["lunar_distances"], 0.68, places=2)
        self.assertEqual(close["starts_at"], "2026-09-02T21:05:00Z")

    def test_hazardous_flag_is_explained_not_alarmist(self):
        pk9 = [e for e in self.collect() if "2010 PK9" in e["title"]["pl"]][0]
        self.assertIn("potencjalnie niebezpieczna", [t["pl"] for t in pk9["tags"]])
        self.assertIn("potentially hazardous", [t["en"] for t in pk9["tags"]])
        self.assertIn("Żaden znany obiekt nie zagraża", pk9["summary"]["pl"])
        self.assertIn("No known object", pk9["summary"]["en"])

    def test_links_point_to_jpl(self):
        for e in self.collect():
            self.assertTrue(any("jpl.nasa.gov" in l["url"] for l in e["links"]))


class TestApod(unittest.TestCase):
    def test_parses_picture_of_the_day(self):
        with mock.patch.object(apod, "get_json", return_value=fixture("apod.json")):
            pic = apod.collect()
        self.assertEqual(pic["title"], "Mgławica Wschodnia Veil")
        self.assertTrue(pic["image"].endswith(".jpg"))
        self.assertEqual(pic["credit"], {"pl": "Jan Kowalski", "en": "Jan Kowalski"})
        self.assertEqual(pic["link"], "https://apod.nasa.gov/apod/ap260830.html")

    def test_missing_author_falls_back_to_neutral_credit(self):
        data = {k: v for k, v in fixture("apod.json").items() if k != "copyright"}
        with mock.patch.object(apod, "get_json", return_value=data):
            pic = apod.collect()
        self.assertEqual(pic["credit"]["pl"], "NASA / domena publiczna")
        self.assertEqual(pic["credit"]["en"], "NASA / public domain")

    def test_video_entry_uses_thumbnail(self):
        data = dict(fixture("apod.json"), media_type="video",
                    thumbnail_url="https://img.youtube.com/vi/x/0.jpg")
        with mock.patch.object(apod, "get_json", return_value=data):
            pic = apod.collect()
        self.assertEqual(pic["image"], "https://img.youtube.com/vi/x/0.jpg")


if __name__ == "__main__":
    unittest.main(verbosity=2)
