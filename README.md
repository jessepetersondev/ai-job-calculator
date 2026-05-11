# The Great Replacement — AI Job Vulnerability Calculator

A full-stack monetization layer for the AI Job Atlas. Users enter their job + state,
get a free personalized vulnerability score, and can buy a $9 PDF report with their
5-year trajectory, adjacent safer roles, recommended skills, and a 90-day pivot plan.

## Stack

- **Backend**: Flask (single `app.py`, ~250 LOC)
- **Frontend**: server-rendered Jinja templates + vanilla JS (no React build step)
- **Data**: 104 curated occupations + 51 states in `data/occupations.json`
- **Payments**: Stripe Checkout (test + live modes)
- **PDF**: ReportLab (pure Python — no Chromium, no LaTeX, no binary deps)
- **Email**: Resend API (preferred) or SMTP fallback
- **Deploy**: gunicorn-ready. Works on Render, Railway, Fly.io, Heroku, or any Linux box.

## Quick start (local dev)

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Set up env
cp .env.example .env
# edit .env — add at minimum STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY
# (test keys are fine for development)

# 3. Run
python app.py
```

Open http://localhost:5000

## Testing Stripe payments locally

1. Install the Stripe CLI: https://stripe.com/docs/stripe-cli
2. In a separate terminal:
   ```
   stripe listen --forward-to localhost:5000/webhook/stripe
   ```
3. Copy the `whsec_...` value it prints into `STRIPE_WEBHOOK_SECRET` in `.env`.
4. Use test card `4242 4242 4242 4242` (any future date, any CVC, any ZIP).
5. The PDF will be generated on webhook receipt and saved to `data/sent_reports/`
   (until you configure Resend or SMTP, at which point it'll be emailed).

## File layout

```
ai-job-calculator/
├── app.py                  # Flask app, all routes
├── build_data.py           # regenerates data/occupations.json
├── requirements.txt
├── .env.example
├── data/
│   └── occupations.json    # 104 occupations + 51 states + skill resources
├── templates/
│   ├── _base.html
│   ├── atlas.html          # landing page (drives traffic to /calculator)
│   ├── calculator.html     # input form + scorecard
│   ├── success.html        # post-payment
│   └── cancel.html
├── static/
│   ├── css/style.css
│   └── js/calculator.js
└── lib/
    ├── scorer.py           # scoring + autocomplete logic
    ├── pdf_generator.py    # 5-page report generator
    └── email_sender.py     # Resend + SMTP delivery
```

## Routes

| Route                     | Method | Purpose                                              |
|---------------------------|--------|------------------------------------------------------|
| `/`                       | GET    | Landing page (atlas) with CTA to calculator          |
| `/calculator`             | GET    | Input form                                           |
| `/api/occupations?q=`     | GET    | Autocomplete                                         |
| `/api/calculate`          | POST   | Returns personalized score JSON                      |
| `/api/checkout`           | POST   | Creates Stripe Checkout session, returns redirect URL|
| `/webhook/stripe`         | POST   | Stripe webhook → generates PDF + emails it           |
| `/success`                | GET    | Post-payment success page                            |
| `/cancel`                 | GET    | Post-payment cancel page                             |
| `/healthz`                | GET    | Healthcheck (for monitors)                           |

## Deploying to production

### Render.com (easiest)

1. Push this repo to GitHub.
2. New → Web Service → connect repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add all env vars from `.env` in the Render dashboard.
6. Set `APP_BASE_URL` to your Render URL (e.g. `https://yourapp.onrender.com`)
7. Configure Stripe webhook in the Stripe dashboard pointing at
   `https://yourapp.onrender.com/webhook/stripe`, then paste the signing secret
   into `STRIPE_WEBHOOK_SECRET`.

### Custom domain

1. Point your domain at Render/Railway/wherever via CNAME.
2. Update `APP_BASE_URL` to `https://yourdomain.com`.
3. Update the Stripe webhook URL to match.

## Customizing the data

Edit `build_data.py` to add/edit occupations. Each occupation has:
- `title`, `aliases` (for autocomplete)
- `job_loss_pct`, `exposure`, `augmentation` (numeric scoring)
- `category`, `physicality`
- `adjacent_safer` (3 safer adjacent roles)
- `at_risk_tasks` (what AI is replacing)
- `skills_to_learn` (with affiliate links via `SKILL_RESOURCES`)

After editing, run:
```bash
python build_data.py
```
Then restart the Flask server.

## Marketing / distribution checklist

The atlas + calculator only matter if people find them. After deploying:

- [ ] **Show HN** with the atlas as the lede ("we built an atlas of AI job risk")
- [ ] **Product Hunt** launch (Tuesday is the conventional day)
- [ ] **X/Twitter thread**: top 10 vulnerable jobs with screenshots, "find yours →"
- [ ] **LinkedIn** long-form post + comments under layoff news posts
- [ ] **Reddit**: r/jobs, r/cscareerquestions, r/AskHR — DM mods first
- [ ] **Career coaches**: offer 30% affiliate revshare for traffic via UTM
- [ ] **Email creator outreach**: AI-anxiety newsletter audiences (Substack)

## Revenue model

- **$9 PDF report** — primary conversion (current setup)
- **Skill course affiliate links** — passive income inside every report
- **Future: $19/quarter subscription** — quarterly re-check email (highest LTV play)
- **Future: B2B HR tier** — "assess your workforce" for $X/seat (highest ARPU)

## Caveats

- The 104-occupation dataset is curated, not the full 784-occupation Tufts dataset
  (which is in a downloadable XLSX they don't yet expose via API). Replace with
  the full dataset when ready by re-implementing `build_data.py`.
- All numbers are scenarios, not forecasts. The PDF report says this explicitly
  in the methodology section. Don't oversell certainty.
- Email deliverability matters. Use a verified domain in Resend, set up SPF/DKIM/DMARC.
  Test from multiple inbox providers before launching.

## License

Your code, your call. The Tufts data is published research; cite it in any
public-facing materials.
