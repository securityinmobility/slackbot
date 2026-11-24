# Mittagessen-Bot (slackbot)

Posts today's lunch menu of **Mensa Ingolstadt** and **Reimanns**, with student and employee prices, to Microsoft Teams (and optionally Slack). In Teams, each dish shows its English name on a second line when the source has one. The team votes on where to eat with emoji **reactions** on that post.

## Architecture

```
systemd user timer (uni server, Mon–Fri 10:45 Europe/Berlin)
  └─ Quadlet container (rootless Podman): python3 slackbot.py
       ├─ Mensa: werkswelt.mensa_meals()
       │     GET https://www.werkswelt.de/index.php?id=ingo&setlang=de  and  …&setlang=en
       │     any error → warning on stderr, fall back to Neuland (IngolstadtMensa, German names only)
       ├─ Reimanns: POST https://api.neuland.app/graphql  (location Reimanns)
       ├─ meals_for_day(): keep today's Neuland meals (Europe/Berlin), drop "static" meals
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
| `slackbot.py` | Fetches the Neuland plan (`gql_GetPlan`), filters it (`meals_for_day`), formats the date (`format_date_de`), picks the Mensa source, renders and sends (`main`). |
| `werkswelt.py` | Scrapes the Mensa menu from werkswelt.de (`parse_menu`) and pairs the German and English pages (`mensa_meals`). |
| `sinks.py` | `teams_sink` wraps the card in a `message` with an Adaptive Card attachment and POSTs it; `slack_sink` posts text. |
| `templates/teams.j2` | Adaptive Card (version 1.0). The menu, voting legend and price legend are a single TextBlock; the labels are German/English. |
| `templates/slack.j2` | Slack text with Slack emoji codes (`:one:`, `:mensa-veg:` …). German names only. |
| `test_slackbot.py` | Offline unit tests. |
| `test_data/werkswelt_ingo_{de,en}.html` | werkswelt menu pages from 2026-11-24, used as test fixtures. |

### Data sources

Both sources deliver meals in the same shape (`name.de`, `name.en`, `prices.student`, `prices.employee`, `flags`), so the templates don't care where a meal came from.

#### Mensa: werkswelt.de (Studierendenwerk Erlangen-Nürnberg)

[werkswelt.de/?id=ingo](https://www.werkswelt.de/index.php?id=ingo) is the canteen operator's own menu page and the original source; Neuland gets its Mensa data from the same system. It has no feed or API, so `werkswelt.py` scrapes two HTML pages per run, `setlang=de` and `setlang=en`. `robots.txt` only disallows `/admin/`.

- The page shows **today only**: `Speiseplan <br><h4>Dienstag 24.11.2026</h4>` followed by one block per dish, separated by `<br> <br>`. Each block is a label (`Suppe`, `Essen 1` …), the name with allergen marks in `<sup>[Wz,Mi]</sup>` (removed), the prices `1,60 € (Stud.) 2,60 € (Bed.) 3,20 € (Gäste)`, and diet icons `<img class="infomax-food-icon veg">`. Extra lines after the prices, like "Optional: Reis", are ignored.
- `Stud.` → `prices.student`, `Bed.` (Bedienstete) → `prices.employee`. The icon class is used as the flag: `veg` vegan, `V` vegetarian, `R` beef, `S` pork, … (the same codes as Neuland).
- German and English dishes are paired by position. The prices must match on both pages; otherwise the English names are dropped with a warning.
- **Fallback:** if the German page can't be fetched, has no menu section, shows another date than today, or yields no dishes, `main()` prints a warning and uses Neuland's `IngolstadtMensa` instead. That data has German names only, because Neuland's `name.en` equals `name.de` for the Mensa.
- Unlike Neuland, werkswelt has no "static" flag: everything on the page is shown.

#### Reimanns (and the Mensa fallback): Neuland API

[Neuland API](https://github.com/neuland-ingolstadt/neuland.app-backend): a public GraphQL API with no authentication, the same one that `web.neuland.app/food` uses. Reimanns isn't on werkswelt. Query `food(locations: [...])` returns `foodData[]`, one entry per day (`timestamp` = `YYYY-MM-DD`, covering this and next week), each with `meals[]`:

| Field | Use |
|---|---|
| `name.de` / `name.en` | Dish name. Reimanns has real English names (e.g. "Hunter's roast with spätzle"); the Mensa's `name.en` is just the German name. |
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

1. In the Teams channel **mittagspause** → **…** → **Workflows**, create a workflow from the template **Send webhook alerts to a channel** ([Microsoft guide](https://support.microsoft.com/en-us/workflows/send-messages-in-teams-using-incoming-webhooks)).
   - It uses the trigger *When a Teams webhook request is received* and posts each Adaptive Card from `attachments` in the channel.
   - Don't use the variants *… from specific people* or *… from people in an org*: they require a Microsoft sign-in token, which the script doesn't send.
   - The account that creates the workflow posts through its Teams connection and must be a member of the team. Otherwise every post fails with `401 UnauthorizedSenderForChannelNotification`.
2. After saving, copy the webhook URL from the workflow's details page into `TEAMS_URL`.
3. **URL migration:** Microsoft announced that legacy webhook URLs on `*.logic.azure.com` stop working after 2025-11-30 (message center MC1168342). If `TEAMS_URL` still points there, open the flow, copy the new trigger URL (`…environment.api.powerplatform.com…`) and replace it.
4. The webhook answers **202 Accepted**. That only means the request was received, so check the flow's run history to confirm the post went out.

This needs only standard connectors, so no Power Automate Premium licence is required. The channel must not be private (the Flow bot can't post there).

Keeping the flow running:
- Power Automate turns a flow off if it fails for 14 days in a row, and emails the owners. Turn it back on after fixing the cause.
- Add a co-owner (flow → Details → Edit owners). The Teams connection belongs to the creator: if that account is deactivated or its sign-in expires, open Data → Connections and use "Fix connection", or rebuild the flow under another account and update `TEAMS_URL`.

## Run and schedule

The bot runs on a uni server as a rootless Podman container, built and run through [Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html) units and started by a systemd **user** timer. The unit files live only on the server, not in this repo:

| File on the server | Generated unit | Purpose |
|---|---|---|
| `~/.config/containers/systemd/slackbot.build` | `slackbot-build.service` | Builds the image from the checkout in `~/slackbot` (`Containerfile`). |
| `~/.config/containers/systemd/slackbot.container` | `slackbot.service` | Runs the image once with the env file. |
| `~/.config/systemd/user/slackbot.timer` | — | Starts `slackbot.service` Mon–Fri at 10:45 Berlin time. |

```ini
# slackbot.build
[Build]
ImageTag=localhost/<user>/slackbot
SetWorkingDirectory=%h/slackbot
```

```ini
# slackbot.container
[Unit]
Description=A slackbot container using systemd.
StartLimitIntervalSec=400
StartLimitBurst=3
After=network.target

