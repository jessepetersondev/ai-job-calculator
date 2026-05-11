"""
AI Job Vulnerability Calculator — Flask backend
================================================
Routes:
  /                   landing (atlas + CTA)
  /calculator         input form
  /api/calculate      POST -> personalized score
  /api/checkout       POST -> Stripe checkout session
  /success            post-payment success
  /cancel             post-payment cancel
  /webhook/stripe     Stripe webhook -> generates PDF + emails it
  /api/occupations    GET autocomplete list

Env vars (see .env.example):
  STRIPE_SECRET_KEY
  STRIPE_PUBLISHABLE_KEY
  STRIPE_WEBHOOK_SECRET
  STRIPE_PRICE_ID            (or use ad-hoc price_data)
  RESEND_API_KEY             (or leave blank to use SMTP)
  EMAIL_FROM                 e.g. "Atlas Reports <reports@yourdomain.com>"
  APP_BASE_URL               https://yourdomain.com  (used in Stripe redirects)
  REPORT_PRICE_CENTS         default 900
"""

import os
import json
import hmac
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, abort, send_file, make_response
)
from dotenv import load_dotenv
import stripe

from lib.scorer import score_for, rank_among, search_occupations
from lib.pdf_generator import build_pdf
from lib.email_sender import send_report_email

# ─── Setup ──────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("calculator")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

# Stripe config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUB_KEY     = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID    = os.getenv("STRIPE_PRICE_ID", "")
APP_BASE_URL       = os.getenv("APP_BASE_URL", "http://localhost:5000")
REPORT_PRICE_CENTS = int(os.getenv("REPORT_PRICE_CENTS", "900"))

# ─── Load data once at startup ──────────────────────────────────
DATA_PATH = Path(__file__).parent / "data" / "occupations.json"
with open(DATA_PATH) as f:
    DATA = json.load(f)

OCCUPATIONS = DATA["occupations"]
STATES = DATA["states"]
NAT_AVG = DATA["national_average"]

# Build a quick lookup table
OCC_BY_TITLE = {o["title"].lower(): o for o in OCCUPATIONS}

# ─── In-memory store of pending reports (would be a DB in prod) ──
# Maps stripe session id -> {occupation_title, state_code, email, ts}
PENDING_REPORTS = {}
PENDING_FILE = Path(__file__).parent / "data" / "pending.json"
if PENDING_FILE.exists():
    try:
        with open(PENDING_FILE) as f:
            PENDING_REPORTS.update(json.load(f))
    except Exception as e:
        log.warning(f"Could not restore pending: {e}")

def persist_pending():
    """Write pending reports to disk so we don't lose them on restart."""
    try:
        with open(PENDING_FILE, "w") as f:
            json.dump(PENDING_REPORTS, f, indent=2)
    except Exception as e:
        log.warning(f"Could not persist pending: {e}")


# ============================================================
# PAGES
# ============================================================

@app.route("/")
def home():
    """Landing page: atlas + CTA to calculator."""
    return render_template(
        "atlas.html",
        occupations=OCCUPATIONS,
        states=STATES,
        industry_baselines=DATA["industry_baselines"]
    )

@app.route("/calculator")
def calculator_page():
    return render_template(
        "calculator.html",
        states=STATES,
        price_dollars=REPORT_PRICE_CENTS / 100
    )

@app.route("/success")
def success_page():
    session_id = request.args.get("session_id")
    return render_template("success.html", session_id=session_id)

@app.route("/cancel")
def cancel_page():
    return render_template("cancel.html")


# ============================================================
# API
# ============================================================

