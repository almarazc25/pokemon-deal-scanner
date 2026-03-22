import os
import json
import requests
from datetime import datetime, timezone, timedelta

# Configuration
DEALS_LOG_FILE = 'deals_log.json'
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')

def send_pushover(title, message):
    """Send notification to phone via Pushover"""
    data = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "priority": 0,
        "sound": "incoming"
    }
    try:
        requests.post("https://api.pushover.net/1/messages.json", data=data)
        print(f"Weekly summary sent!")
    except Exception as e:
        print(f"Failed to send summary: {e}")

def main():
    """Generate and send weekly deal summary"""
    
    # Check if deals log exists
    if not os.path.exists(DEALS_LOG_FILE):
        print("No deals log found - no deals this week!")
        send_pushover(
            "📊 Weekly Pokemon Scanner Report",
            "🔍 No deals found this week\n\n"
            "💡 Consider:\n"
            "• Adjusting buy targets if too aggressive\n"
            "• Market might be hot right now\n"
            "• Keep monitoring - deals come in waves!"
        )
        return
    
    # Load deals
    with open(DEALS_LOG_FILE, 'r') as f:
        all_deals = json.load(f)
    
    if not all_deals:
        print("No deals logged this week!")
        send_pushover(
            "📊 Weekly Pokemon Scanner Report",
            "🔍 No deals found this week\n\n"
            "💡 Consider:\n"
            "• Adjusting buy targets if too aggressive\n"
            "• Market might be hot right now\n"
            "• Keep monitoring - deals come in waves!"
        )
        return
    
    # Filter deals from the last 7 days
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    week_deals = [
        deal for deal in all_deals
        if datetime.fromisoformat(deal['timestamp']) >= cutoff_date
    ]
    
    if not week_deals:
        print("No deals in the last 7 days")
        send_pushover(
            "📊 Weekly Pokemon Scanner Report",
            "🔍 No deals in the last 7 days\n\n"
            "Scanner is running, just no deals below your targets.\n"
            "Keep monitoring!"
        )
        return
    
    # Calculate statistics
    total_deals = len(week_deals)
    avg_discount = sum(d['discount'] for d in week_deals) / total_deals
    avg_desirability = sum(d['desirability'] for d in week_deals) / total_deals
    
    # Find best deal
    best_deal = max(week_deals, key=lambda x: x['discount'])
    
    # Count deals by grade
    grade_counts = {}
    for deal in week_deals:
        grade = deal['grade']
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
    
    # Find most active cards
    card_counts = {}
    for deal in week_deals:
        card = deal['card']
        card_counts[card] = card_counts.get(card, 0) + 1
    
    top_cards = sorted(card_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Build summary message
    msg = (
        f"🎯 DEALS FOUND: {total_deals}\n"
        f"📉 AVG DISCOUNT: {avg_discount:.1f}%\n"
        f"⭐ AVG DESIRABILITY: {avg_desirability:.1f}/10\n\n"
        f"🏆 BEST DEAL:\n"
        f"{best_deal['card']} {best_deal['grade']}\n"
        f"${best_deal['price']:.2f} ({best_deal['discount']}% OFF)\n\n"
        f"📊 GRADE BREAKDOWN:\n"
    )
    
    for grade in ['PSA 10', 'PSA 9', 'PSA 8']:
        count = grade_counts.get(grade, 0)
        if count > 0:
            msg += f"  {grade}: {count} deals\n"
    
    if top_cards:
        msg += f"\n🔥 HOTTEST CARDS:\n"
        for card, count in top_cards:
            short_name = card.split('(')[0].strip()[:30]
            msg += f"  {short_name}: {count}x\n"
    
    msg += f"\n✅ Scanner running 24/7\n92 cards × 3 grades monitored"
    
    # Send notification
    send_pushover("📊 Weekly Pokemon Scanner Report", msg)
    
    # Clean up old deals (keep last 30 days)
    cleanup_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_deals = [
        deal for deal in all_deals
        if datetime.fromisoformat(deal['timestamp']) >= cleanup_cutoff
    ]
    
    with open(DEALS_LOG_FILE, 'w') as f:
        json.dump(recent_deals, f, indent=2)
    
    print(f"Weekly summary complete! {total_deals} deals this week.")

if __name__ == "__main__":
    main()
