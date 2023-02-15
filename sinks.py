from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from urllib import request as req
import json


def slack_sink(message, channel, token):
    client = WebClient(token=token)
    response = client.chat_postMessage(channel=channel, text=message)
    return response

def teams_sink(message, url):
    payload = {
        "text": message
    }
    request = req.Request(url=url, method="POST")
    request.add_header(key="Content-Type", val="application/json")
    with req.urlopen(url=request, data=json.dumps(payload).encode()) as response:
        if response.status != 200:
            raise Exception(response.reason)
