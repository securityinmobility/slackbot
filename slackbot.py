import requests
import os
import sys
from functools import partial
from datetime import date, datetime
from zoneinfo import ZoneInfo
from jinja2 import Environment, FileSystemLoader
from sinks import slack_sink, teams_sink
from types import SimpleNamespace

API_ENDPOINT = os.environ.get("API_ENDPOINT", "https://api.neuland.app/graphql")
TIMEZONE = ZoneInfo("Europe/Berlin")
WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def gql_GetPlan(location: str):
    QUERY = """
        query GetPlan($location: LocationInput!) {
        food(locations: [$location]) {
            foodData {
            timestamp,
            meals { name { de, en } category restaurant static flags prices { student, employee, guest } }
            }
            errors { location message }
        }
        }
    """

    response = requests.post(
        API_ENDPOINT,
        json={"query": QUERY, "variables": {"location": location}},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL error for {location}: {body['errors']}")
    food = body["data"]["food"]
    for error in food.get("errors") or []:
        print(f"Warning: {error['location']}: {error['message']}", file=sys.stderr)
    return food["foodData"] or []


def meals_for_day(plan, day: date):
    """Meals of the given day. Static meals are on offer every day and are left out."""
    return [
        meal
        for entry in plan
        if day.isoformat() in entry["timestamp"]
        for meal in (entry["meals"] or [])
        if not meal.get("static")
    ]


def format_date_de(day: date) -> str:
    return f"{WEEKDAYS_DE[day.weekday()]}, {day.strftime('%d.%m.%Y')}"


def main():
    today = datetime.now(TIMEZONE).date()
    environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
    environment.globals["today"] = today
    environment.filters["date_de"] = format_date_de

    sinks = []
    if (
        token := (os.environ.get("API_KEY") or os.environ.get("SLACK_APIKEY"))
    ) is not None:
        sinks.append(
            SimpleNamespace(
                name="slack",
                template=environment.get_template("slack.j2"),
                send=partial(
                    slack_sink,
                    channel=os.environ.get("SLACK_CHANNEL", "#mittagessen"),
                    token=token,
                ),
            )
        )
    if (teams_url := os.environ.get("TEAMS_URL")) is not None:
        sinks.append(
            SimpleNamespace(
                name="teams",
                template=environment.get_template("teams.j2"),
                send=partial(teams_sink, url=teams_url),
            )
        )

    mensa = meals_for_day(gql_GetPlan(location="IngolstadtMensa"), today)
    reimanns = meals_for_day(gql_GetPlan(location="Reimanns"), today)
    if not mensa and not reimanns:
        print(f"No menu for {today.isoformat()}, nothing posted.")
        return 0

    failed = False
    for sink in sinks:
        try:
            message = sink.template.render(mensa=mensa, reimanns=reimanns)
            sink.send(message)
        except Exception as e:
            print(f"Sink {sink.name} failed: {e}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
