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
import html
import json
import random
import requests
from datetime import datetime, timedelta, timezone

RELAY_BOT_TOKEN = os.environ.get("RELAY_BOT_TOKEN", "").strip()
STAGING_CHAT_ID = os.environ.get("STAGING_CHAT_ID", "").strip().strip("'\"")
MAIN_BOT_TOKEN = os.environ.get("MAIN_BOT_TOKEN", "").strip()
MAIN_CHAT_ID = os.environ.get("MAIN_CHAT_ID", "").strip()

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
    return {"last_update_id": 0, "processed_ids": [], "price_history": {}}


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
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
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


def extract_links_from_post(post):
    """Gathers URLs from BOTH visible text AND Telegram 'hyperlink' entities.
    Amazon/Myntra/Ajio-style links are often hidden behind clickable text
    (e.g. "🔍 Tap here") rather than shown as plain text -- those only show
    up in the message's entities/caption_entities, not in .text itself."""
    text = post.get("text") or post.get("caption") or ""
    links = []

    for match in URL_PATTERN.finditer(text):
        # strip trailing punctuation that regex sometimes grabs along with
        # the URL (e.g. a link at the end of a sentence: "...link).")
        links.append(match.group(0).rstrip(".,;!)]}\"'"))

    for entity in (post.get("entities") or []) + (post.get("caption_entities") or []):
        if entity.get("type") == "text_link" and entity.get("url"):
            links.append(entity["url"])

    # dedupe while preserving order, and never treat our OWN reference
    # link (pricehistoryapp.com) as if it were the product's deal link
    seen = set()
    deduped = []
    for link in links:
        if link and link not in seen and "pricehistoryapp.com" not in link.lower():
            seen.add(link)
            deduped.append(link)

    return deduped


# Known affiliate/shortener domains -- prefer these over a bare original
# product page link when a message contains more than one URL.
PREFERRED_LINK_DOMAINS = [
    # Real EK Affiliaters shortener domains (confirmed from actual staging posts)
    "myntr.it", "bitli.in", "ajiio.in", "fkrt.cc",
    # Other common Indian affiliate/shortener domains, kept as a safety net
    "amzn.to", "fkrt.it", "bit.ly", "ekaro.in", "ekaro-api.affiliaters.in",
    "cuelinks.com", "dl.flipkart.com", "tinyurl.com", "cutt.ly", "rebrand.ly",
]


def pick_best_link(links):
    if not links:
        return None
    for link in links:
        if any(domain in link for domain in PREFERRED_LINK_DOMAINS):
            return link
    return links[0]  # fallback: first link found, whatever it is


def detect_category(title, text, settings):
    """Detects product category by keyword matching against settings.
    Falls back to 'general' if nothing matches, so headers stay neutral
    instead of wrongly showing fashion emojis on an electronics deal."""
    combined = (title + " " + text).lower()
    category_keywords = settings.get("category_keywords", {})
    for category, keywords in category_keywords.items():
        for kw in keywords:
            if kw.lower() in combined:
                return category
    return "general"


