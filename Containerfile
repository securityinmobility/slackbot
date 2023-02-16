FROM python:slim

WORKDIR /app
COPY . .

RUN python -m pip install -r requirements.txt

RUN ls -lah .
CMD ["python3", "slackbot.py"]
