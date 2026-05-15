<<<<<<< Updated upstream
# Rite Audit System

An AI-powered multi-agent system for reviewing employee expense claims. Built with LangGraph, Claude Vision, and Streamlit.

---

## Overview

Employees submit expense claims with receipts and supporting documents. The system automatically scans documents, applies company policy, and produces a decision report. An admin can then review every decision, override individual line items, and those overrides are automatically fed back as training examples for future claims.

**Decisions the system makes:**
- Full Approval — all expenses valid and within policy limits
- Partial Approval — some expenses reduced with clear reasoning
- Rejected — all submitted expenses were rejected (missing proof, duplicates, or no valid items)

---

## Project Structure

```
Rite Audit System/
|-- app.py                      # Streamlit web application (main entry point)
|-- graph.py                    # LangGraph pipeline definition
|-- admin_dashboard.py          # Admin dashboard and claim review pages
|-- requirements.txt            # Python dependencies
|-- .env                        # API keys and configuration (not committed)
|-- .env.example                # Template for required environment variables
|
|-- agents/
|   |-- state.py                # ClaimState TypedDict definition
|   |-- orchestrator.py         # Entry point — validates inputs
|   |-- ingestion_agent.py      # Document scanning via Claude Vision
|   |-- data_agent.py           # Structures receipts into expense categories
|   |-- admin_judgment_agent.py # LLM judgment using training examples
|   |-- calculator_agent.py     # Applies policy caps per category
|   |-- writer.py               # Generates final decision report
|   |-- critic_agent1.py        # Validates data completeness
|   |-- critic_agent2.py        # Verifies calculations
|   `-- critic_agent3.py        # Reviews report quality
|
|-- config/
|   `-- policy.py               # Reimbursement policy rules and limits
|
|-- integrations/
|   |-- vision_ai.py            # Claude Vision receipt scanner
|   |-- unolo_api.py            # Unolo GPS distance verification
|   `-- spinehr_api.py          # SpineHR employee profile and payroll
|
`-- utils/
    |-- auth.py                 # Authentication (password, OTP, Google, Zoho OAuth)
    |-- db.py                   # SQLite claim storage and admin review methods
    |-- training_db.py          # Training examples database for admin judgment agent
    |-- llm.py                  # Claude LLM singletons (Haiku, Sonnet)
    `-- memory.py               # Claim history memory helpers
```

---

## Pipeline Flow

```
orchestrator -> ingestion -> data -> admin_judgment -> critic1 -> calculator -> critic2 -> writer -> critic3 -> END
                                                           ^            |            ^         |         ^         |
                                                           `--revise----'            `--revise-'         `--revise-'
```

| Agent | Responsibility |
|---|---|
| orchestrator | Validates claim amount, period, and required inputs |
| ingestion | Scans receipts and PDFs using Claude Vision |
| data | Structures extracted data into expense categories |
| admin_judgment | LLM decision on each line item using 83+ training examples |
| critic1 | Validates data completeness and OCR confidence |
| calculator | Applies policy caps, computes eligible amounts per category |
| critic2 | Verifies calculations and reconciliation |
| writer | Generates the final decision report |
| critic3 | Reviews report quality; triggers rewrite if critical issues found |

Each critic agent can trigger one revision loop (max 2 revisions per stage) before passing forward.

---

## AI Model Tiers

The system uses two Claude models to balance cost and accuracy:

| Model | Used For | Why |
|---|---|---|
| claude-haiku-4-5 | Receipt image OCR | Fast and cheap — images are simple extraction tasks |
| claude-sonnet-4-6 | PDF voucher parsing, all LLM agents | More accurate for complex reasoning and structured PDFs |

Approximate cost: Rs. 12-15 per claim processed.

---

## Admin Dashboard and Training Loop

After the AI pipeline processes a claim, it appears in the Admin Dashboard with status "Pending Review". The admin can:

1. See all claims with summary stats (total claimed, system approved, admin approved)
2. Open any claim and review every line item side by side with the AI decision
3. Override the decision, approved amount, and reason for any individual item
4. Save the decisions — the total is recalculated automatically

Every override is saved to the training database. The next claim processed will include these as few-shot examples in the admin judgment agent's prompt, so the system learns from admin corrections over time.

---

## Authentication

The app requires login before any page is accessible. Supported sign-in methods:

- Email and password
- Email OTP (requires SMTP configuration)
- Phone OTP (requires Twilio configuration)
- Google OAuth (requires Google client credentials)
- Zoho OAuth (requires Zoho client credentials)

Admin access is controlled via the `ADMIN_EMPLOYEE_IDS` environment variable. Only accounts whose employee ID is listed there will see the Admin Dashboard button.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env
```

