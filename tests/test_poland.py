"""Testy oceny widoczności zjawisk z Polski.

Rachunek horyzontalny sprawdzamy wobec faktów, które nie zależą od żadnej
biblioteki: wysokość Słońca w południe zależy wyłącznie od szerokości
geograficznej i deklinacji, więc znamy wynik z góry.
"""

import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ephem  # noqa: E402
import poland  # noqa: E402
from sources import sky  # noqa: E402


def dn(y, m, d, h=0):
    return ephem.day_number(datetime(y, m, d, h, tzinfo=timezone.utc))


def max_sun_altitude(y, m, d):
    day = math.floor(dn(y, m, d))
    return max(ephem.altitude("Sun", day + i / 1440) for i in range(0, 1440, 2))


class TestHorizon(unittest.TestCase):
    def test_solar_noon_altitude_matches_geometry(self):
        # w południe: wysokość = 90 - szerokość + deklinacja Słońca
        self.assertAlmostEqual(max_sun_altitude(2026, 3, 20), 38.0, delta=0.4)   # równonoc
        self.assertAlmostEqual(max_sun_altitude(2026, 6, 21), 61.4, delta=0.4)   # przesilenie letnie
        self.assertAlmostEqual(max_sun_altitude(2026, 12, 21), 14.6, delta=0.4)  # zimowe

    def test_sidereal_time_at_known_epoch(self):
        self.assertAlmostEqual(ephem.gmst_hours(dn(2026, 1, 1)), 6.71, delta=0.05)

    def test_sidereal_time_gains_on_solar_time(self):
        # doba gwiazdowa jest krótsza od słonecznej o niecałe 4 minuty
        gain = (ephem.gmst_hours(dn(2026, 5, 2)) - ephem.gmst_hours(dn(2026, 5, 1))) % 24
        self.assertAlmostEqual(gain * 60, 3.94, delta=0.2)

    def test_circumpolar_object_never_sets(self):
        # deklinacja +80 stopni z szerokości 52 to obiekt okołobiegunowy
        day = math.floor(dn(2026, 4, 10))
        altitudes = [ephem.altitude_of(6.0, 80.0, day + i / 96) for i in range(96)]
        self.assertGreater(min(altitudes), 0.0)

    def test_far_southern_object_never_rises(self):
        day = math.floor(dn(2026, 4, 10))
        altitudes = [ephem.altitude_of(6.0, -60.0, day + i / 96) for i in range(96)]
        self.assertLess(max(altitudes), 0.0)

    def test_longitude_shifts_local_sidereal_time(self):
        d = dn(2026, 7, 4, 22)
        east = ephem.lst_hours(d, 20.0)
        west = ephem.lst_hours(d, 5.0)
        self.assertAlmostEqual((east - west) % 24, 1.0, delta=0.01)


class TestSkyEvents(unittest.TestCase):
    """Ocena zjawisk odtwarza znane prawidłowości obserwacyjne."""

    def setUp(self):
        events = sky.collect(datetime(2026, 9, 1, tzinfo=timezone.utc), days_ahead=365)
        self.events = poland.annotate(events)

    def elongations(self):
        return {e["starts_at"][:10]: e["poland"]
                for e in self.events if e["subcategory"] == "elongation"}

    def test_autumn_evening_elongation_of_mercury_is_rejected(self):
        # jesienią ekliptyka układa się płasko nad zachodnim horyzontem,
        # więc wieczorne elongacje Merkurego są z naszej szerokości nie do złapania
        self.assertFalse(self.elongations()["2026-10-12"]["visible"])

    def test_autumn_morning_elongation_of_mercury_is_accepted(self):
        # ta sama geometria działa rano na korzyść obserwatora
        verdict = self.elongations()["2026-11-20"]
        self.assertTrue(verdict["visible"])
        self.assertGreater(verdict["max_altitude"], 10)

    def test_oppositions_reach_expected_altitude(self):
        # planeta o deklinacji bliskiej zeru góruje na wysokości 90 - 52 stopnia
        saturn = [e for e in self.events
                  if e["subcategory"] == "opposition" and e["extra"]["body"] == "Saturn"][0]
        self.assertTrue(saturn["poland"]["visible"])
        self.assertAlmostEqual(saturn["poland"]["max_altitude"], 38, delta=6)

    def test_meteor_radiants_are_evaluated(self):
        showers = [e for e in self.events if e["subcategory"] == "meteors"]
        self.assertTrue(showers)
        for shower in showers:
            self.assertIn("visible", shower["poland"])
        perseids = [e for e in showers if "Perseidy" in e["title"]["pl"]][0]
        self.assertTrue(perseids["poland"]["visible"])  # radiant o deklinacji +58

    def test_eclipse_uses_curated_flag(self):
        eclipses = {e["starts_at"][:10]: e["poland"]["visible"]
                    for e in self.events if e["subcategory"] == "eclipse"}
        self.assertTrue(eclipses["2027-08-02"])    # częściowe widoczne z Polski
        self.assertFalse(eclipses["2027-02-06"])   # obrączkowe nad Ameryką Południową

    def test_every_event_gets_a_verdict(self):
        for event in self.events:
            self.assertIn("visible", event["poland"])
            if event["poland"]["visible"]:
                self.assertTrue(event["poland"]["note"]["pl"])
                self.assertTrue(event["poland"]["note"]["en"])

    def test_altitude_is_reported_where_it_makes_sense(self):
        with_altitude = [e for e in self.events
                         if e["poland"].get("max_altitude") is not None]
        self.assertTrue(with_altitude)
        for event in with_altitude:
            self.assertGreater(event["poland"]["max_altitude"], 0)
            self.assertLess(event["poland"]["max_altitude"], 90)
            self.assertTrue(event["poland"]["best_time"].endswith("Z"))


class TestOtherCategories(unittest.TestCase):
    def event(self, **kw):
        base = {"title": {"pl": "X", "en": "X"}, "summary": {"pl": "", "en": ""},
                "starts_at": "2026-09-10T20:00:00Z", "category": "sky",
                "importance": 3, "tags": [], "extra": {}}
        base.update(kw)
        return base

    def test_strong_storm_counts_as_visible(self):
        self.assertTrue(poland.evaluate(self.event(
            category="spaceweather", extra={"kp": 7.0}))["visible"])

    def test_weak_storm_does_not(self):
        self.assertFalse(poland.evaluate(self.event(
            category="spaceweather", extra={"kp": 5.0}))["visible"])

    def test_launch_with_polish_thread_counts(self):
        verdict = poland.evaluate(self.event(
            category="launch", summary={"pl": "", "en": "Carrying the Polish EagleEye satellite"}))
        self.assertTrue(verdict["visible"])

    def test_ordinary_launch_does_not(self):
        self.assertFalse(poland.evaluate(self.event(
            category="launch", summary={"pl": "", "en": "Starlink Group 12-9"}))["visible"])

    def test_asteroids_are_never_in_the_polish_view(self):
        # bez teleskopu i tak nic nie zobaczymy
        self.assertFalse(poland.evaluate(self.event(category="asteroid"))["visible"])

    def test_broken_event_does_not_break_the_run(self):
        events = [{"starts_at": "nieprawidłowa data", "category": "sky",
                   "title": {}, "summary": {}, "importance": 3}]
        poland.annotate(events)
        self.assertFalse(events[0]["poland"]["visible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
