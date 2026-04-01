"""
Train Taekwondo WhatsApp Bot — Dual-Mode v5
============================================
Primary focus: converting new enquiries into free taster bookings.
Secondary mode: existing student support (grading, belt syllabus, membership).

Student mode is ONLY accessible via the "I'm Already a Student" menu option.
All free-text questions from new users default to the new-member AI flow.
"""

import os
import json
import logging
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from agent import TaekwondoAgent

load_dotenv()

WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN", "traintkd_members_2024")
ADMIN_PHONE     = os.getenv("ADMIN_PHONE", "")
ADMIN_EMAIL     = os.getenv("ADMIN_EMAIL", "gavin@traintaekwondo.co.uk")
SMTP_HOST       = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER", "")
SMTP_PASS       = os.getenv("SMTP_PASS", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app   = Flask(__name__)
agent = TaekwondoAgent()

welcomed_users: set = set()
processed_ids:  set = set()


# ── WhatsApp API helpers ──────────────────────────────────────────────────────

def _wa_headers():
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

def _wa_url():
    return f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"


def send_whatsapp_message(to: str, text: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    r = requests.post(_wa_url(), headers=_wa_headers(), json=payload, timeout=10)
    logger.info("Sent text to %s | status %s", to, r.status_code)
    return r.json()


def send_welcome_menu(to: str) -> dict:
    """Send the interactive list menu. New-member options first, student option last."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "🥋 Train Taekwondo Schools"},
            "body": {
                "text": (
                    "Hi! Welcome to Train Taekwondo Schools! 🥋👋\n\n"
                    "I'm your virtual assistant — here to help you get started on your "
                    "martial arts journey. Whether you're looking to build confidence, "
                    "get fit, or just have fun, you're in the right place! 💥\n\n"
                    "Tap *Show Options* below, or just type your question and I'll "
                    "answer straight away!\n\n"
                    "Let's get kicking! 🏆"
                )
            },
            "footer": {"text": "Creating Champions for Life Since 2011"},
            "action": {
                "button": "Show Options",
                "sections": [
                    {
                        "title": "Get Started",
                        "rows": [
                            {"id": "book_taster",  "title": "🎯 Book Free Taster",   "description": "Register for a free class — no kit needed"},
                            {"id": "our_classes",  "title": "🥋 Our Classes",         "description": "Taekwondo, Ninja Skillz & Spectrum Skillz"},
                            {"id": "prices",       "title": "💰 Prices & Membership", "description": "Monthly fees & free taster info"},
                            {"id": "parent_guide", "title": "📄 Free Parent Guide",   "description": "Download our free PDF guide"},
                        ]
                    },
                    {
                        "title": "Learn More",
                        "rows": [
                            {"id": "watch_videos",   "title": "🎬 Watch Our Videos",  "description": "See our classes in action"},
                            {"id": "class_schedule", "title": "📅 Class Schedule",    "description": "All locations & times"},
                            {"id": "speak_to_gavin", "title": "📞 Speak to Gavin",    "description": "Message the instructor directly"},
                            {"id": "tell_a_friend",  "title": "🤝 Tell a Friend",     "description": "Share Train Taekwondo with someone you know"},
                        ]
                    },
                    {
                        "title": "Already a Student?",
                        "rows": [
                            {"id": "existing_student", "title": "🥋 I'm Already a Student", "description": "Grading info, belt syllabus & membership help"},
                        ]
                    }
                ]
            }
        }
    }
    r = requests.post(_wa_url(), headers=_wa_headers(), json=payload, timeout=10)
    logger.info("Sent welcome menu to %s | status %s", to, r.status_code)
    return r.json()


def send_cta_button(to: str, body: str, button_text: str, button_url: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": button_text, "url": button_url}
            }
        }
    }
    r = requests.post(_wa_url(), headers=_wa_headers(), json=payload, timeout=10)
    logger.info("Sent CTA button to %s | status %s", to, r.status_code)
    return r.json()


def handle_menu_selection(to: str, sel_id: str, sel_title: str):
    """Route each menu selection to the correct response."""

    if sel_id == "book_taster":
        reply = agent.start_registration_prompt(to)
        send_whatsapp_message(to, reply)

    elif sel_id == "our_classes":
        send_whatsapp_message(
            to,
            "🥋 *Our Classes*\n\n"
            "*Taekwondo* — For ages 4+ and adults. Build confidence, fitness, "
            "discipline and self-defence through the world's most popular martial art. "
            "Progress from White Belt all the way to Black Belt and beyond! 🏆\n\n"
            "*Ninja Skillz* — For ages 4–7. A fun 30-minute session combining "
            "movement, coordination and basic martial arts skills.\n"
            "Watch the Ninja Skillz video: https://youtu.be/l4k_Sr7kOdo\n\n"
            "*Spectrum Skillz* — A specially adapted programme for children and "
            "adults with additional needs. Delivered in a safe, supportive environment.\n\n"
            "Would you like to book a free taster to try a class? 🎯"
        )

    elif sel_id == "prices":
        send_whatsapp_message(
            to,
            "💰 *Prices & Membership*\n\n"
            "🆓 *Free Taster* — Try a full class completely free. No kit, no commitment.\n\n"
            "📅 *Basic Tuition* — £30/month. One class per week.\n\n"
            "🚀 *Accelerated* — £40/month. Up to 3 classes per week across any location.\n\n"
            "👨‍👩‍👧 *Family Deal* — The 3rd family member always trains *FREE*!\n\n"
            "All memberships are rolling monthly — no contracts, cancel anytime "
            "with one month's notice.\n\n"
            "Ready to get started? Reply *Yes* and I'll register you now! 🥋"
        )

    elif sel_id == "parent_guide":
        send_cta_button(
            to=to,
            body=(
                "📄 *Free Parent Guide*\n\n"
                "Download our free guide — everything you need to know about starting "
                "Taekwondo, what to expect, and how to support your child's journey.\n\n"
                "Tap below to download 👇"
            ),
            button_text="Download Free Guide",
            button_url="https://www.traintaekwondo.co.uk/parent-guide"
        )

    elif sel_id == "watch_videos":
        send_whatsapp_message(
            to,
            "🎬 *Watch Our Videos*\n\n"
            "🥋 *Club Promo* — See what Train Taekwondo Schools is all about:\n"
            "https://youtu.be/22WZjqHc9D8\n\n"
            "🐱‍👤 *Ninja Skillz* — Our programme for 4–7 year olds:\n"
            "https://youtu.be/l4k_Sr7kOdo\n\n"
            "Want to see it in person? Book a free taster and come along! 🎯"
        )

    elif sel_id == "class_schedule":
        send_cta_button(
            to=to,
            body=(
                "📅 *Class Schedule — All Locations*\n\n"
                "🗓 *York* — Tuesday 6:00–8:00pm\n"
                "🗓 *Beverley* — Wednesday 5:00–7:00pm\n"
                "🗓 *Stamford Bridge* — Friday 5:00–8:00pm\n"
                "🗓 *Market Weighton* — Saturday 9:00am–12:00pm\n"
                "🗓 *Pocklington* — Coming September 2026\n\n"
                "Tap below for the full timetable with class types and age groups."
            ),
            button_text="View Full Timetable",
            button_url="https://www.traintaekwondo.co.uk/timetable"
        )

    elif sel_id == "speak_to_gavin":
        send_whatsapp_message(
            to,
            "📞 *Speak to Gavin*\n\n"
            "You can message Gavin directly on WhatsApp:\n"
            "👉 https://wa.me/447833665905\n\n"
            "He's usually available Monday–Friday and will get back to you as soon as possible. 🥋"
        )

    elif sel_id == "tell_a_friend":
        send_whatsapp_message(
            to,
            "🤝 *Tell a Friend!*\n\n"
            "Know someone who'd love Taekwondo? Share this link with them:\n"
            "👉 https://wa.me/447426069502\n\n"
            "They can message us directly to book their free taster. "
            "The more the merrier! 🥋🏆"
        )

    elif sel_id == "existing_student":
        reply = agent.enter_student_mode(to)
        send_whatsapp_message(to, reply)

    else:
        send_whatsapp_message(to, f"Thanks for selecting *{sel_title}*! How can I help you with that? 🥋")


def mark_as_read(message_id: str) -> None:
    payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    requests.post(_wa_url(), headers=_wa_headers(), json=payload, timeout=10)


# ── Email / alert helpers ─────────────────────────────────────────────────────

def send_registration_email(data: dict, sender_phone: str) -> None:
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP credentials not set — skipping email notification.")
        return
    try:
        subject = f"New Registration: {data.get('first_name','')} {data.get('last_name','')} — Train Taekwondo"
        body = (
            f"New member registration received via WhatsApp!\n\n"
            f"Name:              {data.get('first_name','')} {data.get('last_name','')}\n"
            f"Date of Birth:     {data.get('dob','')}\n"
            f"Email:             {data.get('email','')}\n"
            f"Phone:             {data.get('phone','')}\n"
            f"WhatsApp Number:   +{sender_phone}\n"
            f"Address:           {data.get('address1','')}, {data.get('address2','') or ''} "
            f"{data.get('town','')}, {data.get('postcode','')}\n"
            f"Emergency Contact: {data.get('emergency_contact','')}\n"
            f"Membership:        {data.get('membership','')}\n"
        )
        msg = MIMEMultipart()
        msg["From"]    = SMTP_USER
        msg["To"]      = ADMIN_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
        logger.info("Registration email sent for %s", sender_phone)
    except Exception as exc:
        logger.error("Failed to send registration email: %s", exc)


def send_registration_whatsapp_alert(data: dict, sender_phone: str) -> None:
    if not ADMIN_PHONE:
        return
    msg = (
        f"🎉 *New Registration!*\n\n"
        f"*Name:* {data.get('first_name','')} {data.get('last_name','')}\n"
        f"*DOB:* {data.get('dob','')}\n"
        f"*Email:* {data.get('email','')}\n"
        f"*Phone:* {data.get('phone','')}\n"
        f"*WhatsApp:* +{sender_phone}\n"
        f"*Address:* {data.get('address1','')}, {data.get('town','')}, {data.get('postcode','')}\n"
        f"*Emergency:* {data.get('emergency_contact','')}\n"
        f"*Membership:* {data.get('membership','')}"
    )
    send_whatsapp_message(ADMIN_PHONE, msg)


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "agent": "Train Taekwondo Bot v5 (dual-mode)"}), 200


@app.route("/webhook", methods=["GET"])
def verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified")
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]["value"]
        messages = changes.get("messages", [])
        if not messages:
            return jsonify({"status": "ok"}), 200

        message    = messages[0]
        sender     = message["from"]
        message_id = message.get("id", "")

        # ── Deduplication ─────────────────────────────────────────────────────
        if message_id in processed_ids:
            logger.info("Duplicate message %s — skipping", message_id)
            return jsonify({"status": "ok"}), 200
        processed_ids.add(message_id)
        if len(processed_ids) > 5000:
            processed_ids.clear()

        mark_as_read(message_id)

        # ── Interactive (menu tap) ─────────────────────────────────────────────
        m_type = message.get("type", "")
        if m_type == "interactive":
            interactive = message.get("interactive", {})
            i_type = interactive.get("type", "")
            if i_type == "list_reply":
                sel = interactive.get("list_reply", {})
                handle_menu_selection(sender, sel.get("id", ""), sel.get("title", ""))
            elif i_type == "button_reply":
                user_text = interactive.get("button_reply", {}).get("title", "")
                reply, needs_human, registration_data = agent.respond(sender, user_text)
                send_whatsapp_message(sender, reply)
                if registration_data:
                    send_cta_button(
                        to=sender,
                        body="🎯 *Complete your booking in ClubManager*\n\nTap below to confirm your spot.",
                        button_text="Complete Booking Now",
                        button_url="https://www.traintaekwondo.co.uk/membership.html"
                    )
                    send_registration_email(registration_data, sender)
                    send_registration_whatsapp_alert(registration_data, sender)
                if needs_human and ADMIN_PHONE:
                    send_whatsapp_message(ADMIN_PHONE,
                        f"⚠️ *Action needed*\nUser asking to speak to someone.\n\nFrom: +{sender}\nMessage: {user_text}")
            return jsonify({"status": "ok"}), 200

        # ── Text message ──────────────────────────────────────────────────────
        if m_type != "text":
            send_whatsapp_message(sender, "Hi! I can only handle text messages at the moment. Please type your question! 🥋")
            return jsonify({"status": "ok"}), 200

        user_text = message["text"]["body"].strip()
        logger.info("Message from %s: %s", sender, user_text)

        # ── First contact: send welcome menu ──────────────────────────────────
        if sender not in welcomed_users:
            welcomed_users.add(sender)
            send_welcome_menu(sender)
            greetings = {"hi", "hello", "hey", "hiya", "yo", "sup", ""}
            if user_text.lower() not in greetings:
                reply, needs_human, registration_data = agent.respond(sender, user_text)
                send_whatsapp_message(sender, reply)
                if registration_data:
                    send_cta_button(
                        to=sender,
                        body="🎯 *Complete your booking in ClubManager*\n\nTap below to confirm your spot.",
                        button_text="Complete Booking Now",
                        button_url="https://www.traintaekwondo.co.uk/membership.html"
                    )
                    send_registration_email(registration_data, sender)
                    send_registration_whatsapp_alert(registration_data, sender)
                if needs_human and ADMIN_PHONE:
                    send_whatsapp_message(ADMIN_PHONE,
                        f"⚠️ *Action needed*\nUser asking to speak to someone.\n\nFrom: +{sender}\nMessage: {user_text}")
            return jsonify({"status": "ok"}), 200

        # ── Menu keyword: re-send welcome menu at any time ────────────────────
        MENU_KEYWORDS = {"menu", "start", "help", "home", "options", "back", "main menu"}
        if user_text.strip().lower() in MENU_KEYWORDS:
            send_welcome_menu(sender)
            return jsonify({"status": "ok"}), 200

        # ── Normal conversation ───────────────────────────────────────────────
        reply, needs_human, registration_data = agent.respond(sender, user_text)
        send_whatsapp_message(sender, reply)

        if registration_data:
            logger.info("Registration completed for %s", sender)
            send_cta_button(
                to=sender,
                body=(
                    "🎯 *Complete your booking in ClubManager*\n\n"
                    "Tap the button below to confirm your spot and complete your registration. "
                    "It only takes a moment!"
                ),
                button_text="Complete Booking Now",
                button_url="https://www.traintaekwondo.co.uk/membership.html"
            )
            send_registration_email(registration_data, sender)
            send_registration_whatsapp_alert(registration_data, sender)

        if needs_human and ADMIN_PHONE:
            send_whatsapp_message(ADMIN_PHONE,
                f"⚠️ *Action needed*\nUser asking to speak to someone.\n\nFrom: +{sender}\nMessage: {user_text}")

    except (KeyError, IndexError):
        pass

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