Required:
```
ANTHROPIC_API_KEY=sk-ant-...
ADMIN_EMPLOYEE_IDS=EMP001
```

All other variables are optional. The app runs in demo mode for any integration whose key is not set.

### 3. Run the application

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Access at `http://localhost:8501` on the same machine, or `http://<server-ip>:8501` from any device on the same network.

---

## Deployment (Single Device / Office Server)

This app is designed to run on a single Windows machine and be accessed by users on the local network.

**Allow port 8501 through Windows Firewall (run once as administrator):**
```bash
netsh advfirewall firewall add rule name="Streamlit" dir=in action=allow protocol=TCP localport=8501
```

**Find the server IP address:**
```bash
ipconfig
```
Look for "IPv4 Address" under your active network adapter.

**Auto-start on Windows boot via Task Scheduler:**
- Trigger: When the computer starts
- Program: path to `streamlit.exe` (usually in `Scripts/` under your Python install)
- Arguments: `run app.py --server.port 8501 --server.address 0.0.0.0`
- Start in: full path to the project folder
- Check "Run whether user is logged on or not"

No cloud account or external hosting is needed. All data stays on the device.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| ANTHROPIC_API_KEY | Yes | — | Anthropic API key |
| ADMIN_EMPLOYEE_IDS | Yes | — | Comma-separated employee IDs with admin access |
| ANTHROPIC_MODEL | No | claude-sonnet-4-6 | Override default LLM model |
| SMTP_HOST | No | — | SMTP server for email OTP |
| SMTP_PORT | No | — | SMTP port (usually 587) |
| SMTP_USER | No | — | SMTP username |
| SMTP_PASS | No | — | SMTP password or app password |
| SMTP_FROM | No | — | From address for OTP emails |
| TWILIO_ACCOUNT_SID | No | — | Twilio SID for phone OTP |
| TWILIO_AUTH_TOKEN | No | — | Twilio auth token |
| TWILIO_FROM_NUMBER | No | — | Twilio sender number |
| GOOGLE_CLIENT_ID | No | — | Google OAuth client ID |
| GOOGLE_CLIENT_SECRET | No | — | Google OAuth client secret |
| ZOHO_CLIENT_ID | No | — | Zoho OAuth client ID |
| ZOHO_CLIENT_SECRET | No | — | Zoho OAuth client secret |
| SPINEHR_API_KEY | No | — | SpineHR API key for payroll submission |
| UNOLO_API_KEY | No | — | Unolo JWT token for GPS distance verification |
| SESSION_TTL_HOURS | No | 24 | How long login sessions stay active |
| AUTH_DB_PATH | No | auth.db | Path to authentication database |

---

## Supported Expense Categories

| Category | Rate | Monthly Limit | Required Proof |
|---|---|---|---|
| Two Wheeler | Rs. 3.5/km | Rs. 5,000 | Fuel bill + Unolo GPS distance |
| Bus Travel | Actual | Rs. 3,000 | Bus ticket or receipt |
| FASTag / Toll | Actual | Rs. 2,000 | FASTag screenshot or toll receipt |
| Food | Rs. 300/day | Rs. 6,000 | Food bill or receipt |
| Hotel / Lodging | Actual | Per policy grade | Hotel bill or receipt |
| Site Deputation | Actual | Per designation | Supporting documents |
| Other | Actual | Rs. 2,000 | Receipt |

Policy limits and rates are configured in `config/policy.py`.

---

## Customising Policy

Edit `config/policy.py` to change rates, limits, or add new categories:

```python
"two_wheeler": CategoryPolicy(
    rate_per_km=4.0,
    monthly_limit=6000,
    required_proofs=["fuel_bill", "unolo_distance"],
),
```

Add a new category by adding a new key with a `CategoryPolicy` entry. The admin judgment agent and calculator will pick it up automatically on the next run.

---

## Tech Stack

- LangGraph — multi-agent orchestration with revision loops
- Claude Haiku / Sonnet — Vision OCR and LLM reasoning
- Streamlit — web interface
- SQLite — claim history, auth, and training data (three separate DB files)
- Unolo API — GPS-verified travel distance
- SpineHR API — employee profiles and payroll submission
- Python 3.11+
=======
# Rite Audit System

