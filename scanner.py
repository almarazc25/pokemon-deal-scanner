import os
import json
import time
import base64
import requests
import re
from datetime import datetime, timezone

# Configuration
WATCHLIST_FILE = 'watchlist.json'
SEEN_FILE = 'seen_listings.json'
DEALS_LOG_FILE = 'deals_log.json'

# Load Secrets from Environment
EBAY_CLIENT_ID = os.getenv('EBAY_CLIENT_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')

EXCLUDE_KEYWORDS = [
    "keychain", "tin", "pin", "replica", "reprint", "custom", "proxy", "case", 
    "display", "stand", "holder", "sleeve", "toploader", "magnet", "sticker", 
    "poster", "plush", "figure", "toy", "mini slab", "novelty", "ornament", 
    "charm", "mystery", "pack", "box break", "digital", "code", "deck", "proxy",
    "reverse holo", "reverse-holo", "rev holo", "non-holo", "non holo", "rh", "no holo"
]

def get_ebay_token():
    print("Authenticating with eBay API...")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Failed to get eBay token: {e}")
        return None

def send_pushover_priority(title, message, url, priority=1):
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "url": url,
        "url_title": "Open on eBay",
        "priority": priority,
        "sound": "cashregister" if priority == 1 else "siren"
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send Pushover notification: {e}")

def log_deal(card_name, grade, price, market, discount_pct, desirability, link):
    deal_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "card": card_name, "grade": grade, "price": price, "market": market,
        "discount": discount_pct, "desirability": desirability, "link": link
    }
    try:
        if os.path.exists(DEALS_LOG_FILE):
            with open(DEALS_LOG_FILE, 'r') as f: deals = json.load(f)
        else: deals = []
        deals.append(deal_entry)
        with open(DEALS_LOG_FILE, 'w') as f: json.dump(deals, f, indent=2)
    except Exception as e: print(f"Failed to log deal: {e}")

def is_bundle_listing(title):
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in ['lot', 'bundle', 'collection', 'set of', 'complete set', 'bulk']):
        return True
    quantity_patterns = [r'\bx\d+\b', r'\b\d+x\b', r'\b\d+\s*cards\b', r'lot\s*of\s*\d+', r'\+\s*\d+']
    return any(re.search(pattern, title_lower) for pattern in quantity_patterns)

def is_legit_psa_slab(title, grade_num):
    title_lower = title.lower()
    negative = ["raw", "ungraded", "candidate", "potential", "?", "ready", "ready for", "not graded", "non-graded", "facsimile"]
    if any(kw in title_lower for kw in negative): return False
    return bool(re.search(rf'psa\s*-?\s*{grade_num}\b', title_lower))

