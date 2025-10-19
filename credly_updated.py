"""
Credly Certification Tracker - Refactored
Includes Selenium-based scraping, badge parsing, and LangGraph agent integration.
"""

import os
import re
import sqlite3
import time
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent


# ===================================================================
# ENVIRONMENT
# ===================================================================

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("❌ Missing GROQ_API_KEY in .env file")


# ===================================================================
# CONSTANTS
# ===================================================================

PROFILE_URL = "https://www.credly.com/users/cladius/badges"
DB_FILE = "credly_data.db"
POINTS = {"Foundational": 10, "Associate": 5, "Professional": 10, "Specialty": 10}


# ===================================================================
# DATABASE SETUP
# ===================================================================

def init_db():
    """Create and initialize SQLite database with default certification mappings."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            status TEXT,
            points INTEGER,
            UNIQUE(name, issue_date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS certification_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cert_name TEXT UNIQUE,
            category TEXT
        )
    """)

    # Insert default AWS cert mappings if empty
    c.execute("SELECT COUNT(*) FROM certification_mappings")
    if c.fetchone()[0] == 0:
        default_mappings = [
            ("aws certified cloud practitioner", "Foundational"),
            ("solutions architect associate", "Associate"),
            ("developer associate", "Associate"),
            ("sysops administrator associate", "Associate"),
            ("solutions architect professional", "Professional"),
            ("devops engineer professional", "Professional"),
            ("advanced networking specialty", "Specialty"),
            ("security specialty", "Specialty"),
            ("machine learning specialty", "Specialty"),
            ("database specialty", "Specialty"),
            ("data analytics specialty", "Specialty"),
            ("sap on aws specialty", "Specialty"),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO certification_mappings (cert_name, category) VALUES (?, ?)",
            default_mappings,
        )
    conn.commit()
    conn.close()


init_db()


# ===================================================================
# SELENIUM HELPERS
# ===================================================================

def _get_chrome_driver() -> webdriver.Chrome:
    """Configure and return a headless Chrome driver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    return webdriver.Chrome(options=options)


# ===================================================================
# SCRAPING LOGIC
# ===================================================================

def parse_credly_badge(url: str) -> Optional[Dict[str, str]]:
    """Extract Credly badge information from URL using Selenium."""
    driver = _get_chrome_driver()
    details = {}

    try:
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.cr-badges-full-badge__head-group")
            )
        )

        def safe_find(selector, default="N/A"):
            try:
                return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
            except Exception:
                return default

        details["badge_name"] = safe_find("div.cr-badges-full-badge__head-group")
        details["certificate_holder"] = safe_find(
            "p.badge-banner-issued-to-text__name-and-celebrator-list"
        )

        try:
            elem = driver.find_element(By.CSS_SELECTOR, "span.cr-badge-banner-expires-at-text")
            p_elem = elem.find_element(By.XPATH, "./ancestor::p")
            details["dates"] = p_elem.text.replace("\n", " ")
        except Exception:
            details["dates"] = "N/A"

    except Exception as e:
        print(f"[ERROR] Could not parse badge: {e}")
        details = None
    finally:
        driver.quit()

    return details


def scrape_credly_profile(profile_url: str = PROFILE_URL) -> str:
    """Scrape a Credly profile for all badges and insert them into the DB."""
    driver = _get_chrome_driver()
    print(f"[SCRAPER] Opening {profile_url}")

    try:
        driver.get(profile_url)
        time.sleep(5)

        # Scroll to bottom to load all badges
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(10):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Detect badge cards
        cards = driver.find_elements(By.CSS_SELECTOR, "[data-test-id='badge-card']")
        if not cards:
            return "No badges found."

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT cert_name, category FROM certification_mappings")
        mappings = {n: cat for n, cat in c.fetchall()}

        inserted = 0
        for card in cards:
            text = card.text.strip()
            if not text:
                continue

            name = text.split("\n")[0]
            category = _detect_category(name.lower(), mappings)
            status = "Expired" if "expired" in text.lower() else "Valid"

            issue_date = _extract_date(text, "issued")
            expiry_date = _extract_date(text, "expires")

            c.execute(
                """INSERT OR IGNORE INTO badges (name, category, issue_date, expiry_date, status, points)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, category, issue_date, expiry_date, status, POINTS.get(category, 0)),
            )
            if c.rowcount > 0:
                inserted += 1

        conn.commit()
        conn.close()

        return f"✅ Scraped {inserted} new badges from profile."

    except Exception as e:
        return f"Error scraping profile: {e}"
    finally:
        driver.quit()


def _detect_category(name: str, mappings: Dict[str, str]) -> str:
    """Determine badge category."""
    for cert, cat in mappings.items():
        if cert in name:
            return cat
    if "practitioner" in name:
        return "Foundational"
    if "associate" in name:
        return "Associate"
    if "professional" in name:
        return "Professional"
    if "specialty" in name or "advanced" in name:
        return "Specialty"
    return "Unknown"


def _extract_date(text: str, keyword: str) -> str:
    """Extract issue or expiry date from text."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if keyword in line.lower() and i + 1 < len(lines):
            return lines[i + 1].strip()
    return "N/A"


# ===================================================================
# LANGCHAIN TOOLS
# ===================================================================

@tool
def parse_badge_from_url(badge_url: str) -> str:
    badge = parse_credly_badge(badge_url)
    if not badge:
        return "Failed to parse badge details."
    category = _detect_category(badge["badge_name"].lower(), _get_mappings())
    points = POINTS.get(category, 0)
    return f"{badge['badge_name']} ({category}) — {points} points"


@tool
def scrape_profile_tool() -> str:
    return scrape_credly_profile(PROFILE_URL)


@tool
def get_total_points() -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(points) FROM badges WHERE status='Valid'")
    total = c.fetchone()[0] or 0
    conn.close()
    return f"⭐ Total Points: {total}"


def _get_mappings() -> Dict[str, str]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cert_name, category FROM certification_mappings")
    data = {n: c for n, c in c.fetchall()}
    conn.close()
    return data


# ===================================================================
# AGENT SETUP
# ===================================================================

TOOLS = [parse_badge_from_url, scrape_profile_tool, get_total_points]
llm = ChatGroq(groq_api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile")
agent = create_react_agent(llm, TOOLS)


# ===================================================================
# MAIN CLI
# ===================================================================

def main():
    print("\n🎓 CREDLY CERTIFICATION TRACKER\nType 'quit' to exit.\n")

    while True:
        user_input = input("💬 You: ").strip().lower()
        if user_input in {"quit", "exit"}:
            break
        response = chat_with_agent(user_input)
        print(f"🤖 {response}\n")


def chat_with_agent(message: str) -> str:
    inputs = {"messages": [HumanMessage(content=message)]}
    response_text = ""
    for chunk in agent.stream(inputs, stream_mode="values"):
        if "messages" in chunk:
            last_message = chunk["messages"][-1]
            if hasattr(last_message, "content"):
                response_text = last_message.content
    return response_text or "No response."


if __name__ == "__main__":
    main()