[Container]
Image=slackbot.build
EnvironmentFile=%h/.config/slackbot.env

[Service]
Restart=on-failure
RestartSec=90

[Install]
# Do not start automatically.
```

```ini
# slackbot.timer
[Unit]
Description=Slackbot Timer

[Timer]
OnCalendar=Mon..Fri *-*-* 10:45:00 Europe/Berlin
Persistent=false
Unit=slackbot.service

[Install]
WantedBy=timers.target
```

- **Time zone:** the `Europe/Berlin` suffix makes the timer fire at 10:45 Berlin time whatever the server's time zone is. Check the next run with `systemd-analyze calendar "Mon..Fri *-*-* 10:45:00 Europe/Berlin"`.
- **`Persistent=false`:** if the server is down at 10:45, that day's run is skipped instead of posting the lunch poll late.
- **`Restart=on-failure`:** a failed run (exit code ≠ 0) is retried after 90 s, with at most 3 starts in 400 s. A retry sends to every configured sink again, so if Slack and Teams are both configured and only one failed, the other gets a duplicate post.

Set up, or apply changes to the unit files:

```bash
systemctl --user daemon-reload                # Quadlet regenerates the .service units
systemctl --user enable --now slackbot.timer
sudo loginctl enable-linger "$USER"           # run without a login session and after reboots
systemctl --user list-timers slackbot.timer   # shows the next run
```

Run once by hand and read the logs:

```bash
systemctl --user start slackbot.service
journalctl --user -u slackbot.service -n 50
```

Deploying new code: `git -C ~/slackbot pull`. Since Podman 5.3, `slackbot-build.service` runs again every time `slackbot.service` starts, so the next run builds the new code (unchanged layers come from the cache). Podman 5.2 keeps the build unit active after the first build, so there you need `systemctl --user restart slackbot-build.service` after pulling. Check the version with `podman --version`.

The env file (`~/.config/slackbot.env`) holds one `KEY=value` per line, **without quotes**: podman passes quotes literally. Keep it `chmod 600` and never commit it, because the repo is public.

Exit codes:
- `0`: posted, or there was no menu today (nothing posted).
- `1`: a sink failed (the message is on stderr).
- Non-zero with a traceback: fetching the plan failed (HTTP error, timeout or GraphQL error). Nothing was posted.

The script determines "today" in `Europe/Berlin` itself (with the `tzdata` package as a fallback in slim images).

## Tests

```bash
python -m unittest -v
```

All tests run offline: the Neuland API, werkswelt (via the fixtures in `test_data/`) and the webhook are mocked. To also query the live Neuland API and fetch both live werkswelt pages once (nothing is posted), for example on the server after a werkswelt layout change:

```bash
RUN_LIVE_API_TESTS=1 python -m unittest -v
```

## Known data quirks

- On some days Reimanns lists items like "Tagessuppe" or "Süßspeise" as `main` with the full price (6,90 €). They come from the API like that and are shown as delivered.
- English names: the card shows `name.de` and adds `name.en` in italics on the next line only if it differs. Neuland's Mensa `name.en` is the German name (checked 2026-11-13 and 2026-11-23), which is why the Mensa comes from werkswelt.
- werkswelt's English text is the canteen's own translation and sometimes imperfect ("Potatosoup in stew pot", "crunchy beetroot buffer"). It's shown as delivered.
- The werkswelt fixtures were taken from the browser DOM, not the raw server response. If the live page parses differently, the bot falls back to Neuland and logs `Warning: werkswelt failed (…)`; check with `RUN_LIVE_API_TESTS=1`.
