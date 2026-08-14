# Trade Journal Helper 📈

An automated trade journaling and analysis tool that fetches trade execution history from **Fyers** and **CoinDCX**, calculates exact transaction charges and net P/L, matches entry/exit executions, and exports them into a structured trading journal CSV format.

---

## 🌟 Key Features

- **Multi-Broker & Multi-Asset Support**:
  - **Fyers**: Equities, F&O (Futures & Options), and MCX Commodities.
  - **CoinDCX**: Crypto Spot & Derivatives/Futures trading pairs.
- **Automated Trade Matching**:
  - Groups split fills and partial executions by trade/order ID and timestamp.
  - Merges partial exits into structured entry and exit records (`Exit 1`, `Exit 2`).
- **Accurate Fee & Tax Calculation**:
  - Computes Brokerage, STT (Securities Transaction Tax), Exchange Transaction Charges (ETC), SEBI Turnover Fee, GST, Stamp Duty, and IPFT.
  - Applies asset-specific lot size multipliers (e.g., MCX Crude, Gold, Silver, Natural Gas).
- **Live USDT-INR Conversion**:
  - Fetches active USDT/INR conversion rates from CoinDCX API for accurate INR P/L calculations.
- **CSV Export**:
  - Appends formatted trades to `trade_journal.csv` with fields ready for performance analysis, setup explanations, and notes.

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8+
- Required Python package: `requests`

```bash
pip install requests
```

### 2. Configuration (`.env`)

Create a `.env` file in the root directory with your API credentials:

```env
# CoinDCX API Configuration
COINDCX_API=your_coindcx_api_key
COINDCX_SECRATE=your_coindcx_api_secret

# Fyers API Configuration
FYERS_APP_ID=your_fyers_app_id
FYERS_SECRATE_ID=your_fyers_secret_id
FYERS_REDIRECT_URI=http://localhost:5005/
```

> **Note**: `fyers_token.txt` and `.env` are automatically ignored by `.gitignore` to keep credentials secure.

---

## 💻 Usage

### Run for Today's Date
```bash
python generate_journal.py
```

### Run for a Specific Date (`YYYY-MM-DD`)
```bash
python generate_journal.py 2026-08-14
```

### Batch File (Windows)
Double-click `run_journal.bat` or run:
```cmd
run_journal.bat
```

---

## 📊 Output Schema (`trade_journal.csv`)

The generated journal CSV contains the following columns:

| Column Header | Description |
| :--- | :--- |
| `Date` | Trade date (`YYYY-MM-DD`) |
| `Trade Index` | Sequential trade index |
| `Ticker` | Symbol name (e.g., `NSE:NIFTY26AUGFUT`, `BTC_USDT`) |
| `Time` | Entry time (`HH:MM:SS`) |
| `Exit Time 1` | Primary exit time |
| `Exit Time 2` | Secondary/partial exit time |
| `Side` | `BUY` or `SELL` |
| `P/L after Charges` | Net profit/loss after fees and taxes |
| `P/L` | Total Gross P/L |
| `P/L 1` / `P/L 2` | P/L per partial exit |
| `Brokrage` | Total transaction fees & taxes |
| `Trend` / `Setup` ... | Custom columns for manual journaling notes |

---

## 📁 Repository Structure

```
TradeJournalHelper/
├── .env                  # API keys and secrets (git-ignored)
├── .gitignore            # Git ignore configuration
├── README.md             # Project documentation
├── generate_journal.py   # Main journal generator script
├── run_journal.bat       # Windows batch runner
└── trade_journal.csv     # Output journal file
```
