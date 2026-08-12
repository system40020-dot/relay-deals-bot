from flask import Flask
import threading
import time
import os
import json
import re
import random
import requests
import urllib.parse
import html
from playwright.sync_api import sync_playwright

app = Flask('')

@app.route('/')
def home():
    return "Playwright Bot is running and active!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# ================= CONFIGURATION =================
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "")
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "")

STAGING_CHAT_ID = os.getenv("STAGING_CHAT_ID", "")
MAIN_CHAT_ID = os.getenv("MAIN_CHAT_ID", "")

CHANNEL_HANDLE = "@loot_hacked"
DEFAULT_PRICE_HISTORY_LINK = "https://pricehistoryapp.com/"

DEAL_HEADERS = [
    "🔥 MEGA LOOT DEAL ALERT! 🔥", "⚡ LIGHTNING FAST OFFER ⚡", "💥 CRAZY PRICE DROP 💥",
    "🌟 SPECIAL HANDPICKED LOOT 🌟", "🚀 HURRY! MASSIVE DISCOUNT 🚀", "💎 BEST VALUE DEAL FOUND 💎",
    "📉 LOWEST PRICE EVER 📉", "🚨 HOT DEAL ALERT 🚨", "🎯 TODAY'S TOP LOOT 🎯",
    "🛍️ SHOPPING SPREE DEAL 🛍️", "🔊 DEAL OF THE DAY 🔊", "🏷️ UNBEATABLE PRICE TAG 🏷️",
    "⏰ LIMITED TIME LOOT ⏰", "💰 SAVE BIG TODAY 💰", "🎉 EXCLUSIVE DEAL FOR YOU 🎉",
    "🔻 PRICE SLASHED 🔻", "✨ FRESH LOOT ALERT ✨", "🏃‍♂️ GRAB IT BEFORE IT'S GONE 🏃‍♂️",
    "📢 BIG SAVINGS INSIDE 📢", "🎁 STEAL DEAL ALERT 🎁", "🧨 EXPLOSIVE OFFER 🧨",
    "🛒 CART-WORTHY DEAL 🛒", "🔑 UNLOCK THIS OFFER 🔑", "🏆 TOP PICK OF THE DAY 🏆",
    "📦 FRESH ARRIVAL DEAL 📦", "🌈 RAINBOW DISCOUNT 🌈", "🎈 FESTIVE PRICE DROP 🎈",
    "🧲 MAGNET DEAL: TOO GOOD 🧲", "🥇 GOLD STANDARD OFFER 🥇", "🎊 CELEBRATION SALE 🎊",
    "⚙️ SMART BUY ALERT ⚙️", "🌟 TRENDING DEAL NOW 🌟", "🔔 DON'T MISS THIS ONE 🔔",
    "💫 PRICE MAGIC HAPPENING 💫", "🧊 COOL DEAL ALERT 🧊"
]
CATEGORY_CATALOG = {
    "Electronics, Computers & Smart Tech": {
        "Smartphones & Mobile Devices": ["smartphone", "android phone", "iphone", "feature phone", "foldable phone", "refurbished mobile", "unboxed mobile", "wi-fi tablet", "tablet", "ipad", "e-reader"],
        "Mobile & Tech Accessories": ["tempered glass", "back cover", "silicone case", "power bank", "gan charger", "fast charger", "data cable", "type-c cable", "lightning cable", "otg cable", "mobile holder", "ring light", "selfie stick", "vr headset", "smartwatch strap"],
        "Computers & Laptops": ["laptop", "gaming laptop", "2-in-1 convertible", "macbook", "desktop pc", "all-in-one pc", "gpu", "ram", "motherboard"],
        "Computer Peripherals & Storage": ["keyboard", "wireless mouse", "gaming mouse", "external hdd", "external ssd", "pen drive", "monitor", "webcam", "printer", "ink cartridge", "router"],
        "Audio, Wearables & Optics": ["earbuds", "tws", "anc headphone", "headphone", "bluetooth speaker", "soundbar", "home theatre", "smartwatch", "fitness band", "dslr", "mirrorless camera", "action camera", "gopro", "drone", "lens", "tripod", "binocular"],
        "Smart Home & Automation": ["smart bulb", "led strip light", "smart plug", "video doorbell", "smart door lock", "alexa", "google nest", "voice assistant"],
    },
    "Large Appliances & Climate Control": {
        "Cooling & Heating": ["split ac", "window ac", "inverter ac", "tower fan", "air cooler", "room heater", "geyser", "water heater"],
        "Home Appliances": ["refrigerator", "fridge", "washing machine", "dishwasher", "vacuum cleaner", "robotic cleaner", "garment steamer", "water purifier", "ro purifier"],
    },
    "Kitchen & Dining": {
        "Kitchen Appliances": ["microwave", "otg oven", "air fryer", "induction cooktop", "mixer grinder", "food processor", "electric kettle", "coffee maker", "sandwich maker", "toaster"],
        "Cookware & Bakeware": ["pressure cooker", "frying pan", "non-stick pan", "cast iron cookware", "tawa", "dosa pan", "baking tray", "casserole"],
        "Tableware & Storage": ["dinner set", "cutlery", "insulated flask", "water bottle", "container", "glass jar", "spice box", "masala dabba", "kitchen rack", "lunch box", "chopper", "vegetable peeler"],
    },
    "Fashion & Apparel": {
        "Women's Western & Contemporary Wear": ["wrap dress", "shift dress", "slip dress", "bodycon dress", "a-line dress", "jumpsuit", "crop top", "peplum top", "tunic", "t-shirt", "mom jeans", "jeggings", "wide-leg trouser", "skirt", "culottes", "shrug", "co-ord set", "maternity wear"],
        "Women's Ethnic & Festive Wear": ["cotton saree", "silk saree", "georgette saree", "chiffon saree", "bandhani saree", "kanjeevaram saree", "kurti", "anarkali", "chikankari", "kurta palazzo", "sharara set", "lehenga", "salwar suit", "dress material", "dupatta", "ethnic skirt", "gown", "blouse"],
        "Men's Casual & Formal Wear": ["graphic t-shirt", "oversized t-shirt", "henley shirt", "polo shirt", "oxford shirt", "linen shirt", "formal shirt", "slim-fit jeans", "chinos", "cargo pants", "track pants", "joggers", "suit", "blazer", "bomber jacket", "denim jacket", "trench coat", "parka", "hoodie"],
        "Men's Ethnic Wear": ["silk kurta", "asymmetric kurta", "sherwani", "nehru jacket", "dhoti", "mojri"],
        "Kids & Baby Apparel": ["romper", "bodysuit", "booties", "mittens", "frock", "party dress", "kurta set", "dungaree", "school uniform", "kids sweater", "kids hoodie"],
        "Lingerie, Innerwear & Sleepwear": ["padded bra", "t-shirt bra", "bralette", "minimizer bra", "bikini panty", "boy-short panty", "seamless panty", "camisole", "shapewear", "nighty", "night suit", "bathrobe", "vest", "briefs", "trunks"],
        "Indie, Artisanal & Handloom": ["handloom saree", "chanderi saree", "ajrakh print", "block-print dress", "kantha quilt", "kantha jacket", "mangalgiri fabric", "potli bag", "silver jhumka"],
    },
    "Footwear & Accessories": {
        "Footwear": ["running shoes", "walking shoes", "sneakers", "chunky sneakers", "high-top sneakers", "oxford shoes", "brogues", "monk strap", "block heels", "stilettos", "kitten heels", "flat sandals", "ballerinas", "platform sneakers", "crocs", "slippers", "flip-flops", "loafers"],
        "Fashion Jewellery & Watches": ["analog watch", "chronograph watch", "smartwatch", "mangalsutra", "kundan earring", "oxidized silver earring", "bangles", "choker", "finger ring", "nose pin", "anklet", "jewellery set"],
        "Bags, Luggage & Travel": ["trolley bag", "laptop backpack", "canvas backpack", "crossbody bag", "school bag", "duffle bag", "handbag", "wallet", "cardholder", "belt", "travel pouch"],
        "General Accessories": ["sunglasses", "wayfarer", "polarized sunglasses", "silk tie", "cufflinks", "bucket hat", "cap", "scarf"],
    },
    "Beauty, Grooming, Health & Personal Care": {
        "Makeup & Cosmetics": ["foundation", "bb cream", "compact powder", "highlighter", "kajal", "eyeliner", "lipstick", "eyeshadow palette", "makeup brush", "nail polish"],
        "Skincare & Haircare": ["face serum", "sunscreen", "moisturizer", "sheet mask", "hair fall shampoo", "conditioner", "hair oil", "beard oil", "hair serum"],
        "Bath, Body & Fragrances": ["perfume", "edp", "body mist", "deodorant", "shower gel", "body lotion", "loofah", "soap"],
        "Health, Wellness & Pharmacy": ["whey protein", "multivitamin", "bp monitor", "oximeter", "first aid kit", "diaper"],
    },
    "Home Furnishing, Decor & Living": {
        "Bed Linen & Textiles": ["bedsheet", "fitted bedsheet", "comforter", "pillow cover", "memory foam pillow", "blanket", "kantha quilt"],
        "Bath & Window Furnishing": ["bath towel", "hand towel", "face towel", "bath mat", "curtain", "blackout curtain", "sofa cover", "cushion cover", "floor cushion"],
        "Home Decor & Lighting": ["vase", "wall clock", "painting", "wall sticker", "showpiece", "aroma diffuser", "candle", "table lamp", "floor lamp", "artificial flower", "led strip light"],
        "Home Maintenance & Utilities": ["floor wiper", "magic mop", "dustpan", "toilet brush", "mosquito net", "gardening tool", "plant pot", "seeds", "watering can"],
    },
    "Sports, Toys, Books & Automotive": {
        "Sports & Fitness Equipment": ["dumbbell", "resistance band", "exercise bench", "cross trainer", "skipping rope", "yoga mat", "cricket bat", "tennis ball", "leather ball", "badminton racket", "football", "shin guard", "shaker", "gym equipment", "fitness equipment"],
        "Toys, Games & School Supplies": ["soft toy", "remote control car", "puzzle", "board game", "action figure", "doll", "baby walker", "notebook", "fountain pen", "calculator", "desk organizer"],
        "Books & Media": ["exam book", "novel", "textbook", "story book"],
        "Automotive & Industrial": ["helmet", "riding gear", "phone mount", "microfiber cloth", "car care product", "industrial supply"],
        "Grocery & Gourmet Foods": ["atta", "basmati rice", "dal", "pulses", "dry fruit", "honey", "cold-pressed oil", "cereal", "chocolate", "green tea", "health drink", "packaged snack"],
    },
}


