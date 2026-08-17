# 🏆 LeetCode Placement Leaderboard

An elegant, real-time LeetCode tracker and ranking dashboard designed for college placement departments. This application helps training and placement officers track students' daily coding progress, organize them by batches/classes, and foster healthy peer competition to motivate students to solve more problems.

---

## ✨ Features

- **📊 Real-time Stats Syncing:** Automatically fetches public LeetCode profiles to track Easy, Medium, Hard, and total solved counts.
- **📑 Excel / CSV Test Results Uploads:** Staff can drag-and-drop or upload daily test results in Excel (`.xlsx`, `.xls`) or CSV formats with any custom column schema.
- **🔍 Live Multi-Column Sheet Search:** Real-time client-side search across all columns (names, register numbers, scores, rankings) for any uploaded test.
- **⏱️ Configurable Visibility & Auto-Cleanup:** Set test visibility duration (24h, 48h, 1 week, 1 month, or Permanent) with automated lazy-deletion of expired test data.
- **🔀 Class Options Navigation Hub:** Intuitive navigation menu branching between the LeetCode Leaderboard and Academic Test Results.
- **🏫 Class & Category Hierarchy:** Group students by department (e.g., CSE, IT), batch (e.g., 2026, 2027), or specific classes.
- **🎫 Secure Invitation System:** Admins can generate unique signup tokens so students can register themselves to specific classes.
- **🔐 Admin & Staff Dashboard:** Secure administration panel for staff to manage tests, invite links, classes, categories, and student registrations.
- **🌓 Modern Light/Dark Mode:** Sleek, modern UI with theme-switching capabilities to suit student preferences.
- **⚡ Serverless-Ready Architecture:** Fully optimized for seamless deployments on Vercel Serverless Functions with Supabase.

---

## 🛠️ Tech Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Data Processing:** [Pandas](https://pandas.pydata.org/), [OpenPyXL](https://openpyxl.readthedocs.io/)
- **Database:** [Supabase](https://supabase.com/) / PostgreSQL
- **ORM:** [SQLAlchemy](https://www.sqlalchemy.org/) (JSONB support)
- **Frontend:** HTML5, Jinja2 Templates, Vanilla CSS, JavaScript
- **Auth:** Supabase Auth (JWT validated)
- **Deployment:** Vercel (Serverless)

---

## 📂 Project Structure

```text
├── api/
│   └── index.py            # Vercel Serverless entrypoint
├── routers/
│   ├── admin_routes.py     # Admin panel, test uploads, invites, & student management
│   ├── auth_routes.py      # Authentication (Supabase integration)
│   └── public_routes.py    # Public leaderboard & test results views
├── static/
│   ├── css/
│   │   └── main.css        # Custom styles & design tokens
│   ├── js/
│   │   └── app.js          # Client-side interactivity
│   └── logo.jpg            # College/Platform logo
├── templates/
│   ├── admin/              # Admin dashboard templates (classes, staff, tests)
│   ├── public_views/       # Public-facing views (index, class_menu, leaderboard, test_results)
│   ├── base.html           # Core layout containing navbar, sidebar, theme controls
│   ├── join.html           # Student self-registration invite page
│   └── login.html          # Staff login page
├── auth.py                 # Core authentication helper functions
├── database.py             # SQLAlchemy configuration, models & database sessions
├── main.py                 # Main FastAPI application definition
├── utils.py                # LeetCode statistics scraper & points calculator
├── vercel.json             # Vercel deployment routing configuration
└── requirements.txt        # Application dependencies
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description |
| :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string (use Supabase **Transaction Pooler** for Vercel) |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase Anon (public) API Key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Service Role Key (used for admin operations like creating users) |
| `SUPABASE_JWT_SECRET` | Supabase JWT Secret (for verifying cookies/sessions) |
| `ADMIN_EMAILS` | Comma-separated list of emails authorized as admins (e.g., `admin@college.edu,staff@college.edu`) |
| `SESSION_SECRET` | Random string for securing browser sessions |

---

## 🚀 Local Development

### 1. Prerequisites
Make sure you have **Python 3.12** installed on your system.

### 2. Set Up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup & Migrations
The database schema will automatically initialize when you run the application locally. Alternatively, you can apply `migration.sql` to your PostgreSQL database.

To verify database connectivity locally, run:
```bash
python check_db.py
```

### 5. Start the Application
```bash
uvicorn main:app --reload
```
Open your browser and navigate to `http://127.0.0.1:8000`.

---

## ☁️ Vercel Deployment

This project is configured to run out-of-the-box on Vercel using modern **Zero-Config** rewrites.

### 1. Connect to GitHub
Push this repository to your GitHub account:
```bash
git add -A
git commit -m "Prepare deployment"
git push
```

### 2. Import to Vercel
1. Log in to the [Vercel Dashboard](https://vercel.com).
2. Click **Add New** > **Project** and import your repository.
3. In the **Environment Variables** configuration, add all variables defined in `.env.example`.

> [!IMPORTANT]
> **Use the Supabase Pooler URL:** Because Vercel uses ephemeral Serverless Functions, you must set `DATABASE_URL` to Supabase's **Transaction Pooler** connection string (typically port `6543`) rather than the direct database port (`5432`).
>
> **SSL mode:** Append `?sslmode=require` to the end of your `DATABASE_URL` to ensure a secure, encrypted connection to Supabase.
>
> Example:
> `postgresql://postgres.xxxxxx:password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require`

### 3. Deploy
Click **Deploy**. Vercel will build the serverless package and serve your static assets (`/static`) automatically via its global Edge Network.
