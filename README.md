# Langgraph Cert Credit-point agent

# Goal 
To provide an automated way to track, validate, and assign points to professional certifications — from **Credly URLs** .

# User Interaction 
How Users Interact with the Agent

## Step 1:Submit a Query
Users can ask following types of questions:

Query Type 1: Check Credit Points for a Specific Badge (Expired)

User: "How many credit points can I get for https://www.credly.com/badges/e192db17-f8c5-46aa-8f99-8a565223f1d6?"

Agent Response: "Sorry, your cert has expired. So you won't get any credit points. 
But otherwise you would have stood to obtain 5 credit points for your Hashicorp Terraform Cert"

Query Type 2: Check Credit Points for a Valid Badge

User: "What about https://www.credly.com/badges/90ee2ee9-f6cf-4d9b-8a52-f631d8644d58?"

Agent Response: "I see that this is an AWS AI Practitioner cert. And it is still valid. 
So you can be granted 2.5 credit points for it."

## Step 2: View Results
The agent provides:-

Credit Points: Numerical value based on certification tier

Certification Name: Extracted from the badge or query

Validity Status: Whether the certification is currently valid

Reasoning: Clear explanation of the decision





## Features

- Extracts certification data from Credly URLs

- Validates certification expiry dates

- Calculates credit points based on certification tier

- Handles both URL queries and hypothetical questions

- Powered by Groq's  model

## Setup

### Prerequisites
- Python 3.8+
- Groq API Key

## Usage

### With LangGraph Studio
```bash
langgraph dev
```

### Programmatically
```python
from credly_updated import run_agent

response = run_agent("How many credit points can I get for https://www.credly.com/badges/...")
print(response)
```


## Query & Traces (Reference Screenshots)
---<img width="1901" height="929" alt="image" src="https://github.com/user-attachments/assets/3c4c4a72-5034-4f0c-a418-c51515731d43" />

## Credit Point System

| Certification Type | Points |
|-------------------|--------|
| Professional or Specialty | 10 |
| Associate or Hashicorp | 5 |
| Anything Else | 2.5 |
