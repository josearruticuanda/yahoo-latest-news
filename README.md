# Yahoo Latest Stock News API

A simple API that provides the latest stock news from Yahoo Finance.

## Endpoints

- `GET /` - API info
- `GET /health` - Health check  
- `GET /news` - Latest news
- `GET /news/{article_id}` - Full article content

## Legal Disclaimer

This API responsibly scrapes publicly available content from Yahoo Finance using a respectful caching mechanism (1 request per minute maximum). The API serves unlimited users from cached data without overloading Yahoo's servers.

Users are responsible for:

- Complying with Yahoo's Terms of Service
- Ensuring appropriate use of the data
- Respecting intellectual property rights

**This project is not affiliated with or endorsed by Yahoo Finance.**