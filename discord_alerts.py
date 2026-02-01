import requests
import time
from datetime import datetime
import os
import json

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed - running in production (GitHub Actions)
    pass

# ===================================================================
# Configuration from GitHub Secrets or .env file
# ===================================================================
DISCORD_WEBHOOK_FORM4 = os.environ.get('DISCORD_WEBHOOK_FORM4')
DISCORD_WEBHOOK_FORM8K = os.environ.get('DISCORD_WEBHOOK_FORM8K')
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')
MIN_AMOUNT = 100000

# File paths for tracking seen filings
SEEN_TRADES_FILE = 'seen_trades.txt'
SEEN_8K_FILE = 'seen_8k.txt'

# ===================================================================
# SEC EDGAR API configuration
# ===================================================================
SEC_HEADERS = {
    'User-Agent': 'InsiderMonitorBot your-contact@email.com',
    'Accept-Encoding': 'gzip, deflate'
}

# ===================================================================
# Watchlist - 77 stocks to monitor
# ===================================================================
WATCHLIST = [
    "MSFT", "NVDA", "TSLA", "GOOGL", "META", "AMZN", "NFLX", "AMD",
    "INTC", "COIN", "LYFT", "ORCL", "AVGO", "ADBE", "PYPL", "PLTR",
    "SMCI", "SOFI", "SMR", "GME", "HIMS", "CRWV", "XPEV", "HOOD",
    "OKLO", "ACHR", "IREN", "NBIS", "MU", "SNOW", "APP", "TSM",
    "ASTS", "MRVL", "BA", "PDD", "SOUN", "PANW", "TEM", "LLY",
    "ALGN", "SPOT", "CVNA", "SHOP", "DUOL", "NKE", "CSCO", "BULL",
    "JNJ", "LCID", "KO", "GE", "BE", "NEE", "PEP", "RR", "IONQ",
    "QCOM", "LNTH", "CFLT", "LMND", "JOBY", "CAT", "OPEN", "RIVN",
    "PFE", "CNC", "NVO", "NOW", "CVS", "ABT", "IBM", "JPM", "NVAX", 
    "BRK-B", "UNH", "AAPL"
]

# ===================================================================
# Discord Webhook Functions
# ===================================================================
def send_discord_webhook(webhook_url, embed_data):
    """Send a Discord webhook message with rich embed"""
    if not webhook_url:
        print("⚠️  Discord webhook URL not set, skipping alert")
        return False
    
    payload = {
        "embeds": [embed_data]
    }
    
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code in [200, 204]:
            print(f"✅ Discord alert sent at {datetime.now().strftime('%H:%M:%S')}")
            return True
        else:
            print(f"❌ Discord Webhook Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sending Discord alert: {e}")
        return False

# ===================================================================
# Transaction Code Descriptions
# ===================================================================
def get_transaction_code_description(code):
    """Get human-readable description of SEC transaction codes"""
    code_meanings = {
        'A': 'Grant/Award',
        'D': 'Disposition (Sale to Issuer)',
        'P': 'Open Market Purchase',
        'S': 'Open Market Sale',
        'F': 'Tax Payment (Shares Withheld)',
        'M': 'Option Exercise',
        'C': 'Conversion',
        'E': 'Expiration',
        'G': 'Gift',
        'H': 'Withholding',
        'I': 'Discretionary Transaction',
        'J': 'Other',
        'K': 'Equity Swap',
        'L': 'Small Acquisition',
        'U': 'Tender Offer',
        'V': 'Voluntary Transaction',
        'W': 'Acquisition/Disposition by Will',
        'X': 'Exercise of Out-of-the-Money Options',
        'Z': 'Deposit into/Withdrawal from Plan'
    }
    return code_meanings.get(code, code if code else 'Unknown')

