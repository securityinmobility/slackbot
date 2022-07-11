FROM python:slim

WORKDIR /app
COPY requirements.txt slackbot.py ./

RUN pip3 install -r requirements.txt

CMD ["python3", "slackbot.py"]


