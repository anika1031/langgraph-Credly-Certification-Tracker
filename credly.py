import os
import sqlite3
from typing import Dict
from datetime import datetime
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from time import sleep
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# Get Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("Please set GROQ_API_KEY in your .env file")

# --- Points system per certification level ---
POINTS = {
    "Foundational": 10,
    "Associate": 5,
    "Professional": 10,
    "Specialty": 10
}

# --- User's public Credly profile URL ---
PROFILE_URL = "https://www.credly.com/users/cladius/badges"

# ========== DATABASE SETUP ==========
def init_db():
    """Initialize the SQLite database with badges and certification mappings tables."""
    conn = sqlite3.connect("credly_data.db")
    c = conn.cursor()
    
    # Badges table
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
    
    # Certification mappings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS certification_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cert_name TEXT UNIQUE,
            category TEXT
        )
    """)
    
    conn.commit()
    
    # Insert default AWS certification mappings if table is empty
    c.execute("SELECT COUNT(*) FROM certification_mappings")
    if c.fetchone()[0] == 0:
        default_mappings = [
            ("aws certified cloud practitioner", "Foundational"),
            ("cloud practitioner", "Foundational"),
            ("aws certified solutions architect associate", "Associate"),
            ("solutions architect associate", "Associate"),
            ("aws certified developer associate", "Associate"),
            ("developer associate", "Associate"),
            ("aws certified sysops administrator associate", "Associate"),
            ("sysops administrator associate", "Associate"),
            ("sysops associate", "Associate"),
            ("aws certified solutions architect professional", "Professional"),
            ("solutions architect professional", "Professional"),
            ("aws certified devops engineer professional", "Professional"),
            ("devops engineer professional", "Professional"),
            ("devops professional", "Professional"),
            ("aws certified advanced networking specialty", "Specialty"),
            ("advanced networking specialty", "Specialty"),
            ("aws certified security specialty", "Specialty"),
            ("security specialty", "Specialty"),
            ("aws certified machine learning specialty", "Specialty"),
            ("machine learning specialty", "Specialty"),
            ("aws certified database specialty", "Specialty"),
            ("database specialty", "Specialty"),
            ("aws certified data analytics specialty", "Specialty"),
            ("data analytics specialty", "Specialty"),
            ("aws certified sap on aws specialty", "Specialty"),
            ("sap on aws specialty", "Specialty")
        ]
        c.executemany("""
            INSERT OR IGNORE INTO certification_mappings (cert_name, category)
            VALUES (?, ?)
        """, default_mappings)
        conn.commit()
    
    conn.close()

# Initialize database on module load
init_db()

# ========== SELENIUM BADGE PARSER ==========

def parse_credly_badge(url: str) -> dict:
    """
    Parse Credly badge details from the given URL using Selenium
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        print(f"Loading badge page: {url}")
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.cr-badges-full-badge__head-group"))
        )
        
        badge_details = {}
        
        # Extract badge name
        try:
            badge_name = driver.find_element(By.CSS_SELECTOR, "div.cr-badges-full-badge__head-group").text
            badge_details['badge_name'] = badge_name
        except:
            badge_details['badge_name'] = "N/A"
                
        # Extract cert holder name
        try:
            cert_holder = driver.find_element(By.CSS_SELECTOR, "p.badge-banner-issued-to-text__name-and-celebrator-list").text
            badge_details['certificate_holder'] = cert_holder
        except:
            badge_details['certificate_holder'] = "N/A"

        # Extract issue date and expiration date
        try:
            detail_items = driver.find_elements(By.CSS_SELECTOR, "span.cr-badge-banner-expires-at-text")
            p_element = detail_items[0].find_element(By.XPATH, "./ancestor::p")
            full_text = p_element.text.replace("\n", " ")
            badge_details['dates'] = full_text
        except:
            badge_details['dates'] = "N/A"

        return badge_details    
    except Exception as e:
        print(f"Error parsing badge: {str(e)}")
        return None
    finally:
        driver.quit()

# ========== LANGCHAIN TOOLS ==========

