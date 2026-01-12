# Competitor Product Scraper

A Python-based system for scraping product data, prices, and offers from Egyptian wholesale mobile apps (Tager elSaada, Ben Soliman) for competitive analysis.

## Features

- **API Reverse Engineering** - Intercept and replicate mobile app API calls
- **Hourly Price Tracking** - Automated scraping every hour
- **Price History** - Track price changes over time
- **Cross-App Comparison** - Match products by barcode across apps
- **Anti-Detection** - Device fingerprinting, rate limiting, request jitter
- **Docker Deployment** - Containerized for easy deployment

## Project Structure

```
competitor-scraper/
├── docker/                 # Docker configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── src/
│   ├── config/            # Application settings
│   ├── scrapers/          # App-specific scrapers
│   │   ├── base.py        # Abstract base scraper
│   │   ├── tager_elsaada.py
│   │   └── ben_soliman.py
│   ├── models/            # Database & Pydantic models
│   ├── database/          # DB connection & repositories
│   ├── scheduler/         # APScheduler jobs
│   ├── utils/             # HTTP client, rate limiter, etc.
│   └── main.py            # Entry point
├── docs/
│   └── api_documentation/ # Discovered API docs
├── scripts/               # Helper scripts
└── tests/                 # Unit tests
```

## Prerequisites

Before running the scraper, you need to:

1. **Create accounts** on the target apps (Tager elSaada, Ben Soliman)
2. **Perform API discovery** to document the actual API endpoints

See [API Discovery Guide](docs/api_documentation/API_DISCOVERY_GUIDE.md) for detailed instructions.

## Quick Start

### 1. Clone and Setup

```bash
cd C:\Users\ahmed\Documents\scrabing

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example env file
copy docker\.env.example .env  # Windows
# cp docker/.env.example .env  # Linux/Mac

# Edit .env with your credentials
```

Required environment variables:
```
DB_PASSWORD=your_database_password
ENCRYPTION_KEY=your_fernet_key  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TAGER_ELSAADA_USERNAME=your_phone
TAGER_ELSAADA_PASSWORD=your_password
BEN_SOLIMAN_USERNAME=your_phone
BEN_SOLIMAN_PASSWORD=your_password
```

### 3. Perform API Discovery

**This step is required before running the scraper.**

Follow the [API Discovery Guide](docs/api_documentation/API_DISCOVERY_GUIDE.md) to:
1. Set up mitmproxy
2. Bypass SSL pinning with Frida
3. Document the API endpoints
4. Update the scraper code with actual endpoints

### 4. Run with Docker

```bash
cd docker

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f scraper

# Stop
docker-compose down
```

### 5. Run Locally (Development)

```bash
# Start PostgreSQL (required)
docker-compose up -d postgres redis

# Run the scraper
python -m src.main
```

## Scheduling

The scraper runs on the following schedule (Cairo timezone):

| Job | Schedule | Description |
|-----|----------|-------------|
| Tager elSaada | Every hour (minute 0) | Full product scrape |
| Ben Soliman | Every hour (minute 30) | Full product scrape |
| Token Refresh | Every 25 minutes | Keep auth tokens valid |
| Data Cleanup | Daily at 3 AM | Delete records > 90 days |

## Database Schema

### Core Tables

- **products** - Product information (name, barcode, category, etc.)
- **price_records** - Historical prices (time-series data)
- **categories** - Product categories
- **offers** - Promotional offers and discounts
- **scrape_jobs** - Job tracking and statistics
- **credentials** - Encrypted app credentials

### Price Comparison

Products can be matched across apps using the `barcode` field:
```sql
SELECT
  p1.name, p1.barcode,
  pr1.price as tager_price,
  pr2.price as bensoliman_price
FROM products p1
JOIN products p2 ON p1.barcode = p2.barcode
  AND p1.source_app = 'tager_elsaada'
  AND p2.source_app = 'ben_soliman'
JOIN price_records pr1 ON p1.id = pr1.product_id
JOIN price_records pr2 ON p2.id = pr2.product_id;
```

## Configuration

Key settings in `src/config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| requests_per_second | 1.5 | Rate limit for API requests |
| burst_size | 3 | Max burst requests |
| min_request_delay | 0.5 | Min delay between requests (seconds) |
| max_request_delay | 2.0 | Max delay between requests (seconds) |

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Quality

```bash
# Format code
black src/

# Lint
ruff src/

# Type checking
mypy src/
```

## Troubleshooting

### "Authentication failed" errors
- Check your credentials in `.env`
- Verify the API endpoints are correct (see API docs)
- Token may have expired - restart scraper

### "Rate limit" errors
- Reduce `requests_per_second` in settings
- Increase delays between requests

### SSL/Connection errors
- API endpoints may have changed
- Re-do API discovery to verify endpoints

### No data being scraped
- Check logs: `docker-compose logs scraper`
- Verify authentication is working
- Check if API response format changed

## Security

- Credentials are encrypted using Fernet
- Never commit `.env` file or credentials
- Use read-only database users for reporting
- Rotate API tokens regularly

## License

Private - For internal use only.

## Support

For issues or questions, contact the development team.
