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
        "sort": "newlyListed" if not is_auction else "endingSoonest"
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

    for card in watchlist:
        # The highest target is always PSA 10. Use this for the API filter to capture all grades.
        max_api_price = max(card['buyTarget10'], card['buyTarget9'], card['buyTarget8'])
        query = card['searchQuery']
        
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
                
                # 1. Hard $50 minimum filter
                if price < 50:
                    continue
                    
                # 2. Keyword exclusion filter
                if any(kw in title for kw in EXCLUDE_KEYWORDS):
                    continue
                
                # 3. STRICT TITLE MATCHING (Fixes the Charizard/Glaceon keyword stuffing issue)
                # This ensures the first two words of your search query (e.g., "Charizard" and "VSTAR") 
                # are ACTUALLY in the title, ignoring eBay's fuzzy search results.
                query_words = query.lower().split()
                if len(query_words) >= 2:
                    if not (query_words[0] in title and query_words[1] in title):
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
                
                # 6. Check if it's actually a deal
                if price <= target:
                    # For auctions, check time remaining
                    time_str = ""
                    if listing_type == "AUCTION":
                        end_date = item.get('itemEndDate', '')
                        time_str, seconds_left = format_time_left(end_date)
                        
                        # Only notify for auctions ending in less than 2 hours (7200 seconds)
                        if seconds_left > 7200 or seconds_left <= 0:
                            continue
                        time_str = f"\n⏳ Ends in: {time_str}"

                    # Calculate % of market value
                    pct_market = int((price / market) * 100)
                    savings = target - price
                    
                    seller = item.get('seller', {}).get('username', 'Unknown')
                    feedback = item.get('seller', {}).get('feedbackPercentage', 'N/A')
                    condition = item.get('condition', 'Unknown') # Display only, no filtering
                    link = item.get('itemWebUrl')
                    
                    # Format Notification
                    notif_title = f"🚨 {listing_type}: {card['name']}"
                    msg = (
                        f"Grade: {grade_label}\n"
                        f"Price: ${price:.2f} ({pct_market}% of market)\n"
                        f"Target: ${target} | Market: ${market}\n"
                        f"Savings: ${savings:.2f} below your max{time_str}\n"
                        f"Seller: {seller} ({feedback}%)\n"
                        f"Condition: {condition}"
                    )
                    
                    send_pushover(notif_title, msg, link)
                    seen_ids.add(item_id)
                    new_deals_found = True
            
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
