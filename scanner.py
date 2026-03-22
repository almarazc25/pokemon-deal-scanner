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
DEALS_LOG_FILE = 'deals_log.json'  # Track deals for weekly summary

# Load Secrets from Environment
EBAY_CLIENT_ID = os.getenv('EBAY_CLIENT_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')

# Keywords to filter out novelty items, cases, and non-cards
EXCLUDE_KEYWORDS =[
    "keychain", "key chain", "tin", "pin", "replica", "reprint", "custom", "proxy", 
    "lot of", "lot ", "bundle", "case", "display", "stand", "holder", "sleeve", 
    "toploader", "magnet", "sticker", "poster", "plush", "figure", "toy", 
    "mini slab", "mini ", "slabby", "novelty", "ornament", "charm", 
    "graded card case", "slab case", "card stand", "psa slab", "mystery", "pack", "box break"
]

def get_ebay_token():
    """Get OAuth Application Token from eBay"""
    print("Authenticating with eBay API...")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Failed to get eBay token: {e}")
        return None

def send_pushover(title, message, url):
    """Send notification to phone via Pushover"""
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "url": url,
        "url_title": "Open on eBay",
        "priority": 1,
        "sound": "cashregister"
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send Pushover notification: {e}")

def log_deal(card_name, grade, price, market, discount_pct, desirability, link):
    """Log deal to JSON file for weekly summary tracking"""
    deal_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "card": card_name,
        "grade": grade,
        "price": price,
        "market": market,
        "discount": discount_pct,
        "desirability": desirability,
        "link": link
    }
    
    try:
        if os.path.exists(DEALS_LOG_FILE):
            with open(DEALS_LOG_FILE, 'r') as f:
                deals = json.load(f)
        else:
            deals = []
        
        deals.append(deal_entry)
        
        with open(DEALS_LOG_FILE, 'w') as f:
            json.dump(deals, f, indent=2)
    except Exception as e:
        print(f"Failed to log deal: {e}")

