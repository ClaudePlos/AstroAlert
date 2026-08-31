"""Testy katalogu komunikatow.

Katalog jest teraz najlatwiejszym miejscem na cichy blad: brakujacy klucz
wywala sie dopiero przy generowaniu konkretnego wydarzenia, a rozjechany
placeholder daje tekst z dziura albo wyjatek w srodku przebiegu. Te testy
sprawdzaja obie wersje jezykowe od strony struktury.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.i18n import LANGS, LOCALES_DIR, MissingMessage, catalog, join, literal, multi, pick, render, t  # noqa: E402

PLACEHOLDER = re.compile(r"\{(\w+)\}")
#: klucze wolane dynamicznie - sprawdzamy je z listy, bo regex ich nie wylapie
DYNAMIC_FAMILIES = {
    "planet": ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune",
               "moon", "sun"],
    "zodiac": [str(i) for i in range(12)],
    "category": ["sky", "launch", "spaceweather", "asteroid", "mission"],
    "source": ["sky", "launchlibrary", "swpc", "neows", "custom"],
    "attribution": ["sky", "launchlibrary", "swpc", "neows", "custom"],
}


class TestCatalogStructure(unittest.TestCase):
    def test_every_language_has_a_file(self):
        for lang in LANGS:
            self.assertTrue((LOCALES_DIR / f"{lang}.json").exists(), lang)

    def test_key_sets_are_identical(self):
        reference = set(catalog(LANGS[0]))
        for lang in LANGS[1:]:
            missing = reference - set(catalog(lang))
            extra = set(catalog(lang)) - reference
            self.assertEqual(missing, set(), f"brak kluczy w {lang}")
            self.assertEqual(extra, set(), f"nadmiarowe klucze w {lang}")

    def test_no_empty_messages(self):
        for lang in LANGS:
            empty = [k for k, v in catalog(lang).items() if not str(v).strip()]
            self.assertEqual(empty, [], lang)

    def test_placeholders_match_between_languages(self):
        reference = catalog(LANGS[0])
        for lang in LANGS[1:]:
            for key, template in catalog(lang).items():
                self.assertEqual(
                    set(PLACEHOLDER.findall(template)),
                    set(PLACEHOLDER.findall(reference[key])),
                    f"rozjechane pola w kluczu {key} ({lang})",
                )

    def test_translations_are_not_copies(self):
        # kilka kluczy celowo brzmi tak samo (NEO, G3, nazwy własne),
        # ale przepisana w całości wersja językowa to zwykle przeoczenie
        same = [k for k, v in catalog("pl").items() if v == catalog("en")[k]]
        self.assertLess(len(same), 25, f"podejrzanie wiele identycznych: {same}")


class TestKeysUsedInCode(unittest.TestCase):
    def literal_keys(self):
        pattern = re.compile(r'(?:render|\bt)\(\s*"([a-z][\w.]*)"')
        keys = set()
        for path in (ROOT / "scripts").rglob("*.py"):
            keys |= set(pattern.findall(path.read_text(encoding="utf-8")))
        return keys

    def test_every_key_used_in_code_exists(self):
        available = set(catalog(LANGS[0]))
        missing = sorted(self.literal_keys() - available)
        self.assertEqual(missing, [], "klucze wołane z kodu, których nie ma w katalogu")

    def test_dynamic_key_families_are_complete(self):
        available = set(catalog(LANGS[0]))
        for prefix, members in DYNAMIC_FAMILIES.items():
            for member in members:
                self.assertIn(f"{prefix}.{member}", available)

    def test_planet_helper_keys_exist(self):
        available = set(catalog(LANGS[0]))
        for body in DYNAMIC_FAMILIES["planet"]:
            self.assertIn(f"planet.{body}.gen", available)
            self.assertIn(f"planet.{body}.blurb", available)


class TestRendering(unittest.TestCase):
    def test_render_returns_every_language(self):
        out = render("category.sky")
        self.assertEqual(set(out), set(LANGS))
        self.assertEqual(out["pl"], "Niebo nad nami")
        self.assertEqual(out["en"], "The sky above")

    def test_parameters_are_resolved_per_language(self):
        out = render("opposition.title", body=render("planet.mars.gen"))
        self.assertEqual(out["pl"], "Opozycja Marsa")
        self.assertEqual(out["en"], "Mars at opposition")

    def test_plain_parameters_pass_through(self):
        out = render("meteor.title", name="Perseidy")
        self.assertEqual(out["pl"], "Maksimum roju Perseidy")
        self.assertEqual(out["en"], "Perseidy meteor shower peak")

    def test_missing_key_fails_loudly(self):
        with self.assertRaises(MissingMessage):
            t("nie.ma.takiego.klucza", "pl")

    def test_join_concatenates_each_language(self):
        out = join(render("category.sky"), render("category.launch"))
        self.assertEqual(out["pl"], "Niebo nad nami Starty rakiet")
        self.assertEqual(out["en"], "The sky above Rocket launches")

    def test_literal_and_multi(self):
        self.assertEqual(literal("Falcon 9"), {"pl": "Falcon 9", "en": "Falcon 9"})
        self.assertEqual(multi(pl="Marsa", en="Mars"), {"pl": "Marsa", "en": "Mars"})

    def test_pick_handles_plain_strings(self):
        self.assertEqual(pick("Falcon 9", "en"), "Falcon 9")
        self.assertEqual(pick({"pl": "Nów", "en": "New Moon"}, "en"), "New Moon")

    def test_pick_falls_back_to_default_language(self):
        self.assertEqual(pick({"pl": "Nów"}, "en"), "Nów")


class TestFrontendCatalog(unittest.TestCase):
    """Interfejs portalu ma własny słownik w app.js - musi mieć te same języki."""

    def test_ui_dictionary_covers_every_language(self):
        source = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        block = source[source.index("const UI = {"):source.index("const CATEGORY_COLORS")]
        for lang in LANGS:
            self.assertRegex(block, rf"\n    {lang}: {{", f"brak sekcji {lang} w UI")
        keys = {lang: set(re.findall(r"\n      (\w+):", block.split(f"\n    {lang}: {{")[1]
                                     .split("\n    },")[0]))
                for lang in LANGS}
        reference = keys[LANGS[0]]
        for lang in LANGS[1:]:
            self.assertEqual(keys[lang], reference, f"inne klucze UI w {lang}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
