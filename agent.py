"""
TaekwondoAgent
==============
AI agent that handles WhatsApp conversations for a Taekwondo club.

Features:
  - Maintains per-user conversation history (in-memory)
  - Uses OpenAI GPT to generate natural, friendly responses
  - Loads club-specific knowledge from knowledge_base.json
  - Detects when a human should take over and flags the escalation
  - In-WhatsApp registration flow collecting 12 member details
"""

import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 10          # Keep last N user+assistant pairs per session
ESCALATION_PHRASES = [
    "speak to someone",
    "talk to a human",
    "real person",
    "call me",
    "phone me",
    "manager",
    "complaint",
    "urgent",
    "emergency",
    "speak to a person",
    "talk to someone",
]

REGISTER_TRIGGERS = [
    "register",
    "sign up",
    "sign me up",
    "join up",
    "join now",
    "i want to join",
    "how do i join",
    "i'd like to join",
    "i would like to join",
    "book a taster",
    "free taster",
    "book taster",
    "taster session",
    "enrol",
    "enroll",
    "membership",
    "start classes",
    "get started",
]

# Registration steps in order
REGISTRATION_STEPS = [
    {
        "field": "first_name",
        "question": "Great, let's get you registered! 🥋\n\nFirst, what is your *first name*?",
    },
    {
        "field": "last_name",
        "question": "Thanks {first_name}! What is your *last name*?",
    },
    {
        "field": "dob",
        "question": "What is your *date of birth*? (e.g. 15/03/1990)",
    },
    {
        "field": "email",
        "question": "What is your *email address*?",
    },
    {
        "field": "phone",
        "question": "What is your *phone number*? (so we can confirm your class)",
    },
    {
        "field": "address1",
        "question": "What is your *address line 1*? (house number and street)",
    },
    {
        "field": "address2",
        "question": "What is your *address line 2*? (e.g. village or area — or type *skip* to leave blank)",
    },
    {
        "field": "town",
        "question": "What is your *town or city*?",
    },
    {
        "field": "postcode",
        "question": "What is your *postcode*?",
    },
    {
        "field": "emergency_contact",
        "question": "What is the name of your *emergency contact*? (e.g. a parent, partner or family member)",
    },
    {
        "field": "location",
        "question": (
            "Which *location* would you like to train at?\n\n"
            "1️⃣ York (Tuesday 6–8pm)\n"
            "2️⃣ Beverley (Wednesday 5–7pm)\n"
            "3️⃣ Stamford Bridge (Friday 5–8pm)\n"
            "4️⃣ Market Weighton (Saturday 9am–12pm)\n"
            "5️⃣ Pocklington (Coming September 2026)\n"
            "6️⃣ Not sure yet\n\n"
            "Reply with the number or name of your preferred location."
        ),
    },
    {
        "field": "membership",
        "question": (
            "Finally, which *membership* would you like?\n\n"
            "1️⃣ *Free Taster Session* — £0, one full class, no commitment\n"
            "2️⃣ *Basic Tuition* — £30/month, 1 class per week\n"
            "3️⃣ *Accelerated Tuition* — £40/month, up to 3 classes per week\n\n"
            "Reply with 1, 2 or 3."
        ),
    },
]

LOCATION_MAP = {
    "1": "York (Tuesday 6–8pm)",
    "2": "Beverley (Wednesday 5–7pm)",
    "3": "Stamford Bridge (Friday 5–8pm)",
    "4": "Market Weighton (Saturday 9am–12pm)",
    "5": "Pocklington (Coming September 2026)",
    "6": "Not sure yet",
    "york": "York (Tuesday 6–8pm)",
    "beverley": "Beverley (Wednesday 5–7pm)",
    "stamford bridge": "Stamford Bridge (Friday 5–8pm)",
    "market weighton": "Market Weighton (Saturday 9am–12pm)",
    "pocklington": "Pocklington (Coming September 2026)",
    "not sure": "Not sure yet",
    "not sure yet": "Not sure yet",
    "unsure": "Not sure yet",
    "don't know": "Not sure yet",
    "dont know": "Not sure yet",
    "no idea": "Not sure yet",
}

