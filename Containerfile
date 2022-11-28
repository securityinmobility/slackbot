FROM python:slim

WORKDIR /app
COPY requirements.txt slackbot.py ./
ADD templates templates/

RUN python -m pip install -r requirements.txt

RUN ls -lah .
CMD ["python3", "slackbot.py"]
