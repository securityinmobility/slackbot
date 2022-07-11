import requests
import os
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def generate_meals_list(url):
    data = requests.get(url).json()
    today = datetime.now().strftime('%Y-%m-%d')
    entries = [x for x in data if x["timestamp"] == today]

    if len(entries) == 0:
        return "keine Einträge :("
    else:
        meals = [f'- {x["name"]} ({x["prices"]["employee"]:.2f}€)' for x in entries[0]["meals"]]
        return '\n'.join(meals)

mensa = generate_meals_list("https://dev.neuland.app/api/mensa")
reimanns = generate_meals_list("https://dev.neuland.app/api/reimanns")

msg = """Abstimmung bzgl. Mittagsessen heute:

Mensa = :one::
{}

Reimanns = :two::
{}

Home Office = :three::
send pics!

beep boop""".format(mensa, reimanns)

client = WebClient(token=os.environ['API_KEY'])

try:
    response = client.chat_postMessage(channel='#mittagspause', text=msg)
except SlackApiError as e:
    print(e)
