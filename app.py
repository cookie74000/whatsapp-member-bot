import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from agent import get_agent, MENU_OPTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', '')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'traintkd_members_2024')
ADMIN_PHONE = os.environ.get('ADMIN_PHONE', '')

WHATSAPP_API = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
HEADERS = lambda: {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

# Track first-time contacts
first_time_contacts = set()


def send_text(to: str, body: str):
    """Send a plain text WhatsApp message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    r = requests.post(WHATSAPP_API, headers=HEADERS(), json=payload)
    if r.status_code != 200:
        logger.error(f"Failed to send text: {r.text}")
    return r


def send_interactive_list(to: str, header: str, body: str, footer: str, button_text: str, sections: list):
    """Send an interactive list message with sections."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "footer": {"text": footer},
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    }
    r = requests.post(WHATSAPP_API, headers=HEADERS(), json=payload)
    if r.status_code != 200:
        logger.error(f"Failed to send list: {r.text}")
    return r


def send_welcome_menu(to: str):
    """Send the welcome message with the interactive quick-topic menu."""
    sections = [{
        "title": "What would you like help with?",
        "rows": [
            {"id": "grading", "title": "📋 My Next Grading", "description": "What do I need to know?"},
            {"id": "pattern", "title": "🥋 Pattern Help", "description": "Step-by-step pattern guide"},
            {"id": "korean", "title": "🇰🇷 Korean Terms", "description": "Terminology & numbers"},
            {"id": "equipment", "title": "🛡️ Equipment", "description": "What do I need to buy?"},
            {"id": "timetable", "title": "📅 Class Times", "description": "All locations & times"},
            {"id": "competitions", "title": "🏆 Competitions", "description": "How to enter & upcoming events"},
            {"id": "contact", "title": "📞 Contact Gavin", "description": "Get in touch directly"},
        ]
    }]

    send_interactive_list(
        to=to,
        header="🥋 Train Taekwondo Members",
        body=(
            "Hi! Welcome to the Train Taekwondo Members Knowledge Bot! 🥋\n\n"
            "I'm here to help you with grading revision, patterns, Korean terms, "
            "equipment, class times and competitions.\n\n"
            "Tap *Show Topics* to browse, or just type your question directly! 💬"
        ),
        footer="Creating Champions for Life Since 2011",
        button_text="Show Topics",
        sections=sections
    )


def send_topic_menu(to: str):
    """Send just the topic menu (for returning users who ask for the menu)."""
    sections = [{
        "title": "Choose a topic",
        "rows": [
            {"id": "grading", "title": "📋 My Next Grading", "description": "What do I need to know?"},
            {"id": "pattern", "title": "🥋 Pattern Help", "description": "Step-by-step pattern guide"},
            {"id": "korean", "title": "🇰🇷 Korean Terms", "description": "Terminology & numbers"},
            {"id": "equipment", "title": "🛡️ Equipment", "description": "What do I need to buy?"},
            {"id": "timetable", "title": "📅 Class Times", "description": "All locations & times"},
            {"id": "competitions", "title": "🏆 Competitions", "description": "How to enter & upcoming events"},
            {"id": "contact", "title": "📞 Contact Gavin", "description": "Get in touch directly"},
        ]
    }]

    send_interactive_list(
        to=to,
        header="🥋 Topics",
        body="What would you like help with today?",
        footer="Or just type your question directly",
        button_text="Show Topics",
        sections=sections
    )


def handle_topic_selection(to: str, topic_id: str):
    """Handle a topic selection from the interactive menu."""
    agent = get_agent()

    topic_prompts = {
        "grading": "What do I need to know for my next grading? Give me a summary of what's typically tested.",
        "pattern": "Can you help me with my pattern? What patterns are required at each belt level?",
        "korean": "What are the most important Korean terms I need to know for my grading?",
        "equipment": "What equipment do I need for Taekwondo? What should I buy and when?",
        "timetable": "What are the class times and locations for Train Taekwondo?",
        "competitions": "Tell me about competitions — how do I enter and what types are there?",
        "contact": None,  # Handle separately
    }

    if topic_id == "contact":
        send_text(to,
            "📞 *Contact Gavin Cook — Chief Instructor*\n\n"
            "📱 Phone/WhatsApp: 07833 665905\n"
            "📧 Email: gavin@traintaekwondo.co.uk\n"
            "🌐 Website: www.traintaekwondo.co.uk\n\n"
            "Gavin is usually available between classes. For urgent matters please call directly."
        )
        return

    prompt = topic_prompts.get(topic_id)
    if prompt:
        reply = agent.respond(to, prompt)
        send_text(to, reply)
    else:
        send_text(to, "I'm not sure what you mean — try typing your question directly! 😊")


@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Handle Meta webhook verification."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return challenge, 200
    else:
        logger.warning(f"Webhook verification failed. Token: {token}")
        return 'Forbidden', 403


@app.route('/webhook', methods=['POST'])
def receive_message():
    """Handle incoming WhatsApp messages."""
    try:
        data = request.get_json()
        logger.info(f"Incoming webhook: {json.dumps(data)[:500]}")

        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])

        if not messages:
            return jsonify({'status': 'ok'}), 200

        message = messages[0]
        from_number = message.get('from')
        msg_type = message.get('type')

        # Extract message content
        user_text = None
        interactive_reply_id = None

        if msg_type == 'text':
            user_text = message.get('text', {}).get('body', '').strip()
        elif msg_type == 'interactive':
            interactive_data = message.get('interactive', {})
            if interactive_data.get('type') == 'list_reply':
                interactive_reply_id = interactive_data['list_reply']['id']
                user_text = interactive_data['list_reply']['title']
            elif interactive_data.get('type') == 'button_reply':
                interactive_reply_id = interactive_data['button_reply']['id']
                user_text = interactive_data['button_reply']['title']

        if not from_number:
            return jsonify({'status': 'ok'}), 200

        # Handle interactive topic selections
        if interactive_reply_id:
            handle_topic_selection(from_number, interactive_reply_id)
            return jsonify({'status': 'ok'}), 200

        # First-time contact — send welcome menu
        if from_number not in first_time_contacts:
            first_time_contacts.add(from_number)
            send_welcome_menu(from_number)
            return jsonify({'status': 'ok'}), 200

        # Handle menu trigger words
        if user_text and user_text.lower() in ['menu', 'help', 'topics', 'hi', 'hello', 'start']:
            send_topic_menu(from_number)
            return jsonify({'status': 'ok'}), 200

        # Route to AI agent for all other messages
        if user_text:
            agent = get_agent()
            reply = agent.respond(from_number, user_text)
            send_text(from_number, reply)

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'service': 'Train Taekwondo Members Knowledge Bot',
        'version': '1.0'
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