An AI-powered multi-agent system for reviewing employee expense claims. Built with LangGraph, Claude Vision, and Streamlit.

---

## Overview

Employees submit expense claims with receipts and supporting documents. The system automatically scans documents, applies company policy, and produces a decision report. An admin can then review every decision, override individual line items, and those overrides are automatically fed back as training examples for future claims.

**Decisions the system makes:**
- Full Approval — all expenses valid and within policy limits
- Partial Approval — some expenses reduced with clear reasoning
- Rejected — all submitted expenses were rejected (missing proof, duplicates, or no valid items)

---

## Project Structure

```
Rite Audit System/
|-- app.py                      # Streamlit web application (main entry point)
|-- graph.py                    # LangGraph pipeline definition
|-- admin_dashboard.py          # Admin dashboard and claim review pages
|-- requirements.txt            # Python dependencies
|-- .env                        # API keys and configuration (not committed)
|-- .env.example                # Template for required environment variables
|
|-- agents/
|   |-- state.py                # ClaimState TypedDict definition
|   |-- orchestrator.py         # Entry point — validates inputs
|   |-- ingestion_agent.py      # Document scanning via Claude Vision
|   |-- data_agent.py           # Structures receipts into expense categories
|   |-- admin_judgment_agent.py # LLM judgment using training examples
|   |-- calculator_agent.py     # Applies policy caps per category
|   |-- writer.py               # Generates final decision report
|   |-- critic_agent1.py        # Validates data completeness
|   |-- critic_agent2.py        # Verifies calculations
|   `-- critic_agent3.py        # Reviews report quality
|
|-- config/
|   `-- policy.py               # Reimbursement policy rules and limits
|
|-- integrations/
|   |-- vision_ai.py            # Claude Vision receipt scanner
|   |-- unolo_api.py            # Unolo GPS distance verification
|   `-- spinehr_api.py          # SpineHR employee profile and payroll
|
`-- utils/
    |-- auth.py                 # Authentication (password, OTP, Google, Zoho OAuth)
    |-- db.py                   # SQLite claim storage and admin review methods
    |-- training_db.py          # Training examples database for admin judgment agent
    |-- llm.py                  # Claude LLM singletons (Haiku, Sonnet)
    `-- memory.py               # Claim history memory helpers
```

---

## Pipeline Flow

```
orchestrator -> ingestion -> data -> admin_judgment -> critic1 -> calculator -> critic2 -> writer -> critic3 -> END
                                                           ^            |            ^         |         ^         |
                                                           `--revise----'            `--revise-'         `--revise-'
```

| Agent | Responsibility |
|---|---|
| orchestrator | Validates claim amount, period, and required inputs |
| ingestion | Scans receipts and PDFs using Claude Vision |
| data | Structures extracted data into expense categories |
| admin_judgment | LLM decision on each line item using 83+ training examples |
| critic1 | Validates data completeness and OCR confidence |
| calculator | Applies policy caps, computes eligible amounts per category |
| critic2 | Verifies calculations and reconciliation |
| writer | Generates the final decision report |
| critic3 | Reviews report quality; triggers rewrite if critical issues found |

Each critic agent can trigger one revision loop (max 2 revisions per stage) before passing forward.

---

## AI Model Tiers

The system uses two Claude models to balance cost and accuracy:

| Model | Used For | Why |
|---|---|---|
| claude-haiku-4-5 | Receipt image OCR | Fast and cheap — images are simple extraction tasks |
| claude-sonnet-4-6 | PDF voucher parsing, all LLM agents | More accurate for complex reasoning and structured PDFs |

Approximate cost: Rs. 12-15 per claim processed.

---

## Admin Dashboard and Training Loop

After the AI pipeline processes a claim, it appears in the Admin Dashboard with status "Pending Review". The admin can:

1. See all claims with summary stats (total claimed, system approved, admin approved)
2. Open any claim and review every line item side by side with the AI decision
3. Override the decision, approved amount, and reason for any individual item
4. Save the decisions — the total is recalculated automatically

Every override is saved to the training database. The next claim processed will include these as few-shot examples in the admin judgment agent's prompt, so the system learns from admin corrections over time.

---

## Authentication

The app requires login before any page is accessible. Supported sign-in methods:

- Email and password
- Email OTP (requires SMTP configuration)
- Phone OTP (requires Twilio configuration)
- Google OAuth (requires Google client credentials)
- Zoho OAuth (requires Zoho client credentials)

Admin access is controlled via the `ADMIN_EMPLOYEE_IDS` environment variable. Only accounts whose employee ID is listed there will see the Admin Dashboard button.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env
```

