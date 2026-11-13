import unittest
import json
import os
from datetime import date, datetime
from unittest import mock
from jinja2 import Environment, FileSystemLoader

import sinks
import slackbot
from slackbot import TIMEZONE, format_date_de, gql_GetPlan, meals_for_day

DAY = date(2026, 11, 13)


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
    def run_main(self, plan, sink_error=None):
        with mock.patch.dict(os.environ, {"TEAMS_URL": "https://example.invalid/webhook"}, clear=True), \
                mock.patch("slackbot.gql_GetPlan", return_value=plan), \
                mock.patch("slackbot.teams_sink", side_effect=sink_error) as teams_sink:
            return slackbot.main(), teams_sink

    def test_posts_today(self):
        exit_code, teams_sink = self.run_main(plan_for(datetime.now(TIMEZONE).date()))
        self.assertEqual(exit_code, 0)
        teams_sink.assert_called_once()
        json.loads(teams_sink.call_args.args[0])

    def test_no_menu_posts_nothing(self):
        exit_code, teams_sink = self.run_main([])
        self.assertEqual(exit_code, 0)
        teams_sink.assert_not_called()

    def test_sink_failure_exit_code(self):
        exit_code, _ = self.run_main(plan_for(datetime.now(TIMEZONE).date()), sink_error=Exception("down"))
        self.assertEqual(exit_code, 1)


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