def match_category(text):
    """Finds best matching (parent_category, catalogue_name) for given text using keyword search."""
    if not text:
        return None
    text_lower = text.lower()
    best_match = None
    best_score = 0
    for main_cat, subcats in CATEGORY_CATALOG.items():
        for catalogue_name, keywords in subcats.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if catalogue_name.lower() in text_lower:
                score += 3
            if score > best_score:
                best_score = score
                best_match = (main_cat, catalogue_name)
    return best_match if best_score > 0 else None
STATE_FILE = "state.json"

# ================= STATE MANAGEMENT =================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("processed_ids"), list):
                    return data
        except Exception:
            pass
    return {"processed_ids": [], "last_update_id": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving state: {e}")

# ================= LINK & EXTRACTION =================
def extract_all_links(msg):
    text = msg.get("caption") or msg.get("text") or ""
    entities = msg.get("caption_entities") or msg.get("entities") or []
    urls = re.findall(r'https?://[^\s>"]+', text)
    for entity in entities:
        if entity.get("type") == "text_link" and entity.get("url"):
            urls.append(entity["url"])
    clean_urls = []
    for u in urls:
        c = u.rstrip(".,;!)")
        if c not in clean_urls:
            clean_urls.append(c)
    return clean_urls

def unshorten_link(short_url):
    try:
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = session.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        final_url = resp.url
        if any(x in final_url for x in ["bitli.in", "linkredirect", "earnkaro", "myntr.it", "fkrt.cc", "bit.ly"]):
            meta_match = re.search(r'url=(https?://[^\s"\']+)', resp.text, re.IGNORECASE)
            if meta_match:
                resp2 = session.get(meta_match.group(1), headers=headers, allow_redirects=True, timeout=10)
                final_url = resp2.url
        return final_url
    except Exception:
        return short_url

def fetch_product_metadata_with_playwright(url):
    """Uses Playwright real headless browser with advanced timeout, JSON-LD extraction, and generic fallback."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                device_scale_factor=1,
                locale="en-IN",
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                }
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
            """)
            page = context.new_page()
            
            page.goto(url, timeout=40000, wait_until="networkidle")
            time.sleep(2)
            
            final_url = page.url
            html_content = page.content()
            print(f"DEBUG: Final URL = {final_url}")
            print(f"DEBUG: HTML length = {len(html_content)}")
            browser.close()

            title, image_url, price, discount_text = None, None, None, None

            # ===== STEP 1: Try JSON-LD structured data (works across most modern e-commerce sites) =====
            ld_blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_content, re.IGNORECASE | re.DOTALL)
            for block in ld_blocks:
                try:
                    data = json.loads(block.strip())
                    candidates = data if isinstance(data, list) else [data]
                    for item in candidates:
                        if not isinstance(item, dict):
                            continue
                        if "@graph" in item and isinstance(item["@graph"], list):
                            candidates.extend([g for g in item["@graph"] if isinstance(g, dict)])
                        item_type = item.get("@type", "")
                        if isinstance(item_type, list):
                            is_product = "Product" in item_type
                        else:
                            is_product = item_type == "Product"
                        if is_product:
                            if not title and item.get("name"):
                                title = html.unescape(str(item["name"])).strip()
                            if not image_url and item.get("image"):
                                img = item["image"]
                                if isinstance(img, list):
                                    image_url = img[0] if img else None
                                elif isinstance(img, dict):
                                    image_url = img.get("url")
                                else:
                                    image_url = img
                            offers = item.get("offers")
                            if offers:
                                if isinstance(offers, list):
                                    offers = offers[0] if offers else {}
                                if isinstance(offers, dict) and offers.get("price"):
                                    try:
                                        price = float(str(offers["price"]).replace(",", ""))
                                    except:
                                        pass
                except Exception:
                    continue
                if title and price:
                    break

            # ===== STEP 2: og:title / og:image fallback =====
            if not title:
                og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if og_title:
                    title = html.unescape(og_title.group(1)).strip()

            if not image_url:
                og_image = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if og_image:
                    img_candidate = og_image.group(1).strip()
                    if not any(bad in img_candidate.lower() for bad in ["logo", "icon", "default", "placeholder", "sprite"]):
                        image_url = img_candidate

            # ===== STEP 3: Generic bad-title detection (pattern-based, not hardcoded per platform) =====
            BAD_TITLE_PATTERNS = [
                "access denied", "site maintenance", "under maintenance", "robot check",
                "are you a human", "verify you are human", "captcha", "forbidden",
                "error 403", "error 404", "page not found", "just a moment",
                "attention required", "service unavailable", "bot detection",
                "online shopping", "online store", "e-commerce", "welcome to",
                "oops", "something went wrong", "unexpected error", "please try again",
                "temporarily unavailable", "we're sorry", "we are sorry", "session expired",
                "invalid request", "suspicious activity", "blocked", "not found",
                "try again later", "went wrong", "server error", "internal error",
                "cannot process", "unavailable", "denied", "unauthorized"
            ]
            def is_bad_title(t):
                if not t or len(t.strip()) < 5:
                    return True
                tl = t.lower()
                if any(pat in tl for pat in BAD_TITLE_PATTERNS):
                    return True
                # Titles that are JUST a brand/domain name (very short, no product details)
                if len(tl.split()) <= 2 and len(tl) < 20:
                    return True
                if re.fullmatch(r'[A-Za-z0-9\s]{3,20}', t) and any(c.isdigit() for c in t) and t.upper() == t.replace(" ", "").upper():
                    letters_upper = sum(1 for c in t if c.isupper())
                    if letters_upper >= 3:
                        return True
                return False

            if is_bad_title(title):
                h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.IGNORECASE | re.DOTALL)
                if h1_match:
                    clean_h1 = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
                    if clean_h1 and not is_bad_title(clean_h1):
                        title = html.unescape(clean_h1)

            if is_bad_title(title):
                tag_title = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
                if tag_title:
                    tt = html.unescape(tag_title.group(1)).strip()
                    if not is_bad_title(tt):
                        title = tt

            if is_bad_title(title):
                title = "SPECIAL OFFER DEAL"

            # ===== STEP 4: Generic image fallback chain =====
            if not image_url:
                dynamic_img = re.search(r'data-a-dynamic-image=["\'](\{[^\'"]+\})["\']', html_content, re.IGNORECASE)
                if dynamic_img:
                    try:
                        img_data = json.loads(html.unescape(dynamic_img.group(1)))
                        if img_data:
                            image_url = list(img_data.keys())[0]
                    except Exception:
                        pass

            if not image_url:
                old_hires = re.search(r'data-old-hires=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if old_hires and old_hires.group(1).strip():
                    image_url = old_hires.group(1).strip()

            if not image_url:
                landing_img = re.search(r'id=["\']landingImage["\'][^>]*src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if landing_img:
                    image_url = landing_img.group(1).strip()

            if not image_url:
                item_img = re.search(r'itemprop=["\']image["\'][^>]*(?:content|src)=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if item_img:
                    image_url = item_img.group(1).strip()

            if not image_url:
                twitter_img = re.search(r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                if twitter_img:
                    img_candidate = twitter_img.group(1).strip()
                    if not any(bad in img_candidate.lower() for bad in ["logo", "icon", "default", "placeholder"]):
                        image_url = img_candidate

            print(f"DEBUG: image_url resolved = {image_url}")

    
           # ===== STEP 5: Price fallback (Amazon-specific first, then generic regex) =====
            if not price:
                amazon_price = re.search(r'class=["\']a-price-whole["\'][^>]*>([\d,]+)', html_content, re.IGNORECASE)
                if amazon_price:
                    try: price = float(amazon_price.group(1).replace(",", ""))
                    except: pass

            if not price:
                core_price = re.search(r'id=["\']priceblock_(?:ourprice|dealprice|saleprice)["\'][^>]*>[^₹]*₹\s?([\d,]+(?:\.\d+)?)', html_content, re.IGNORECASE)
                if core_price:
                    try: price = float(core_price.group(1).replace(",", ""))
                    except: pass

            if not price:
                price_match = re.search(r'₹\s?([\d,]+(?:\.\d+)?)', html_content)
                if price_match:
                    try: price = float(price_match.group(1).replace(",", ""))
                    except: pass

            # ===== STEP 5b: MRP extraction (for strikethrough display + fallback calculation) =====
            mrp_value = None
            mrp_patterns = [
                r'"mrp"\s*:\s*"?₹?\s?([\d,]+(?:\.\d+)?)"?',
                r'MRP[:\s₹]*([\d,]+(?:\.\d+)?)',
                r'class=["\'][^"\']*(?:strike|line-through|linethrough|mrp|original-?price|was-?price)[^"\']*["\'][^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<[^>]*style=["\'][^"\']*text-decoration:\s*line-through[^"\']*["\'][^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<del[^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
                r'<s[^>]*>\s*₹?\s?([\d,]+(?:\.\d+)?)',
            ]
            for pat in mrp_patterns:
                m = re.search(pat, html_content, re.IGNORECASE)
                if m:
                    try:
                        candidate = float(m.group(1).replace(",", ""))
                        if price and candidate > price:
                            mrp_value = candidate
                            break
                    except:
                        continue

            # ===== STEP 6: Discount — explicit text FIRST, calculate ONLY if not found anywhere =====
            discount_patterns = [
                r'savingsPercentage[\s\S]{0,100}?(\d+)\s*%',
                r'\(\s*(\d+)\s*%\s*off\s*\)',
                r'(\d+)\s*%\s*off',
                r'(\d+)\s*%\s*discount',
                r'save\s*(\d+)\s*%',
                r'-\s?(\d{1,2})\s*%',
            ]
            for pat in discount_patterns:
                m = re.search(pat, html_content, re.IGNORECASE)
                if m:
                    discount_text = f"{m.group(1)}% off"
                    break

            if not discount_text and mrp_value and price and mrp_value > price:
                computed_disc = round((mrp_value - price) / mrp_value * 100)
                if computed_disc > 0:
                    discount_text = f"{computed_disc}% off"
            return {"title": title, "image_url": image_url, "price": price, "discount": discount_text, "mrp": mrp_value, "link": final_url}
    except Exception as e:
        print(f"Playwright detailed error: {e}")
        return None

     
            

def get_canonical_url(expanded_url):
    if not expanded_url: return None
    if "flipkart.com" in expanded_url.lower():
        itm_match = re.search(r'/(?:p|dp)/(itm[a-zA-Z0-9]+)', expanded_url)
        if itm_match: return f"https://www.flipkart.com/p/{itm_match.group(1)}"
    elif "amazon" in expanded_url.lower():
        dp_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', expanded_url, re.I)
        if dp_match: return f"https://www.amazon.in/dp/{dp_match.group(1)}"
    return expanded_url

def build_price_history_link(canonical_url, title):
    if canonical_url and "amazon.in/dp/" in canonical_url:
        asin = canonical_url.rstrip("/").split("/")[-1]
        return f"https://keepa.com/#!product/10-{asin}"
    return DEFAULT_PRICE_HISTORY_LINK

# ================= FORMATTING =================
def get_emoji(text):
    t = text.lower()
    if any(k in t for k in ["phone", "mobile", "iphone", "5g", "samsung"]): return "📱"
    if any(k in t for k in ["shoe", "sneaker", "nike", "puma", "adidas"]): return "👟"
    if any(k in t for k in ["watch", "smartwatch"]): return "⌚"
    if any(k in t for k in ["headphone", "audio", "boat", "earbud"]): return "🎧"
    return "🛍️"

def extract_fallback_title_from_text(text):
    """Extracts a usable title from the original staging message when scraping fails."""
    if not text:
        return None
    text = re.sub(r'https?://\S+', '', text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    noise_patterns = ["buy now", "join for", "join our", "@loot", "price:", "discount"]
    good_lines = [l for l in lines if not any(p in l.lower() for p in noise_patterns)]
    candidate = good_lines[0] if good_lines else (lines[0] if lines else None)
    if candidate:
        candidate = re.sub(r'[^\w\s₹%.,&\-]', '', candidate).strip()
        if len(candidate) > 100:
            candidate = candidate[:100].strip()
        if len(candidate) < 5:
            return None
        return candidate
    return None
def parse_category_deal(text):
    """Detects category/collection-style messages (e.g. 'LOOT: Shakers Starting @ ₹99')
    and extracts (subject, price_phrase). Returns None for normal single-product messages."""
    if not text:
        return None
    clean = re.sub(r'https?://\S+', '', text).strip()
    clean = re.sub(r'^(loot|grab|deal|offer)\s*:\s*', '', clean, flags=re.IGNORECASE).strip()
    m = re.search(
        r'^(.*?)(?:\s*[\|:]\s*|\s+)(starting\s*@?\s*₹\s?[\d,]+(?:\.\d+)?|up\s*to\s*\d+\s*%\s*off|flat\s*\d+\s*%\s*off)',
        clean, re.IGNORECASE
    )
    
    if not m:
        return None
    subject = m.group(1).strip(" |-:").strip()
    phrase = m.group(2).strip()
    phrase = phrase[0].upper() + phrase[1:]
    if len(subject) < 3:
        return None
    return subject, phrase
def format_caption(title, emoji, link, scraped, show_price_line=True):
    header = random.choice(DEAL_HEADERS)
    lines = [f"<b>{header}</b>\n", f"👀 {emoji} <b>{html.escape(title)}</b>\n"]

    if show_price_line:
        if scraped and scraped.get("price"):
            p_str = f"₹{scraped['price']:,.0f}"
            d_str = f" ({scraped['discount']})" if scraped.get("discount") else ""
            lines.append(f"💰 Price: <b>{p_str}</b>{d_str}\n")
        else:
            lines.append("💰 Price: <b>Check Live Platform Price</b>\n")

    lines.extend([f"🛒 <b>BUY NOW:</b> {link}\n", f"📢 <b>JOIN FOR MORE DEALS:</b> {CHANNEL_HANDLE}"])
    return "\n".join(lines)
def post_deal(image_url, caption, ph_link):
    keyboard = json.dumps({"inline_keyboard": [[{"text": "📉 Price History 📉", "url": ph_link}]]})
    if image_url:
        try:
            img_data = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12).content
            payload = {"chat_id": MAIN_CHAT_ID, "caption": caption, "parse_mode": "HTML", "reply_markup": keyboard}
            r = requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendPhoto", data=payload, files={"photo": ("img.jpg", img_data)}, timeout=15)
            if r.ok: return True
        except: pass

    payload = {"chat_id": MAIN_CHAT_ID, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": keyboard}
    requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json=payload, timeout=15)

# ================= WORKFLOW =================
def process_message(msg):
    urls = extract_all_links(msg)
    if not urls: return
        
def process_message(msg):
    urls = extract_all_links(msg)
    if not urls: return

    if len(urls) > 1:
        try:
            requests.post(
                f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/copyMessage",
                json={"chat_id": MAIN_CHAT_ID, "from_chat_id": STAGING_CHAT_ID, "message_id": msg.get("message_id")},
                timeout=15
            )
        except Exception as e:
            print(f"Copy error: {e}")
        return

    original_text = (msg.get("caption") or msg.get("text") or "").strip()
    # ... baaki poora function same rahega
    
    original_text = (msg.get("caption") or msg.get("text") or "").strip()
    aff_link = urls[0]

    scraped = fetch_product_metadata_with_playwright(aff_link)
    final_link = scraped.get("link") if scraped else None
    canonical = get_canonical_url(final_link) if final_link else get_canonical_url(unshorten_link(aff_link))
    category_deal = parse_category_deal(original_text)

    if category_deal:
        subject, price_phrase = category_deal
        scraped_title = scraped.get("title") if scraped else None

        combined_text = f"{subject} {scraped_title or ''} {original_text}"
        cat_match = match_category(combined_text)
        category_label = cat_match[1] if cat_match else None

        title_lines = []
        if category_label:
            title_lines.append(f"Category: {category_label}")
        title_lines.append(subject.upper())
        title_lines.append(price_phrase)
        title = "\n".join(title_lines)

        emoji = get_emoji(subject)
        ph_link = build_price_history_link(canonical, subject)
        caption = format_caption(title, emoji, aff_link, None, show_price_line=False)
        image_url = scraped.get("image_url") if scraped else None
        post_deal(image_url, caption, ph_link)
        return

    title = scraped.get("title") if scraped and scraped.get("title") else None
    if not title or title == "SPECIAL OFFER DEAL":
        fallback_title = extract_fallback_title_from_text(original_text)
        title = fallback_title if fallback_title else "SPECIAL OFFER DEAL"

    title = re.sub(r'(?i)(\||\-|\:)\s*(Buy|Online|Flipkart|Amazon|Myntra|Boat).*$', '', title).strip().upper()
    emoji = get_emoji(title)
    ph_link = build_price_history_link(canonical, title)
    caption = format_caption(title, emoji, aff_link, scraped)
    image_url = scraped.get("image_url") if scraped else None
    post_deal(image_url, caption, ph_link)

def background_bot_loop():
    print("Playwright background bot listener started...")
    while True:
        try:
            state = load_state()
            processed = set(state.get("processed_ids", []))
            last_offset = state.get("last_update_id", 0)

            resp = requests.get(f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/getUpdates", params={"offset": last_offset + 1, "timeout": 15}, timeout=20)
            if resp.ok:
                updates = resp.json().get("result", [])
                for update in updates:
                    last_offset = max(last_offset, update["update_id"])
                    msg = update.get("channel_post") or update.get("message")
                    if not msg: continue

                    if str(msg.get("chat", {}).get("id")) != str(STAGING_CHAT_ID): continue

                    msg_id = msg.get("message_id")
                    if msg_id in processed: continue

                    process_message(msg)
                    processed.add(msg_id)

            state["processed_ids"] = list(processed)[-200:]
            state["last_update_id"] = last_offset
            save_state(state)
        except Exception as e:
            print(f"Loop error: {e}")
        
        time.sleep(3)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    background_bot_loop()
            
