#  Credly Certification Tracker – LangGraph + Groq API

Track your AWS (or other) certifications from Credly, compute points based on certification level, and interact using LLM-powered tools via LangGraph.

---

##  Features

-  **LLM Agent with LangGraph + Groq (LLaMA 3 70B)**
-  **Tool calling support** for scraping, parsing, querying, and calculating
-  **Selenium-based Credly badge parser**
-  **SQLite database** to store and manage badge info
-  **Points system** to compute certification value
-  CLI interface (terminal-based) for local usage

---

###  LLM Agent with LangGraph + Groq (LLaMA 3 70B)

This project integrates [LangGraph](https://docs.langchain.com/langgraph/) — a state-machine framework for LLMs — with [LangChain](https://www.langchain.com/) and the [Groq API](https://groq.com/), using **Meta’s LLaMA 3 70B Versatile** model.

- Enables fast, structured, and dynamic agent behavior
- Supports tool chaining and control flow
- Empowers the agent to reason, plan, and execute tools based on your prompts

> Groq provides ultra-fast inference with token speeds exceeding 500 tokens/sec.

---

###  Tool Calling Support (Dynamic Function Execution)

The agent can **autonomously invoke Python tools** based on your query, thanks to LangChain’s `@tool` decorators.

Available tools include:

-  `parse_badge_from_url`: Parse a single badge from its Credly URL
-  `scrape_credly_profile`: Scrape all badges from a user's public Credly profile
-  `get_my_certifications`: View all certifications and their points
-  `calculate_certification_points`: Estimate how many points a new certification will earn
-  `get_total_points`: Get your current total valid certification points
-  `show_points_table`: Show the entire points system for reference

> The agent understands which tool to call without explicit instructions — just ask naturally.

---

###  Selenium-Based Credly Badge Parser

No API? No problem. This project uses **Selenium with ChromeDriver** to extract badge data from Credly pages.

- Works with both individual badge URLs and full profiles
- Parses badge title, cert holder name, issue/expiry dates, and status
- Scrolls to load all badges dynamically on profile pages
- Bypasses bot detection with custom headers and stealth options

> Supports real-time scraping from public profiles and badges.

---

###  SQLite Database to Store and Manage Badge Info

Data is stored persistently using **SQLite**, including:

-  Badge name
-  Certification category (e.g., Associate, Specialty)
-  Issue & Expiry Dates
-  Status (Valid / Expired)
-  Points per certification

Additionally, a separate table maps certification names to categories, improving classification accuracy.

> All parsed or scraped data is cached locally to avoid re-parsing.

---

###  Points System for Certification Levels

Certifications are scored based on their **category**, following this table:

| Category     | Points |
|--------------|--------|
| Foundational | 10     |
| Associate    | 5      |
| Professional | 10     |
| Specialty    | 10     |
| Other/Unknown| 2.5    |

Used to:

- Quantify your certification progress
- Predict point increase from upcoming exams
- Motivate team members or gamify internal skill tracking

> You can modify point values by editing the `POINTS` dictionary in the code.

---

###  Command-Line Interface (CLI) for Local Use

Run the tool locally in your terminal:

- Type prompts like:
  - `"How many points do I have?"`
  - `"If I get AWS Developer Associate?"`
  - `"https://www.credly.com/badges/..."`
- Responses are **numerical** — perfect for:
  - Scripts
  - Integrations
  - Terminal automation

Special handling for:

- Total point queries
- Badge parsing from URL
- Certification point predictions

> Designed for **"points-only" output** to enable easy integrations.

---


