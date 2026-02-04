#!/usr/bin/env python3
"""
IPO Calendar Alert Script
Alerts ONLY IPOs with CONFIRMED valuation >= $1B
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta

# ===================== CONFIG =====================

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_API_KEY_2 = os.getenv("FINNHUB_API_KEY_2")
FINNHUB_API_KEY_3 = os.getenv("FINNHUB_API_KEY_3")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_IPO_CALENDAR")
HISTORY_FILE = "data/ipo_calendar_history.json"

MIN_IPO_VALUE = 1_000_000_000  # $1B

# Create list of API keys (filter out None values)
API_KEYS = [key for key in [FINNHUB_API_KEY, FINNHUB_API_KEY_2, FINNHUB_API_KEY_3] if key]
api_key_index = 0

def get_next_api_key():
    """Round-robin through available API keys"""
    global api_key_index
    key = API_KEYS[api_key_index % len(API_KEYS)]
    api_key_index += 1
    return key

# ===================== HELPERS =====================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_ipo_calendar(from_date, to_date, max_retries=3):
    url = "https://finnhub.io/api/v1/calendar/ipo"
    
    for attempt in range(max_retries):
        params = {
            "from": from_date,
            "to": to_date,
            "token": get_next_api_key()  # Use round-robin API key
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            
            # Rate limit with 3 API keys: 180 API calls per minute = 0.33s per call
            # Using 0.4s for safety buffer
            time.sleep(0.4)
            
            return r.json().get("ipoCalendar", [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit hit
                wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                print(f"Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Error fetching IPO calendar: {e}")
                return []
        except Exception as e:
            print(f"Error fetching IPO calendar: {e}")
            return []
    
    print(f"Failed after {max_retries} retries")
    return []


def create_ipo_id(ipo):
    return f"{ipo.get('symbol')}_{ipo.get('date')}"


def is_valid_billion_dollar_ipo(ipo):
    """
    STRICT filter:
    - Value must exist
    - Must be numeric
    - Must be >= $1B
    """
    value = ipo.get("totalSharesValue")

    if not isinstance(value, (int, float)):
        return False

    return value >= MIN_IPO_VALUE


def format_value(value):
    return f"${value / 1_000_000_000:.2f}B"


def format_price_range(ipo):
    """Format price range if available"""
    price_low = ipo.get("priceLow")
    price_high = ipo.get("priceHigh")
    
    if price_low and price_high:
        return f"${price_low:.2f} - ${price_high:.2f}"
    return "N/A"


def format_embed(ipo, upcoming=False):
    symbol = ipo.get('symbol', 'N/A')
    name = ipo.get('name', 'Unknown Company')
    date = ipo.get("date", "N/A")
    exchange = ipo.get("exchange", "N/A")
    status = ipo.get("status", "N/A")
    value = ipo["totalSharesValue"]
    shares = ipo.get("totalSharesOffered", "N/A")
    price_range = format_price_range(ipo)
    
    # Determine emoji and color based on upcoming/recent
    if upcoming:
        emoji = "📅"
        color = 3447003  # Blue
    else:
        emoji = "🆕"
        color = 3066993  # Green
    
    # Format shares
    shares_formatted = f"{shares:,}" if isinstance(shares, (int, float)) else shares
    
    embed = {
        "title": f"{emoji} {status.upper()} - {symbol}",
        "description": f"**{name}**",
        "color": color,
        "fields": [
            {
                "name": "Date",
                "value": date,
                "inline": True
            },
            {
                "name": "Exchange",
                "value": exchange,
                "inline": True
            },
            {
                "name": "Status",
                "value": status.capitalize(),
                "inline": True
            },
            {
                "name": "Price Range",
                "value": price_range,
                "inline": True
            },
            {
                "name": "Shares",
                "value": shares_formatted,
                "inline": True
            },
            {
                "name": "Value",
                "value": format_value(value),
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub IPO Calendar"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    return embed


def send_discord(embeds):
    if not DISCORD_WEBHOOK:
        print("Discord webhook not set")
        return

    for i in range(0, len(embeds), 10):
        batch = embeds[i:i + 10]
        try:
            r = requests.post(DISCORD_WEBHOOK, json={"embeds": batch}, timeout=10)
            r.raise_for_status()
            print(f"✓ Sent {len(batch)} alerts")
            time.sleep(1)
        except Exception as e:
            print(f"✗ Discord send failed: {e}")

# ===================== MAIN =====================

def main():
    if not API_KEYS:
        print("FINNHUB_API_KEY missing")
        return

    print(f"Using {len(API_KEYS)} API key(s)")
    
    history = load_history()
    today = datetime.utcnow()

    recent_from = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    recent_to = today.strftime("%Y-%m-%d")

    upcoming_from = recent_to
    upcoming_to = (today + timedelta(days=60)).strftime("%Y-%m-%d")

    new_alerts = []

    print(f"Checking recent IPOs {recent_from} → {recent_to}")
    for ipo in get_ipo_calendar(recent_from, recent_to):
        ipo_id = create_ipo_id(ipo)
        if ipo_id in history:
            continue

        if is_valid_billion_dollar_ipo(ipo):
            history[ipo_id] = {"seen": datetime.utcnow().isoformat()}
            new_alerts.append(format_embed(ipo, upcoming=False))
            print(f"✓ {ipo.get('symbol')} — {format_value(ipo['totalSharesValue'])}")

    print(f"\nChecking upcoming IPOs {upcoming_from} → {upcoming_to}")
    for ipo in get_ipo_calendar(upcoming_from, upcoming_to):
        ipo_id = create_ipo_id(ipo)
        if ipo_id in history:
            continue

        if is_valid_billion_dollar_ipo(ipo):
            history[ipo_id] = {"seen": datetime.utcnow().isoformat()}
            new_alerts.append(format_embed(ipo, upcoming=True))
            print(f"✓ {ipo.get('symbol')} — {format_value(ipo['totalSharesValue'])}")

    if new_alerts:
        send_discord(new_alerts)
    else:
        print("No confirmed $1B+ IPOs found")

    # Keep 90 days of history
    cutoff = datetime.utcnow() - timedelta(days=90)
    history = {
        k: v for k, v in history.items()
        if 'seen' in v and datetime.fromisoformat(v["seen"]) > cutoff
    }

    save_history(history)
    print(f"History size: {len(history)}")


if __name__ == "__main__":
    main()
