import unittest
import json
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

class TestSlackbot(unittest.TestCase):
    def setUp(self):
        self.environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
        self.template = self.environment.get_template("message.txt")
        self.template.globals['now'] = datetime.now()

    def test_empty(self):
        self.assertIn("keine Einträge", self.template.render(mensa = [], reimanns = []))

    def test_date_filter(self):
        mensa = json.loads("""
        [
            {
                "timestamp": "2021-01-17T23:00:00.000Z",
                "meals": [
                {
                    "name": "Puten Cordon Bleu mit Zitrone Pommes-Frites",
                    "prices": {
                        "student": 3.39,
                        "employee": 4.39,
                        "guest": 6.78
                    },
                    "allergenes": [
                    "1",
                    "4",
                    "7",
                    "Wz",
                    "Mi"
                    ]
                }
                ]
            }
            ]
        """)
        self.assertIn('keine Einträge', self.template.render(mensa = mensa, reimanns = []))
        self.assertIn('Zitrone', self.template.render(mensa = mensa, reimanns = [], now=datetime.strptime('2021-01-17 10:00:00', '%Y-%m-%d %H:%M:%S')))


if __name__ == '__main__':
    unittest.main()