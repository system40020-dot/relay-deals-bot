"""
Relay Deals Bot: EK Affiliaters (staging channel) -> Formatted repost (main channel)
======================================================================================
HOW THIS WORKS:
EK Affiliaters auto-posts deals (with affiliate links already generated)
into a private "staging" Telegram channel you don't show your audience.
This script uses a SEPARATE bot (added as admin to that staging channel)
to read those messages, extract the useful bits (title, price, link,
image), reformat them in your branded style, and post the result to
your real public channel.

--------------------------------------------------------------------
SETUP REQUIRED (one-time):
--------------------------------------------------------------------
1. Create a private Telegram channel (e.g. "Deal Staging") -- your
   audience never sees this.
2. In the EK Affiliaters app: Socials -> Telegram -> Add Telegram ->
   link THIS staging channel + its own bot. Turn on Autopost there.
   This is what feeds deals INTO the staging channel automatically.
3. Create a SECOND, separate bot via @BotFather (the "relay bot").
   Add this relay bot as an ADMIN of the staging channel (needs to
   at least be able to read messages -- admin is simplest).
4. Get the staging channel's numeric chat ID (see note below).
5. Your MAIN public channel keeps using its own existing bot (the one
   from the original deals_bot.py setup) to actually post.

Environment variables needed (GitHub Secrets):
    RELAY_BOT_TOKEN        - the second bot's token (reads staging channel)
    STAGING_CHAT_ID        - staging channel's numeric ID (e.g. -1001234567890)
    MAIN_BOT_TOKEN         - your main channel's bot token (posts final result)
    MAIN_CHAT_ID           - your main channel's @username or numeric ID

NOTE ON GETTING STAGING_CHAT_ID:
Channel usernames don't work reliably with getUpdates filtering, so we
need the numeric ID. Easiest way: post any message in the staging
channel, then run this script once with DEBUG_PRINT_UPDATES=true (see
bottom of file) to print raw updates including chat IDs, then copy the
ID you see (looks like -1001234567890) into your STAGING_CHAT_ID secret.
"""

import os
import re
import json
import random
import requests
from datetime import datetime, timedelta, timezone

RELAY_BOT_TOKEN = os.environ.get("RELAY_BOT_TOKEN", "")
STAGING_CHAT_ID = os.environ.get("STAGING_CHAT_ID", "")
MAIN_BOT_TOKEN = os.environ.get("MAIN_BOT_TOKEN", "")
MAIN_CHAT_ID = os.environ.get("MAIN_CHAT_ID", "")

STATE_FILE = "state.json"
SETTINGS_FILE = "settings.json"

IST_OFFSET = timedelta(hours=5, minutes=30)


# ---------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def default_state():
    return {"last_update_id": 0, "price_history": {}}


def now_ist():
    return datetime.now(timezone.utc) + IST_OFFSET


# ---------------------------------------------------------------------
# READ FROM STAGING CHANNEL (relay bot)
# ---------------------------------------------------------------------

