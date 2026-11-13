# Mittagessen-Bot (slackbot)

Posts today's lunch menu of **Mensa Ingolstadt** and **Reimanns**, with student and employee prices, to Microsoft Teams (and optionally Slack). The team votes on where to eat with emoji **reactions** on that post.

## Architecture

```
cron (uni server, Mon–Fri 10:45)
  └─ container: python3 slackbot.py
       ├─ POST https://api.neuland.app/graphql   (once per restaurant: IngolstadtMensa, Reimanns)
       ├─ meals_for_day(): keep today's meals (Europe/Berlin), drop "static" meals
       ├─ no meal at either restaurant → print "No menu …", exit 0, post nothing
       ├─ render templates/teams.j2 (Adaptive Card JSON) / templates/slack.j2 (text)
       └─ sinks.py
            ├─ teams_sink → POST to the Teams Workflow webhook (TEAMS_URL)
            │     Power Automate: "When a Teams webhook request is received"
            │     → posts the card in the channel as the Workflows (Flow) bot
            └─ slack_sink → chat.postMessage (only if API_KEY / SLACK_APIKEY is set)
```

| File | Purpose |
|---|---|
| `slackbot.py` | Fetches the plan (`gql_GetPlan`), filters it (`meals_for_day`), formats the date (`format_date_de`), renders and sends (`main`). |
| `sinks.py` | `teams_sink` wraps the card in a `message` with an Adaptive Card attachment and POSTs it; `slack_sink` posts text. |
| `templates/teams.j2` | Adaptive Card (version 1.0). The menu, voting legend and price legend are a single TextBlock. |
| `templates/slack.j2` | Slack text with Slack emoji codes (`:one:`, `:mensa-veg:` …). |
| `test_slackbot.py` | Offline unit tests. |

### Data source

[Neuland API](https://github.com/neuland-ingolstadt/neuland.app-backend): a public GraphQL API with no authentication, the same one that `web.neuland.app/food` uses. Query `food(locations: [...])` returns `foodData[]`, one entry per day (`timestamp` = `YYYY-MM-DD`, covering this and next week), each with `meals[]`:

| Field | Use |
|---|---|
| `name.de` | Dish name |
| `prices.student` / `prices.employee` | Shown as `(student € \| employee €)`. A missing student price is left out; a missing employee price shows `??`. |
| `static` | `true` = on offer every day (Reimanns: Thai Curry, Burger, Currywurst, salads, Tagessuppe). **Hidden**, like in the Neuland app. |
| `flags` | Mensa only (Reimanns sends `null`). Teams shows `veg` → 🌱 vegan and `V` → 🥕 vegetarian; Slack shows every flag as `:mensa-<flag>:`. |
| `errors[]` | Per-restaurant scraper errors. They are printed as a warning, and the other restaurant is still posted. |

Soups are included, because they have `category: soup` and aren't static.

## Voting: reactions instead of checkboxes

The card asks people to react with 1️⃣ Mensa, 2️⃣ Reimanns, 3️⃣ Home Office, 🙋‍♂️ Pick up Achim, 🙆‍♂️ Pick up Thomas or 🙋‍♀️ Pick up Patrizia. Teams shows every reaction, and who added it, to everyone. A user can add several reactions to one message. To change the emoji or names, edit the `text` block in `templates/teams.j2`.

Why there are no checkboxes any more (decided 2026-11-13):
- The old `Input.Toggle` elements had no `Action.Submit`, so a tick only changed in the clicker's own Teams client and was never sent anywhere.
- A shared, updating card needs a callback. With Power Automate (no Premium) that means one of these, and none is reliable or cheap:
  - Post the card and use the trigger *When someone responds to an adaptive card*. Microsoft lists combining that trigger with *Post adaptive card in a chat or channel* as a known issue ("Something went wrong" on submit), and users report that the trigger fails after *Update an adaptive card*.
  - *Post adaptive card and wait for a response*. It accepts only the first response per card, so every click would create a new post.
  - A custom Teams bot (Azure Bot, `Action.Execute`). It works, but needs Azure, an Entra app registration, an uploaded custom Teams app and a public endpoint.

## Configuration

| Env var | Required | Meaning |
|---|---|---|
| `TEAMS_URL` | for Teams | Webhook URL of the Power Automate workflow (secret: anyone with the URL can post to the channel) |
| `API_KEY` or `SLACK_APIKEY` | for Slack | Slack bot token |
| `SLACK_CHANNEL` | no | Default `#mittagessen` |
| `API_ENDPOINT` | no | Default `https://api.neuland.app/graphql` |

## Power Automate workflow (Teams side)

1. In the Teams channel **mittagspause** → **…** → **Workflows**, create a workflow from the template that posts to a channel when a webhook request is received. It uses the trigger *When a Teams webhook request is received*, loops over `attachments` and posts each Adaptive Card in the channel. Set *Who can trigger the flow* to *Anyone*.
2. Copy the URL from the trigger into `TEAMS_URL`.
3. **URL migration:** Microsoft announced that legacy webhook URLs on `*.logic.azure.com` stop working after 2025-11-30 (message center MC1168342). If `TEAMS_URL` still points there, open the flow, copy the new trigger URL (`…environment.api.powerplatform.com…`) and replace it.
4. The webhook answers **202 Accepted**. That only means the request was received, so check the flow's run history to confirm the post went out.

This needs only standard connectors, so no Power Automate Premium licence is required. The channel must not be private (the Flow bot can't post there).

## Run and schedule

Deployment isn't part of this repo. Example with the container:

```bash
podman build -t slackbot .
podman run --rm -e TEAMS_URL="$TEAMS_URL" slackbot
```

Crontab on the server (cron uses the server's time zone; check it with `timedatectl`):

```
45 10 * * 1-5  podman run --rm --env-file /path/to/slackbot.env slackbot >> /var/log/slackbot.log 2>&1
```

Exit codes:
- `0`: posted, or there was no menu today (nothing posted).
- `1`: a sink failed (the message is on stderr).
- Non-zero with a traceback: fetching the plan failed (HTTP error, timeout or GraphQL error). Nothing was posted.

The script determines "today" in `Europe/Berlin` itself (with the `tzdata` package as a fallback in slim images).

## Tests

```bash
python -m unittest -v
```

All tests run offline: the API and the webhook are mocked. To also query the live API once:

```bash
RUN_LIVE_API_TESTS=1 python -m unittest -v
```

## Known data quirks

- On some days Reimanns lists items like "Tagessuppe" or "Süßspeise" as `main` with the full price (6,90 €). They come from the API like that and are shown as delivered.
- English names (`name.en`) are often just the German name, so the bot always uses `name.de`.
