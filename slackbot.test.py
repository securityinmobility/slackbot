import unittest
import json
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

class TestSlackbot(unittest.TestCase):
    def setUp(self):
        self.environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
        self.environment.globals["now"] = datetime.now()

    def test_empty(self):
        template = self.environment.get_template("slack.j2")
        self.assertIn("keine Einträge", template.render(mensa = [], reimanns = []))

    def test_date_filter(self):
        template = self.environment.get_template("slack.j2")
        mensa = json.loads("""
        [
            {
                "timestamp": "2023-06-27",
                "meals": [
                    {
                        "name": {
                            "de": "Spargelcremesuppe in der Eintopfschale mit Brötchen",
                            "en": "Cream of asparagus soup in stew bowl with roll"
                        },
                        "category": "Suppe",
                        "prices": {
                            "student": 1.6,
                            "employee": 2.6,
                            "guest": 3.2
                        },
                        "allergens": [
                            "Wz",
                            "Mi",
                            "Sel"
                        ],
                        "flags": [
                            "V"
                        ],
                        "nutrition": {
                            "kj": 352,
                            "kcal": 84,
                            "fat": 2.4,
                            "fatSaturated": 1.5,
                            "carbs": 11.8,
                            "sugar": 7.6,
                            "fiber": 1.7,
                            "protein": 2.5,
                            "salt": 2.2
                        },
                        "originalLanguage": "de"
                    }
                ]
            }
        ]
        """)
        self.assertIn('keine Einträge', template.render(mensa = mensa, reimanns = []))
        self.assertIn('Spargelcremesuppe', template.render(mensa = mensa, reimanns = [], now=datetime.strptime('2023-06-27 10:00:00', '%Y-%m-%d %H:%M:%S')))
        self.assertIn('Spargelcremesuppe in der Eintopfschale mit Brötchen', template.render(mensa = mensa, reimanns = [], now=datetime.strptime('2023-06-27 10:00:00', '%Y-%m-%d %H:%M:%S')))
        self.assertNotIn('asparagus',  template.render(mensa = mensa, reimanns = [], now=datetime.strptime('2023-06-27 10:00:00', '%Y-%m-%d %H:%M:%S')))

    def test_teams_render(self):
        template = self.environment.get_template("teams.j2")
        payload = template.render(mensa = [], reimanns = [])
        self.assertIn("keine Einträge", payload)
        try:
            json.loads(payload)
        except ValueError:
            self.fail("Invalid JSON")


if __name__ == '__main__':
    unittest.main()
