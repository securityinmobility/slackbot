import unittest
import json
import os
from datetime import date, datetime
from unittest import mock
from jinja2 import Environment, FileSystemLoader

import sinks
import slackbot
import werkswelt
from slackbot import TIMEZONE, format_date_de, gql_GetPlan, meals_for_day

DAY = date(2026, 11, 13)
WERKSWELT_DAY = date(2026, 11, 24)  # test_data/werkswelt_ingo_*.html: raw server responses of that day (14:30)


def fixture(lang):
    with open(os.path.join("test_data", f"werkswelt_ingo_{lang}.html"), encoding="utf-8") as f:
        return f.read()


def meal(name, static=False, flags=None, student=2.5, employee=3.5):
    return {
        "name": {"de": name, "en": name},
        "category": "main",
        "restaurant": "IngolstadtMensa",
        "static": static,
        "flags": flags,
        "prices": {"student": student, "employee": employee, "guest": 5.0},
    }


def plan_for(day):
    return [
        {"timestamp": "2026-11-12", "meals": [meal("Gestern-Gericht")]},
        {
            "timestamp": day.isoformat(),
            "meals": [
                meal('Tofuragout "Jambalaya Art"', flags=["veg", "CO2"]),
                meal("Gemüselasagne", flags=["V"]),
                meal("Schnitzel", flags=["S"], student=None),
                meal("Currywurst", static=True),
            ],
        },
    ]


def gql_response(payload):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class TestMealsForDay(unittest.TestCase):
    def test_filters_day_and_static(self):
        names = [m["name"]["de"] for m in meals_for_day(plan_for(DAY), DAY)]
        self.assertEqual(names, ['Tofuragout "Jambalaya Art"', "Gemüselasagne", "Schnitzel"])

    def test_other_day_is_empty(self):
        self.assertEqual(meals_for_day(plan_for(DAY), date(2026, 11, 14)), [])

    def test_null_meals(self):
        self.assertEqual(meals_for_day([{"timestamp": "2026-11-13", "meals": None}], DAY), [])

    def test_format_date_de(self):
        self.assertEqual(format_date_de(DAY), "Freitag, 13.11.2026")


class TestTemplates(unittest.TestCase):
    def setUp(self):
        self.environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
        self.environment.globals["today"] = DAY
        self.environment.filters["date_de"] = format_date_de
        self.meals = meals_for_day(plan_for(DAY), DAY)

    def test_teams_render(self):
        payload = self.environment.get_template("teams.j2").render(mensa=self.meals, reimanns=[])
        card = json.loads(payload)
        container = card["body"][1]["items"]
        self.assertEqual(container[0]["text"], "Freitag, 13.11.2026")
        text = container[1]["text"]
        self.assertIn('- Tofuragout "Jambalaya Art" (2.50 € | 3.50 €) 🌱\n', text)
        self.assertIn("- Gemüselasagne (2.50 € | 3.50 €) 🥕\n", text)
        self.assertIn("- Schnitzel (3.50 €)\n", text)
        self.assertNotIn("Currywurst", text)
        self.assertIn("keine Einträge", text)
        self.assertIn("Pick up Achim = 🙋‍♂️", text)
        self.assertNotIn(":one:", text)
        self.assertNotIn(":mensa-", text)
        self.assertNotIn("Input.Toggle", payload)

    def test_slack_render(self):
        message = self.environment.get_template("slack.j2").render(mensa=self.meals, reimanns=[])
        self.assertIn('- Tofuragout "Jambalaya Art" (2.50 € | 3.50 €) :mensa-veg: :mensa-co2:\n', message)
        self.assertIn("keine Einträge", message)

    def test_empty(self):
        self.assertIn("keine Einträge", self.environment.get_template("slack.j2").render(mensa=[], reimanns=[]))
        card = json.loads(self.environment.get_template("teams.j2").render(mensa=[], reimanns=[]))
        self.assertIn("keine Einträge", card["body"][1]["items"][1]["text"])

    def test_teams_english_line_only_if_different(self):
        meals = [meal("Gemüsecurry", flags=["veg"]), meal("Lasagne Bolognese")]
        meals[0]["name"]["en"] = "Vegetable curry"
        card = json.loads(self.environment.get_template("teams.j2").render(mensa=meals, reimanns=[]))
        text = card["body"][1]["items"][1]["text"]
        self.assertIn("- Gemüsecurry (2.50 € | 3.50 €) 🌱\n  _Vegetable curry_\n", text)
        self.assertIn("- Lasagne Bolognese (2.50 € | 3.50 €)\n", text)
        self.assertNotIn("_Lasagne Bolognese_", text)


