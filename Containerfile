FROM python:slim

WORKDIR /app
COPY requirements.txt slackbot.py templates ./

RUN python -m pip install -r requirements.txt

CMD ["python3", "slackbot.py"]