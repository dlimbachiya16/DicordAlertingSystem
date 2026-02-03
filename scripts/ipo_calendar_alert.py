#!/usr/bin/env python3
"""
IPO Calendar Alert Script
Monitors upcoming and recent IPOs and sends alerts to Discord
Only alerts on IPOs valued at $1 billion or more
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_IPO_CALENDAR')
HISTORY_FILE = 'data/ipo_calendar_history.json'

# Minimum IPO value to alert on (in dollars)
MIN_IPO_VALUE = 1_000_000_000  # $1 billion


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


def is_billion_dollar_ipo(ipo):
    """Check if IPO is valued at $1 billion or more"""
    total_value = ipo.get('totalSharesValue', 0)
    
    # If no value data, we'll include it (benefit of the doubt)
    if total_value is None or total_value == 0:
        return True
    
    return total_value >= MIN_IPO_VALUE


def sanitize_value(value, max_length=1024):
    """Sanitize value for Discord embed - remove None, validate length"""
    if value is None:
        return "N/A"
    
    str_value = str(value)
    
    # Discord field value limit is 1024 characters
    if len(str_value) > max_length:
        return str_value[:max_length-3] + "..."
    
    # Remove any problematic characters
    str_value = str_value.replace('\x00', '')  # Remove null bytes
    
    return str_value if str_value else "N/A"


def format_discord_embed(ipo, is_upcoming=False):
    """Format IPO data as Discord embed with validation"""
    symbol = sanitize_value(ipo.get('symbol', 'N/A'), 256)
    name = sanitize_value(ipo.get('name', 'Unknown Company'), 256)
    date = sanitize_value(ipo.get('date', 'N/A'))
    exchange = sanitize_value(ipo.get('exchange', 'N/A'))
    price_low = ipo.get('priceLow', 0)
    price_high = ipo.get('priceHigh', 0)
    shares = ipo.get('numberOfShares', 0)
    total_shares = ipo.get('totalSharesValue', 0)
    status = sanitize_value(ipo.get('status', 'N/A'))
    
    # Determine color and title based on status
    if is_upcoming:
        color = 3447003  # Blue
        title_prefix = "📅 Upcoming IPO"
    else:
        color = 3066993  # Green
        title_prefix = "🆕 Recent IPO"
    
    # Format values safely
    try:
        if price_low and price_high:
            price_range = f"${float(price_low):.2f} - ${float(price_high):.2f}"
        else:
            price_range = "N/A"
    except (ValueError, TypeError):
        price_range = "N/A"
    
    try:
        shares_formatted = f"{int(shares):,}" if shares else "N/A"
    except (ValueError, TypeError):
        shares_formatted = "N/A"
    
    try:
        if total_shares:
            # Format in billions if >= $1B
            if total_shares >= 1_000_000_000:
                total_value = f"${total_shares / 1_000_000_000:.2f}B"
            else:
                total_value = f"${int(total_shares):,.0f}"
        else:
            total_value = "N/A"
    except (ValueError, TypeError):
        total_value = "N/A"
    
    # Parse date for better formatting
    try:
        date_obj = datetime.strptime(str(date), '%Y-%m-%d')
        date_formatted = date_obj.strftime('%B %d, %Y')
    except:
        date_formatted = str(date)
    
    # Title must be 256 chars or less
    title = f"{title_prefix}: {symbol} 💰"
    if len(title) > 256:
        title = title[:253] + "..."
    
    # Description must be 4096 chars or less
    description = f"**{name}**"
    if len(description) > 4096:
        description = description[:4093] + "..."
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [
            {
                "name": "Date",
                "value": date_formatted[:1024],
                "inline": True
            },
            {
                "name": "Exchange",
                "value": exchange[:1024],
                "inline": True
            },
            {
                "name": "Status",
                "value": status[:1024],
                "inline": True
            },
            {
                "name": "Price Range",
                "value": price_range[:1024],
                "inline": True
            },
            {
                "name": "Shares",
                "value": shares_formatted[:1024],
                "inline": True
            },
            {
                "name": "Total Value",
                "value": total_value[:1024],
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub IPO Calendar • $1B+ IPOs only"[:2048]
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_discord_alert(embeds):
    """Send alert to Discord webhook with proper batching and rate limiting"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured")
        return False
    
    total_sent = 0
    total_failed = 0
    
    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {
            "embeds": batch
        }
        
        try:
            response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            response.raise_for_status()
            total_sent += len(batch)
            print(f"✓ Sent batch of {len(batch)} alerts (total: {total_sent}/{len(embeds)})")
            
            # Discord rate limit: 5 requests per 2 seconds
            # Wait 1 second between batches to be safe
            if i + 10 < len(embeds):
                time.sleep(1)
                
        except requests.exceptions.HTTPError as e:
            total_failed += len(batch)
            if e.response.status_code == 429:
                print(f"⚠ Rate limited. Waiting 2 seconds...")
                time.sleep(2)
                # Retry this batch
                try:
                    response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
                    response.raise_for_status()
                    total_sent += len(batch)
                    total_failed -= len(batch)
                    print(f"✓ Retry successful")
                except Exception as retry_error:
                    print(f"✗ Retry failed: {retry_error}")
            else:
                print(f"✗ HTTP {e.response.status_code} error for batch {i//10 + 1}")
                try:
                    print(f"  Response: {e.response.text[:200]}")
                except:
                    pass
        except Exception as e:
            total_failed += len(batch)
            print(f"✗ Error sending batch {i//10 + 1}: {e}")
    
    print(f"\nSummary: {total_sent} sent, {total_failed} failed")
    return total_sent > 0


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
    filtered_count = 0
    
    print(f"Checking recent IPOs from {recent_from} to {recent_to}")
    recent_data = get_ipo_calendar(recent_from, recent_to)
    
    if recent_data and 'ipoCalendar' in recent_data:
        for ipo in recent_data['ipoCalendar']:
            ipo_id = create_ipo_id(ipo)
            
            if ipo_id not in history:
                # Check if IPO meets minimum value threshold
                if is_billion_dollar_ipo(ipo):
                    new_ipos.append((ipo, False))  # False = not upcoming
                    history[ipo_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'ipo': ipo,
                        'type': 'recent',
                        'value': ipo.get('totalSharesValue', 0)
                    }
                    value = ipo.get('totalSharesValue', 0)
                    value_str = f"${value/1_000_000_000:.2f}B" if value >= 1_000_000_000 else f"${value:,.0f}"
                    print(f"  ✓ New IPO: {ipo.get('symbol')} - {ipo.get('name')} ({value_str})")
                else:
                    filtered_count += 1
                    value = ipo.get('totalSharesValue', 0)
                    print(f"  ✗ Filtered: {ipo.get('symbol')} - ${value:,.0f} (below $1B)")
    
    print(f"\nChecking upcoming IPOs from {upcoming_from} to {upcoming_to}")
    upcoming_data = get_ipo_calendar(upcoming_from, upcoming_to)
    
    if upcoming_data and 'ipoCalendar' in upcoming_data:
        for ipo in upcoming_data['ipoCalendar']:
            ipo_id = create_ipo_id(ipo)
            
            if ipo_id not in history:
                # Check if IPO meets minimum value threshold
                if is_billion_dollar_ipo(ipo):
                    new_ipos.append((ipo, True))  # True = upcoming
                    history[ipo_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'ipo': ipo,
                        'type': 'upcoming',
                        'value': ipo.get('totalSharesValue', 0)
                    }
                    value = ipo.get('totalSharesValue', 0)
                    value_str = f"${value/1_000_000_000:.2f}B" if value >= 1_000_000_000 else f"${value:,.0f}"
                    print(f"  ✓ New IPO: {ipo.get('symbol')} - {ipo.get('name')} ({value_str})")
                else:
                    filtered_count += 1
                    value = ipo.get('totalSharesValue', 0)
                    print(f"  ✗ Filtered: {ipo.get('symbol')} - ${value:,.0f} (below $1B)")
    
    # Send alerts for new billion-dollar IPOs
    if new_ipos:
        print(f"\nFound {len(new_ipos)} new billion-dollar IPOs ({filtered_count} filtered out)")
        
        # Send summary first if many IPOs
        if len(new_ipos) > 10:
            summary_embed = {
                "title": "💰 Billion-Dollar IPO Alert",
                "description": f"Found **{len(new_ipos)}** new IPOs valued at $1B+\n({filtered_count} smaller IPOs filtered out)",
                "color": 3447003,
                "timestamp": datetime.utcnow().isoformat()
            }
            try:
                requests.post(DISCORD_WEBHOOK, json={"embeds": [summary_embed]}, timeout=10)
                time.sleep(1)
            except Exception as e:
                print(f"Warning: Could not send summary: {e}")
        
        # Create embeds with validation
        embeds = []
        for ipo, is_upcoming in new_ipos:
            try:
                embed = format_discord_embed(ipo, is_upcoming)
                embeds.append(embed)
            except Exception as e:
                print(f"Warning: Could not create embed for {ipo.get('symbol')}: {e}")
        
        if embeds:
            send_discord_alert(embeds)
    else:
        print(f"No new billion-dollar IPOs found ({filtered_count} filtered out)")
    
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
