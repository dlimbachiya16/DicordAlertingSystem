#!/usr/bin/env python3
"""
IPO Calendar Alert Script
Monitors upcoming and recent IPOs and sends alerts to Discord
"""

import os
import json
import requests
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_IPO_CALENDAR')
HISTORY_FILE = 'data/ipo_calendar_history.json'


def load_history():
    """Load IPO history"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                else:
                    return {}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Could not parse history file, starting fresh: {e}")
            return {}
    return {}


def save_history(history):
    """Save IPO history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_ipo_calendar(from_date, to_date):
    """Fetch IPO calendar from Finnhub"""
    url = 'https://finnhub.io/api/v1/calendar/ipo'
    params = {
        'from': from_date,
        'to': to_date,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching IPO calendar: {e}")
        return None


def create_ipo_id(ipo):
    """Create unique ID for IPO"""
    return f"{ipo.get('symbol')}_{ipo.get('date')}"


def format_discord_embed(ipo, is_upcoming=False):
    """Format IPO data as Discord embed"""
    symbol = ipo.get('symbol', 'N/A')
    name = ipo.get('name', 'Unknown Company')
    date = ipo.get('date', 'N/A')
    exchange = ipo.get('exchange', 'N/A')
    price_low = ipo.get('priceLow', 0)
    price_high = ipo.get('priceHigh', 0)
    shares = ipo.get('numberOfShares', 0)
    total_shares = ipo.get('totalSharesValue', 0)
    status = ipo.get('status', 'N/A')
    
    # Determine color and title based on status
    if is_upcoming:
        color = 3447003  # Blue
        title_prefix = "📅 Upcoming IPO"
    else:
        color = 3066993  # Green
        title_prefix = "🆕 Recent IPO"
    
    # Format values
    price_range = f"${price_low:.2f} - ${price_high:.2f}" if price_low and price_high else "N/A"
    shares_formatted = f"{shares:,}" if shares else "N/A"
    total_value = f"${total_shares:,.0f}" if total_shares else "N/A"
    
    # Parse date for better formatting
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        date_formatted = date_obj.strftime('%B %d, %Y')
    except:
        date_formatted = date
    
    embed = {
        "title": f"{title_prefix}: {symbol}",
        "description": f"**{name}**",
        "color": color,
        "fields": [
            {
                "name": "Date",
                "value": date_formatted,
                "inline": True
            },
            {
                "name": "Exchange",
                "value": exchange,
                "inline": True
            },
            {
                "name": "Status",
                "value": status,
                "inline": True
            },
            {
                "name": "Price Range",
                "value": price_range,
                "inline": True
            },
            {
                "name": "Shares Offered",
                "value": shares_formatted,
                "inline": True
            },
            {
                "name": "Total Value",
                "value": total_value,
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub IPO Calendar"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_discord_alert(embeds):
    """Send alert to Discord webhook"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured")
        return False
    
    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {
            "embeds": batch
        }
        
        try:
            response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Sent {len(batch)} alerts to Discord")
        except Exception as e:
            print(f"Error sending Discord alert: {e}")
            return False
    
    return True


def main():
    """Main execution function"""
    if not FINNHUB_API_KEY:
        print("Error: FINNHUB_API_KEY not set")
        return
    
    # Load history
    history = load_history()
    
    # Calculate date ranges
    today = datetime.now()
    
    # Check recent IPOs (last 14 days)
    recent_from = (today - timedelta(days=14)).strftime('%Y-%m-%d')
    recent_to = today.strftime('%Y-%m-%d')
    
    # Check upcoming IPOs (next 60 days)
    upcoming_from = today.strftime('%Y-%m-%d')
    upcoming_to = (today + timedelta(days=60)).strftime('%Y-%m-%d')
    
    new_ipos = []
    
    print(f"Checking recent IPOs from {recent_from} to {recent_to}")
    recent_data = get_ipo_calendar(recent_from, recent_to)
    
    if recent_data and 'ipoCalendar' in recent_data:
        for ipo in recent_data['ipoCalendar']:
            ipo_id = create_ipo_id(ipo)
            
            if ipo_id not in history:
                new_ipos.append((ipo, False))  # False = not upcoming
                history[ipo_id] = {
                    'first_seen': datetime.utcnow().isoformat(),
                    'ipo': ipo,
                    'type': 'recent'
                }
                print(f"  New recent IPO: {ipo.get('symbol')} - {ipo.get('name')}")
    
    print(f"\nChecking upcoming IPOs from {upcoming_from} to {upcoming_to}")
    upcoming_data = get_ipo_calendar(upcoming_from, upcoming_to)
    
    if upcoming_data and 'ipoCalendar' in upcoming_data:
        for ipo in upcoming_data['ipoCalendar']:
            ipo_id = create_ipo_id(ipo)
            
            if ipo_id not in history:
                new_ipos.append((ipo, True))  # True = upcoming
                history[ipo_id] = {
                    'first_seen': datetime.utcnow().isoformat(),
                    'ipo': ipo,
                    'type': 'upcoming'
                }
                print(f"  New upcoming IPO: {ipo.get('symbol')} - {ipo.get('name')}")
    
    # Send alerts for new IPOs
    if new_ipos:
        print(f"\nFound {len(new_ipos)} new IPOs")
        embeds = [format_discord_embed(ipo, is_upcoming) for ipo, is_upcoming in new_ipos]
        send_discord_alert(embeds)
    else:
        print("No new IPOs found")
    
    # Clean up old history (keep last 90 days)
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    history = {
        k: v for k, v in history.items()
        if datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} IPOs")


if __name__ == '__main__':
    main()
