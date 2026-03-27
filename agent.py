import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Load knowledge base
with open(os.path.join(os.path.dirname(__file__), 'knowledge_base.json')) as f:
    KNOWLEDGE_BASE = json.load(f)

# Build a compact system prompt from the knowledge base
def _build_system_prompt():
    kb = KNOWLEDGE_BASE
    belt_list = "\n".join([
        f"  - {b['grade']} ({b['belt']}): Pattern = {b['pattern']}"
        for b in kb['belt_system']['belt_order']
    ])

    grading_summary = ""
    for grade, content in kb.get('grading_requirements', {}).items():
        # Truncate each grade to first 600 chars to keep prompt manageable
        grading_summary += f"\n\n### {grade}\n{content[:600]}..."

    tenets = "\n".join([f"  - {k.title()}: {v}" for k, v in kb['tenets'].items()])

    korean = "\n".join([f"  - {k}: {v}" for k, v in kb['common_korean_terms'].items()])

    timetable = "\n".join([
        f"  - {loc['location']}: {loc['day']} {loc['time']}"
        for loc in kb['class_timetable']['locations']
    ])

    equipment_beginner = "\n".join([f"  - {e}" for e in kb['equipment']['beginners']])
    equipment_sparring = "\n".join([f"  - {e}" for e in kb['equipment']['sparring_equipment_required_from_green_belt']])

    prompt = f"""You are the Train Taekwondo Members Knowledge Bot — a friendly, enthusiastic and knowledgeable assistant for existing students and parents of Train Taekwondo Schools.

Your role is to help members with:
- Grading revision and syllabus questions (what do I need to know for my next grading?)
- Pattern (tul) requirements for each belt
- Korean terminology
- Equipment advice
- Class times and locations
- Competition information
- General Taekwondo knowledge
- Club rules and conduct

Always be warm, encouraging and positive. Use emojis occasionally to keep it friendly 🥋. Keep answers concise but complete. If you don't know something specific, direct them to ask Gavin at their next class or contact the club.

---

CLUB INFO:
- Name: {kb['club']['name']}
- Instructor: {kb['club']['instructor']}
- Phone: {kb['club']['phone']}
- Email: {kb['club']['email']}
- Website: {kb['club']['website']}
- Affiliation: {kb['club']['affiliation']}

---

BELT SYSTEM (White to Black Belt):
{belt_list}

---

THE 5 TENETS OF TAE KWON-DO:
{tenets}

---

STUDENT OATH:
{kb['student_oath']}

---

COMMON KOREAN TERMS:
{korean}

---

KOREAN NUMBERS: 1=Hanna, 2=Dool, 3=Seth, 4=Neth, 5=Dasaul, 6=Yosaul, 7=Ilgop, 8=Yodoll, 9=Ahop, 10=Yoll

---

CLASS TIMETABLE:
{timetable}
Note: {kb['class_timetable']['note']}

---

EQUIPMENT:
Beginners need:
{equipment_beginner}

From Green Belt onwards (sparring equipment required):
{equipment_sparring}

Where to buy: {kb['equipment']['where_to_buy']}
Dobok care: {kb['equipment']['dobok_care']}

---

GRADING PROCESS:
- Frequency: {kb['grading_process']['frequency']}
- Your instructor must approve you before you can grade
- Grading includes: practical (patterns, kicks, sparring from green belt) and theory (Korean terms, belt meanings, tenets)
- Tips: {'; '.join(kb['grading_process']['tips'])}

---

COMPETITIONS:
{kb['competitions']['overview']}
Types: {', '.join(kb['competitions']['types'])}
Categories: {', '.join(kb['competitions']['categories'])}
How to enter: {kb['competitions']['how_to_enter']}

---

FULL GRADING REQUIREMENTS BY BELT:
{grading_summary}
"""
    return prompt


SYSTEM_PROMPT = _build_system_prompt()

# Quick-reply menu options
MENU_OPTIONS = [
    ("grading", "📋 My Next Grading"),
    ("pattern", "🥋 Pattern Help"),
    ("korean", "🇰🇷 Korean Terms"),
    ("equipment", "🛡️ Equipment"),
    ("timetable", "📅 Class Times"),
    ("competitions", "🏆 Competitions"),
    ("contact", "📞 Contact Gavin"),
]


class MemberKnowledgeAgent:
    def __init__(self):
        self.client = OpenAI()
        self.conversations = {}  # phone_number -> list of messages

    def get_or_create_conversation(self, phone_number):
        if phone_number not in self.conversations:
            self.conversations[phone_number] = []
        return self.conversations[phone_number]

    def respond(self, phone_number: str, user_message: str) -> str:
        """Generate a response to the user's message."""
        history = self.get_or_create_conversation(phone_number)

        # Add user message to history
        history.append({"role": "user", "content": user_message})

        # Keep history manageable (last 10 exchanges)
        if len(history) > 20:
            history = history[-20:]
            self.conversations[phone_number] = history

        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=600,
                temperature=0.7,
            )

            reply = response.choices[0].message.content.strip()

            # Add assistant reply to history
            history.append({"role": "assistant", "content": reply})

            return reply

        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return "Sorry, I'm having a technical issue right now 🙏 Please try again in a moment, or contact Gavin directly on 07833 665905."

    def get_grading_info(self, belt_grade: str) -> str:
        """Get specific grading requirements for a belt."""
        grading = KNOWLEDGE_BASE.get('grading_requirements', {})
        for grade_name, content in grading.items():
            if belt_grade.lower() in grade_name.lower():
                return f"*{grade_name} Requirements:*\n\n{content[:800]}"
        return None

    def clear_conversation(self, phone_number: str):
        """Reset conversation history for a phone number."""
        if phone_number in self.conversations:
            del self.conversations[phone_number]


# Singleton instance
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = MemberKnowledgeAgent()
    return _agent