MEMBERSHIP_MAP = {
    "1": "Free Taster Session (£0)",
    "2": "Basic Tuition (£30/month)",
    "3": "Accelerated Tuition (£40/month)",
    "free": "Free Taster Session (£0)",
    "taster": "Free Taster Session (£0)",
    "basic": "Basic Tuition (£30/month)",
    "accelerated": "Accelerated Tuition (£40/month)",
}


# ── Student mode constants ────────────────────────────────────────────────────

# Maps belt colour keywords and number shortcuts to the belt key
BELT_PAGES = {
    "white":         "https://www.traintaekwondo.co.uk/white-belt-to-yellow-stripe.html",
    "yellow stripe": "https://www.traintaekwondo.co.uk/yellow-stripe-to-yellow-belt.html",
    "yellow":        "https://www.traintaekwondo.co.uk/yellow-belt-to-green-stripe.html",
    "green stripe":  "https://www.traintaekwondo.co.uk/green-stripe-to-green-belt.html",
    "green":         "https://www.traintaekwondo.co.uk/green-belt-to-blue-stripe.html",
    "blue stripe":   "https://www.traintaekwondo.co.uk/blue-stripe-to-blue-belt.html",
    "blue":          "https://www.traintaekwondo.co.uk/blue-belt-to-red-stripe.html",
    "red stripe":    "https://www.traintaekwondo.co.uk/red-stripe-to-red-belt.html",
    "red":           "https://www.traintaekwondo.co.uk/red-belt-to-black-stripe.html",
    "black stripe":  "https://www.traintaekwondo.co.uk/black-stripe-to-black-belt.html",
}

BELT_NUMBER_MAP = {
    "1": "white",
    "2": "yellow stripe",
    "3": "yellow",
    "4": "green stripe",
    "5": "green",
    "6": "blue stripe",
    "7": "blue",
    "8": "red stripe",
    "9": "red",
    "10": "black stripe",
}

BELT_MENU_TEXT = (
    "What colour belt are you currently? 🥋\n\n"
    "Reply with the number:\n\n"
    "1 — ⬜ White Belt\n"
    "2 — 🟡 Yellow Stripe\n"
    "3 — 🟡 Yellow Belt\n"
    "4 — 💚 Green Stripe\n"
    "5 — 🟢 Green Belt\n"
    "6 — 💙 Blue Stripe\n"
    "7 — 🔵 Blue Belt\n"
    "8 — ❤️ Red Stripe\n"
    "9 — 🔴 Red Belt\n"
    "10 — 🖤 Black Stripe\n\n"
    "Or just type your belt colour."
)