Required:
```
ANTHROPIC_API_KEY=sk-ant-...
ADMIN_EMPLOYEE_IDS=EMP001
```

All other variables are optional. The app runs in demo mode for any integration whose key is not set.

### 3. Run the application

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Access at `http://localhost:8501` on the same machine, or `http://<server-ip>:8501` from any device on the same network.

---

## Deployment (Single Device / Office Server)

This app is designed to run on a single Windows machine and be accessed by users on the local network.

**Allow port 8501 through Windows Firewall (run once as administrator):**
```bash
netsh advfirewall firewall add rule name="Streamlit" dir=in action=allow protocol=TCP localport=8501
```

**Find the server IP address:**
```bash
ipconfig
```
Look for "IPv4 Address" under your active network adapter.

**Auto-start on Windows boot via Task Scheduler:**
- Trigger: When the computer starts
- Program: path to `streamlit.exe` (usually in `Scripts/` under your Python install)
- Arguments: `run app.py --server.port 8501 --server.address 0.0.0.0`
- Start in: full path to the project folder
- Check "Run whether user is logged on or not"

No cloud account or external hosting is needed. All data stays on the device.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| ANTHROPIC_API_KEY | Yes | — | Anthropic API key |
| ADMIN_EMPLOYEE_IDS | Yes | — | Comma-separated employee IDs with admin access |
| ANTHROPIC_MODEL | No | claude-sonnet-4-6 | Override default LLM model |
| SMTP_HOST | No | — | SMTP server for email OTP |
| SMTP_PORT | No | — | SMTP port (usually 587) |
| SMTP_USER | No | — | SMTP username |
| SMTP_PASS | No | — | SMTP password or app password |
| SMTP_FROM | No | — | From address for OTP emails |
| TWILIO_ACCOUNT_SID | No | — | Twilio SID for phone OTP |
| TWILIO_AUTH_TOKEN | No | — | Twilio auth token |
| TWILIO_FROM_NUMBER | No | — | Twilio sender number |
| GOOGLE_CLIENT_ID | No | — | Google OAuth client ID |
| GOOGLE_CLIENT_SECRET | No | — | Google OAuth client secret |
| ZOHO_CLIENT_ID | No | — | Zoho OAuth client ID |
| ZOHO_CLIENT_SECRET | No | — | Zoho OAuth client secret |
| SPINEHR_API_KEY | No | — | SpineHR API key for payroll submission |
| UNOLO_API_KEY | No | — | Unolo JWT token for GPS distance verification |
| SESSION_TTL_HOURS | No | 24 | How long login sessions stay active |
| AUTH_DB_PATH | No | auth.db | Path to authentication database |

---

## Supported Expense Categories

| Category | Rate | Monthly Limit | Required Proof |
|---|---|---|---|
| Two Wheeler | Rs. 3.5/km | Rs. 5,000 | Fuel bill + Unolo GPS distance |
| Bus Travel | Actual | Rs. 3,000 | Bus ticket or receipt |
| FASTag / Toll | Actual | Rs. 2,000 | FASTag screenshot or toll receipt |
| Food | Rs. 300/day | Rs. 6,000 | Food bill or receipt |
| Hotel / Lodging | Actual | Per policy grade | Hotel bill or receipt |
| Site Deputation | Actual | Per designation | Supporting documents |
| Other | Actual | Rs. 2,000 | Receipt |

Policy limits and rates are configured in `config/policy.py`.

---

## Customising Policy

Edit `config/policy.py` to change rates, limits, or add new categories:

```python
"two_wheeler": CategoryPolicy(
    rate_per_km=4.0,
    monthly_limit=6000,
    required_proofs=["fuel_bill", "unolo_distance"],
),
```

Add a new category by adding a new key with a `CategoryPolicy` entry. The admin judgment agent and calculator will pick it up automatically on the next run.

---

## Tech Stack

- LangGraph — multi-agent orchestration with revision loops
- Claude Haiku / Sonnet — Vision OCR and LLM reasoning
- Streamlit — web interface
- SQLite — claim history, auth, and training data (three separate DB files)
- Unolo API — GPS-verified travel distance
- SpineHR API — employee profiles and payroll submission
- Python 3.11+
>>>>>>> Stashed changes
