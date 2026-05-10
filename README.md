# 🤫 PsstBot — Telegram Inline Whisper Bot (Pyrogram)

An inline Telegram whisper bot built with **Pyrogram** (MTProto).
Targeted whispers are locked by **numeric user ID** — not username — so they stay secure even if the recipient later changes their @handle.

---

## ✨ Features

- **Open whisper** — anyone in the chat can tap to reveal
- **Targeted whisper** — only one specific person can read (locked by user ID)
- **Username → ID resolution** via MTProto (Pyrogram's superpower over Bot API)
- **Graceful fallback** — if username can't be resolved, shows a clear error
- **Long message support** — whispers over ~150 chars are sent to the reader's DM

---

## 🔑 Credentials you need (3 things)

| Credential | Where to get it |
|---|---|
| `API_ID` | https://my.telegram.org → Log in → API Development Tools → Create app |
| `API_HASH` | Same page as API_ID |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |

---

## 🚀 Deploy on Railway

### 1. Create your bot on Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts → copy the token
2. Run `/setinline` in BotFather → pick your bot → set placeholder (e.g. `Type your secret...`)

### 2. Get API credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click **API Development Tools**
4. Create an app (name/description can be anything)
5. Copy your `App api_id` and `App api_hash`

### 3. Deploy

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Select your repo
4. Go to **Variables** tab and add all three:

```
API_ID      = 12345678
API_HASH    = abcdef1234567890abcdef1234567890
BOT_TOKEN   = 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

5. Railway auto-detects the `Procfile` and starts the bot ✅

---

## 🖥️ Run Locally

```bash
git clone https://github.com/yourname/psstbot.git
cd psstbot

pip install -r requirements.txt

export API_ID=your_api_id
export API_HASH=your_api_hash
export BOT_TOKEN=your_bot_token

python bot.py
```

---

## 📖 How to Use

**Open whisper** (anyone can read):
```
@YourBot hello this is a secret
```

**Targeted whisper** (only @alice can read):
```
@YourBot hello this is a secret @alice
```

When typing with `@username`, the inline menu shows two options:
1. 🔒 *Whisper to @alice only* — locked to her user ID
2. 🤫 *Send as open whisper instead* — anyone can tap

---

## 🗂️ Project Structure

```
psstbot/
├── bot.py            # Complete bot logic (Pyrogram)
├── requirements.txt  # pyrogram + TgCrypto
├── Procfile          # Railway / Heroku start command
├── railway.toml      # Railway config
├── .env.example      # Env variable template
└── README.md
```

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_ID` | ✅ | From my.telegram.org |
| `API_HASH` | ✅ | From my.telegram.org |
| `BOT_TOKEN` | ✅ | From @BotFather |

---

## 📝 Why Pyrogram instead of python-telegram-bot?

The Bot API doesn't have a `getUser(username)` endpoint. Pyrogram uses **MTProto** directly, which lets it call `get_users("alice")` and get back Alice's permanent **numeric user ID**. This means:

- ✅ Whisper stays locked to the right person even after a username change
- ✅ Nobody can hijack a targeted whisper by taking a username
- ✅ Access check is `user.id == target_id` — a simple integer comparison