class TaekwondoAgent:
    """Conversational AI agent for a Taekwondo club WhatsApp channel."""

    def __init__(self):
        self.client  = OpenAI()   # Uses OPENAI_API_KEY from environment
        self.sessions: dict[str, list[dict]] = {}   # phone -> message history
        self.reg_state: dict[str, dict] = {}         # phone -> registration state
        self._pending_reg: dict[str, bool] = {}      # phone -> awaiting reg confirmation
        self._student_mode: set = set()              # phones currently in student mode
        self._awaiting_belt: set = set()             # phones waiting to reply with belt colour
        self.kb      = self._load_knowledge_base()
        self.system_prompt = self._build_system_prompt()
        self.student_prompt = self._build_student_prompt()

    # ── Knowledge base ────────────────────────────────────────────────────────

    def _load_knowledge_base(self) -> dict:
        """Load club-specific FAQ and info from knowledge_base.json."""
        kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base.json")
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                kb = json.load(f)
            logger.info("Knowledge base loaded successfully.")
            return kb
        except FileNotFoundError:
            logger.warning("knowledge_base.json not found. Using empty knowledge base.")
            return {}

    def _build_system_prompt(self) -> str:
        """Construct the system prompt injected into every conversation."""
        club     = self.kb.get("club", {})
        name     = club.get("name", "our Taekwondo club")
        location = club.get("location", "")
        phone    = club.get("phone", "")
        email    = club.get("email", "")
        website  = club.get("website", "")

        classes_text = ""
        for cls in self.kb.get("classes", []):
            classes_text += (
                f"\n  - {cls['name']}: {cls['day']} at {cls['time']}, "
                f"Age group: {cls['age_group']}, Venue: {cls['venue']}"
            )

        memberships_text = ""
        for mem in self.kb.get("memberships", []):
            memberships_text += (
                f"\n  - {mem['name']}: {mem['price']} per {mem['period']}"
            )

        grading_text = ""
        for grade in self.kb.get("belt_grades", []):
            grading_text += f"\n  - {grade['belt']}: {grade['description']}"

        faq_text = ""
        for faq in self.kb.get("faq", []):
            faq_text += f"\n  Q: {faq['question']}\n  A: {faq['answer']}\n"

        equipment = self.kb.get("equipment", {})
        equipment_text = ""
        if equipment:
            required = equipment.get("required", [])
            if required:
                equipment_text = "\n  Required: " + ", ".join(required)

        joining = self.kb.get("joining", {})
        membership_url = joining.get("membership_url", "https://www.traintaekwondo.co.uk/membership.html")
        timetable_url = joining.get("timetable_url", "https://www.traintaekwondo.co.uk/timetable")

        prompt = f"""You are a friendly and helpful WhatsApp assistant for {name}, a Taekwondo club.
Your job is to answer questions about joining the club, class schedules, belt grading,
membership fees, equipment, and general Taekwondo questions.

Club Information:
  Name: {name}
  Location: {location}
  Phone: {phone}
  Email: {email}
  Website: {website}

Class Schedule:{classes_text if classes_text else " Please contact the club for the latest schedule."}

Membership Options:
  - Free Taster Session: £0 — one full class, no kit, no commitment
  - Basic Tuition: £30/month — 1 class per week
  - Accelerated Tuition: £40/month — up to 3 classes per week
  - 3rd family member always trains FREE
  - Membership page: {membership_url}
  - Timetable: {timetable_url}

Belt Grading System:{grading_text if grading_text else " Please contact the club for grading information."}

Equipment:{equipment_text if equipment_text else " Please contact the club for equipment details."}

Frequently Asked Questions:{faq_text if faq_text else " No FAQs loaded."}

Guidelines:
1. Be warm, encouraging, and professional at all times.
2. Keep responses concise — this is WhatsApp, not an email. Aim for 3–5 sentences max.
3. Use simple language; avoid jargon unless the user is clearly experienced.
4. If you do not know the answer, say so honestly and offer to connect them with the club.
5. For joining enquiries, always mention the free trial class and share the link: {membership_url}
6. Never make up prices, dates, or facts not in your knowledge base.
7. If the user wants to speak to a human, acknowledge it warmly and let them know someone will be in touch shortly.
8. Always end with a helpful follow-up question or offer if appropriate.
9. Use occasional relevant emojis (🥋, 🏆, 👊) to keep the tone friendly, but do not overdo it.
10. Respond in the same language the user writes in.
11. IMPORTANT: If someone says they want to join, register, sign up, or book a taster session, 
    tell them you can register them right here in WhatsApp and ask if they'd like to do that now.
    Say something like: "I can register you right here in WhatsApp — it only takes 2 minutes! 
    Would you like to go ahead? Just reply *Yes* to start."
"""
        return prompt

    def _build_student_prompt(self) -> str:
        """System prompt used when a student has selected the existing-student menu option."""
        sm = self.kb.get("student_mode", {})
        policies = sm.get("membership_policies", {})
        store = sm.get("store", {})
        v121 = sm.get("virtual_121", {})
        # Extract values into variables to avoid backslash-in-f-string (Python < 3.12)
        p_cancel   = policies.get("cancellation", "One month notice required.")
        p_freeze   = policies.get("freeze", "One month notice required.")
        p_cross    = policies.get("cross_location", "Accelerated members can train at any location.")
        p_upgrade  = policies.get("upgrade", "Contact Gavin to upgrade.")
        s_url      = store.get("url", "https://www.traintaekwondo.co.uk/store")
        s_note     = store.get("note", "")
        s_instr    = store.get("unlock_instruction", "")
        s_code     = store.get("members_unlock_code", "tkd2011")
        v_price    = v121.get("price", "\u00a325/session")
        v_desc     = v121.get("description", "")
        v_book     = v121.get("booking", "")
        return (
            "You are the WhatsApp assistant for Train Taekwondo Schools, helping an *existing student*.\n\n"
            "Your job is to answer questions about grading, belt syllabus, membership policies, club events, and the store.\n"
            "Keep replies concise and friendly. Use occasional relevant emojis.\n\n"
            "Belt Testing Pages (share the relevant link when a student asks about their grading syllabus):\n"
            "  White Belt to Yellow Stripe: https://www.traintaekwondo.co.uk/white-belt-to-yellow-stripe.html\n"
            "  Yellow Stripe to Yellow Belt: https://www.traintaekwondo.co.uk/yellow-stripe-to-yellow-belt.html\n"
            "  Yellow Belt to Green Stripe: https://www.traintaekwondo.co.uk/yellow-belt-to-green-stripe.html\n"
            "  Green Stripe to Green Belt: https://www.traintaekwondo.co.uk/green-stripe-to-green-belt.html\n"
            "  Green Belt to Blue Stripe: https://www.traintaekwondo.co.uk/green-belt-to-blue-stripe.html\n"
            "  Blue Stripe to Blue Belt: https://www.traintaekwondo.co.uk/blue-stripe-to-blue-belt.html\n"
            "  Blue Belt to Red Stripe: https://www.traintaekwondo.co.uk/blue-belt-to-red-stripe.html\n"
            "  Red Stripe to Red Belt: https://www.traintaekwondo.co.uk/red-stripe-to-red-belt.html\n"
            "  Red Belt to Black Stripe: https://www.traintaekwondo.co.uk/red-belt-to-black-stripe.html\n"
            "  Black Stripe to Black Belt: https://www.traintaekwondo.co.uk/black-stripe-to-black-belt.html\n\n"
            "Club Calendar (grading dates, tournaments, events): https://www.traintaekwondo.co.uk/club-calendar.html\n\n"
            "Membership Policies:\n"
            f"  Cancellation: {p_cancel}\n"
            f"  Freeze: {p_freeze}\n"
            f"  Cross-location training: {p_cross}\n"
            f"  Upgrading: {p_upgrade}\n\n"
            f"Store: {s_url}\n"
            f"  {s_note}\n"
            f"  IMPORTANT: {s_instr} The code is: {s_code}\n\n"
            f"Virtual 1-2-1 with Mr Cook: {v_price} -- {v_desc} {v_book}\n\n"
            "Guidelines:\n"
            "1. Be warm and supportive -- these are existing students, treat them like you know them.\n"
            "2. Keep replies concise (3-5 sentences max).\n"
            "3. If asked about their belt syllabus, share the relevant link above.\n"
            "4. For grading/event dates, direct them to the live calendar: https://www.traintaekwondo.co.uk/club-calendar.html\n"
            "5. If you don't know something, direct them to Gavin on 07833 665905.\n"
            "6. Never make up facts not in your knowledge base.\n"
            "7. If they want to speak to Gavin, acknowledge warmly and say he will be in touch.\n"
        )

    # ── Belt detection ────────────────────────────────────────────────────────

    def _detect_belt(self, text: str) -> str | None:
        """Return the belt key if the message matches a belt colour or number."""
        t = text.strip().lower()
        if t in BELT_NUMBER_MAP:
            return BELT_NUMBER_MAP[t]
        # Longest match first so 'yellow stripe' matches before 'yellow'
        for belt in sorted(BELT_PAGES.keys(), key=len, reverse=True):
            if belt in t:
                return belt
        return None

    # ── Session management ────────────────────────────────────────────────────

    def _get_history(self, phone: str) -> list[dict]:
        return self.sessions.get(phone, [])

    def _update_history(self, phone: str, role: str, content: str) -> None:
        if phone not in self.sessions:
            self.sessions[phone] = []
        self.sessions[phone].append({"role": role, "content": content})
        # Trim to last MAX_HISTORY_TURNS pairs (2 messages per turn)
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.sessions[phone]) > max_messages:
            self.sessions[phone] = self.sessions[phone][-max_messages:]

    # ── Escalation detection ──────────────────────────────────────────────────

    def _needs_escalation(self, text: str) -> bool:
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in ESCALATION_PHRASES)

    # ── Registration trigger detection ───────────────────────────────────────

    def _wants_to_register(self, text: str) -> bool:
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in REGISTER_TRIGGERS)

    # ── Registration flow ─────────────────────────────────────────────────────

    def _start_registration(self, phone: str) -> str:
        """Initialise registration state and return the first question."""
        self.reg_state[phone] = {
            "step": 0,
            "data": {}
        }
        first_q = REGISTRATION_STEPS[0]["question"]
        return first_q

    def _handle_registration_step(self, phone: str, user_text: str) -> tuple[str, bool, dict | None]:
        """
        Process the current registration step.

        Returns:
            (reply, is_complete, completed_data)
            completed_data is the full registration dict when is_complete=True,
            otherwise None.
        """
        state = self.reg_state.get(phone)
        if not state:
            return self._start_registration(phone), False, None

        step_index = state["step"]
        current_step = REGISTRATION_STEPS[step_index]
        field = current_step["field"]

        # Handle "skip" for optional fields
        value = user_text.strip()
        location_not_sure = False
        if value.lower() == "skip" and field == "address2":
            value = ""

        # Normalise location input
        if field == "location":
            normalised = LOCATION_MAP.get(value.lower(), value)
            value = normalised
            # Flag if they chose "not sure" so we can add reassurance after saving
            location_not_sure = (value == "Not sure yet")

        # Normalise membership input
        if field == "membership":
            normalised = MEMBERSHIP_MAP.get(value.lower(), value)
            value = normalised

        # Save the answer
        state["data"][field] = value
        state["step"] += 1

        # Check if registration is complete
        if state["step"] >= len(REGISTRATION_STEPS):
            completed_data = state["data"].copy()
            del self.reg_state[phone]
            first_name = completed_data.get("first_name", "")
            confirmation = (
                f"✅ *Details received! Thank you, {first_name}!* 🥋\n\n"
                f"Here's a summary of what we've got:\n"
                f"📛 *Name:* {completed_data.get('first_name', '')} {completed_data.get('last_name', '')}\n"
                f"🎂 *DOB:* {completed_data.get('dob', '')}\n"
                f"📧 *Email:* {completed_data.get('email', '')}\n"
                f"📞 *Phone:* {completed_data.get('phone', '')}\n"
                f"🏠 *Address:* {completed_data.get('address1', '')}, {completed_data.get('address2', '') or ''} {completed_data.get('town', '')}, {completed_data.get('postcode', '')}\n"
                f"🆘 *Emergency contact:* {completed_data.get('emergency_contact', '')}\n"
                f"📍 *Location:* {completed_data.get('location', '')}\n"
                f"🥋 *Membership:* {completed_data.get('membership', '')}\n\n"
                f"*One last step* — tap the button below to complete your booking in ClubManager. "
                f"It only takes a moment and confirms your spot! 👊"
            )
            return confirmation, True, completed_data

        # Ask the next question
        next_step = REGISTRATION_STEPS[state["step"]]
        next_q = next_step["question"]

        # Personalise question with first name if available
        if "{first_name}" in next_q:
            next_q = next_q.format(first_name=state["data"].get("first_name", ""))

        # Add reassurance if they weren't sure about location
        if location_not_sure:
            next_q = (
                "No worries at all! 😊 Once you're registered, Gavin will be in touch with all the info you need to choose the right class for you.\n\n"
                + next_q
            )

        return next_q, False, None

    def is_in_registration(self, phone: str) -> bool:
        """Returns True if this user is currently in the registration flow."""
        return phone in self.reg_state

    def start_registration_prompt(self, phone: str) -> str:
        """Return the prompt to ask if user wants to register."""
        return (
            "I can register you right here in WhatsApp — it only takes 2 minutes! 🥋\n\n"
            "I'll ask you a few quick questions and your details will be sent straight to Gavin.\n\n"
            "Would you like to go ahead? Reply *Yes* to start, or *No* if you'd prefer to register online at "
            "https://www.traintaekwondo.co.uk/membership.html"
        )

    # ── Student mode helpers ──────────────────────────────────────────────────

    def enter_student_mode(self, phone: str) -> str:
        """Switch a user into student mode and ask for their belt colour."""
        self._student_mode.add(phone)
        self._awaiting_belt.add(phone)
        return BELT_MENU_TEXT

    def is_in_student_mode(self, phone: str) -> bool:
        return phone in self._student_mode

    def _student_ai_reply(self, phone: str, user_text: str) -> str:
        """Generate an AI reply using the student system prompt."""
        history = self._get_history(phone)
        messages = [{"role": "system", "content": self.student_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=400,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("OpenAI API error (student mode): %s", exc)
            reply = (
                "Sorry, I'm having a little trouble right now. 😅 "
                "Please try again in a moment, or contact Gavin on 07833 665905."
            )
        self._update_history(phone, "user", user_text)
        self._update_history(phone, "assistant", reply)
        return reply

    # ── Main respond method ───────────────────────────────────────────────────

    def respond(self, phone: str, user_text: str) -> tuple[str, bool, dict | None]:
        """
        Generate a reply for the given user message.

        Returns:
            (reply_text, needs_human, registration_data) tuple.
            needs_human is True when the agent detects the user wants
            to speak to a real person.
            registration_data is a dict when a registration is completed,
            otherwise None.
        """
        needs_human = self._needs_escalation(user_text)
        registration_data = None
        text_lower = user_text.strip().lower()

        # ── Handle active registration flow ────────────────────────────────────
        if self.is_in_registration(phone):
            reply, is_complete, registration_data = self._handle_registration_step(phone, user_text)
            return reply, False, registration_data

        # ── Student mode: awaiting belt colour reply ───────────────────────────
        if phone in self._awaiting_belt:
            belt = self._detect_belt(user_text)
            if belt:
                self._awaiting_belt.discard(phone)
                url = BELT_PAGES[belt]
                belt_display = belt.replace("_", " ").title()
                reply = (
                    f"Here's your *{belt_display}* grading revision page 🥋\n\n"
                    f"{url}\n\n"
                    f"It has your full checklist, technique videos, Korean terms and theory. "
                    f"Tick off every item before grading day — no excuses! 💪\n\n"
                    f"Is there anything else I can help you with?"
                )
                self._update_history(phone, "user", user_text)
                self._update_history(phone, "assistant", reply)
                return reply, False, None
            else:
                reply = "I didn't quite catch that belt colour. 😊\n\n" + BELT_MENU_TEXT
                return reply, False, None

        # ── Student mode: general conversation ───────────────────────────────
        if self.is_in_student_mode(phone):
            # If they ask about their belt/grading, trigger belt menu
            if any(kw in text_lower for kw in ["syllabus", "belt testing", "what do i need for my grading", "grading requirements", "grading checklist", "revision", "checklist", "my belt", "what do i need to know", "what techniques", "what patterns"]):
                self._awaiting_belt.add(phone)
                return BELT_MENU_TEXT, False, None
            reply = self._student_ai_reply(phone, user_text)
            return reply, needs_human, None

        # ── Check if user confirmed they want to register ─────────────────────────
        # (after we asked "Would you like to register? Reply Yes to start")
        if self._pending_reg.get(phone):
            if text_lower in ["yes", "y", "yeah", "yep", "ok", "okay", "sure", "go ahead", "yes please"]:
                del self._pending_reg[phone]
                reply = self._start_registration(phone)
                return reply, False, None
            elif text_lower in ["no", "n", "nope", "not now", "no thanks"]:
                del self._pending_reg[phone]
                reply = (
                    "No problem! You can register online anytime at:\n"
                    "https://www.traintaekwondo.co.uk/membership.html\n\n"
                    "Is there anything else I can help you with? 🥋"
                )
                return reply, False, None

        # ── Check if user wants to register ──────────────────────────────────
        if self._wants_to_register(user_text):
            self._pending_reg[phone] = True
            reply = self.start_registration_prompt(phone)
            return reply, False, None

        # ── Normal AI conversation (new-member mode) ──────────────────────────
        history  = self._get_history(phone)
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=400,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            club_phone = self.kb.get("club", {}).get("phone", "the club directly")
            reply = (
                "Sorry, I'm having a little trouble right now. 😅 "
                f"Please try again in a moment, or contact us at {club_phone}."
            )

        # Update conversation history
        self._update_history(phone, "user", user_text)
        self._update_history(phone, "assistant", reply)

        return reply, needs_human, None