def get_new_channel_posts(state):
    """Fetch new messages from the staging channel since last check."""
    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates"
    params = {
        "offset": state.get("last_update_id", 0) + 1,
        "allowed_updates": json.dumps(["channel_post"]),
        "timeout": 5,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  [error] getUpdates failed: {e}")
        return [], state.get("last_update_id", 0)

    if not data.get("ok"):
        print(f"  [error] Telegram API error: {data}")
        return [], state.get("last_update_id", 0)

    posts = []
    max_update_id = state.get("last_update_id", 0)

    for update in data.get("result", []):
        max_update_id = max(max_update_id, update["update_id"])
        post = update.get("channel_post")
        if not post:
            continue
        chat_id = str(post.get("chat", {}).get("id", ""))
        if STAGING_CHAT_ID and chat_id != str(STAGING_CHAT_ID):
            continue  # message from a different channel, ignore
        posts.append(post)

    return posts, max_update_id


# ---------------------------------------------------------------------
# PARSE A DEAL OUT OF A RAW EK AFFILIATERS MESSAGE
# ---------------------------------------------------------------------

PRICE_PATTERN = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?₹")
URL_PATTERN = re.compile(r"https?://\S+")
DISCOUNT_PATTERN = re.compile(r"-?\s?(\d{1,3})\s?%")
# Matches ratings like "4.3 ★", "⭐ 4.3", "4.3/5", "Rating: 4.3", "4.3 stars"
RATING_PATTERN = re.compile(
    r"(?:rating[:\s]*)?([1-5](?:\.\d)?)\s?(?:/\s?5|★|⭐|stars?)|"
    r"(?:★|⭐|rating[:\s]*)\s?([1-5](?:\.\d)?)",
    re.IGNORECASE,
)


def find_all_prices(text):
    """Returns all ₹ amounts found in text, as floats, in order of appearance.
    Handles both '₹350' and '350.00₹' formats."""
    prices = []
    for match in PRICE_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            prices.append(float(raw.replace(",", "")))
    return prices


def extract_deal_from_post(post):
    text = post.get("text") or post.get("caption") or ""
    if not text.strip():
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = lines[0] if lines else "Deal"
    # strip leading emojis/symbols from title for cleanliness
    title = re.sub(r"^[^\w]+", "", title).strip() or "Deal"

    price_list = find_all_prices(text)
    price = None
    original_price = None
    if len(price_list) >= 2:
        # typical "at only X instead of Y" -> X is current, Y is original (higher)
        price, original_price = price_list[0], price_list[1]
        if price > original_price:
            price, original_price = original_price, price
    elif len(price_list) == 1:
        price = price_list[0]

    discount_match = DISCOUNT_PATTERN.search(text)
    if discount_match:
        discount = f"{discount_match.group(1)}%"
        if original_price is None and price is not None:
            try:
                pct = float(discount_match.group(1))
                if 0 < pct < 100:
                    original_price = round(price / (1 - pct / 100))
            except (ValueError, ZeroDivisionError):
                pass
    else:
        discount = ""

    url_match = URL_PATTERN.search(text)
    link = url_match.group(0) if url_match else None

    rating_match = RATING_PATTERN.search(text)
    rating = None
    if rating_match:
        rating = rating_match.group(1) or rating_match.group(2)

    image_file_id = None
    if post.get("photo"):
        # Telegram sends multiple sizes; take the largest (last in list)
        image_file_id = post["photo"][-1]["file_id"]

    if not link:
        return None  # no usable link, skip this post

    return {
        "title": title,
        "price": price,
        "original_price": original_price,
        "discount": discount,
        "rating": rating,
        "link": link,
        "image_file_id": image_file_id,
        "raw_text": text,
    }


def get_file_url(file_id):
    """Convert a Telegram file_id into a downloadable/postable URL."""
    url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getFile"
    try:
        resp = requests.get(url, params={"file_id": file_id}, timeout=15)
        data = resp.json()
        if data.get("ok"):
            file_path = data["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{RELAY_BOT_TOKEN}/{file_path}"
    except requests.exceptions.RequestException as e:
        print(f"  [warn] getFile failed: {e}")
    return None


# ---------------------------------------------------------------------
# PRICE HISTORY (keyed by link, since that's our stable identifier)
# ---------------------------------------------------------------------

def record_price_history(state, key, price, max_points=5):
    if price is None:
        return
    history = state["price_history"].setdefault(key, [])
    today_str = now_ist().strftime("%Y-%m-%d")
    if history and history[-1].get("date") == today_str:
        history[-1]["price"] = price
    else:
        history.append({"price": price, "date": today_str})
    if len(history) > max_points:
        state["price_history"][key] = history[-max_points:]


def price_history_line(state, key, current_price):
    history = state["price_history"].get(key, [])
    if not history:
        return ""
    past = [h["price"] for h in history]
    trend = " → ".join(f"₹{int(p):,}" for p in past)
    if current_price is not None:
        trend += f" → ₹{int(current_price):,} (now)"
    lines = [f"📊 Price History: {trend}"]
    all_p = past + ([current_price] if current_price is not None else [])
    nums = [p for p in all_p if isinstance(p, (int, float))]
    if nums and current_price is not None and current_price <= min(nums):
        lines.append("🔥 *Lowest price recorded yet!*")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# FORMAT + POST TO MAIN CHANNEL
# ---------------------------------------------------------------------

def is_historical_minimum(state, key, current_price):
    if current_price is None:
        return False
    history = state["price_history"].get(key, [])
    past_prices = [h["price"] for h in history if isinstance(h.get("price"), (int, float))]
    if not past_prices:
        return False
    return current_price <= min(past_prices)


def format_caption(deal, settings, state):
    lines = []

    headers = settings.get("headers") or ([settings.get("header_text")] if settings.get("header_text") else [])
    if headers:
        lines.append(random.choice(headers))
        lines.append("")

    if is_historical_minimum(state, deal["link"], deal["price"]):
        lines.append("↗️ *HISTORICAL MINIMUM* ↗️")
        lines.append("")

    lines.append(f"👀 {deal['title']}")
    lines.append("")

    if deal["price"] is not None:
        price_str = f"₹{deal['price']:,.0f}"
        if deal["original_price"] is not None:
            orig_str = f"₹{deal['original_price']:,.0f}"
            disc_str = f" (-{deal['discount']})" if deal["discount"] else ""
            lines.append(f"💰 At only *{price_str}* instead of {orig_str}{disc_str}")
        else:
            disc_str = f" (-{deal['discount']})" if deal["discount"] else ""
            lines.append(f"💰 At only *{price_str}*{disc_str}")

    if deal.get("rating"):
        stars_filled = "⭐" * round(float(deal["rating"]))
        lines.append(f"{stars_filled} {deal['rating']}/5")

    lines.append("")
    lines.append(f"🔍 {deal['link']}")

    history_line = price_history_line(state, deal["link"], deal["price"])
    if history_line:
        lines.append("")
        lines.append(history_line)

    if settings.get("show_pricehistoryapp_link", True):
        lines.append("")
        lines.append("📈 Verify Flipkart/Amazon price trends: https://pricehistoryapp.com/")

    footer = settings.get("footer_text", "")
    if footer:
        lines += ["", footer]

    return "\n".join(lines)


def post_photo(image_url, caption):
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": MAIN_CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        print("  Posted (with image) to main channel.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  [warn] sendPhoto failed ({e}); falling back to text-only.")
        return False


def post_text(caption):
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": MAIN_CHAT_ID, "text": caption, "parse_mode": "Markdown",
               "disable_web_page_preview": False}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("  Posted (text-only) to main channel.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  [error] Telegram text post failed: {e}")
        return False


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    if os.environ.get("DEBUG_PRINT_UPDATES") == "true":
        url = f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates"
        resp = requests.get(url, timeout=15)
        print(json.dumps(resp.json(), indent=2))
        return

    if not all([RELAY_BOT_TOKEN, STAGING_CHAT_ID, MAIN_BOT_TOKEN, MAIN_CHAT_ID]):
        print("ERROR: Missing one or more required secrets:")
        print("  RELAY_BOT_TOKEN, STAGING_CHAT_ID, MAIN_BOT_TOKEN, MAIN_CHAT_ID")
        return

    settings = load_json(SETTINGS_FILE, {"footer_text": ""})
    state = load_json(STATE_FILE, default_state())

    posts, new_max_update_id = get_new_channel_posts(state)

    if not posts:
        print("No new posts in staging channel.")
        state["last_update_id"] = new_max_update_id
        save_json(STATE_FILE, state)
        return

    print(f"Found {len(posts)} new post(s) in staging channel.")

    for post in posts:
        deal = extract_deal_from_post(post)
        if not deal:
            print("  Skipped a post (no usable link found).")
            continue

        print(f"  Relaying: {deal['title']}")

        caption = format_caption(deal, settings, state)

        image_url = get_file_url(deal["image_file_id"]) if deal["image_file_id"] else None
        success = post_photo(image_url, caption) if image_url else post_text(caption)
        if not success and image_url:
            post_text(caption)

        record_price_history(state, deal["link"], deal["price"])

    state["last_update_id"] = new_max_update_id
    save_json(STATE_FILE, state)
    print("Done.")


if __name__ == "__main__":
    main()