@tool
def parse_badge_from_url(badge_url: str) -> str:
    """
    Parse a single Credly badge URL and extract details including badge name, 
    certificate holder, and dates. Also calculates points for the certification.
    
    Args:
        badge_url: The full Credly badge URL (e.g., https://www.credly.com/badges/xxx/public_url)
        
    Returns:
        Formatted string with badge details and calculated points
    """
    print(f"[TOOL CALL] parse_badge_from_url called with: badge_url={badge_url}")
    
    try:
        # Parse the badge using Selenium
        badge_info = parse_credly_badge(badge_url)
        
        if not badge_info:
            return " Failed to parse badge details from the URL. Please check if the URL is correct and accessible."
        
        badge_name = badge_info.get('badge_name', 'N/A')
        cert_holder = badge_info.get('certificate_holder', 'N/A')
        dates = badge_info.get('dates', 'N/A')
        
        # Determine category and points
        conn = sqlite3.connect("credly_data.db")
        c = conn.cursor()
        c.execute("SELECT cert_name, category FROM certification_mappings")
        cert_mappings = {row[0]: row[1] for row in c.fetchall()}
        
        category = "Unknown"
        badge_lower = badge_name.lower()
        
        # Check against database mappings
        for cert_name, cat in cert_mappings.items():
            if cert_name in badge_lower:
                category = cat
                break
        
        # Fallback to keyword matching
        if category == "Unknown":
            if "practitioner" in badge_lower or "foundational" in badge_lower:
                category = "Foundational"
            elif "professional" in badge_lower:
                category = "Professional"
            elif "specialty" in badge_lower or "advanced" in badge_lower:
                category = "Specialty"
            elif "associate" in badge_lower:
                category = "Associate"
        
        # Determine points based on new rules
        if category in ["Professional", "Specialty"]:
            points = 10
            cert_type = "Any Professional or Specialty"
        elif category == "Associate":
            points = 5
            cert_type = "Any associate or Hashicorp"
        elif category == "Foundational":
            points = 10
            cert_type = "Any Foundational"
        else:
            points = 2.5
            cert_type = "Anything else"
        
        conn.close()
        
        # Format response
        response = "\n CREDLY BADGE DETAILS\n"
        response += "="*60 + "\n\n"
        response += f" Badge Name: {badge_name}\n"
        response += f" Certificate Holder: {cert_holder}\n"
        response += f" Dates: {dates}\n"
        response += f" Category: {category}\n\n"
        
        response += "| Cert | Point |\n"
        response += "|------|-------|\n"
        response += f"| {cert_type} | {points} |\n\n"
        
        response += f" Source: {badge_url}\n"
        
        print("[TOOL RESULT] parse_badge_from_url returned successfully")
        return response
        
    except Exception as e:
        error_msg = f"Error parsing badge: {str(e)}"
        print("[TOOL ERROR]", error_msg)
        return error_msg