# ===================================================================
# Discord Embed Formatting Functions
# ===================================================================
def format_form4_discord_embed(trade, symbol, sec_link):
    """Format a Form 4 insider trade alert as Discord embed"""
    change = trade.get('change', 0)
    trade_type = "BUY" if change > 0 else "SELL"
    
    name = trade.get('name', 'Unknown Insider')
    shares = abs(change)
    transaction_price = trade.get('transactionPrice', 0)
    
    # Determine color (green for buy, red for sell)
    color = 0x00ff88 if trade_type == 'BUY' else 0xff3366
    
    if transaction_price and transaction_price > 0:
        price = transaction_price
        total_value = shares * price
        value_text = f"${total_value:,.0f}"
        price_text = f"${price:.2f}"
    else:
        value_text = "Not available"
        price_text = "Not available"
    
    shares_owned_after = trade.get('share', 0)
    transaction_date = trade.get('transactionDate', 'Unknown')
    filing_date = trade.get('filingDate', 'Unknown')
    transaction_code = trade.get('transactionCode', '')
    transaction_desc = get_transaction_code_description(transaction_code)
    
    # Build embed
    embed = {
        "title": f"🟢 INSIDER {trade_type}: {symbol}" if trade_type == 'BUY' else f"🔴 INSIDER {trade_type}: {symbol}",
        "description": f"**{name}** {'is buying' if trade_type == 'BUY' else 'is selling'} shares",
        "color": color,
        "fields": [
            {
                "name": "📊 Transaction Details",
                "value": f"**Code:** {transaction_code} - {transaction_desc}\n**Shares:** {shares:,}\n**Price/Share:** {price_text}\n**Total Value:** {value_text}",
                "inline": False
            },
            {
                "name": "📅 Dates",
                "value": f"**Transaction:** {transaction_date}\n**Filed:** {filing_date}",
                "inline": True
            },
            {
                "name": "💼 After Transaction",
                "value": f"**Shares Owned:** {shares_owned_after:,}",
                "inline": True
            },
            {
                "name": "💡 Signal",
                "value": "Bullish - Insider is buying" if trade_type == 'BUY' else "⚠️ Insider is selling",
                "inline": False
            },
            {
                "name": "🔗 SEC Filing",
                "value": f"[View Form 4 on SEC EDGAR]({sec_link})",
                "inline": False
            }
        ],
        "footer": {
            "text": "Form 4 Alert • Insider Trading Monitor"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed

def format_form8k_discord_embed(filing):
    """Format a Form 8-K filing alert as Discord embed"""
    symbol = filing.get('symbol', 'Unknown')
    filing_date = filing.get('filedDate', 'Unknown')
    form = filing.get('form', '8-K')
    accept_time = filing.get('acceptedDate', 'Unknown')
    url = filing.get('reportUrl', '')
    item_codes = filing.get('items', [])
    
    item_descriptions = {
        '1.01': 'Important contract signed',
        '1.02': 'Major contract terminated',
        '1.03': '🚨 Bankruptcy/receivership',
        '2.01': 'Acquisition or asset sale',
        '2.02': 'Earnings release',
        '2.03': 'New debt issued',
        '2.04': 'Debt acceleration',
        '2.05': 'Restructuring/layoffs',
        '2.06': 'Asset write-downs',
        '3.01': '🚨 Delisting risk',
        '3.02': 'Private stock sale',
        '3.03': 'Shareholder rights changed',
        '4.01': 'Auditor changed',
        '4.02': '🚩 Financial restatement',
        '5.01': 'Ownership change',
        '5.02': 'CEO/CFO/Director change',
        '5.03': 'Governance rules updated',
        '5.04': 'Employee trading suspended',
        '5.05': 'Ethics code updated',
        '7.01': 'Material info disclosed',
        '8.01': 'Other material event',
        '9.01': 'Financial statements attached'
    }
    
    items_text = ""
    if item_codes and len(item_codes) > 0:
        for code in item_codes:
            desc = item_descriptions.get(code, 'Material event')
            items_text += f"**Item {code}:** {desc}\n"
    else:
        items_text = "Material event requiring SEC disclosure"
    
    embed = {
        "title": f"📋 FORM 8-K FILED: {symbol}",
        "description": f"**{form}** filing detected",
        "color": 0x00d4ff,  # Blue color
        "fields": [
            {
                "name": "📋 Items Filed",
                "value": items_text if items_text else "No specific items",
                "inline": False
            },
            {
                "name": "📅 Filing Information",
                "value": f"**Filed:** {filing_date}\n**Accepted:** {accept_time}",
                "inline": False
            },
            {
                "name": "🔗 SEC Filing",
                "value": f"[View Full Filing on SEC]({url})" if url else "Link not available",
                "inline": False
            }
        ],
        "footer": {
            "text": "Form 8-K Alert • Material Events Monitor"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed

# ===================================================================
# Finnhub API Functions
# ===================================================================
def fetch_insider_trades(symbol):
    """Fetch insider trades using Finnhub API - Limited to top 7"""
    url = "https://finnhub.io/api/v1/stock/insider-transactions"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[:7] if data else []
        elif response.status_code == 429:
            print("   ⚠️ Rate limited - waiting...")
            time.sleep(2)
            return []
        else:
            print(f"   ❌ API error: {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Error fetching {symbol}: {e}")
        return []

def fetch_form8k_filings(symbol):
    """Fetch Form 8-K filings using Finnhub API - Limited to top 7"""
    url = "https://finnhub.io/api/v1/stock/filings"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY, "form": "8-K"}
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return data[:7] if data else []
        elif response.status_code == 429:
            print("   ⚠️ Rate limited - waiting...")
            time.sleep(2)
            return []
        else:
            print(f"   ❌ API error: {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Error fetching 8-K for {symbol}: {e}")
        return []

# ===================================================================
# SEC Form 4 URL Resolution
# ===================================================================
def get_cik_for_ticker(ticker):
    """Get CIK number for a ticker from SEC company tickers file"""
    try:
        response = requests.get(
            'https://www.sec.gov/files/company_tickers.json',
            headers=SEC_HEADERS,
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            for entry in data.values():
                if entry.get('ticker', '').upper() == ticker.upper():
                    return str(entry.get('cik_str'))
        return None
    except Exception as e:
        print(f"      ⚠️ Error fetching CIK: {e}")
        return None

def fetch_sec_form4_url(symbol, filing_date):
    """Resolve direct Form 4 URL from SEC EDGAR"""
    cik = get_cik_for_ticker(symbol)
    if not cik:
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type=4&dateb=&owner=include&count=10"
    
    try:
        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        response = requests.get(url, headers=SEC_HEADERS, timeout=15)
        
        if response.status_code != 200:
            return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=10"
        
        data = response.json()
        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        filing_dates = recent.get('filingDate', [])
        accession_numbers = recent.get('accessionNumber', [])
        primary_docs = recent.get('primaryDocument', [])
        
        best_fallback = None
        for i, form in enumerate(forms):
            if form != '4':
                continue
            
            acc = accession_numbers[i] if i < len(accession_numbers) else ''
            primary_doc = primary_docs[i] if i < len(primary_docs) else ''
            filed = filing_dates[i] if i < len(filing_dates) else ''
            
            if not acc or not primary_doc:
                continue
            
            acc_no_dashes = acc.replace('-', '')
            direct_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/{primary_doc}"
            
            if best_fallback is None:
                best_fallback = direct_url
            
            if filed == filing_date:
                return direct_url
        
        return best_fallback or f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=10"
    
    except Exception as e:
        print(f"      ⚠️ Error fetching SEC URL: {e}")
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type=4&dateb=&owner=include&count=10"

# ===================================================================
# Form 8-K Item Code Extraction
# ===================================================================
def extract_8k_item_codes(report_url):
    """Extract item codes from Form 8-K filing"""
    if not report_url:
        return []
    
    try:
        response = requests.get(report_url, headers=SEC_HEADERS, timeout=15)
        if response.status_code != 200:
            return []
        
        content = response.text.upper()
        import re
        
        all_matches = set(
            re.findall(r'ITEM\s+(\d+\.\d+)', content) +
            re.findall(r'ITEM\s+(\d+\.\d+)\.', content) +
            re.findall(r'ITEM\s+(\d+\.\d+):', content) +
            re.findall(r'\[X\]\s*ITEM\s+(\d+\.\d+)', content)
        )
        
        valid_items = [
            '1.01','1.02','1.03','1.04',
            '2.01','2.02','2.03','2.04','2.05','2.06',
            '3.01','3.02','3.03',
            '4.01','4.02',
            '5.01','5.02','5.03','5.04','5.05','5.06','5.07','5.08',
            '6.01','6.02','6.03','6.04','6.05',
            '7.01','8.01','9.01'
        ]
        
        item_codes = [code for code in all_matches if code in valid_items]
        return sorted(item_codes)
    except Exception as e:
        print(f"      ⚠️ Error extracting item codes: {e}")
        return []

# ===================================================================
# Tracking Functions (Prevent Duplicate Alerts)
# ===================================================================
def load_seen_trades():
    """Load previously seen trade IDs"""
    try:
        with open(SEEN_TRADES_FILE, 'r') as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_seen_trades(seen_trades):
    """Save seen trade IDs to file"""
    with open(SEEN_TRADES_FILE, 'w') as f:
        for trade_id in seen_trades:
            f.write(f"{trade_id}\n")

def load_seen_8k():
    """Load previously seen 8-K filing IDs"""
    try:
        with open(SEEN_8K_FILE, 'r') as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_seen_8k(seen_8k):
    """Save seen 8-K filing IDs to file"""
    with open(SEEN_8K_FILE, 'w') as f:
        for filing_id in seen_8k:
            f.write(f"{filing_id}\n")

# ===================================================================
# Main Monitoring Function
# ===================================================================
def monitor_insider_activity():
    """Monitor insider trades and Form 8-K filings, send Discord alerts"""
    print(f"{'='*60}")
    print(f"💬 Discord Insider Alert Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"📋 Watchlist: {len(WATCHLIST)} stocks")
    print(f"💰 Minimum alert threshold: ${MIN_AMOUNT:,}")
    print(f"📊 Alert limit: 5 most recent Form 4 trades per run")
    print(f"{'='*60}\n")
    
    seen_trades = load_seen_trades()
    seen_8k = load_seen_8k()
    
    form4_alerts = 0
    form8k_alerts = 0
    
    # Collect all new trades first
    all_new_trades = []
    
    for idx, symbol in enumerate(WATCHLIST, 1):
        print(f"📊 [{idx}/{len(WATCHLIST)}] Checking {symbol}...")
        
        # ============================================================
        # Form 4 - Insider Trades
        # ============================================================
        try:
            trades = fetch_insider_trades(symbol)
            if trades:
                print(f"   📄 Found {len(trades)} Form 4 filings")
                
                for trade in trades:
                    change = trade.get('change', 0)
                    shares = abs(change)
                    transaction_price = trade.get('transactionPrice', 0)
                    value = shares * transaction_price if transaction_price > 0 else 0
                    
                    name = trade.get('name', 'Unknown')
                    transaction_date = trade.get('transactionDate', 'Unknown')
                    filing_date = trade.get('filingDate', 'Unknown')
                    
                    trade_id = f"{symbol}_{name}_{transaction_date}_{shares}_{change}"
                    
                    # Skip if already seen
                    if trade_id in seen_trades:
                        continue
                    
                    # Skip if below minimum threshold
                    if value > 0 and value < MIN_AMOUNT:
                        continue
                    
                    action = "BUY" if change > 0 else "SELL"
                    
                    # Add to collection for sorting
                    all_new_trades.append({
                        'trade': trade,
                        'symbol': symbol,
                        'filing_date': filing_date,
                        'trade_id': trade_id,
                        'action': action,
                        'name': name,
                        'shares': shares,
                        'value': value
                    })
                    
                    print(f"      ✅ Found {action}: {name} - {shares:,} shares")
        
        except Exception as e:
            print(f"   ❌ Error checking Form 4: {e}")
        
        time.sleep(0.5)
    
    # ============================================================
    # Sort and send only the 5 most recent Form 4 trades
    # ============================================================
    if all_new_trades:
        print(f"\n{'='*60}")
        print(f"📊 Found {len(all_new_trades)} new Form 4 trades total")
        print(f"📤 Sending alerts for the 5 most recent trades...")
        print(f"{'='*60}\n")
        
        # Sort by filing date (most recent first)
        all_new_trades.sort(key=lambda x: x['filing_date'], reverse=True)
        
        # Take only the top 5
        top_5_trades = all_new_trades[:5]
        
        for trade_data in top_5_trades:
            symbol = trade_data['symbol']
            filing_date = trade_data['filing_date']
            trade = trade_data['trade']
            trade_id = trade_data['trade_id']
            action = trade_data['action']
            name = trade_data['name']
            shares = trade_data['shares']
            
            # Get SEC Form 4 URL
            sec_link = fetch_sec_form4_url(symbol, filing_date)
            time.sleep(0.15)  # SEC rate limit
            
            print(f"🚨 SENDING {action}: {symbol} - {name} - {shares:,} shares")
            
            # Send Discord alert
            embed = format_form4_discord_embed(trade, symbol, sec_link)
            if send_discord_webhook(DISCORD_WEBHOOK_FORM4, embed):
                form4_alerts += 1
                seen_trades.add(trade_id)
                time.sleep(1)
        
        # Mark ALL trades as seen (even ones we didn't alert for)
        for trade_data in all_new_trades:
            seen_trades.add(trade_data['trade_id'])
        
        print(f"\n✅ Sent {form4_alerts} Form 4 alerts (top 5 most recent)")
        print(f"💾 Marked {len(all_new_trades)} total trades as seen\n")
    else:
        print(f"\n📭 No new Form 4 trades found\n")
    
    # ============================================================
    # Form 8-K Filings
    # ============================================================
    print(f"{'='*60}")
    print(f"📋 Checking Form 8-K filings...")
    print(f"{'='*60}\n")
    
    for idx, symbol in enumerate(WATCHLIST, 1):
        print(f"📋 [{idx}/{len(WATCHLIST)}] Checking {symbol} 8-K filings...")
        
        # ============================================================
        # Form 8-K Filings
        # ============================================================
        try:
            filings = fetch_form8k_filings(symbol)
            if filings:
                print(f"   📋 Found {len(filings)} Form 8-K filings")
                
                for filing in filings:
                    filing_id = f"{symbol}_{filing.get('acceptedDate', '')}_{filing.get('accessNumber', '')}"
                    
                    # Skip if already seen
                    if filing_id in seen_8k:
                        continue
                    
                    report_url = filing.get('reportUrl', '')
                    item_codes = extract_8k_item_codes(report_url) if report_url else []
                    
                    filing_data = {
                        'symbol': symbol,
                        'form': filing.get('form', '8-K'),
                        'filedDate': filing.get('filedDate', 'Unknown'),
                        'acceptedDate': filing.get('acceptedDate', 'Unknown'),
                        'reportUrl': report_url,
                        'items': item_codes
                    }
                    
                    items_display = ', '.join(item_codes) if item_codes else 'No items'
                    print(f"      🚨 NEW Form 8-K: {filing.get('filedDate')} - Items: {items_display}")
                    
                    # Send Discord alert
                    embed = format_form8k_discord_embed(filing_data)
                    if send_discord_webhook(DISCORD_WEBHOOK_FORM8K, embed):
                        form8k_alerts += 1
                        seen_8k.add(filing_id)
                        time.sleep(1)
        
        except Exception as e:
            print(f"   ❌ Error checking Form 8-K: {e}")
        
        time.sleep(1)
    
    # Save tracking files
    save_seen_trades(seen_trades)
    save_seen_8k(seen_8k)
    
    print(f"\n{'='*60}")
    print(f"✅ MONITORING COMPLETE")
    print(f"{'='*60}")
    print(f"📬 Form 4 alerts sent: {form4_alerts}")
    print(f"📬 Form 8-K alerts sent: {form8k_alerts}")
    print(f"🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

# ===================================================================
# Run the monitor
# ===================================================================
if __name__ == "__main__":
    monitor_insider_activity()
