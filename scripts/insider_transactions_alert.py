#!/usr/bin/env python3
"""
Insider Transactions Alert Script
Monitors insider transactions and sends alerts to Discord
"""

import os
import json
import requests
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_INSIDER_TRANSACTIONS')
HISTORY_FILE = 'data/insider_transactions_history.json'

# Symbols to monitor
SYMBOLS_TO_MONITOR = [
    'ABBV', 'ABT', 'ADBE', 'AEO', 'ALAB', 'ALGN', 'ALGT', 'AMD',
    'AMZN', 'APP', 'ASTS', 'BA', 'BABA', 'BE', 'BULL',
    'CDNS', 'CFLT', 'CMCL', 'CNC', 'COIN', 'COP', 'CPNG',
    'CRWV', 'CSCO', 'CVNA', 'CVS', 'CVX', 'DUOL',
    'ENPH', 'FIG', 'FLR', 'GE', 'GME', 'GOOGL',
    'HIMS', 'HOOD', 'IBM', 'IBRX', 'INTC', 'IONQ',
    'IREN', 'JNJ', 'JOBY', 'KO', 'LCID',
    'LLY', 'LMND', 'LNTH', 'LYFT', 'MARA',
    'META', 'MRVL', 'MSFT', 'MU', 'NEE',
    'NFLX', 'NKE', 'NRG', 'NVAX', 'NVDA',
    'OKLO', 'ONC', 'OPEN', 'ORCL', 'PANW',
    'PATH', 'PEP', 'PDD', 'PFE', 'PLTR',
    'PYPL', 'QBTS', 'QCOM', 'RGTI', 'RKLB',
    'RR', 'SHOP', 'SMCI', 'SMR', 'SNOW',
    'SOFI', 'SOUN', 'SPOT', 'SYNA', 'TEM',
    'TMC', 'TSLA', 'TSM', 'TTD', 'UBER',
    'UAMY', 'UNH', 'USAR', 'UUUU', 'XOM',
    'XPEV', 'Z', 'ZBRA'
]


def load_history():
    """Load transaction history to avoid duplicates"""
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
    """Save transaction history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_insider_transactions(symbol, from_date, to_date):
    """Fetch insider transactions from Finnhub"""
    url = 'https://finnhub.io/api/v1/stock/insider-transactions'
    params = {
        'symbol': symbol,
        'from': from_date,
        'to': to_date,
        'token': FINNHUB_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching transactions for {symbol}: {e}")
        return None


def create_transaction_id(transaction):
    """Create unique ID for transaction"""
    return f"{transaction.get('symbol')}_{transaction.get('name')}_{transaction.get('transactionDate')}_{transaction.get('share')}_{transaction.get('transactionCode')}"


def format_discord_embed(transaction):
    """Format transaction data as Discord embed"""
    symbol = transaction.get('symbol', 'N/A')
    name = transaction.get('name', 'Unknown')
    shares = transaction.get('share', 0)
    value = transaction.get('value', 0)
    transaction_code = transaction.get('transactionCode', 'N/A')
    transaction_date = transaction.get('transactionDate', 'N/A')
    filing_date = transaction.get('filingDate', 'N/A')
    
    # Determine transaction type and color
    if transaction_code in ['P', 'A']:
        transaction_type = '🟢 BUY'
        color = 3066993  # Green
    elif transaction_code in ['S', 'D']:
        transaction_type = '🔴 SELL'
        color = 15158332  # Red
    else:
        transaction_type = f'📊 {transaction_code}'
        color = 3447003  # Blue
    
    # Format values
    shares_formatted = f"{shares:,}" if shares else "N/A"
    value_formatted = f"${value:,.2f}" if value else "N/A"
    
    embed = {
        "title": f"{transaction_type} - {symbol}",
        "description": f"**{name}**",
        "color": color,
        "fields": [
            {
                "name": "Shares",
                "value": shares_formatted,
                "inline": True
            },
            {
                "name": "Value",
                "value": value_formatted,
                "inline": True
            },
            {
                "name": "Transaction Code",
                "value": transaction_code,
                "inline": True
            },
            {
                "name": "Transaction Date",
                "value": transaction_date,
                "inline": True
            },
            {
                "name": "Filing Date",
                "value": filing_date,
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub Insider Transactions"
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
    
    # Calculate date range (last 7 days to catch any delayed filings)
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    print(f"Checking insider transactions from {from_date} to {to_date}")
    
    new_transactions = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_insider_transactions(symbol, from_date, to_date)
        
        if data and 'data' in data:
            for transaction in data['data']:
                transaction_id = create_transaction_id(transaction)
                
                # Check if we've seen this transaction before
                if transaction_id not in history:
                    new_transactions.append(transaction)
                    history[transaction_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'transaction': transaction
                    }
                    print(f"  New transaction: {transaction.get('name')} - {transaction.get('transactionCode')}")
    
    # Send alerts for new transactions
    if new_transactions:
        print(f"\nFound {len(new_transactions)} new transactions")
        embeds = [format_discord_embed(t) for t in new_transactions]
        send_discord_alert(embeds)
    else:
        print("No new transactions found")
    
    # Clean up old history (keep last 30 days)
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    history = {
        k: v for k, v in history.items()
        if datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} transactions")


if __name__ == '__main__':
    main()
