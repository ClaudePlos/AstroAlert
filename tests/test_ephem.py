"""Testy silnika efemeryd - sprawdzamy zgodnosc z faktami astronomicznymi."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ephem  # noqa: E402
from sources import sky  # noqa: E402


def dn(y, m, d, h=0):
    return ephem.day_number(datetime(y, m, d, h, tzinfo=timezone.utc))


class TestEphem(unittest.TestCase):
    def test_day_number_epoch(self):
        self.assertAlmostEqual(dn(2000, 1, 1), 1.0, places=6)
        self.assertAlmostEqual(dn(2000, 1, 1, 12), 1.5, places=6)

    def test_sun_longitude_at_equinox(self):
        # 20 marca Slonce jest tuz przy punkcie Barana (dlugosc 0 stopni)
        lon = ephem.sun(dn(2026, 3, 20, 15))["lon"]
        self.assertLess(min(lon, 360 - lon), 0.5)

    def test_sun_longitude_grows_one_degree_per_day(self):
        a = ephem.sun(dn(2026, 6, 1))["lon"]
        b = ephem.sun(dn(2026, 6, 2))["lon"]
        self.assertAlmostEqual(ephem.rev180(b - a), 0.955, delta=0.05)

    def test_earth_perihelion_in_early_january(self):
        events = sky.apsides(dn(2026, 1, 1), dn(2026, 12, 31))
        peri = [e for e in events if "Peryhelium" in e["title"]["pl"]]
        self.assertEqual(len(peri), 1)
        self.assertEqual(peri[0]["starts_at"][:7], "2026-01")
        self.assertLessEqual(int(peri[0]["starts_at"][8:10]), 7)

    def test_moon_distance_within_real_range(self):
        for day in range(0, 60):
            km = ephem.moon(dn(2026, 1, 1) + day)["dist_km"]
            self.assertTrue(352_000 < km < 407_000, f"nierealna odległość Księżyca: {km}")

    def test_moon_illumination_matches_phase_angle(self):
        d = dn(2026, 5, 10)
        self.assertAlmostEqual(ephem.moon_illumination(d),
                               (1 - ephem.cosd(ephem.moon_phase_angle(d))) / 2, places=9)

    def test_synodic_month_between_new_moons(self):
        news = [e for e in sky.moon_phases(dn(2026, 1, 1), dn(2026, 12, 31))
                if e["title"]["pl"] == "Nów"]
        self.assertGreaterEqual(len(news), 12)
        times = [datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")) for e in news]
        for a, b in zip(times, times[1:]):
            gap = (b - a).total_seconds() / 86400
            self.assertAlmostEqual(gap, 29.53, delta=0.8)

    def test_full_moon_is_opposite_the_sun(self):
        fulls = [e for e in sky.moon_phases(dn(2026, 1, 1), dn(2026, 6, 30))
                 if "ełni" in e["title"]["pl"]]
        self.assertGreaterEqual(len(fulls), 5)
        for e in fulls:
            d = ephem.day_number(datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")))
            self.assertAlmostEqual(ephem.moon_phase_angle(d), 180.0, delta=0.05)

    def test_inner_planet_elongation_limits(self):
        # Merkury nigdy nie odsuwa sie od Slonca dalej niz ~28 st., Wenus ~47 st.
        for day in range(0, 400, 3):
            d = dn(2026, 1, 1) + day
            self.assertLess(ephem.elongation("Mercury", d), 29.0)
            self.assertLess(ephem.elongation("Venus", d), 48.0)

    def test_polish_names_still_work_as_aliases(self):
        d = dn(2026, 6, 1)
        self.assertEqual(ephem.body("Wenus", d)["lon"], ephem.body("Venus", d)["lon"])
        self.assertEqual(ephem.body("Księżyc", d)["lon"], ephem.body("Moon", d)["lon"])

    def test_outer_planets_reach_opposition(self):
        events = sky.oppositions(dn(2026, 1, 1), dn(2027, 1, 1))
        bodies = {e["extra"]["body"] for e in events}
        self.assertIn("Jupiter", bodies)
        self.assertIn("Saturn", bodies)
        for e in events:
            d = ephem.day_number(datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")))
            body = e["extra"]["body"]
            # w opozycji roznica dlugosci ekliptycznych planety i Slonca wynosi 180 st.
            delta = ephem.rev180(ephem.body(body, d)["lon"] - ephem.sun(d)["lon"] - 180.0)
            self.assertAlmostEqual(delta, 0.0, delta=0.01, msg=body)
            self.assertGreater(ephem.elongation(body, d), 172.0)

    def test_seasons_land_on_expected_dates(self):
        events = sky.seasons(dn(2026, 1, 1), dn(2026, 12, 31))
        got = {e["title"]["pl"]: e["starts_at"][:10] for e in events}
        self.assertEqual(len(got), 4)
        expected = {
            "Równonoc wiosenna": "2026-03-20",
            "Przesilenie letnie": "2026-06-21",
            "Równonoc jesienna": "2026-09-23",
            "Przesilenie zimowe": "2026-12-21",
        }
        self.assertEqual(got, expected)

    def test_planet_positions_against_known_values(self):
        # Pozycje kontrolne (dlugosc ekliptyczna) wg efemeryd JPL Horizons,
        # 2026-08-30 12:00 UTC. Tolerancja 0.3 st. - tyle wynosi bledy metody.
        d = dn(2026, 8, 30, 12)
        for name, expected in (("Sun", 157.1), ("Venus", 202.0), ("Mars", 102.4),
                               ("Jupiter", 133.4), ("Saturn", 13.7), ("Neptune", 3.7)):
            self.assertAlmostEqual(ephem.body(name, d)["lon"], expected, delta=0.3, msg=name)

    def test_conjunction_separation_is_a_real_minimum(self):
        events = sky.conjunctions(dn(2026, 9, 1), dn(2027, 3, 1))
        self.assertTrue(events)
        for e in events:
            d = ephem.day_number(datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")))
            a, b = e["extra"]["bodies"]
            sep = ephem.separation(ephem.body(a, d), ephem.body(b, d))
            self.assertLessEqual(sep, 4.01)
            # separacja rosnie po obu stronach - to faktycznie moment najwiekszego zblizenia
            for delta in (-0.5, 0.5):
                self.assertGreaterEqual(
                    ephem.separation(ephem.body(a, d + delta), ephem.body(b, d + delta)), sep - 1e-6
                )


class TestSkyCollect(unittest.TestCase):
    def test_collect_produces_well_formed_events(self):
        events = sky.collect(datetime(2026, 8, 30, tzinfo=timezone.utc), days_ahead=365)
        self.assertGreater(len(events), 60)
        for e in events:
            for lang in ("pl", "en"):
                self.assertTrue(e["title"][lang], e["title"])
                self.assertTrue(e["summary"][lang], e["summary"])
            self.assertIn(e["category"], {"sky"})
            self.assertTrue(1 <= e["importance"] <= 5)
            self.assertTrue(e["links"])
            datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00"))

    def test_both_languages_differ(self):
        # gdyby ktorys tekst zostal wygenerowany tylko raz, obie wersje bylyby
        # identyczne - to najprostszy sygnal, ze tlumaczenie gdzies wypadlo
        events = sky.collect(datetime(2026, 8, 30, tzinfo=timezone.utc), days_ahead=365)
        identical = [e for e in events if e["summary"]["pl"] == e["summary"]["en"]]
        self.assertEqual(identical, [])

    def test_static_datasets_show_up(self):
        events = sky.collect(datetime(2026, 8, 30, tzinfo=timezone.utc), days_ahead=365)
        subs = {e["subcategory"] for e in events}
        self.assertIn("meteors", subs)
        self.assertIn("eclipse", subs)
        perseids = [e for e in events if "Perseidy" in e["title"]["pl"]]
        self.assertEqual(len(perseids), 1)
        self.assertIn("ZHR", perseids[0]["summary"]["pl"])
        self.assertIn("Perseids", perseids[0]["title"]["en"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