class TestWerkswelt(unittest.TestCase):
    def test_parse_german_page(self):
        day, meals = werkswelt.parse_menu(fixture("de"))
        self.assertEqual(day, WERKSWELT_DAY)
        self.assertEqual([m["name"] for m in meals], [
            "Kartoffelsuppe in der Eintopfschale mit Brötchen",
            "Kartoffelsuppe",
            "Nudeln Bolognese",
            "Rote Bete Puffer mit Apfel-Senf Dip",
            "Gemüsecurry mit Sojawürfeln und Reis",
            "Mais Nuggets mit Barbecue Dip und Coleslaw",
        ])
        self.assertEqual(meals[0]["prices"], {"student": 1.6, "employee": 2.6})
        self.assertEqual([m["flags"] for m in meals], [["V"], ["V"], ["R"], ["veg"], ["veg"], ["veg"]])

    def test_mensa_meals_pairs_languages(self):
        with mock.patch("werkswelt._fetch", side_effect=fixture):
            meals = werkswelt.mensa_meals(WERKSWELT_DAY)
        self.assertEqual(meals[4]["name"], {"de": "Gemüsecurry mit Sojawürfeln und Reis",
                                            "en": "Vegetable curry with diced soy chunks and rice"})
        self.assertEqual(meals[2]["name"], {"de": "Nudeln Bolognese", "en": "Pasta Bolognese"})
        self.assertEqual(meals[3]["prices"], {"student": 2.48, "employee": 3.68})

    def test_other_day_raises(self):
        with mock.patch("werkswelt._fetch", side_effect=fixture):
            with self.assertRaises(ValueError):
                werkswelt.mensa_meals(date(2026, 11, 25))

    def test_changed_layout_raises(self):
        with mock.patch("werkswelt._fetch", return_value="<html><body>Wartungsarbeiten</body></html>"):
            with self.assertRaises(ValueError):
                werkswelt.mensa_meals(WERKSWELT_DAY)

    def test_english_mismatch_keeps_german(self):
        pages = {"de": fixture("de"), "en": fixture("en").replace("1,60&nbsp;€", "1,70&nbsp;€")}
        with mock.patch("werkswelt._fetch", side_effect=pages.get), mock.patch("sys.stderr") as stderr:
            meals = werkswelt.mensa_meals(WERKSWELT_DAY)
        self.assertTrue(all(m["name"]["en"] == m["name"]["de"] for m in meals))
        self.assertTrue(stderr.write.called)

    @unittest.skipUnless(os.environ.get("RUN_LIVE_API_TESTS") == "1", "set RUN_LIVE_API_TESTS=1 to fetch the live werkswelt page")
    def test_live_page(self):
        for lang in ("de", "en"):
            page = werkswelt._fetch(lang)
            _, meals = werkswelt.parse_menu(page)
            if "(Stud.)" in page:  # the page lists prices, so the parser must find meals
                self.assertTrue(meals, f"{lang}: prices on the page but no meals parsed")


