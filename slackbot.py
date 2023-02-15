import requests
import os
from functools import partial
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from sinks import slack_sink, teams_sink


def main():
    sinks = []
    if (token := (os.environ.get('API_KEY') or os.environ.get('SLACK_APIKEY'))) is not None:
        sinks.append(partial(slack_sink, channel=os.environ.get('SLACK_CHANNEL', '#mittagessen'), token=token))
    if (teams_url := os.environ.get('TEAMS_URL')) is not None:
        sinks.append(partial(teams_sink, url=teams_url))

    mensa = requests.get('https://dev.neuland.app/api/mensa').json()
    reimanns = requests.get('https://dev.neuland.app/api/reimanns').json()

    environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
    template = environment.get_template("message.txt")
    template.globals['now'] = datetime.now()

    msg = template.render(mensa=mensa, reimanns=reimanns)
    try:
        for sink in sinks:
            sink(msg)
    except Exception as e:
        print(e)

if __name__ == '__main__':
    main()
