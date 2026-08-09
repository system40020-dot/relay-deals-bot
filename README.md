# Relay Deals Bot

Turns EK Affiliaters' auto-discovered deals into fully automated,
custom-formatted posts on your main channel — no manual link entry.

## How it works

1. EK Affiliaters auto-discovers deals and posts them into a private
   **staging channel** (one you create, your audience never sees it).
2. This bot (a separate "relay" bot) reads new messages from that
   staging channel every 15 minutes.
3. It extracts the title, price, discount, image, and affiliate link
   from each message.
4. It reformats everything in your branded style (emojis, price
   history, bold text) and posts it to your **real public channel**.

## One-time setup

### 1. Create a private staging channel
Name it anything (e.g. "Deal Staging"). Keep it private — this is
just a pipe, not something your audience sees.

### 2. Connect EK Affiliaters to the staging channel
In the EK Affiliaters app: **Socials → Telegram → Add Telegram** →
enter the staging channel's @username and EK Affiliaters' own bot
token for it. Turn on **Autopost** and **Autopost Image** there. This
is what feeds deals INTO the staging channel automatically — same
process as before, just pointed at this new private channel instead
of your public one.

### 3. Create a second bot (the "relay" bot)
Via @BotFather: `/newbot` → give it any name → save its token as
`RELAY_BOT_TOKEN`.

### 4. Add the relay bot as admin of the staging channel
Staging channel → Administrators → Add Admin → search for your relay
bot's username → add with at least read permissions.

### 5. Get the staging channel's numeric chat ID
Channel usernames don't work reliably for this, so we need the actual
ID (looks like `-1001234567890`):
1. Post any test message in the staging channel (once EK Affiliaters
   posts something, or post one yourself)
2. Temporarily add a GitHub Actions secret `DEBUG_PRINT_UPDATES` = `true`
3. Run the workflow manually once
4. Check the run's log output — it'll print the raw Telegram update,
   which includes the chat ID
5. Copy that ID into a secret called `STAGING_CHAT_ID`
6. Remove/set `DEBUG_PRINT_UPDATES` back to `false` (or delete it)

### 6. Add all secrets
Settings → Secrets and variables → Actions:
- `RELAY_BOT_TOKEN` — the relay bot's token
- `STAGING_CHAT_ID` — the staging channel's numeric ID
- `MAIN_BOT_TOKEN` — your real channel's existing bot token
- `MAIN_CHAT_ID` — your real channel's @username or numeric ID

### 7. Enable write permissions
Settings → Actions → General → Workflow permissions → **Read and
write permissions** → Save

### 8. Test it
Wait for EK Affiliaters to post a deal into staging (or post a test
message yourself in the right format, e.g. `Test Product\n₹499 30%
off\nhttps://example.com`), then Actions tab → Run workflow → check
your main channel.

## Ongoing use

Nothing — this is now fully hands-off. EK Affiliaters discovers deals,
this bot relays and reformats them automatically every 15 minutes.

## Settings (settings.json)
- `footer_text` — your channel promo line, attached to every post
