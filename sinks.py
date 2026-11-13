from urllib import request as req
import json


def slack_sink(message, channel, token):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    
    client = WebClient(token=token)
    response = client.chat_postMessage(channel=channel, text=message)
    return response

def teams_sink(message, url):
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": json.loads(message),
            }
        ]
    }
    request = req.Request(url=url, method="POST")
    request.add_header(key="Content-Type", val="application/json")
    # Teams Workflow webhooks answer 202 Accepted, so any 2xx counts as success.
    with req.urlopen(url=request, data=json.dumps(payload).encode(), timeout=30) as response:
        if not 200 <= response.status < 300:
            raise Exception(f"{response.status} {response.reason}")
