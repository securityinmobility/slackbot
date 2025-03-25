import requests
import os
from functools import partial
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from sinks import slack_sink, teams_sink
from types import SimpleNamespace

API_ENDPOINT = os.environ.get("API_ENDPOINT", "https://api.neuland.app/graphql")


def gql_GetPlan(location: str):
    QUERY = """
        query GetPlan($location: LocationInput!) {
        food(locations: [$location]) {
            foodData {
            timestamp,
            meals { name { de, en } category restaurant prices { student, employee, guest } }
            }
        }
        }
    """

    response = requests.post(
        API_ENDPOINT,
        json={"query": QUERY, "variables": {"location": location}},
    )
    assert response.status_code == 200
    return response.json()["data"]["food"]["foodData"]


def main():
    environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
    environment.globals["now"] = datetime.now()

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

    try:
        mensa = gql_GetPlan(location="IngolstadtMensa")
        reimanns = gql_GetPlan(location="Reimanns")

        for sink in sinks:
            message = sink.template.render(mensa=mensa, reimanns=reimanns)
            sink.send(message)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    main()
