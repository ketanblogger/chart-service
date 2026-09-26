"""A fake LLM client for the rashifal pipeline: no network, deterministic, rashi-specific.

Lives under tests/ on purpose - nothing in app/ can import it, so fake text can never reach production.
It reads the transit brief out of the prompt (like the model would) and writes sentences from the
brief's own houses and signs, so the real safety screen and fact validator run on realistic text.
"""

import json
import re

from app.ai.client import LLMResult

MARK = "[TEST CONTENT]"
MARK_DEVANAGARI = {"mr": "[चाचणी मजकूर]", "hi": "[परीक्षण सामग्री]"}  # Devanagari pages must not contain Latin words
_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}
_PAD = {
    "en": "Keep your plans simple and your words kind, and give steady effort to the work in front of you. "
          "Small, regular steps bring more than sudden pushes in this period.",
    "mr": "तुमची कामे साधी आणि नियोजनबद्ध ठेवा, बोलण्यात गोडवा ठेवा आणि समोर असलेल्या कामाला सातत्याने वेळ द्या. "
          "या काळात अचानक घाई करण्यापेक्षा छोट्या, नियमित पावलांचा जास्त उपयोग होईल.",
    "hi": "अपनी योजनाएँ सरल रखें, वाणी में मिठास रखें और सामने के काम को लगातार समय दें। "
          "इस अवधि में अचानक जल्दबाज़ी की जगह छोटे, नियमित कदम अधिक फल देंगे।",
}


def _ordinal(n: int) -> str:
    return _ORDINAL.get(n, f"{n}th")


def brief_from_prompt(user: str) -> dict:
    return json.loads(re.search(r"<data>\n(.*?)\n</data>", user, re.S).group(1))


def languages_from_schema(schema: dict) -> list[str]:
    return list(schema["properties"])


def _devanagari(node: dict, language: str) -> str:
    """The brief's Devanagari name for a graha or a sign, in the spelling that language uses.

    Marathi writes मंगळ, शनी, गुरू, राहू, केतू and तूळ where the engine's single `devanagari` field carries the
    Hindi मंगल, शनि, गुरु, राहु, केतु, तुला, so the brief adds `devanagari_mr` wherever the two differ. A model
    that ignores it produces the Hindi spelling in a Marathi reading, which is what the live pages did, so the
    fake reads the field the same way a correct model would - otherwise the tests would pass on text the
    checker is there to reject.
    """
    return node["devanagari_mr"] if language == "mr" and node.get("devanagari_mr") else node["devanagari"]