def extract_deal_from_post(post, settings):
    text = post.get("text") or post.get("caption") or ""
    if not text.strip():
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = None
    for line in lines:
        candidate = re.sub(r"^[^\w]+", "", line).strip()
        if candidate and not URL_PATTERN.match(candidate):
            title = candidate
            break

    if not title:
        return None  # no usable title text (e.g. source post was just a bare link) -- skip

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

    all_links = extract_links_from_post(post)
    link = pick_best_link(all_links)

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

    category = detect_category(title, text, settings)

    return {
        "title": title,
        "price": price,
        "original_price": original_price,
        "discount": discount,
        "rating": rating,
        "link": link,
        "category": category,
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
    lines = [f"📊 <b>Price History:</b> {trend}"]
    all_p = past + ([current_price] if current_price is not None else [])
    nums = [p for p in all_p if isinstance(p, (int, float))]
    if nums and current_price is not None and current_price <= min(nums):
        lines.append("🔥 <b>Lowest price recorded yet!</b>")
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


def format_caption(deal, settings, state, for_photo=True):
    category = deal.get("category", "general")
    category_headers = settings.get("category_headers", {})
    headers = category_headers.get(category) or category_headers.get("general") or settings.get("headers") or []

    header_line = html.escape(random.choice(headers)) if headers else ""
    hist_min = is_historical_minimum(state, deal["link"], deal["price"])

    clean_title = html.escape(deal["title"])
    title_block = (("↗️ <b>HISTORICAL MINIMUM</b> ↗️\n" if hist_min else "")
                   + f"👀 <b>{clean_title}</b>")

    price_line = ""
    if deal["price"] is not None:
        price_str = f"₹{deal['price']:,.0f}"
        disc_str = f" (-{html.escape(deal['discount'])})" if deal["discount"] else ""
        if deal["original_price"] is not None:
            orig_str = f"₹{deal['original_price']:,.0f}"
            price_line = f"💰 At only <b>{price_str}</b> instead of <s>{orig_str}</s>{disc_str}"
        else:
            price_line = f"💰 At only <b>{price_str}</b>{disc_str}"

    rating_line = ""
    if deal.get("rating"):
        try:
            stars_filled = "⭐" * round(float(deal["rating"]))
            rating_line = f"{stars_filled} {deal['rating']}/5"
        except ValueError:
            pass

    price_rating_block = "\n".join(l for l in [price_line, rating_line] if l)

    link_line = f"🔍 {deal['link']}"
    history_line = price_history_line(state, deal["link"], deal["price"])
    ph_line = "📈 Verify Flipkart/Amazon price trends: https://pricehistoryapp.com/" if settings.get("show_pricehistoryapp_link", True) else ""
    footer = html.escape(settings.get("footer_text", ""))

    # Essential blocks always kept; optional blocks dropped (lowest priority
    # first) if the caption would otherwise exceed Telegram's length limit.
    essential_blocks = [b for b in [header_line, title_block, price_rating_block, link_line] if b]
    optional_blocks = [b for b in [history_line, ph_line, footer] if b]

    max_len = 1024 if for_photo else 4096
    caption = "\n\n".join(essential_blocks + optional_blocks)

    while len(caption) > max_len and optional_blocks:
        optional_blocks.pop()
        caption = "\n\n".join(essential_blocks + optional_blocks)

    if len(caption) > max_len:
        # last resort: hard truncate the title itself
        overflow = len(caption) - max_len + 3
        trimmed_title = html.escape(deal["title"][: max(10, len(deal["title"]) - overflow)]) + "..."
        essential_blocks[1] = (("↗️ <b>HISTORICAL MINIMUM</b> ↗️\n" if hist_min else "")
                                + f"👀 <b>{trimmed_title}</b>")
        caption = "\n\n".join(essential_blocks + optional_blocks)[:max_len]

    return caption


def post_photo(image_url, caption):
    url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": MAIN_CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
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
    payload = {"chat_id": MAIN_CHAT_ID, "text": caption, "parse_mode": "HTML",
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
    processed_ids = set(state.get("processed_ids", []))

    posts, new_max_update_id = get_new_channel_posts(state)

    if not posts:
        print("No new posts in staging channel.")
        state["last_update_id"] = new_max_update_id
        save_json(STATE_FILE, state)
        return

    print(f"Found {len(posts)} new post(s) in staging channel.")

    # IMPORTANT: mark the offset as consumed right away, and save immediately.
    # This is the fix for "old deals repost on re-run" -- previously the
    # offset only saved at the very end, so any crash mid-batch meant the
    # next run re-fetched and re-relayed everything from scratch.
    # processed_ids is a SECOND, independent safety net on top of this: even
    # if the offset mechanism somehow re-delivers a message, its message_id
    # will already be marked processed, so it won't be relayed twice.
    state["last_update_id"] = new_max_update_id
    save_json(STATE_FILE, state)

    for post in posts:
        msg_id = post.get("message_id")
        if msg_id and msg_id in processed_ids:
            print(f"  Skipping message_id {msg_id} (already processed).")
            continue

        try:
            deal = extract_deal_from_post(post, settings)
            if not deal:
                print("  Skipped a post (no usable title/link found).")
                if msg_id:
                    processed_ids.add(msg_id)
                continue

            print(f"  Relaying: {deal['title']} [category: {deal['category']}]")

            image_url = get_file_url(deal["image_file_id"]) if deal["image_file_id"] else None

            if image_url:
                caption = format_caption(deal, settings, state, for_photo=True)
                success = post_photo(image_url, caption)
                if not success:
                    caption_text = format_caption(deal, settings, state, for_photo=False)
                    success = post_text(caption_text)
            else:
                caption = format_caption(deal, settings, state, for_photo=False)
                success = post_text(caption)

            if success:
                record_price_history(state, deal["link"], deal["price"])
                if msg_id:
                    processed_ids.add(msg_id)

            # save after EVERY post (success, skip, or failure) so progress
            # is never lost even if a later post in this same batch crashes
            state["processed_ids"] = list(processed_ids)[-200:]  # cap growth
            save_json(STATE_FILE, state)
        except Exception as e:
            # one bad post should never take down the whole run or cause
            # already-relayed posts to be silently lost/reprocessed
            print(f"  [error] Failed to process a post, skipping it: {e}")
            if msg_id:
                processed_ids.add(msg_id)
                state["processed_ids"] = list(processed_ids)[-200:]
                save_json(STATE_FILE, state)
            continue
       
 print("Done.") 

if __name__ == "__main__":
    main()
   