def search_ebay(token, query, max_price, is_auction=False):
    """Search eBay Browse API (Combined query for PSA 8/9/10)"""
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Filter: Category 183454 (CCG Cards), Price $50 to max_price
    buying_option = "AUCTION" if is_auction else "FIXED_PRICE"
    
    params = {
        "q": query,
        "category_ids": "183454",
        "filter": f"buyingOptions:{{{buying_option}}},price:[50..{max_price}],priceCurrency:USD",
        "limit": 15,
        "sort": "newlyListed" if not is_auction else "endingSoonest",
        "fieldgroups": "EXTENDED"  # Get shipping costs and best offer info
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get('itemSummaries',[])
        else:
            print(f"API Error ({response.status_code}) for query '{query}'")
            return[]
    except Exception as e:
        print(f"Request failed for query '{query}': {e}")
        return[]

def format_time_left(end_date_str):
    """Calculate time left for auctions"""
    try:
        # eBay returns ISO 8601 e.g., 2026-03-21T22:45:00.000Z
        end_date = datetime.strptime(end_date_str.replace('Z', '+0000'), "%Y-%m-%dT%H:%M:%S.%f%z")
        now = datetime.now(timezone.utc)
        time_left = end_date - now
        
        if time_left.total_seconds() <= 0:
            return None, 0
            
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m", time_left.total_seconds()
    except Exception:
        return "Unknown", 999999

def main():
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)['watchlist']
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return
    
    # ROTATING GROUP LOGIC - 4 Groups rotating every 15 min
    # This allows monitoring 92 cards while staying under API limits
    # Group A: :00 | Group B: :15 | Group C: :30 | Group D: :45
    current_minute = datetime.now(timezone.utc).minute
    total_cards = len(watchlist)
    cards_per_group = total_cards // 4
    
    # Determine which group based on minute
    if current_minute <= 14:
        group_index = 0
        group_name = "A 🔵"
    elif current_minute <= 29:
        group_index = 1
        group_name = "B 🟢"
    elif current_minute <= 44:
        group_index = 2
        group_name = "C 🟡"
    else:
        group_index = 3
        group_name = "D 🟣"
    
    # Calculate start and end indices for this group
    start_idx = group_index * cards_per_group
    if group_index == 3:  # Last group gets any remainder cards
        end_idx = total_cards
    else:
        end_idx = (group_index + 1) * cards_per_group
    
    active_watchlist = watchlist[start_idx:end_idx]
    print(f"🎯 Scanning GROUP {group_name} ({len(active_watchlist)} cards) - Cards {start_idx+1}-{end_idx}")
    
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                seen_ids = set(json.load(f))
        except:
            seen_ids = set()
    else:
        seen_ids = set()

    token = get_ebay_token()
    if not token:
        return

    new_deals_found = False

    for card in active_watchlist:
        # The highest target is always PSA 10. Use this for the API filter to capture all grades.
        max_api_price = max(card['buyTarget10'], card['buyTarget9'], card['buyTarget8'])
        query = card['searchQuery']
        card_number = str(card.get('cardNumber', '')).lower()
        
        print(f"Scanning: {card['name']} (Max API Price: ${max_api_price})")
        
        # We do exactly TWO API calls per card to stay under rate limits
        search_types =[
            ("BUY IT NOW", search_ebay(token, query, max_api_price, is_auction=False)),
            ("AUCTION", search_ebay(token, query, max_api_price, is_auction=True))
        ]
        
        for listing_type, results in search_types:
            for item in results:
                item_id = item.get('itemId')
                if item_id in seen_ids:
                    continue
                
                title = item.get('title', '').lower()
                price = float(item.get('price', {}).get('value', 0))
                
                # FEATURE 1: SHIPPING COST CONSIDERATION
                shipping_cost = 0
                shipping_info = item.get('shippingOptions', [])
                if shipping_info and len(shipping_info) > 0:
                    shipping_cost = float(shipping_info[0].get('shippingCost', {}).get('value', 0))
                
                total_price = price + shipping_cost
                
                # FEATURE 2: BEST OFFER DETECTION
                buying_options = item.get('buyingOptions', [])
                has_best_offer = 'BEST_OFFER' in buying_options
                best_offer_emoji = " 💰" if has_best_offer else ""
                
                # 1. Hard $50 minimum filter (on base price, not including shipping)
                if price < 50:
                    continue
                    
                # 2. Keyword exclusion filter
                if any(kw in title for kw in EXCLUDE_KEYWORDS):
                    continue
                
                # 3. CARD NUMBER VERIFICATION (CRITICAL FIX)
                # Ensures the card number (e.g., "189" or "GG70") is in the title.
                # The regex ensures "18" doesn't falsely match "189".
                if card_number:
                    pattern = r'(?<![a-zA-Z0-9])' + re.escape(card_number) + r'(?![a-zA-Z0-9])'
                    if not re.search(pattern, title):
                        continue

                # 4. Detect Grade from Title
                grade_match = re.search(r'psa\s*-?\s*(10|9|8)\b', title)
                if not grade_match:
                    continue # Skip if we can't confirm it's a PSA 8, 9, or 10
                    
                grade_num = grade_match.group(1)
                grade_label = f"PSA {grade_num}"
                
                # 5. Match to correct targets
                if grade_num == "10":
                    target = card['buyTarget10']
                    market = card['psa10Market']
                elif grade_num == "9":
                    target = card['buyTarget9']
                    market = card['psa9Market']
                else:
                    target = card['buyTarget8']
                    market = card['psa8Market']
                
                # 6. Check if it's actually a deal (using TOTAL price including shipping)
                if total_price <= target:
                    # For auctions, check time remaining
                    time_str = ""
                    if listing_type == "AUCTION":
                        end_date = item.get('itemEndDate', '')
                        time_str, seconds_left = format_time_left(end_date)
                        
                        # Only notify for auctions ending in less than 30 minutes (1800 seconds)
                        if seconds_left > 1800 or seconds_left <= 0:
                            continue
                        time_str = f"\n⏳ Ends in: {time_str}"

                    # Calculate % of market value and discount
                    pct_market = int((total_price / market) * 100) if market > 0 else 0
                    discount_pct = int(((market - total_price) / market) * 100) if market > 0 else 0
                    savings = target - total_price
                    
                    # DESIRABILITY SCORE CALCULATION (1-10)
                    desirability = 0
                    
                    # Grade bonus: PSA 10 = +3, PSA 9 = +2, PSA 8 = +1
                    if grade_num == "10":
                        desirability += 3
                        grade_emoji = "🏆"
                    elif grade_num == "9":
                        desirability += 2
                        grade_emoji = "✨"
                    else:
                        desirability += 1
                        grade_emoji = "⚠️"
                    
                    # Discount quality: 25%+ = +3, 20-25% = +2, 15-20% = +1, 10-15% = +1
                    if discount_pct >= 25:
                        desirability += 3
                    elif discount_pct >= 20:
                        desirability += 2
                    elif discount_pct >= 10:
                        desirability += 1
                    
                    # Iconic Pokemon bonus: Umbreon, Charizard, Pikachu, Rayquaza, Lugia = +2
                    iconic_names = ['umbreon', 'charizard', 'pikachu', 'rayquaza', 'lugia', 'mewtwo', 'giratina']
                    if any(name in card['name'].lower() for name in iconic_names):
                        desirability += 2
                    
                    # Out of print bonus: Evolving Skies, Lost Origin, Silver Tempest = +1
                    oop_sets = ['evolving skies', 'lost origin', 'silver tempest', 'brilliant stars']
                    if any(set_name in card['name'].lower() for set_name in oop_sets):
                        desirability += 1
                    
                    # Premium card types: Alt Art, SIR, VMAX = +1
                    if any(term in card['name'].lower() for term in ['alt art', 'sir', 'vmax']):
                        desirability += 1
                    
                    # Cap at 10
                    desirability = min(desirability, 10)
                    
                    # CONFIDENCE RATING
                    if desirability >= 8 and discount_pct >= 15:
                        confidence = "HIGH 🔥"
                    elif desirability >= 5 and discount_pct >= 10:
                        confidence = "MEDIUM 👍"
                    else:
                        confidence = "LOW 💡"
                    
                    # HOLD STRATEGY
                    if discount_pct >= 20 and 'evolving skies' in card['name'].lower() or 'lost origin' in card['name'].lower():
                        strategy = "Long-term hold 📈 (Dipped card)"
                    elif 'prismatic' in card['name'].lower() or 'surging sparks' in card['name'].lower():
                        strategy = "Quick flip 💰 (Hot card)"
                    else:
                        strategy = "Medium hold ⏳"
                    
                    # Star rating visual
                    stars = "⭐" * desirability
                    
                    seller = item.get('seller', {}).get('username', 'Unknown')
                    feedback = item.get('seller', {}).get('feedbackPercentage', 'N/A')
                    condition = item.get('condition', 'Unknown')
                    link = item.get('itemWebUrl')
                    
                    # Build shipping line
                    if shipping_cost > 0:
                        shipping_line = f"\nShipping: ${shipping_cost:.2f}"
                    else:
                        shipping_line = "\nShipping: FREE ✅"
                    
                    # Build best offer line
                    best_offer_line = "\n🤝 ACCEPTS OFFERS - Negotiate lower!" if has_best_offer else ""
                    
                    # Enhanced Notification
                    notif_title = f"🚨 {listing_type}: {card['name']}{best_offer_emoji}"
                    msg = (
                        f"Grade: {grade_label} {grade_emoji}\n"
                        f"Price: ${price:.2f}{shipping_line}\n"
                        f"TOTAL: ${total_price:.2f} ({pct_market}% of market, {discount_pct}% OFF)\n"
                        f"Target: ${target} | Market: ${market}\n"
                        f"Savings: ${savings:.2f} below your max{time_str}{best_offer_line}\n\n"
                        f"⭐ DESIRABILITY: {desirability}/10 {stars}\n"
                        f"🎯 CONFIDENCE: {confidence}\n"
                        f"📊 STRATEGY: {strategy}\n\n"
                        f"Seller: {seller} ({feedback}%)\n"
                        f"Condition: {condition}"
                    )
                    
                    send_pushover(notif_title, msg, link)
                    seen_ids.add(item_id)
                    new_deals_found = True
                    
                    # FEATURE 3: LOG DEAL FOR WEEKLY SUMMARY
                    log_deal(card['name'], grade_label, total_price, market, discount_pct, desirability, link)
            
            # Sleep 1 second between API calls to respect rate limits
            time.sleep(1)

    if new_deals_found:
        with open(SEEN_FILE, 'w') as f:
            json.dump(list(seen_ids), f, indent=2)
        print("Scan complete. New deals found and saved.")
    else:
        print("Scan complete. No new deals found.")

if __name__ == "__main__":
    main()
