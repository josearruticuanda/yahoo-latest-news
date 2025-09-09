# RUN: uvicorn app:app --reload

# Import necessary libraries
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import json
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Yahoo Latest Stock News API",
    description="A REST API that provides the latest stock news from Yahoo Finance",
    version="1.0.0",
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT",
    },
)

# Define the path for the news file
NEWS_FILE = "latest_news.json"

# Function to scrape and update the news file
def update_news_cache():
    """
    Scrapes the latest news from Yahoo Finance and saves it to a JSON file.
    This function runs periodically in the background.
    """
    logger.info("Starting scheduled news update...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/139.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = "https://finance.yahoo.com/topic/latest-news/"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, "lxml")
        scripts = soup.find_all("script", {"type": "application/json", "data-sveltekit-fetched": True})
        
        filtered_stories = []

        for script_tag in scripts:
            outer_json = json.loads(script_tag.string)
            body = outer_json.get("body", "")
            if body.startswith("{"):
                try:
                    body_json = json.loads(body)
                    main_stream = body_json.get("data", {}).get("main", {}).get("stream", [])
                    if main_stream:
                        for story in main_stream:
                            content = story.get("content", {})
                            finance = content.get("finance") or {}
                            tickers = finance.get("stockTickers")
                            if tickers is None:
                                tickers = []
                            
                            story_info = {
                                "id": content.get("id"),
                                "title": content.get("title"),
                                "pubDate": content.get("pubDate"), # Remember: This is in UTC time
                                # "providerContentUrl": content.get("providerContentUrl"),
                                "canonicalUrl": content.get("canonicalUrl", {}).get("url"),
                                "stockTickers": [t.get("symbol") for t in tickers]
                            }
                            filtered_stories.append(story_info)
                        break # Stop after finding and processing the first main stream
                except json.JSONDecodeError:
                    continue
        
        # Save the scraped data to the news file
        with open(NEWS_FILE, "w") as f:
            json.dump(filtered_stories, f)
        
        logger.info(f"News updated successfully at {datetime.now()}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch news from Yahoo: {e}")
    except IOError as e:
        logger.error(f"Failed to write to file: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during news update: {e}")

# Create the scheduler instance
scheduler = BackgroundScheduler()

@app.on_event("startup")
def startup_event():
    """
    Event handler that runs when the API application starts.
    It initializes the news file and starts the scheduler.
    """
    logger.info("Application starting up...")
    
    # Run the file update function immediately to populate the file
    # before the first user request.
    update_news_cache()
    
    # Add the update job to the scheduler to run every minute
    scheduler.add_job(
        update_news_cache,
        trigger=IntervalTrigger(minutes=1),
        id="news_job",
        name="Update news",
        replace_existing=True
    )
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started.")

@app.on_event("shutdown")
def shutdown_event():
    """
    Event handler that runs when the FastAPI application shuts down.
    It shuts down the scheduler gracefully.
    """
    logger.info("Application shutting down...")
    scheduler.shutdown()
    logger.info("Scheduler shut down.")

@app.get("/health")
def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns:
        JSONResponse: API health status and basic information.
    """
    try:
        # Check if news file exists and is readable
        news_file_status = "available" if os.path.exists(NEWS_FILE) else "initializing"
        
        # Check scheduler status
        scheduler_status = "running" if scheduler.running else "stopped"
        
        return JSONResponse(content={
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "Yahoo Latest Stock News API",
            "version": "1.0.0",
            "news_cache": news_file_status,
            "scheduler": scheduler_status
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.get("/")
def root():
    """
    Root endpoint providing API information.
    
    Returns:
        JSONResponse: Basic API information and available endpoints.
    """
    return JSONResponse(content={
        "message": "Yahoo Latest Stock News API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check endpoint",
            "/news": "Get latest news",
            "/news/{article_id}": "Get full article content by ID"
        }
    })

@app.get("/news")
def get_latest_news_from_cache(limit: int = 50):
    """
    Retrieves the latest news from the local news file.
    
    Args:
        limit (int): The maximum number of news stories to return.
    
    Returns:
        JSONResponse: A list of the latest news stories.
    
    Raises:
        HTTPException: If the news file does not exist.
    """
    logger.info(f"Received request for news, serving from file.")
    
    # Check if the file exists
    if not os.path.exists(NEWS_FILE):
        logger.warning("File not found, a new update will be triggered on next interval.")
        raise HTTPException(
            status_code=503,
            detail="News file is not yet available. Please try again in a moment."
        )

    try:
        # Read the data from the file
        with open(NEWS_FILE, "r") as f:
            cached_data = json.load(f)
            
        # Return the requested number of stories
        return JSONResponse(content=cached_data[:limit])
    
    except json.JSONDecodeError:
        logger.error("Error decoding JSON from file. File might be corrupted.")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reading the news file."
        )
    except IOError:
        logger.error("Error reading news file.")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reading the news file."
        )
    
@app.get("/news/{article_id}")
def get_article_content(article_id: str):
    """
    Retrieves the full HTML content of a news article by its ID and returns a JSON object
    with the article's title, URL, paragraph count, and a list of paragraphs.
    
    Args:
        article_id (str): The ID of the news article to retrieve.
    
    Returns:
        JSONResponse: A structured JSON object with the article data.
    
    Raises:
        HTTPException: If the article is not found or cannot be retrieved.
    """
    logger.info(f"Received request for article ID: {article_id}")
    
    # Ensure news file exists
    if not os.path.exists(NEWS_FILE):
        raise HTTPException(status_code=503, detail="News file is not yet available.")
    
    try:
        # Read the data from the file
        with open(NEWS_FILE, "r") as f:
            cached_data = json.load(f)
            
        # Find the article with the matching ID
        article = next((item for item in cached_data if item["id"] == article_id), None)
        
        if not article:
            raise HTTPException(status_code=404, detail="Article not found.")

        canonical_url = article.get("canonicalUrl")
        if not canonical_url:
            logger.error(f"URL not found for article ID: {article_id}")
            raise HTTPException(status_code=500, detail="Article data is corrupted or incomplete.")

        # Make a GET request to the canonical URL
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/139.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        article_response = requests.get(canonical_url, headers=headers, timeout=10)
        article_response.raise_for_status()
        
        # Parse the HTML content and extract all paragraph text
        soup = BeautifulSoup(article_response.text, "html.parser")
        paragraphs = soup.find_all("p")
        article_paragraphs = [p.get_text() for p in paragraphs]

        # Create the structured JSON response
        article_data = {
            "id": article_id,
            "title": article.get("title"),
            "url": canonical_url,
            "paragraph_count": len(article_paragraphs),
            "paragraphs": article_paragraphs
        }
        
        return JSONResponse(content=article_data)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch content from URL {canonical_url}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve article content.")
    except json.JSONDecodeError:
        logger.error("Error decoding JSON from news file. File might be corrupted.")
        raise HTTPException(status_code=500, detail="An error occurred while reading the news file.")
    except IOError:
        logger.error("Error reading news file.")
        raise HTTPException(status_code=500, detail="An error occurred while reading the news file.")