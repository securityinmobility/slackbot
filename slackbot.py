import requests
import os
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from jinja2 import Environment, FileSystemLoader


client = WebClient(token=os.environ['API_KEY'])
mensa = requests.get('https://dev.neuland.app/api/mensa').json()
reimanns = requests.get('https://dev.neuland.app/api/reimanns').json()

environment = Environment(loader=FileSystemLoader("templates/"), trim_blocks=True)
template = environment.get_template("message.txt")
template.globals['now'] = datetime.now()

msg = template.render(mensa = mensa, reimanns = reimanns)
try:
    response = client.chat_postMessage(channel='#mittagspause', text=msg)
except SlackApiError as e:
    print(e)