@tool
def scrape_credly_profile(profile_url: str = PROFILE_URL) -> str:
    """
    Scrape a Credly profile and store all badges in the database.
    
    Args:
        profile_url: The Credly profile URL to scrape (defaults to configured URL)
        
    Returns:
        A summary of scraped badges with counts by category
    """
    print(f"[TOOL CALL] scrape_credly_profile called with: profile_url={profile_url}")
    
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(options=options)
        driver.get(profile_url)
        sleep(5)
        
        # Scroll to load all badges
        last_height = driver.execute_script("return document.body.scrollHeight")
        attempts = 0
        max_attempts = 10
        
        while attempts < max_attempts:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            attempts += 1
        
        # Find badge cards
        selectors = [
            "[data-test-id='badge-card']",
            "div.cr-standard-grid__item",
            "div[class*='BadgeCard']",
            "div[class*='badge']",
            "a[href*='/badges/']"
        ]
        
        cards = []
        for selector in selectors:
            cards = driver.find_elements(By.CSS_SELECTOR, selector)
            if cards:
                break
        
        if not cards:
            driver.quit()
            return "No badge cards found on the profile page."
        
        # Get certification mappings
        conn = sqlite3.connect("credly_data.db")
        c = conn.cursor()
        c.execute("SELECT cert_name, category FROM certification_mappings")
        cert_mappings = {row[0]: row[1] for row in c.fetchall()}
        
        badges_scraped = 0
        category_counts = {cat: 0 for cat in POINTS.keys()}
        category_counts["Unknown"] = 0
        
        for card in cards:
            try:
                card_text = card.text.strip()
                if not card_text:
                    continue
                
                # Extract badge name
                name = None
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'span']:
                    try:
                        elements = card.find_elements(By.TAG_NAME, tag)
                        for elem in elements:
                            text = elem.text.strip()
                            if text and 10 < len(text) < 200:
                                name = text
                                break
                        if name:
                            break
                    except:
                        continue
                
                if not name:
                    continue
                
                # Extract dates
                issue_date = "Unknown"
                expiry_date = "N/A"
                lines = card_text.split('\n')
                
                for i, line in enumerate(lines):
                    if 'issued' in line.lower():
                        if i + 1 < len(lines):
                            issue_date = lines[i + 1].strip()
                    if 'expires' in line.lower():
                        if i + 1 < len(lines):
                            expiry_date = lines[i + 1].strip()
                
                # Determine category
                category = "Unknown"
                name_lower = name.lower()
                
                for cert_name, cat in cert_mappings.items():
                    if cert_name in name_lower:
                        category = cat
                        break
                
                if category == "Unknown":
                    if "practitioner" in name_lower:
                        category = "Foundational"
                    elif "associate" in name_lower:
                        category = "Associate"
                    elif "professional" in name_lower:
                        category = "Professional"
                    elif "specialty" in name_lower:
                        category = "Specialty"
                
                # Determine status
                status = "Valid"
                if "expired" in card_text.lower():
                    status = "Expired"
                
                # Insert badge
                c.execute("""
                    INSERT OR IGNORE INTO badges (name, category, issue_date, expiry_date, status, points)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, category, issue_date, expiry_date, status, POINTS.get(category, 0)))
                
                if c.rowcount > 0:
                    badges_scraped += 1
                    category_counts[category] += 1
                
            except Exception as e:
                continue
        
        conn.commit()
        conn.close()
        driver.quit()
        
        # Build response
        response = f"✅ Successfully scraped {badges_scraped} badges from Credly profile\n\n"
        response += "📊 Breakdown by Category:\n"
        for cat, count in category_counts.items():
            if count > 0:
                points = POINTS.get(cat, 0)
                response += f"  • {cat}: {count} badges ({count * points} points)\n"
        
        print("[TOOL RESULT] scrape_credly_profile returned:", response)
        return response
        
    except Exception as e:
        error_msg = f"Error scraping Credly profile: {str(e)}"
        print("[TOOL ERROR]", error_msg)
        return error_msg

@tool
def get_my_certifications() -> str:
    """
    Get all certifications from the database with their details and points.
    
    Returns:
        A formatted list of all certifications with status and points
    """
    print("[TOOL CALL] get_my_certifications called")
    
    try:
        conn = sqlite3.connect("credly_data.db")
        c = conn.cursor()
        c.execute("SELECT name, category, issue_date, expiry_date, status, points FROM badges ORDER BY points DESC, name")
        badges = c.fetchall()
        conn.close()
        
        if not badges:
            return "No certifications found in database. Please run scrape_credly_profile first."
        
        valid_count = sum(1 for b in badges if b[4] == "Valid")
        expired_count = len(badges) - valid_count
        total_points = sum(b[5] for b in badges if b[4] == "Valid")
        
        response = f"📋 YOUR CERTIFICATIONS ({len(badges)} total)\n"
        response += f"✅ Valid: {valid_count} | ❌ Expired: {expired_count} | ⭐ Total Points: {total_points}\n\n"
        
        for i, (name, category, issue_date, expiry_date, status, points) in enumerate(badges, 1):
            status_icon = "✅" if status == "Valid" else "❌"
            response += f"{i}. {status_icon} {name}\n"
            response += f"   Category: {category} | Points: {points}\n"
            response += f"   Issued: {issue_date} | Expires: {expiry_date}\n\n"
        
        print("[TOOL RESULT] get_my_certifications returned first 200 chars")
        return response
        
    except Exception as e:
        error_msg = f"Error retrieving certifications: {str(e)}"
        print("[TOOL ERROR]", error_msg)
        return error_msg

@tool
def calculate_certification_points(certification_name: str) -> str:
    """
    Calculate how many points a specific certification would give you.
    Useful for answering "If I get X certification, how many points will I get?"
    
    Args:
        certification_name: The name of the certification to look up
        
    Returns:
        Points for that certification in a formatted table
    """
    print(f"[TOOL CALL] calculate_certification_points called with: certification_name={certification_name}")
    
    try:
        # Get certification mappings
        conn = sqlite3.connect("credly_data.db")
        c = conn.cursor()
        c.execute("SELECT cert_name, category FROM certification_mappings")
        cert_mappings = {row[0]: row[1] for row in c.fetchall()}
        
        # Determine category
        category = None
        cert_lower = certification_name.lower()
        
        for cert_name, cat in cert_mappings.items():
            if cert_name in cert_lower:
                category = cat
                break
        
        if not category:
            # Fallback to keyword matching
            if "practitioner" in cert_lower or "foundational" in cert_lower:
                category = "Foundational"
            elif "professional" in cert_lower:
                category = "Professional"
            elif "specialty" in cert_lower or "advanced" in cert_lower:
                category = "Specialty"
            elif "associate" in cert_lower:
                category = "Associate"
            else:
                category = "Other"
        
        # Determine points based on category
        if category in ["Professional", "Specialty"]:
            points = 10
            cert_type = "Any Professional or Specialty"
        elif category == "Associate":
            points = 5
            cert_type = "Any associate or Hashicorp"
        elif category == "Foundational":
            points = 10
            cert_type = "Any Foundational"
        else:
            points = 2.5
            cert_type = "Anything else"
        
        # Get current total
        c.execute("SELECT SUM(points) FROM badges WHERE status = 'Valid'")
        result = c.fetchone()
        current_total = result[0] if result[0] else 0
        new_total = current_total + points
        
        conn.close()
        
        # Format response in table format
        response = f"\n🎯 Certification: {certification_name}\n"
        response += f"📂 Category: {category}\n\n"
        response += "| Cert | Point |\n"
        response += "|------|-------|\n"
        response += f"| {cert_type} | {points} |\n\n"
        
        response += f"📈 Your Status:\n"
        response += f"  • Current Points: {current_total}\n"
        response += f"  • After Earning: {new_total}\n"
        response += f"  • Increase: +{points}\n"
        
        print("[TOOL RESULT] calculate_certification_points returned:", response)
        return response
        
    except Exception as e:
        error_msg = f"Error calculating points: {str(e)}"
        print("[TOOL ERROR]", error_msg)
        return error_msg

@tool
def get_total_points() -> str:
    """
    Get the total points from all valid certifications.
    
    Returns:
        Total points and breakdown by category
    """
    print("[TOOL CALL] get_total_points called")
    
    try:
        conn = sqlite3.connect("credly_data.db")
        c = conn.cursor()
        c.execute("SELECT category, points FROM badges WHERE status = 'Valid'")
        badges = c.fetchall()
        conn.close()
        
        if not badges:
            return "No valid certifications found. Total points: 0"
        
        total_points = sum(b[1] for b in badges)
        category_points = {}
        
        for category, points in badges:
            category_points[category] = category_points.get(category, 0) + points
        
        response = f"⭐ TOTAL POINTS: {total_points}\n\n"
        response += "📊 Breakdown by Category:\n"
        for cat, pts in sorted(category_points.items(), key=lambda x: x[1], reverse=True):
            response += f"  • {cat}: {pts} points\n"
        
        print("[TOOL RESULT] get_total_points returned:", response)
        return response
        
    except Exception as e:
        error_msg = f"Error getting total points: {str(e)}"
        print("[TOOL ERROR]", error_msg)
        return error_msg

@tool
def show_points_table() -> str:
    """
    Show the complete certification points table with all categories and their points.
    Use this when user asks about the points system or wants to see the full table.
    
    Returns:
        A formatted table showing all certification types and their points
    """
    print("[TOOL CALL] show_points_table called")
    
    response = "\n CERTIFICATION POINTS TABLE\n\n"
    response += "| Cert | Point |\n"
    response += "|------|-------|\n"
    response += "| Any Professional or Specialty | 10 |\n"
    response += "| Any associate or Hashicorp | 5 |\n"
    response += "| Anything else | 2.5 |\n"
    
    print("[TOOL RESULT] show_points_table returned")
    return response

# ========== LANGRAPH AGENT SETUP ==========

# List of all tools
tools = [
    parse_badge_from_url,
    scrape_credly_profile,
    get_my_certifications,
    calculate_certification_points,
    get_total_points,
    show_points_table
]

# Initialize LLM
llm = ChatGroq(groq_api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile")

# Create the agent
graph = create_react_agent(llm, tools)

# ========== MAIN INTERACTION FUNCTION ==========

def chat_with_agent(user_message: str) -> str:
    """
    Send a message to the agent and get a response.
    
    Args:
        user_message: The user's question or command
        
    Returns:
        The agent's response
    """
    print(f"\n{'='*60}")
    print(f"USER: {user_message}")
    print(f"{'='*60}\n")
    
    inputs = {"messages": [HumanMessage(content=user_message)]}
    
    response_text = ""
    for chunk in graph.stream(inputs, stream_mode="values"):
        if "messages" in chunk:
            last_message = chunk["messages"][-1]
            if hasattr(last_message, 'content') and last_message.content:
                response_text = last_message.content
    
    print(f"\n{'='*60}")
    print(f"AGENT: {response_text}")
    print(f"{'='*60}\n")
    
    return response_text

# ========== CLI INTERFACE ==========

def main():
    """Main CLI interface for the Credly certification tracker."""
    # Minimal header: do not show example options. The CLI will return only credit points
    print("\n" + "="*60)
    print("CREDLY CERTIFICATION TRACKER - POINTS ONLY MODE")
    print("="*60)
    print("Type 'quit' or 'exit' to end the session.\n")
    print("="*60 + "\n")
    
    while True:
        try:
            user_input = input("💬 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("\n👋 Goodbye! Your certifications are safely stored in the database.\n")
                break

            # Handle common intents directly and output only the numeric points (or simple number)
            li = user_input.lower()

            # 1) Total points
            if 'total' in li and 'point' in li:
                resp = get_total_points()
                m = re.search(r"TOTAL POINTS[:\s]*([0-9]+(?:\.[0-9]+)?)", resp, re.IGNORECASE)
                if not m:
                    m = re.search(r"Total Points[:\s]*([0-9]+(?:\.[0-9]+)?)", resp, re.IGNORECASE)
                if m:
                    print(m.group(1))
                else:
                    # Fallback: try any 'points' number
                    m2 = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*points", resp, re.IGNORECASE)
                    print(m2.group(1) if m2 else "0")
                continue

            # 2) If user asks how many points for a certification
            if 'how many point' in li or (li.startswith('if') and 'point' in li):
                resp = calculate_certification_points(user_input)
                # Try to extract the single points number from the table
                m = re.search(r"\|[^\n]*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|", resp)
                if not m:
                    m = re.search(r"Increase:\s*\+([0-9]+(?:\.[0-9]+)?)", resp)
                if m:
                    print(m.group(1))
                else:
                    # Last fallback: any number followed by 'point(s)'
                    m2 = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*points", resp, re.IGNORECASE)
                    print(m2.group(1) if m2 else "0")
                continue

            # 3) Parse a badge URL and return its points only
            url_match = re.search(r"https?://[\w\-\.\/:?=&%]+credly\.com[\w\-\.\/:?=&%]*", user_input, re.IGNORECASE)
            if url_match:
                url = url_match.group(0)
                resp = parse_badge_from_url(url)
                # extract points from the returned markdown table
                m = re.search(r"\|[^\n]*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|", resp)
                if m:
                    print(m.group(1))
                else:
                    m2 = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*points", resp, re.IGNORECASE)
                    print(m2.group(1) if m2 else "0")
                continue

            # 4) Fallback: ask the agent but only print numbers that look like points
            response = chat_with_agent(user_input)
            matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(?:points|point)", response, re.IGNORECASE)
            if matches:
                # Print unique numbers separated by commas (most relevant: first match)
                unique = []
                for x in matches:
                    if x not in unique:
                        unique.append(x)
                print(', '.join(unique))
            else:
                # If nothing looks like points, return 0 to keep outputs strictly 'points only'
                print("0")
            
        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!\n")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")
            continue

if __name__ == "__main__":
    main()