class TestGraphQL(unittest.TestCase):
    def test_graphql_errors_raise(self):
        with mock.patch("slackbot.requests.post", return_value=gql_response({"errors": [{"message": "boom"}]})):
            with self.assertRaises(RuntimeError):
                gql_GetPlan(location="IngolstadtMensa")

    def test_location_errors_warn_and_return_data(self):
        payload = {"data": {"food": {"foodData": plan_for(DAY), "errors": [{"location": "Reimanns", "message": "down"}]}}}
        with mock.patch("slackbot.requests.post", return_value=gql_response(payload)):
            with mock.patch("sys.stderr") as stderr:
                self.assertEqual(gql_GetPlan(location="Reimanns"), plan_for(DAY))
        self.assertTrue(stderr.write.called)

    @unittest.skipUnless(os.environ.get("RUN_LIVE_API_TESTS") == "1", "set RUN_LIVE_API_TESTS=1 to query the live Neuland API")
    def test_live_api(self):
        self.assertIsInstance(gql_GetPlan(location="IngolstadtMensa"), list)


class TestMain(unittest.TestCase):
    def run_main(self, plan, sink_error=None, werkswelt_meals=None):
        """Run main() offline. Without werkswelt_meals, werkswelt fails and the Mensa falls back to Neuland."""
        if werkswelt_meals is None:
            werkswelt_patch = mock.patch("slackbot.werkswelt.mensa_meals", side_effect=RuntimeError("offline"))
        else:
            werkswelt_patch = mock.patch("slackbot.werkswelt.mensa_meals", return_value=werkswelt_meals)
        with mock.patch.dict(os.environ, {"TEAMS_URL": "https://example.invalid/webhook"}, clear=True), \
                mock.patch("slackbot.gql_GetPlan", return_value=plan) as gql, werkswelt_patch, \
                mock.patch("slackbot.teams_sink", side_effect=sink_error) as teams_sink, \
                mock.patch("sys.stderr"):
            return slackbot.main(), teams_sink, gql

    def test_posts_today(self):
        exit_code, teams_sink, _ = self.run_main(plan_for(datetime.now(TIMEZONE).date()))
        self.assertEqual(exit_code, 0)
        teams_sink.assert_called_once()
        json.loads(teams_sink.call_args.args[0])

    def test_no_menu_posts_nothing(self):
        exit_code, teams_sink, _ = self.run_main([])
        self.assertEqual(exit_code, 0)
        teams_sink.assert_not_called()

    def test_sink_failure_exit_code(self):
        exit_code, _, _ = self.run_main(plan_for(datetime.now(TIMEZONE).date()), sink_error=Exception("down"))
        self.assertEqual(exit_code, 1)

    def test_uses_werkswelt_for_mensa(self):
        mensa = [{"name": {"de": "Gemüsecurry", "en": "Vegetable curry"},
                  "prices": {"student": 2.46, "employee": 4.57}, "flags": ["veg"]}]
        exit_code, teams_sink, gql = self.run_main(plan_for(datetime.now(TIMEZONE).date()), werkswelt_meals=mensa)
        self.assertEqual(exit_code, 0)
        gql.assert_called_once_with(location="Reimanns")
        text = json.loads(teams_sink.call_args.args[0])["body"][1]["items"][1]["text"]
        self.assertIn("- Gemüsecurry (2.46 € | 4.57 €) 🌱\n  _Vegetable curry_\n", text)

    def test_werkswelt_failure_falls_back_to_neuland(self):
        exit_code, teams_sink, gql = self.run_main(plan_for(datetime.now(TIMEZONE).date()))
        self.assertEqual(exit_code, 0)
        self.assertEqual([c.kwargs["location"] for c in gql.call_args_list], ["IngolstadtMensa", "Reimanns"])
        teams_sink.assert_called_once()


class TestTeamsSink(unittest.TestCase):
    def test_accepts_202(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 202
        with mock.patch("sinks.req.urlopen", return_value=response):
            sinks.teams_sink(json.dumps({"type": "AdaptiveCard"}), url="https://example.invalid/webhook")

    def test_rejects_non_2xx(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 302
        response.__enter__.return_value.reason = "Found"
        with mock.patch("sinks.req.urlopen", return_value=response):
            with self.assertRaises(Exception):
                sinks.teams_sink(json.dumps({"type": "AdaptiveCard"}), url="https://example.invalid/webhook")


if __name__ == '__main__':
    unittest.main()
