"""Consultation chat, code-level safety on the way IN, plus language detection and the fixed replies.

Input screen: questions that ask the astrologer to predict death, diagnose or predict serious
illness, predict accidents, or that signal self-harm are never sent to the AI. The user gets a fixed,
compassionate reply in their language; it costs no AI call and does not use up a message.
Gemstone / paid-ritual shopping questions get a fixed reply too (the service never sells those).

The output screen is app/ai/safety.py + app/ai/validator.py, applied in app/ai/chat.py.

Languages: en, hi, mr in Devanagari, and romanised Hindi / Marathi ("hi-Latn", "mr-Latn").
Tele-MANAS 14416 is the Government of India's free 24x7 mental-health line (telemanas.mohfw.gov.in).
"""

import re

LANGUAGES = ("en", "hi", "mr", "hi-Latn", "mr-Latn")
LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi (Devanagari)", "mr": "Marathi (Devanagari)",
    "hi-Latn": "Hindi written in Latin letters (romanised)", "mr-Latn": "Marathi written in Latin letters (romanised)",
}

# ---- language detection ----------------------------------------------------------------------------

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[a-z']+")
_MR_DEV = ("आहे", "आहेत", "माझ", "मला", "काय", "कधी", "होईल", "नाही", "कसे", "कसा", "कशी", "तुम्ही", "आणि",
           "साठी", "मध्ये", "का ", "सांगा", "करू", "झाल", "पाहिजे", "होणार", "चे ", "ची ", "चा ", "ला ")
_HI_DEV = ("है", "हैं", "मेरा", "मेरी", "मेरे", "मुझे", "क्या", "कब", "होगा", "होगी", "नहीं", "कैसे", "कैसा", "आप",
           "और", "के लिए", "में ", "बताइए", "बताओ", "करूं", "चाहिए", "का ", "की ", "को ")
_MR_LATIN = {"aahe", "ahe", "aahet", "majha", "mazha", "majhi", "mazhi", "majhe", "mala", "kadhi", "hoil", "kasa",
             "kashi", "kase", "kay", "kaay", "tumhi", "ani", "sathi", "madhe", "sanga", "karu", "pahije", "honar",
             "lagna", "nokri", "nahi", "zala", "zali", "kiti", "mhanje", "asel", "milel", "kuthe", "aata"}
_HI_LATIN = {"hai", "hain", "mera", "meri", "mere", "mujhe", "kya", "kab", "hoga", "hogi", "nahi", "nahin", "kaise",
             "kaisa", "aap", "aur", "liye", "mein", "batao", "bataiye", "karu", "karun", "chahiye", "shaadi", "shadi",
             "naukri", "kitna", "kitni", "kaun", "kahan", "abhi", "milega", "milegi", "rahega", "rahegi", "hun", "hoon"}
_SHARED_LATIN = _MR_LATIN & _HI_LATIN  # "nahi", "karu": count for neither


def detect_language(text: str, default: str = "en") -> str:
    """Best guess of the user's language and script. `default` wins when there is no signal (e.g. "ok")."""
    if _DEVANAGARI.search(text or ""):
        padded = f" {text} "
        marathi = sum(padded.count(marker) for marker in _MR_DEV)
        hindi = sum(padded.count(marker) for marker in _HI_DEV)
        if marathi == hindi:
            return default if default in ("hi", "mr") else "hi"
        return "mr" if marathi > hindi else "hi"
    words = _WORD.findall((text or "").lower())
    if not words:
        return default
    marathi = sum(1 for w in words if w in _MR_LATIN and w not in _SHARED_LATIN)
    hindi = sum(1 for w in words if w in _HI_LATIN and w not in _SHARED_LATIN)
    if marathi == 0 and hindi == 0:
        shared = sum(1 for w in words if w in _SHARED_LATIN)
        if shared and default in ("hi-Latn", "mr-Latn"):
            return default
        return "en" if len(words) >= 3 or default not in LANGUAGES else default
    if marathi == hindi:
        return default if default in ("hi-Latn", "mr-Latn") else "hi-Latn"
    return "mr-Latn" if marathi > hindi else "hi-Latn"


# ---- input screen ----------------------------------------------------------------------------------

_D = r"(?<![ऀ-ॿ])"
_I = re.IGNORECASE

_INPUT_PATTERNS = [
    # order matters: the first matching category wins, and self-harm must win over "death"
    ("self_harm", re.compile(
        r"\b(?:kill(?:ing)? myself|suicid\w*|end(?:ing)? my (?:own )?life|take my (?:own )?life|want to die|wish i (?:was|were) dead|"
        r"don'?t want to live|do not want to live|no reason to live|better off dead|hurt(?:ing)? myself|self[- ]harm|"
        r"marna chahta|marna chahti|mar jaana chahta|mar jana chahta|mar jaun|jeena nahi chahta|jeena nahi chahti|"
        r"jina nahi chahta|jeene ka mann? nahi|zindagi khatam|aatmahatya|atmahatya|khudkushi|jaan de du|jaan dena|"
        r"jiv dyava|jeev dyava|jiv deu|jagaycha nahi|jagayche nahi|jagu vatat nahi|maraves? vatat|marava vatta)\b", _I)),
    ("self_harm", re.compile(
        _D + r"(?:आत्महत्या|खुदकुशी|मरना चाहत|मर जाना चाहत|जीना नहीं चाहत|जीने का मन नहीं|जान दे दूं|जान देना|"
             r"जीव द्याव|जीव देऊ|जीव देण|जगायचं नाही|जगायचे नाही|जगावंसं वाटत नाही|जगावेसे वाटत नाही|मरावंसं वाट|मरावेसे वाट|स्वतःला संपव)")),
    ("death", re.compile(
        r"\b(?:when (?:will|do|would|shall) (?:i|he|she|they|we|my \w+) die|how (?:long|many years) (?:will|do|would) (?:i|he|she|they|my \w+) (?:live|have)|"
        r"(?:my|his|her|their) (?:death|lifespan|life span|longevity)|(?:date|time|year|age) of (?:my |his |her )?death|"
        r"will (?:i|he|she|they|my \w+) (?:die|survive|live long)|(?:am i|is (?:he|she|my \w+)) going to die|"
        r"going to die|about to die|how will i die|early death|untimely death|death (?:prediction|yog|yoga)|"
        r"kab marunga|kab marungi|kab maroonga|meri maut|meri mrityu|kitna jiyunga|kitni umar|kitni umra|meri umar kitni|"
        r"maut kab|mrityu kab|kab tak jiyunga|kab tak zinda|bach jayenge|bach jayega|bachega ya nahi|"
        r"kadhi marnar|majha mrutyu|maza mrutyu|mrutyu kadhi|kiti varsha jagnar|kiti varsh jagnar|ayushya kiti|vachel ka|vachnar ka)\b", _I)),
    ("death", re.compile(
        _D + r"(?:मृत्यु|मृत्यू|मौत|मरूंगा|मरूँगा|मरूंगी|मरूँगी|मरणार|मरेन|कितना जि|कितने साल जि|कब तक जि|कितनी उम्र|कितनी आयु|"
             r"आयुष्य किती|किती वर्षे जग|किती वर्ष जग|बच जाएंगे|बच जाएगा|बच जाएगी|बच पाएंगे|बचेंगे या नहीं|वाचेल का|वाचतील का|वाचणार का|अल्पायु)")),
    ("illness", re.compile(
        r"\b(?:(?<![(/])cancer\b(?!\)?,? (?:lagna|rashi|rasi|sign|ascendant|moon|rising|zodiac))|tumou?r|heart attack|stroke\b(?! of)|paralysis|kidney|dialysis|"
        r"chemo\w*|surgery|operation|transplant|hiv|aids\b|diabet\w+|infertil\w+|miscarriage|ivf|"
        r"(?:serious|terminal|chronic|incurable|fatal) (?:illness|disease)|will (?:i|he|she|my \w+) (?:recover|be cured|get cured|get well)|"
        r"do i have (?:a |any )?(?:disease|illness|tumou?r|cancer)|what (?:disease|illness)|which (?:disease|illness)|"
        r"bimari kab|bimari thik|bimari theek|beemari|kaun si bimari|konsi bimari|thik ho jaunga|theek ho jaunga|theek ho jayega|"
        r"ajar kadhi|aajar kadhi|ajar bara|aajar bara|konta ajar|bara honar ka|bare honar ka|operation karu|garbhpat|garbhapat)\b", _I)),
    ("illness", re.compile(
        _D + r"(?:कैंसर|कॅन्सर|कर्करोग|ट्यूमर|हार्ट अटैक|हार्ट अटॅक|दिल का दौरा|हृदयविकार|लकवा|पक्षाघात|अर्धांगवायू|किडनी|डायलिसिस|"
             r"कीमो|केमो|सर्जरी|ऑपरेशन|शस्त्रक्रिया|प्रत्यारोपण|मधुमेह|डायबिटीज|बांझपन|वंध्यत्व|गर्भपात|गंभीर बीमारी|गंभीर आजार|"
             r"कौन सी बीमारी|कौनसी बीमारी|बीमारी कब|बीमारी ठीक|ठीक हो जाऊंगा|ठीक हो जाएगा|ठीक हो जाएगी|कोणता आजार|आजार कधी|"
             r"आजार बरा|बरा होईल का|बरी होईल का|बरे होतील का|बरा होणार का)")),
    ("accident", re.compile(
        r"\b(?:accidents?|crash|will i (?:go to |be in )?(?:jail|prison)|go bankrupt|bankruptcy|"
        r"durghatna|accident hoga|hadsa|apghat|apaghat|jail hogi|jail jaunga|turungat)\b", _I)),
    ("accident", re.compile(_D + r"(?:दुर्घटना|एक्सीडेंट|अॅक्सिडेंट|हादसा|हादसे|अपघात|जेल|कारावास|तुरुंग|दिवालिया|दिवाळखोर)")),
    ("purchase", re.compile(
        r"\b(?:gem ?stones?|which (?:stone|ring|gem)|blue sapphire|yellow sapphire|neelam|pukhraj|pushkaraj|ruby|manik|emerald|panna|"
        r"red coral|moonga|munga|pearl|moti pehn|cat'?s eye|lehsunia|hessonite|gomed|rudraksha? (?:buy|kharid)|"
        r"kaun ?sa ratna|konsa ratna|ratna pehn|ratna dharan|konta ratna|kontha ratna|khada vapar|yantra (?:buy|kharid|ghya))\b", _I)),
    ("purchase", re.compile(_D + r"(?:रत्न(?!ागिरी)|नीलम|पुखराज|पुष्कराज|माणिक|पन्ना|पाचू|मूंगा|पोवळे|गोमेद|लहसुनिया|कौन सा पत्थर|कोणता खडा)")),
]


def screen_input(text: str) -> str | None:
    """Category of a question the AI must not be asked, or None if the message can go to the AI."""
    for category, pattern in _INPUT_PATTERNS:
        if pattern.search(text or ""):
            return category
    return None


# ---- fixed replies ---------------------------------------------------------------------------------

_HELPLINE = "14416"

CANNED = {
    "self_harm": {
        "en": "I'm really sorry you're carrying so much right now. What you're feeling matters far more than any chart, and you don't "
              "have to face it alone. Please talk to someone you trust today - a family member, a friend, a doctor. In India you can "
              f"call Tele-MANAS on {_HELPLINE}, free and open 24 hours, in your own language. If you are in immediate danger, please "
              "call 112. I'm here to talk about calmer things whenever you feel ready.",
        "hi": "मुझे बहुत दुख है कि आप इस समय इतना बोझ उठा रहे हैं। आप जो महसूस कर रहे हैं वह किसी भी कुंडली से कहीं ज़्यादा मायने रखता है, और आपको "
              "यह अकेले नहीं झेलना है। कृपया आज ही किसी भरोसेमंद व्यक्ति से बात करें - परिवार, मित्र या डॉक्टर। भारत में आप टेली-मानस "
              f"{_HELPLINE} पर निःशुल्क, 24 घंटे, अपनी भाषा में बात कर सकते हैं। तुरंत खतरा हो तो 112 पर कॉल करें। जब मन हो, मैं यहाँ हूँ।",
        "mr": "तुम्ही सध्या इतकं ओझं वाहत आहात हे ऐकून मला खरंच वाईट वाटलं. तुम्हाला जे वाटतंय ते कोणत्याही कुंडलीपेक्षा खूप महत्त्वाचं आहे, आणि हे "
              "तुम्हाला एकट्याने सोसायचं नाही. कृपया आजच विश्वासातल्या कुणाशी तरी बोला - घरचे, मित्र किंवा डॉक्टर. भारतात टेली-मानस "
              f"{_HELPLINE} या क्रमांकावर मोफत, २४ तास, तुमच्या भाषेत बोलता येतं. तातडीचा धोका असेल तर 112 वर फोन करा. मन झालं की मी इथे आहे.",
        "hi-Latn": "Mujhe bahut dukh hai ki aap is samay itna bojh utha rahe hain. Aap jo mehsoos kar rahe hain woh kisi bhi kundali se zyada "
                   "zaroori hai, aur aapko yeh akele nahi jhelna hai. Kripya aaj hi kisi bharosemand vyakti se baat karein - parivaar, dost ya "
                   f"doctor. Bharat mein aap Tele-MANAS {_HELPLINE} par muft, 24 ghante, apni bhasha mein baat kar sakte hain. Turant khatra ho "
                   "to 112 par call karein. Jab mann ho, main yahan hoon.",
        "mr-Latn": "Tumhi sadhya itka ojha vahat aahat he aikun mala kharach vait vatla. Tumhala je vatatay te kontyahi kundalipeksha khup "
                   "mahattvacha aahe, ani he tumhala ekatyane sosaycha nahi. Krupaya aajach vishvasatlya kunashi tari bola - gharche, mitra kinva "
                   f"doctor. Bharatat Tele-MANAS {_HELPLINE} var mofat, 24 taas, tumchya bhashet bolta yeta. Tatdicha dhoka asel tar 112 var "
                   "phone kara. Man zala ki mi ithe aahe.",
    },
    "death": {
        "en": "I don't make predictions about death or how long anyone will live - for you or for anyone you love. No chart can honestly "
              "answer that, and guessing would only cause worry. If someone is unwell, their doctors are the right people to ask. What I can "
              "do is look at what this period in your chart asks of you, and how to stay steady and useful to the people you care about. "
              "Would you like that?",
        "hi": "मैं मृत्यु या आयु के बारे में कोई भविष्यवाणी नहीं करता - न आपके लिए, न आपके किसी अपने के लिए। कोई भी कुंडली इसका ईमानदार उत्तर नहीं दे सकती, "
              "और अंदाज़ा लगाना केवल चिंता बढ़ाएगा। यदि कोई अस्वस्थ है तो सही सलाह उनके डॉक्टर ही देंगे। मैं यह ज़रूर देख सकता हूँ कि आपकी कुंडली में यह समय "
              "आपसे क्या माँगता है और आप अपनों के लिए कैसे स्थिर रह सकते हैं। क्या यह देखें?",
        "mr": "मृत्यू किंवा आयुष्य किती याबद्दल मी कोणतंही भाकीत करत नाही - तुमच्यासाठीही नाही आणि तुमच्या जवळच्यांसाठीही नाही. कोणतीही कुंडली याचं "
              "प्रामाणिक उत्तर देऊ शकत नाही, आणि अंदाज बांधणं फक्त काळजी वाढवेल. कुणी आजारी असेल तर योग्य सल्ला त्यांचे डॉक्टरच देतील. तुमच्या कुंडलीत "
              "हा काळ तुमच्याकडून काय मागतो आणि जवळच्यांसाठी तुम्ही कसे स्थिर राहू शकता, हे मी नक्की पाहू शकतो. ते पाहूया का?",
        "hi-Latn": "Main mrityu ya aayu ke baare mein koi bhavishyavani nahi karta - na aapke liye, na aapke kisi apne ke liye. Koi bhi kundali "
                   "iska imaandaar uttar nahi de sakti, aur andaza lagana sirf chinta badhayega. Agar koi aswasth hai to sahi salah unke doctor hi "
                   "denge. Main yeh zaroor dekh sakta hoon ki aapki kundali mein yeh samay aapse kya maangta hai aur aap apno ke liye kaise sthir "
                   "reh sakte hain. Kya yeh dekhein?",
        "mr-Latn": "Mrutyu kinva ayushya kiti yabaddal mi kontahi bhakit karat nahi - tumchyasathi nahi ani tumchya javalchyansathi pan nahi. "
                   "Kontihi kundali yacha pramanik uttar deu shakat nahi, ani andaj bandhna fakta kalji vadhvel. Kuni aajari asel tar yogya salla "
                   "tyanche doctor-ach detil. Tumchya kundalit ha kaal tumchyakadun kay magto ani javalchyansathi tumhi kase sthir rahu shakta, "
                   "he mi nakki pahu shakto. Te pahuya ka?",
    },
    "illness": {
        "en": "Astrology can't diagnose an illness or tell how a treatment will go, so I won't guess - please take this question to a "
              "qualified doctor, and follow their advice on any treatment decision. What I can offer from your chart is support around it: "
              "which routines, rest and mental habits suit you, and how to stay calm through a demanding phase. Shall we look at that?",
        "hi": "ज्योतिष न तो किसी बीमारी का निदान कर सकता है और न यह बता सकता है कि इलाज कैसा रहेगा, इसलिए मैं अंदाज़ा नहीं लगाऊँगा - कृपया यह प्रश्न योग्य "
              "डॉक्टर से पूछें और इलाज के हर निर्णय में उन्हीं की सलाह मानें। आपकी कुंडली से मैं इतना ज़रूर बता सकता हूँ कि कौन-सी दिनचर्या, विश्राम और मानसिक "
              "आदतें आपके लिए अनुकूल हैं और कठिन समय में मन शांत कैसे रखें। क्या यह देखें?",
        "mr": "ज्योतिष आजाराचं निदान करू शकत नाही किंवा उपचार कसे होतील हे सांगू शकत नाही, म्हणून मी अंदाज बांधणार नाही - कृपया हा प्रश्न तज्ज्ञ डॉक्टरांना "
              "विचारा आणि उपचाराचा प्रत्येक निर्णय त्यांच्या सल्ल्यानेच घ्या. तुमच्या कुंडलीवरून मी इतकं नक्की सांगू शकतो की कोणती दिनचर्या, विश्रांती आणि "
              "मानसिक सवयी तुम्हाला अनुकूल आहेत आणि कठीण काळात मन शांत कसं ठेवायचं. ते पाहूया का?",
        "hi-Latn": "Jyotish na to kisi bimari ka nidaan kar sakta hai aur na yeh bata sakta hai ki ilaaj kaisa rahega, isliye main andaza nahi "
                   "lagaunga - kripya yeh prashn yogya doctor se poochein aur ilaaj ke har nirnay mein unhi ki salah maanein. Aapki kundali se main "
                   "itna zaroor bata sakta hoon ki kaun-si dincharya, vishram aur mansik aadatein aapke liye anukool hain. Kya yeh dekhein?",
        "mr-Latn": "Jyotish aajarache nidan karu shakat nahi kinva upchar kase hotil he sangu shakat nahi, mhanun mi andaj bandhnar nahi - "
                   "krupaya ha prashna tajnya doctoranna vichara ani upcharacha pratyek nirnay tyanchya sallyanech ghya. Tumchya kundalivarun mi "
                   "itka nakki sangu shakto ki konti dincharya, vishranti ani mansik savayi tumhala anukul aahet. Te pahuya ka?",
    },
    "accident": {
        "en": "I don't predict accidents, legal trouble or other frightening events - no chart can honestly do that, and such guesses only "
              "create fear. For a legal or money matter, please speak to a qualified professional. From your chart I can tell you which "
              "periods call for extra patience and care with decisions, and what helps you stay steady. Would that be useful?",
        "hi": "मैं दुर्घटना, कानूनी परेशानी या ऐसी डरावनी घटनाओं की भविष्यवाणी नहीं करता - कोई कुंडली यह ईमानदारी से नहीं बता सकती, और ऐसे अंदाज़े केवल डर "
              "पैदा करते हैं। कानूनी या आर्थिक विषय में कृपया योग्य विशेषज्ञ से बात करें। आपकी कुंडली से मैं यह बता सकता हूँ कि किन अवधियों में निर्णयों में अधिक "
              "धैर्य और सावधानी चाहिए। क्या यह उपयोगी होगा?",
        "mr": "अपघात, कायदेशीर अडचणी किंवा अशा भीतीदायक घटनांचं भाकीत मी करत नाही - कोणतीही कुंडली ते प्रामाणिकपणे सांगू शकत नाही, आणि असे अंदाज फक्त "
              "भीती निर्माण करतात. कायदेशीर किंवा आर्थिक बाबतीत कृपया पात्र तज्ज्ञांशी बोला. तुमच्या कुंडलीवरून कोणत्या काळात निर्णय घेताना जास्त संयम आणि "
              "काळजी हवी, हे मी सांगू शकतो. ते उपयोगी ठरेल का?",
        "hi-Latn": "Main durghatna, kanooni pareshani ya aisi daravni ghatnaon ki bhavishyavani nahi karta - koi kundali yeh imaandari se nahi "
                   "bata sakti, aur aise andaze sirf dar paida karte hain. Kanooni ya aarthik vishay mein kripya yogya visheshagya se baat karein. "
                   "Aapki kundali se main yeh bata sakta hoon ki kin avadhiyon mein nirnayon mein adhik dhairya chahiye. Kya yeh upyogi hoga?",
        "mr-Latn": "Apghat, kaydeshir adchani kinva asha bhitidayak ghatnancha bhakit mi karat nahi - kontihi kundali te pramanikpane sangu "
                   "shakat nahi, ani ase andaj fakta bhiti nirman kartat. Kaydeshir kinva arthik babtit krupaya patra tajnyanshi bola. Tumchya "
                   "kundalivarun kontya kalat nirnay ghetana jast sanyam hava, he mi sangu shakto. Te upyogi tharel ka?",
    },
    "purchase": {
        "en": "We don't recommend gemstones, rings, yantras or paid rituals here - they are costly, and the tradition's simplest remedies "
              "work through your own effort, not a purchase. Ask me instead for free remedies suited to your chart - a mantra, a small act "
              "of charity or service, or a daily habit for the graha that needs support - and I'll suggest a few.",
        "hi": "हम यहाँ रत्न, अंगूठी, यंत्र या सशुल्क अनुष्ठान की सलाह नहीं देते - ये महँगे होते हैं, और परंपरा के सबसे सरल उपाय आपके अपने प्रयास से काम करते हैं, "
              "ख़रीदारी से नहीं। इसके बजाय मुझसे अपनी कुंडली के अनुसार निःशुल्क उपाय पूछिए - कोई मंत्र, छोटा-सा दान या सेवा, या किसी ग्रह के लिए रोज़ की आदत।",
        "mr": "आम्ही इथे रत्न, अंगठी, यंत्र किंवा सशुल्क विधी सुचवत नाही - ते महाग असतात, आणि परंपरेतले सर्वात सोपे उपाय तुमच्या स्वतःच्या प्रयत्नांनी काम "
              "करतात, खरेदीने नाही. त्याऐवजी तुमच्या कुंडलीला साजेसे मोफत उपाय मला विचारा - एखादा मंत्र, छोटंसं दान किंवा सेवा, किंवा एखाद्या ग्रहासाठी रोजची सवय.",
        "hi-Latn": "Hum yahan ratna, anguthi, yantra ya paid anushthan ki salah nahi dete - yeh mehenge hote hain, aur parampara ke sabse saral "
                   "upay aapke apne prayas se kaam karte hain, kharidari se nahi. Iske bajay mujhse apni kundali ke anusar muft upay poochiye - koi "
                   "mantra, chhota-sa daan ya seva, ya kisi graha ke liye roz ki aadat.",
        "mr-Latn": "Aamhi ithe ratna, angathi, yantra kinva paid vidhi suchvat nahi - te mahag astat, ani paramparetle sarvat sope upay tumchya "
                   "swatahchya prayatnanni kaam kartat, kharedine nahi. Tyaaivaji tumchya kundalila sajese mofat upay mala vichara - ekhada mantra, "
                   "chhotasa daan kinva seva, kinva ekhadya grahasathi rojchi savay.",
    },
    "fallback": {
        "en": "I couldn't put together a reliable answer to that just now, so I'd rather not guess. Could you ask it a little differently - "
              "for example about career, relationships, your current dasha, or what to focus on this year? This message was not counted.",
        "hi": "मैं अभी इसका भरोसेमंद उत्तर तैयार नहीं कर पाया, इसलिए अंदाज़ा नहीं लगाऊँगा। क्या आप इसे थोड़ा अलग तरह से पूछ सकते हैं - जैसे करियर, रिश्ते, "
              "वर्तमान दशा, या इस वर्ष किस पर ध्यान दें? यह संदेश गिना नहीं गया है।",
        "mr": "याचं विश्वासार्ह उत्तर मला आत्ता तयार करता आलं नाही, म्हणून मी अंदाज बांधणार नाही. हा प्रश्न थोडा वेगळ्या पद्धतीने विचाराल का - उदा. करिअर, "
              "नातेसंबंध, सध्याची दशा, किंवा या वर्षी कशावर लक्ष द्यावं? हा संदेश मोजला गेलेला नाही.",
        "hi-Latn": "Main abhi iska bharosemand uttar taiyar nahi kar paya, isliye andaza nahi lagaunga. Kya aap ise thoda alag tarah se pooch "
                   "sakte hain - jaise career, rishte, vartaman dasha, ya is varsh kis par dhyan dein? Yeh sandesh gina nahi gaya hai.",
        "mr-Latn": "Yacha vishvasarh uttar mala aatta tayar karta aala nahi, mhanun mi andaj bandhnar nahi. Ha prashna thoda veglya paddhatine "
                   "vicharal ka - uda. career, natesambandh, sadhyachi dasha, kinva ya varshi kashavar laksha dyava? Ha sandesh mojla gelela nahi.",
    },
}


def canned_reply(category: str, language: str) -> str:
    replies = CANNED[category]
    return replies.get(language) or replies["en"]