@app.route("/api/occupations")
def api_occupations():
    """Lightweight autocomplete endpoint."""
    q = request.args.get("q", "").strip().lower()
    limit = min(int(request.args.get("limit", "20")), 50)
    if not q:
        # Top 20 most common (just first N for the dropdown)
        results = OCCUPATIONS[:limit]
    else:
        results = search_occupations(OCCUPATIONS, q, limit=limit)
    return jsonify([{
        "title": o["title"],
        "aliases": o.get("aliases", []),
        "category": o["category"]
    } for o in results])


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """
    Body: { occupation: str, state: 2-letter code }
    Returns the free scorecard JSON.
    """
    body = request.get_json(silent=True) or {}
    occ_input = (body.get("occupation") or "").strip()
    state_code = (body.get("state") or "").strip().upper()

    if not occ_input or state_code not in STATES:
        return jsonify({"error": "occupation and valid state required"}), 400

    # Resolve occupation: exact match -> alias match -> fuzzy search
    occ = (
        OCC_BY_TITLE.get(occ_input.lower())
        or search_occupations(OCCUPATIONS, occ_input.lower(), limit=1)
    )
    if isinstance(occ, list):
        occ = occ[0] if occ else None
    if not occ:
        return jsonify({"error": "Occupation not recognized. Try a more common title."}), 404

    result = score_for(occ, STATES[state_code], NAT_AVG)
    result["state_code"] = state_code
    result["state_name"] = STATES[state_code]["name"]
    result["occupation_title"] = occ["title"]
    result["price_cents"] = REPORT_PRICE_CENTS

    return jsonify(result)


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """
    Create a Stripe Checkout session for the full report.
    Body: { occupation: str, state: code, email: str }
    Returns: { url: stripe_checkout_url, session_id }
    """
    body = request.get_json(silent=True) or {}
    occ_title = (body.get("occupation") or "").strip()
    state_code = (body.get("state") or "").strip().upper()
    email = (body.get("email") or "").strip()

    if not occ_title or state_code not in STATES or "@" not in email:
        return jsonify({"error": "occupation, state, and valid email required"}), 400

    if not stripe.api_key:
        return jsonify({
            "error": "Stripe is not configured.",
            "hint": "Set STRIPE_SECRET_KEY in your .env to enable payments."
        }), 503

    try:
        # Build line items: either reference a price ID or ad-hoc price_data
        if STRIPE_PRICE_ID:
            line_items = [{"price": STRIPE_PRICE_ID, "quantity": 1}]
        else:
            line_items = [{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Personalized AI Vulnerability Report",
                        "description": f"Custom report for {occ_title} in {STATES[state_code]['name']}",
                    },
                    "unit_amount": REPORT_PRICE_CENTS,
                },
                "quantity": 1,
            }]

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            customer_email=email,
            success_url=f"{APP_BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_BASE_URL}/cancel",
            metadata={
                "occupation": occ_title,
                "state_code": state_code,
                "email": email,
            },
            # 1 hour expiry
            expires_at=int(datetime.now(timezone.utc).timestamp()) + 3600,
        )

        PENDING_REPORTS[session.id] = {
            "occupation": occ_title,
            "state_code": state_code,
            "email": email,
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        persist_pending()

        return jsonify({"url": session.url, "session_id": session.id})

    except stripe.error.StripeError as e:
        log.error(f"Stripe error: {e}")
        return jsonify({"error": "Payment processor error.", "detail": str(e)}), 502


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """
    Stripe webhook: on checkout.session.completed, generate + email the PDF.
    """
    payload = request.data
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        log.error("STRIPE_WEBHOOK_SECRET not configured; rejecting webhook.")
        return "Webhook not configured", 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.warning(f"Bad webhook signature: {e}")
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        sid = session["id"]
        session_dict = session.to_dict()  # stripe v8+ StripeObject; convert for .get() compat
        meta = session_dict.get("metadata") or {}
        occ_title = meta.get("occupation")
        state_code = meta.get("state_code")
        email = meta.get("email") or session_dict.get("customer_email")

        if not (occ_title and state_code and email):
            log.error(f"Webhook missing metadata on session {sid}")
            return "Bad metadata", 400

        try:
            _deliver_report(occ_title, state_code, email)
            if sid in PENDING_REPORTS:
                PENDING_REPORTS[sid]["status"] = "delivered"
                PENDING_REPORTS[sid]["delivered_at"] = datetime.now(timezone.utc).isoformat()
                persist_pending()
            log.info(f"Delivered report for {email} ({occ_title}/{state_code})")
        except Exception as e:
            log.exception(f"Failed to deliver report for session {sid}: {e}")
            # We don't 500 here — Stripe will retry; we'll handle idempotently
            if sid in PENDING_REPORTS:
                PENDING_REPORTS[sid]["status"] = "error"
                PENDING_REPORTS[sid]["error"] = str(e)
                persist_pending()

    return jsonify({"received": True})


def _deliver_report(occ_title: str, state_code: str, email: str):
    """Build the PDF for this customer and email it."""
    occ = OCC_BY_TITLE.get(occ_title.lower())
    if not occ:
        match = search_occupations(OCCUPATIONS, occ_title.lower(), limit=1)
        occ = match[0] if match else None
    if not occ:
        raise ValueError(f"Unknown occupation: {occ_title}")

    state = STATES[state_code]
    result = score_for(occ, state, NAT_AVG)

    pdf_bytes = build_pdf(
        occ=occ,
        state_code=state_code,
        state_name=state["name"],
        state_pct=state["p"],
        result=result,
        skill_resources=DATA["skill_resources"],
        national_avg=NAT_AVG,
    )

    send_report_email(
        to=email,
        occupation_title=occ_title,
        state_name=state["name"],
        pdf_bytes=pdf_bytes,
        score_pct=result["vulnerability_pct"],
    )


# ─── Manual delivery endpoint (admin / testing only) ────────────
@app.route("/admin/redeliver", methods=["POST"])
def admin_redeliver():
    """For testing without Stripe webhooks — call directly to deliver a PDF."""
    if os.getenv("FLASK_ENV") != "development":
        return abort(403)
    body = request.get_json(silent=True) or {}
    _deliver_report(body["occupation"], body["state"], body["email"])
    return jsonify({"ok": True})


# ─── Healthcheck ────────────────────────────────────────────────
@app.route("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "occupations": len(OCCUPATIONS),
        "stripe_configured": bool(stripe.api_key),
        "webhook_configured": bool(STRIPE_WEBHOOK_SECRET),
    })


# ─── Stripe public key for the front end ────────────────────────
@app.route("/config.js")
def config_js():
    """Inline JS config — frontend reads STRIPE_PUB_KEY etc."""
    js = f"""
window.APP_CONFIG = {{
  stripePublishableKey: "{STRIPE_PUB_KEY}",
  reportPriceCents: {REPORT_PRICE_CENTS},
  baseUrl: "{APP_BASE_URL}"
}};
""".strip()
    resp = make_response(js)
    resp.headers["Content-Type"] = "application/javascript"
    return resp


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