def search_ebay(token, query, max_price, is_auction=False):
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}"}
    buying_option = "AUCTION" if is_auction else "FIXED_PRICE"
    params = {
        "q": query, "category_ids": "183454",
        "filter": f"buyingOptions:{{{buying_option}}},price:[50..{max_price}],priceCurrency:USD",
        "limit": 50, "sort": "newlyListed" if not is_auction else "endingSoonest", "fieldgroups": "EXTENDED"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200: return response.json().get('itemSummaries', [])
        return []
    except Exception as e:
        print(f"Request failed for query '{query}': {e}")
        return []

def format_time_left(end_date_str):
    try:
        end_date = datetime.strptime(end_date_str.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S.%f%z")
        now = datetime.now(timezone.utc)
        time_left = end_date - now
        if time_left.total_seconds() <= 0: return None, 0
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m", time_left.total_seconds()
    except Exception: return "Unknown", 999999

def find_matching_card(title, card_batch):
    """
    Precisely match an eBay listing to a card in the watchlist batch.
    Requires Name Match, Number Match, and Set Verification.
    """
    title_lower = title.lower()
    
    # 1. Clean the title: remove PSA grade numbers
    cleaned_title = re.sub(r'psa\s*-?\s*\d+', 'psa ', title_lower)
    cleaned_title = re.sub(r'grade\s*\d+', 'grade ', cleaned_title)
    cleaned_title = re.sub(r'bgs\s*-?\s*\d+', 'bgs ', cleaned_title)
    cleaned_title = re.sub(r'cgc\s*-?\s*\d+', 'cgc ', cleaned_title)

    for card in card_batch:
        card_name_lower = card['name'].lower()
        set_name_lower = card.get('set', '').lower()
        
        # FACTOR 1: Set Validation (Crucial for high-end vintage)
        # If the set is Neo Revelation, the title should ideally mention 'Neo' or 'Revelation'
        # We use a broad check to be safe but effective.
        set_keywords = set_name_lower.split()
        if not any(kw in title_lower for kw in set_keywords if len(kw) > 3):
            # If set is 'Base Set', check for 'Base'
            if "base" in set_name_lower and "base" not in title_lower:
                continue
            # Special case for Neo sets
            if "neo" in set_name_lower and "neo" not in title_lower:
                continue

        # FACTOR 2: Name Validation
        # Extract keywords from card name (excluding common words)
        name_parts = [p for p in card_name_lower.split() if p not in ["holo", "art", "rare", "sir", "ir"]]
        if not all(part in title_lower for p in name_parts for part in [p] if len(p) > 2):
            continue
            
        # EXTRA STRICT: "Shining" or "Crystal" MUST be in the title if they are in the name
        if "shining" in card_name_lower and "shining" not in title_lower:
            continue
        if "crystal" in card_name_lower and "crystal" not in title_lower:
            continue

        # FACTOR 3: Number Validation (Strict)
        card_num = str(card.get('cardNumber', '')).lower()
        if not card_num:
            continue
            
        pattern = r'(?<![a-zA-Z0-9])' + re.escape(card_num) + r'(?![a-zA-Z0-9])'
        if re.search(pattern, cleaned_title):
            
            # FACTOR 4: 1st Edition / Shadowless Check
            is_1st_ed_watchlist = "1st edition" in card_name_lower
            is_1st_ed_listing = any(x in title_lower for x in ["1st edition", "1st ed", "first edition"])
            
            if is_1st_ed_watchlist and not is_1st_ed_listing:
                continue
            # If listing is 1st Edition but watchlist entry isn't, also skip (to avoid overpaying for unlimited targets)
            if not is_1st_ed_watchlist and is_1st_ed_listing:
                continue
                
            is_shadowless_watchlist = "shadowless" in card_name_lower
            is_shadowless_listing = "shadowless" in title_lower
            
            if is_shadowless_watchlist and not is_shadowless_listing:
                continue

            return card
            
    return None

def calculate_strategy(set_name, market_price):
    modern_sets = ["151", "Prismatic Evolutions", "Surging Sparks", "Stellar Crown", "Paldean Fates", "Twilight Masquerade"]
    mid_sets = ["Evolving Skies", "Lost Origin", "Silver Tempest", "Brilliant Stars", "Fusion Strike", "Chilling Reign"]
    
    if any(s in set_name for s in modern_sets):
        return "Quick Flip (High Demand) 🔥"
    elif any(s in set_name for s in mid_sets):
        return "Long-term Hold (Investment Grade) 📈"
    else:
        return "Legacy Hold (Ultra Rare Vintage) 🏛️"

def generate_misspellings(query):
    """Generate common misspellings to catch underpriced listings others miss"""
    misspelling_map = {
        'umbreon': ['umbreon', 'umbreoon', 'umbrion'],
        'espeon': ['espion', 'espon'],
        'glaceon': ['glacoen', 'glacion'],
        'leafeon': ['leafon', 'leafion'],
        'sylveon': ['sylvion', 'sylvon'],
        'vaporeon': ['vapereon', 'vaporion'],
        'flareon': ['flarion', 'flaroen'],
        'jolteon': ['joltion', 'joltoen'],
        'charizard': ['charizad', 'charizrd', 'charzard'],
        'pikachu': ['pikchu', 'pikacu'],
        'rayquaza': ['rayquza', 'raquaza'],
        'mewtwo': ['mewto', 'mewtoo'],
        'giratina': ['giritina', 'garatina'],
        'dragonite': ['dragonight', 'dragonit'],
        'gengar': ['genger', 'gangar'],
        'lucario': ['lucario', 'lucarion'],
        'gardevoir': ['gardevior', 'gardvoir']
    }
    
    query_lower = query.lower()
    for correct, mistakes in misspelling_map.items():
        if correct in query_lower:
            return query.lower().replace(correct, mistakes[0])
    return None

def main():
    try:
        with open(WATCHLIST_FILE, 'r') as f: watchlist = json.load(f)['watchlist']
    except Exception as e:
        print(f"Error loading watchlist: {e}"); return

    # GROUPING BY SET FOR BATCHING
    batches = {}
    for card in watchlist:
        set_name = card.get('set', 'Unknown')
        if set_name not in batches: batches[set_name] = []
        batches[set_name].append(card)

    batch_queries = []
    for set_name, cards in batches.items():
        for i in range(0, len(cards), 5):
            chunk = cards[i:i+5]
            nums = ",".join([str(c['cardNumber']) for c in chunk])
            query = f"({nums}) \"{set_name}\" PSA"
            if len(query) > 100:
                for c in chunk: batch_queries.append(([c], f"{c['cardNumber']} \"{set_name}\" PSA"))
            else: batch_queries.append((chunk, query))

    # ROTATION: 4 groups (every 15 min)
    # 500 cards / 5 per batch = 100 batches. 
    # 100 / 4 groups = 25 batches per scan.
    # 25 batches * 2 calls = 50 calls per scan.
    # 50 calls * 96 scans = 4,800 calls (96% DAILY USAGE - PERFECT MAX)
    current_minute = datetime.now(timezone.utc).minute
    group_idx = current_minute // 15
    chunk_size = 25 
    start = group_idx * chunk_size
    end = min(len(batch_queries), (group_idx + 1) * chunk_size)
    active_queries = batch_queries[start:end]

    print(f"🎯 Scanning GROUP {group_idx+1} ({len(active_queries)} Batches / ~{len(active_queries)*5} Cards)")
    print(f"📊 Projected Daily API Usage: {len(active_queries) * 2 * 96} calls ({(len(active_queries) * 2 * 96 / 5000)*100:.1f}%)")

    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f: seen_ids = set(json.load(f))
        except: seen_ids = set()
    else: seen_ids = set()

    token = get_ebay_token()
    if not token: return

    new_deals = False
    for card_chunk, query in active_queries:
        # Determine max price for this batch query
        targets = []
        for c in card_chunk:
            targets.extend([c.get('buyTarget10', 0), c.get('buyTarget9', 0)])
        max_price = max(targets) if targets else 50000
        
        print(f"Batch Search: {query} (Max: ${max_price})")
        
        search_runs = [("BIN", search_ebay(token, query, max_price, False)), 
                       ("AUCTION", search_ebay(token, query, max_price, True))]
        
        # BONUS: Misspelling Search for the first card in the chunk (to keep API usage balanced)
        if card_chunk:
            primary_card = card_chunk[0]
            misspelled_name = generate_misspellings(primary_card['name'].split()[0])
            if misspelled_name:
                m_query = f"{misspelled_name} {primary_card['cardNumber']} PSA"
                print(f"  + Bonus Misspelling: {m_query}")
                search_runs.append(("BIN [MISSPELLING]", search_ebay(token, m_query, max_price, False)))

        for l_type, items in search_runs:
            for item in items:
                item_id = item.get('itemId')
                if item_id in seen_ids: continue
                
                title = item.get('title', '')
                card = find_matching_card(title, card_chunk)
                if not card: continue

                price = float(item.get('price', {}).get('value', 0))
                watch_count = item.get('watchCount', 0)
                
                # Reputation Filter (Safety Shield): Standard for all investment-grade slabs
                if watch_count > 5 or price < 50 or is_bundle_listing(title): continue
                
                seller_feedback = item.get('seller',{}).get('feedbackPercentage', 0)
                seller_score = item.get('seller',{}).get('feedbackScore', 0)
                
                # Auto-skip low-rep sellers to avoid scams
                if float(seller_feedback) < 98.0 or int(seller_score) < 50:
                    continue

                if any(kw in title.lower() for kw in EXCLUDE_KEYWORDS): continue

                shipping = float(item.get('shippingOptions', [{}])[0].get('shippingCost', {}).get('value', 0)) if item.get('shippingOptions') else 0
                total_cost = price + shipping
                
                grade_m = re.search(r'psa\s*-?\s*(10|9|8)\b', title.lower())
                if not grade_m or not is_legit_psa_slab(title, grade_m.group(1)): continue
                
                grade = grade_m.group(1)
                target = card.get(f'buyTarget{grade}', card.get('buyTarget10', 0))
                market = card.get(f'psa{grade}Market', card.get('psa10Market', 0))

                if total_cost <= target:
                    is_snipe = False
                    time_str = ""
                    if l_type == "AUCTION":
                        time_str, seconds_left = format_time_left(item.get('itemEndDate', ''))
                        if seconds_left <= 300 and seconds_left > 0:
                            is_snipe = True
                            time_str = f"\n🔥 SNIPE NOW - {int(seconds_left/60)}m left!"
                        elif seconds_left <= 1800:
                            time_str = f"\n⏳ Ends in: {time_str}"
                        else: continue

                    discount = int(((market - total_cost) / market) * 100) if market > 0 else 0
                    
                    # Profit Margin Calculator (13% eBay fee + $5 estimated shipping)
                    estimated_fees = (market * 0.13) + 5
                    net_profit = market - total_cost - estimated_fees
                    profit_pct = (net_profit / total_cost) * 100 if total_cost > 0 else 0
                    
                    # Likelihood Rating
                    if discount >= 25: likelihood = "LOW (RARE STEAL) 💎"
                    elif discount >= 18: likelihood = "MEDIUM ⚖️"
                    else: likelihood = "HIGH (DAILY DEAL) ✅"
                    
                    # Score (Integrity preserved)
                    score = min(10, (3 if grade=="10" else 2) + (3 if discount>=25 else 2 if discount>=15 else 1))
                    
                    strategy = calculate_strategy(card.get('set', 'Unknown'), market)
                    notif_title = f"{'🔥 URGENT SNIPE' if is_snipe else '🚨 DEAL'}: {card['name']}"
                    
                    best_offer_line = ""
                    if 'BEST_OFFER' in item.get('buyingOptions', []):
                        optimal = price * 0.87
                        best_offer_line = f"\n💰 OPTIMAL OFFER: ${optimal:.0f}"

                    msg = (f"Grade: PSA {grade} | Price: ${total_cost:.2f}\n"
                           f"Market: ${market} ({discount}% OFF)\n"
                           f"Likelihood: {likelihood}\n"
                           f"💵 Est. Net Profit: ${net_profit:.2f} ({profit_pct:.1f}%)\n"
                           f"📊 Strategy: {strategy}{time_str}{best_offer_line}\n"
                           f"Score: {score}/10 {'⭐'*score}\n"
                           f"Seller: {item.get('seller',{}).get('username')} ({item.get('seller',{}).get('feedbackPercentage')}%)")
                    
                    send_pushover_priority(notif_title, msg, item.get('itemWebUrl'), 2 if is_snipe else 1)
                    seen_ids.add(item_id)
                    new_deals = True
                    log_deal(card['name'], f"PSA {grade}", total_cost, market, discount, score, item.get('itemWebUrl'))
        time.sleep(1)

    if new_deals:
        with open(SEEN_FILE, 'w') as f: json.dump(list(seen_ids), f, indent=2)
    print("Scan complete.")

if __name__ == "__main__":
    main()
