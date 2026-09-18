# Job Applying Agent

Single-user local CLI. It uses **your** Telegram account to read job channels
you already joined, match posts to keywords, and log applications to CSV/Excel.

Secrets stay on this machine. Do not paste `api_hash`, phone numbers, or login
codes into Cursor chat.

## 1. Get `api_id` and `api_hash`

1. Open [https://my.telegram.org](https://my.telegram.org) in a browser.
2. Enter **your** phone number with country code (same number as the Telegram app).
3. Telegram sends a login code **in the Telegram app**. Type that code on the website.
4. Open **API development tools**.
5. If you have no app yet, create one:
   - App title: `JobApplyingAgent` (any name is fine)
   - Short name: `jobagent` (5–32 letters/digits)
   - Platform: Desktop
6. Copy **`api_id`** (a number) and **`api_hash`** (a long hex string).
7. In this project folder, copy `.env.example` to `.env` and fill those two values.
   Leave `TELEGRAM_PHONE` empty. The login command will ask for the phone in your
   own terminal.

If the site already shows an app, reuse those credentials. Do not create many apps.

## 2. Install and log in

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env
python -m jobagent login
```

`login` asks for the phone and the Telegram code **in that terminal**. After that,
`data/user.session` is your login cookie. Keep it private, like a password.

Put your CV at `data/cv.pdf`.

## 3. Daily use

```bash
python -m jobagent channels   # list joined channels; copy usernames into config.yaml
python -m jobagent scan       # fetch new posts
python -m jobagent review     # apply / skip / later
python -m jobagent export     # write data/applied.csv and data/applied.xlsx
python -m jobagent status
```

Telegram applies always ask `y/n` first. The tool will not mass-DM on its own.