def write_page(brief: dict, language: str, run: int) -> dict:
    rashi, period = brief["rashi"], brief["period"]["slug"]
    by_key = {p["graha"]["key"]: p for p in brief["positions_at_start"]}
    guru, shani, mangal = by_key["Jupiter"], by_key["Saturn"], by_key["Mars"]
    # Enough padding to clear the period's floor with room to spare, DERIVED from the floor rather than
    # hardcoded: when app/rashifal/generate.py raises a minimum, this follows it instead of silently
    # failing every generation in the suite. Four blocks carry the pad (overview + three sections).
    from app.rashifal.generate import _MIN_WORDS
    pad_words = max(1, len(_PAD[language].split()))
    repeat = max(1, -(-int(_MIN_WORDS[period] * 1.3) // (4 * pad_words)))
    pad = " ".join([_PAD[language]] * repeat)
    if language == "en":
        line = lambda p: f"{p['graha']['name']} in your {_ordinal(p['house'])} house in {p['sign']['name']}"
        overview = (f"{MARK} run {run}. For {rashi['name']} rashi this period is shaped by {line(guru)} and {line(shani)}. {pad}")
        sections = {
            "career_money": [f"With {line(mangal)}, work asks for focus and patience. {pad}"],
            "love_family": [f"At home, {line(guru)} supports warm conversations. {pad}"],
            "health_wellbeing": [f"Keep regular sleep, light food and a daily walk. {pad}"],
        }
        tip, note = "Light a lamp at home each evening and sit quietly for five minutes.", "A good day to plan calmly."
        headline = f"{MARK} {rashi['name']}: steady steps, run {run}"
    else:
        mark = MARK_DEVANAGARI[language]
        in_sign = "राशीत" if language == "mr" else "राशि में"
        line = lambda p: f"{_devanagari(p['graha'], language)} {_devanagari(p['sign'], language)} {in_sign}"
        if language == "mr":
            house = f"{_devanagari(shani['graha'], language)} तुमच्या {shani['house']} व्या स्थानात आहे."
            overview = f"{mark} फेरी {run}. {_devanagari(rashi, language)} राशीसाठी या काळात {line(guru)} आणि {line(shani)} आहे. {house} {pad}"
            sections = {
                "career_money": [f"{line(mangal)} असल्यामुळे कामात एकाग्रता आणि संयम महत्त्वाचा आहे. {pad}"],
                "love_family": [f"घरात {line(guru)} असल्याने संवाद सुखद राहील. {pad}"],
                "health_wellbeing": [f"नियमित झोप, हलका आहार आणि रोज चालणे ठेवा. {pad}"],
            }
            tip, note = "रोज संध्याकाळी घरी दिवा लावा आणि पाच मिनिटे शांत बसा.", "शांतपणे नियोजन करण्यासाठी चांगला दिवस."
            headline = f"{mark} {_devanagari(rashi, language)}: स्थिर पावले, फेरी {run}"
        else:
            house = f"{shani['graha']['devanagari']} आपके {shani['house']} वें भाव में है।"
            overview = f"{mark} क्रम {run}. {rashi['devanagari']} राशि के लिए इस अवधि में {line(guru)} और {line(shani)} है। {house} {pad}"
            sections = {
                "career_money": [f"{line(mangal)} होने से काम में एकाग्रता और धैर्य ज़रूरी है। {pad}"],
                "love_family": [f"घर में {line(guru)} होने से बातचीत सुखद रहेगी। {pad}"],
                "health_wellbeing": [f"नियमित नींद, हल्का भोजन और रोज़ टहलना बनाए रखें। {pad}"],
            }
            tip, note = "हर शाम घर में दीपक जलाएँ और पाँच मिनट शांत बैठें।", "शांति से योजना बनाने के लिए अच्छा दिन।"
            headline = f"{mark} {rashi['devanagari']}: स्थिर कदम, क्रम {run}"
    key_dates = [{"event_id": event["id"], "note": note} for event in brief["events"][:3]]
    summary = " ".join(overview.split()[:30])
    return {"headline": headline, "summary": summary, "overview": overview, "sections": sections, "key_dates": key_dates,
            "tip": tip}


class FakeRashifalClient:
    """Counts calls; `mutate(data, brief, call_number)` lets a test corrupt the output."""

    def __init__(self, mutate=None, model: str = "fake-model"):
        self.calls: list[dict] = []
        self.mutate = mutate
        self.model = model

    def generate_json(self, *, system: str, user: str, schema: dict) -> LLMResult:
        self.calls.append({"system": system, "user": user, "schema": schema})
        brief = brief_from_prompt(user)
        data = {code: write_page(brief, code, len(self.calls)) for code in languages_from_schema(schema)}
        if self.mutate:
            data = self.mutate(data, brief, len(self.calls)) or data
        return LLMResult(data=data, model=self.model, stop_reason="end_turn",
                         usage={"input_tokens": 2000, "output_tokens": 1500, "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 1200}, request_id=f"req_fake_{len(self.calls)}")


class FakeBatchClient(FakeRashifalClient):
    """Same, through the batch interface (one `batches` entry per round)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.batches: list[list[str]] = []

    def generate_json_batch(self, requests, *, poll_seconds=0, timeout_seconds=0, on_poll=None):
        self.batches.append([item["custom_id"] for item in requests])
        self.batch_schemas = [item["schema"] for item in requests]
        if on_poll:
            on_poll()
        return {item["custom_id"]: self.generate_json(system=item["system"], user=item["user"], schema=item["schema"])
                for item in reversed(requests)}  # results come back in any order
