"""What the numerology pages say, in three trees.

THE RULES, which are the proprietor's and are not negotiable in this copy:
  - Chaldean only, and the page says so.
  - Positive framing: strong, good, neutral. Never "unlucky", never "bad number", never a dosh, and
    never "change your name or else". A person cannot change their date of birth.
  - No guarantees, and a disclaimer under every result.
  - The method is shown on the page, so a reader can check the arithmetic rather than trust it.
"""

PAGE = {
    "en": {
        "title": "Numerology Calculator: Name Number & Date of Birth (Free)",
        "h1": "Numerology calculator",
        "meta": ("Free numerology calculator: your mulank and bhagyank from your date of birth, your "
                 "name number in the Chaldean system, and your Lo Shu grid. The method is shown, so "
                 "you can check every number yourself."),
        "lead": ("Enter a name and a date of birth. You get the mulank and bhagyank, the name number "
                 "in the Chaldean system, and the Lo Shu grid - with the working shown for each, so "
                 "you can check it rather than take it on trust."),
        "name_label": "Name",
        "name_help": "In English letters. The Chaldean table is for the Latin alphabet.",
        "dob_label": "Date of birth",
        "day_label": "Day", "month_label": "Month", "year_label": "Year",
        "submit": "Calculate",
        "mulank_heading": "Mulank (your day number)",
        "bhagyank_heading": "Bhagyank (your destiny number)",
        "name_heading": "Name number (Chaldean)",
        "loshu_heading": "Lo Shu grid",
        "method_heading": "How these are worked out",
        "back_to_calculator": "Work out your own numbers",
        "repeated_label": "Repeated",
        "missing_label": "Missing",
        "planes_label": "Complete planes",
        "none": "none",
        "unusable_name": ("This name has no Latin letters in it, so the Chaldean table cannot read "
                          "it. Type it in English letters to get a name number."),
        "method": (
            "Mulank is the day of the month you were born, added until one digit is left: born on "
            "the 29th, 2+9 = 11, and 1+1 = 2.",
            "Bhagyank uses the whole date in the form DD-MM-YYYY, the same way.",
            "The name number uses the Chaldean table, which gives every letter a value from 1 to 8. "
            "There is no letter worth 9: the 9 was held apart.",
            "The Lo Shu grid places every non-zero digit of your date of birth, plus your mulank and "
            "your bhagyank, into the nine cells. Schools differ on whether the last two go in; this "
            "is the common Indian method and it is stated here so you know which you are reading.",
        ),
        "disclaimer": ("Numerology is a traditional practice, not a measurement. Nothing here "
                       "predicts what will happen, and no number is lucky or unlucky - a number you "
                       "were born with is not something to fix."),
    },
    "hi": {
        # The Roman term is required on a Devanagari title and is the one people type:
        # "numerology calculator" is 500,000 a month, "numerology in hindi" 5,000.
        "title": "अंक ज्योतिष कैलकुलेटर | Numerology Calculator in Hindi",
        "h1": "अंक ज्योतिष कैलकुलेटर",
        "meta": ("मुफ़्त अंक ज्योतिष कैलकुलेटर: जन्मतिथि से मूलांक और भाग्यांक, कैल्डियन पद्धति से नाम अंक, "
                 "और लो शू ग्रिड। गणना का तरीक़ा पन्ने पर दिया है, ताकि आप हर अंक ख़ुद जाँच सकें।"),
        "lead": ("नाम और जन्मतिथि भरिए। आपको मूलांक, भाग्यांक, कैल्डियन पद्धति से नाम अंक और लो शू ग्रिड "
                 "मिलेंगे - हर एक की गणना साथ में दिखाई गई है, ताकि आप उसे मान लेने के बजाय जाँच सकें।"),
        "name_label": "नाम",
        "name_help": "अंग्रेज़ी अक्षरों में। कैल्डियन तालिका रोमन वर्णमाला के लिए है।",
        "dob_label": "जन्मतिथि",
        "day_label": "दिन", "month_label": "महीना", "year_label": "साल",
        "submit": "गणना कीजिए",
        "mulank_heading": "मूलांक",
        "bhagyank_heading": "भाग्यांक",
        "name_heading": "नाम अंक (कैल्डियन)",
        "loshu_heading": "लो शू ग्रिड",
        "method_heading": "ये कैसे निकाले जाते हैं",
        "back_to_calculator": "अपने अंक निकालिए",
        "repeated_label": "बार-बार आने वाले",
        "missing_label": "अनुपस्थित",
        "planes_label": "पूर्ण तल",
        "none": "कोई नहीं",
        "unusable_name": ("इस नाम में रोमन अक्षर नहीं हैं, इसलिए कैल्डियन तालिका इसे नहीं पढ़ सकती। नाम "
                          "अंक के लिए नाम अंग्रेज़ी अक्षरों में लिखिए।"),
        "method": (
            "मूलांक जन्म की तारीख़ है, एक अंक बचने तक जोड़ी गई: 29 तारीख़ को जन्म हो तो 2+9 = 11, और 1+1 = 2।",
            "भाग्यांक में पूरी तारीख़ - दिन, महीना और साल - इसी तरह जोड़ी जाती है।",
            "नाम अंक कैल्डियन तालिका से निकलता है, जिसमें हर अक्षर का मान 1 से 8 तक है। 9 के मान का कोई "
            "अक्षर नहीं है: 9 को अलग रखा गया।",
            "लो शू ग्रिड में जन्मतिथि के सभी ग़ैर-शून्य अंक, साथ में मूलांक और भाग्यांक, नौ ख़ानों में रखे जाते "
            "हैं। आख़िरी दो को रखना है या नहीं, इस पर पद्धतियाँ अलग हैं; यह प्रचलित भारतीय तरीक़ा है और यहाँ "
            "लिख दिया गया है ताकि आपको पता रहे कि आप कौन-सा पढ़ रहे हैं।",
        ),
        "disclaimer": ("अंक ज्योतिष एक परंपरा है, कोई माप नहीं। यहाँ कुछ भी यह नहीं बताता कि क्या होगा, और "
                       "कोई अंक शुभ या अशुभ नहीं होता - जिस अंक के साथ आप जन्मे हैं, वह सुधारने की चीज़ नहीं है।"),
    },
    "mr": {
        "title": "अंकज्योतिष कॅल्क्युलेटर | Numerology Calculator Marathi",
        "h1": "अंकज्योतिष कॅल्क्युलेटर",
        "meta": ("मोफत अंकज्योतिष कॅल्क्युलेटर: जन्मतारखेवरून मूलांक आणि भाग्यांक, कॅल्डियन पद्धतीने नाम अंक, "
                 "आणि लो शू ग्रिड. गणनेची पद्धत पानावर दिली आहे, जेणेकरून तुम्ही प्रत्येक अंक स्वतः तपासू शकता."),
        "lead": ("नाव आणि जन्मतारीख भरा. तुम्हाला मूलांक, भाग्यांक, कॅल्डियन पद्धतीने नाम अंक आणि लो शू ग्रिड "
                 "मिळेल - प्रत्येकाची गणना सोबत दाखवली आहे, म्हणजे ती गृहीत न धरता तपासता येईल."),
        "name_label": "नाव",
        "name_help": "इंग्रजी अक्षरांत. कॅल्डियन तक्ता रोमन वर्णमालेसाठी आहे.",
        "dob_label": "जन्मतारीख",
        "day_label": "दिवस", "month_label": "महिना", "year_label": "वर्ष",
        "submit": "गणना करा",
        "mulank_heading": "मूलांक",
        "bhagyank_heading": "भाग्यांक",
        "name_heading": "नाम अंक (कॅल्डियन)",
        "loshu_heading": "लो शू ग्रिड",
        "method_heading": "हे कसे काढले जातात",
        "back_to_calculator": "तुमचे अंक काढा",
        "repeated_label": "पुन्हा येणारे",
        "missing_label": "नसलेले",
        "planes_label": "पूर्ण तल",
        "none": "काहीही नाही",
        "unusable_name": ("या नावात रोमन अक्षरे नाहीत, त्यामुळे कॅल्डियन तक्ता ते वाचू शकत नाही. नाम अंकासाठी "
                          "नाव इंग्रजी अक्षरांत लिहा."),
        "method": (
            "मूलांक म्हणजे जन्माची तारीख, एक अंक उरेपर्यंत बेरीज केलेली: 29 तारखेला जन्म असेल तर 2+9 = 11, "
            "आणि 1+1 = 2.",
            "भाग्यांकात संपूर्ण तारीख - दिवस, महिना आणि वर्ष - अशीच बेरीज केली जाते.",
            "नाम अंक कॅल्डियन तक्त्यावरून येतो, ज्यात प्रत्येक अक्षराचे मूल्य 1 ते 8 आहे. 9 मूल्याचे अक्षर नाही: "
            "9 वेगळा ठेवला गेला.",
            "लो शू ग्रिडमध्ये जन्मतारखेचे सर्व शून्येतर अंक, सोबत मूलांक आणि भाग्यांक, नऊ चौकटींत ठेवले जातात. "
            "शेवटचे दोन ठेवायचे की नाही यावर पद्धती भिन्न आहेत; ही प्रचलित भारतीय पद्धत आहे आणि ती इथे "
            "लिहिली आहे जेणेकरून तुम्ही कोणती वाचत आहात हे कळेल.",
        ),
        "disclaimer": ("अंकज्योतिष ही एक परंपरा आहे, मोजमाप नव्हे. इथले काहीही काय होईल हे सांगत नाही, आणि "
                       "कोणताही अंक शुभ किंवा अशुभ नसतो - ज्या अंकासह तुम्ही जन्मलात तो दुरुस्त करण्याची गोष्ट नाही."),
    },
}


#: THE NUMBER CHECKER. One page, four kinds of number. Four separate pages would say the same thing
#: about different digits and compete with each other for the same phrases.
CHECK = {
    "en": {
        "title": "Mobile Number Numerology: Check Any Number (Free)",
        "h1": "Number check: mobile, vehicle, house, business",
        "meta": ("Free numerology check for a mobile, vehicle, house or business number: its total, "
                 "its single digit, and how it sits with your mulank and bhagyank. The working is "
                 "shown."),
        "lead": ("Enter any number. You get its total, the single digit it reduces to, and - if you "
                 "give your date of birth - how that number sits with your own."),
        "number_label": "Number to check",
        "day_label": "Day", "month_label": "Month", "year_label": "Year",
        "number_help": "A mobile, vehicle, house or business number. Only the digits are read.",
        "kinds": ("Mobile", "Vehicle", "House", "Business"),
        "total_label": "Total",
        "number_heading": "Reduces to",
        "ruler_label": "Ruled by",
        "fit_heading": "How it sits with your numbers",
        "fit_mulank": "With your mulank",
        "fit_bhagyank": "With your bhagyank",
        "levels": {"strong": "Strong match", "good": "Good match", "neutral": "Neutral"},
        "neutral_note": ("Neutral means no special affinity either way - not a problem, and not "
                         "something to change a number over."),
        "unusable": "There were no digits in that. Type the number itself.",
        "disclaimer": ("Numerology is a traditional practice, not a measurement. No number here is "
                       "lucky or unlucky, and nothing on this page is a reason to spend money on a "
                       "different one."),
    },
    "hi": {
        "title": "मोबाइल नंबर अंक ज्योतिष | Mobile Number Numerology",
        "h1": "नंबर जाँच: मोबाइल, गाड़ी, घर, व्यवसाय",
        "meta": ("मोबाइल, गाड़ी, घर या व्यवसाय के नंबर की मुफ़्त अंक ज्योतिष जाँच: उसका योग, उसका एक अंक, "
                 "और वह आपके मूलांक और भाग्यांक के साथ कैसा बैठता है। गणना साथ में दिखाई गई है।"),
        "lead": ("कोई भी नंबर भरिए। आपको उसका योग मिलेगा, वह जिस एक अंक में सिमटता है वह मिलेगा, और "
                 "अगर आप जन्मतिथि देंगे तो यह भी कि वह आपके अपने अंकों के साथ कैसा बैठता है।"),
        "number_label": "जाँचने का नंबर",
        "day_label": "दिन", "month_label": "महीना", "year_label": "साल",
        "number_help": "मोबाइल, गाड़ी, घर या व्यवसाय का नंबर। सिर्फ़ अंक पढ़े जाते हैं।",
        "kinds": ("मोबाइल", "गाड़ी", "घर", "व्यवसाय"),
        "total_label": "योग",
        "number_heading": "सिमटकर बनता है",
        "ruler_label": "स्वामी",
        "fit_heading": "यह आपके अंकों के साथ कैसा बैठता है",
        "fit_mulank": "मूलांक के साथ",
        "fit_bhagyank": "भाग्यांक के साथ",
        "levels": {"strong": "मज़बूत मेल", "good": "अच्छा मेल", "neutral": "तटस्थ"},
        "neutral_note": ("तटस्थ का अर्थ है किसी ओर कोई ख़ास खिंचाव नहीं - यह कोई समस्या नहीं है, और "
                         "नंबर बदलने की वजह तो बिलकुल नहीं।"),
        "unusable": "उसमें कोई अंक नहीं था। नंबर ही लिखिए।",
        "disclaimer": ("अंक ज्योतिष एक परंपरा है, कोई माप नहीं। यहाँ कोई अंक शुभ या अशुभ नहीं है, और इस "
                       "पन्ने पर ऐसा कुछ नहीं है जो दूसरा नंबर ख़रीदने की वजह बने।"),
    },
    "mr": {
        "title": "मोबाइल नंबर अंकज्योतिष | Mobile Number Numerology",
        "h1": "नंबर तपासणी: मोबाइल, गाडी, घर, व्यवसाय",
        "meta": ("मोबाइल, गाडी, घर किंवा व्यवसायाच्या नंबरची मोफत अंकज्योतिष तपासणी: त्याची बेरीज, त्याचा "
                 "एक अंक, आणि तो तुमच्या मूलांक व भाग्यांकाशी कसा जुळतो. गणना सोबत दाखवली आहे."),
        "lead": ("कोणताही नंबर भरा. तुम्हाला त्याची बेरीज मिळेल, तो ज्या एका अंकात येतो तो मिळेल, आणि "
                 "जन्मतारीख दिल्यास तो तुमच्या स्वतःच्या अंकांशी कसा जुळतो तेही."),
        "number_label": "तपासायचा नंबर",
        "day_label": "दिवस", "month_label": "महिना", "year_label": "वर्ष",
        "number_help": "मोबाइल, गाडी, घर किंवा व्यवसायाचा नंबर. फक्त अंक वाचले जातात.",
        "kinds": ("मोबाइल", "गाडी", "घर", "व्यवसाय"),
        "total_label": "बेरीज",
        "number_heading": "येतो",
        "ruler_label": "स्वामी",
        "fit_heading": "हा तुमच्या अंकांशी कसा जुळतो",
        "fit_mulank": "मूलांकाशी",
        "fit_bhagyank": "भाग्यांकाशी",
        "levels": {"strong": "मजबूत जुळणी", "good": "चांगली जुळणी", "neutral": "तटस्थ"},
        "neutral_note": ("तटस्थ म्हणजे कोणत्याही बाजूने विशेष ओढ नाही - ही अडचण नाही, आणि नंबर बदलण्याचे "
                         "कारण तर मुळीच नाही."),
        "unusable": "त्यात एकही अंक नव्हता. नंबरच लिहा.",
        "disclaimer": ("अंकज्योतिष ही परंपरा आहे, मोजमाप नव्हे. इथे कोणताही अंक शुभ किंवा अशुभ नाही, आणि "
                       "दुसरा नंबर विकत घेण्याचे कारण या पानावर काहीही नाही."),
    },
}


#: THE LO SHU PAGE. The main calculator already draws the grid; this is the page somebody typing
#: "lo shu grid calculator" lands on, with the grid first and no name field in the way.
LO_SHU = {
    "en": {
        "title": "Lo Shu Grid Calculator: Your Grid From Your Date of Birth",
        "h1": "Lo Shu grid calculator",
        "meta": ("Free Lo Shu grid calculator: your grid from your date of birth, with the repeated "
                 "and missing numbers and which planes are complete. The method used is stated on "
                 "the page."),
        "lead": ("The Lo Shu square is a three-by-three magic grid - every row, column and diagonal "
                 "adds to 15. Your date of birth places digits into it, and what is repeated, what "
                 "is absent and which lines are complete is what the tradition reads."),
        "grid_heading": "Your grid",
        "planes_heading": "The planes",
        "plane_names": {
            "mental": "Mental (4-9-2)", "emotional": "Emotional (3-5-7)",
            "practical": "Practical (8-1-6)", "thought": "Thought (4-3-8)",
            "will": "Will (9-5-1)", "action": "Action (2-7-6)",
            "golden": "Golden (4-5-6)", "silver": "Silver (2-5-8)",
        },
        "complete": "complete", "incomplete": "not complete",
        "missing_note": ("A missing number is not a fault and not something to fix. It is read as an "
                         "area the tradition says you work at rather than one that comes free."),
        "submit": "Draw my grid",
    },
    "hi": {
        "title": "लो शू ग्रिड कैलकुलेटर | Lo Shu Grid Calculator Hindi",
        "h1": "लो शू ग्रिड कैलकुलेटर",
        "meta": ("मुफ़्त लो शू ग्रिड कैलकुलेटर: जन्मतिथि से आपका ग्रिड, बार-बार आने वाले और अनुपस्थित अंकों "
                 "के साथ, और कौन से तल पूरे हैं। जो पद्धति इस्तेमाल हुई है वह पन्ने पर लिखी है।"),
        "lead": ("लो शू वर्ग तीन-गुणा-तीन का जादुई ग्रिड है - हर पंक्ति, स्तंभ और विकर्ण का योग 15 होता है। "
                 "आपकी जन्मतिथि इसमें अंक रखती है, और क्या बार-बार आता है, क्या नहीं है, और कौन सी "
                 "रेखाएँ पूरी हैं - परंपरा यही पढ़ती है।"),
        "grid_heading": "आपका ग्रिड",
        "planes_heading": "तल",
        "plane_names": {
            "mental": "मानसिक (4-9-2)", "emotional": "भावनात्मक (3-5-7)",
            "practical": "व्यावहारिक (8-1-6)", "thought": "विचार (4-3-8)",
            "will": "संकल्प (9-5-1)", "action": "कर्म (2-7-6)",
            "golden": "स्वर्ण (4-5-6)", "silver": "रजत (2-5-8)",
        },
        "complete": "पूर्ण", "incomplete": "अपूर्ण",
        "missing_note": ("कोई अंक न होना दोष नहीं है और सुधारने की चीज़ भी नहीं। परंपरा इसे ऐसा क्षेत्र "
                         "मानती है जिस पर आप मेहनत करते हैं, जो मुफ़्त में नहीं मिलता।"),
        "submit": "मेरा ग्रिड बनाइए",
    },
    "mr": {
        "title": "लो शू ग्रिड कॅल्क्युलेटर | Lo Shu Grid Calculator",
        "h1": "लो शू ग्रिड कॅल्क्युलेटर",
        "meta": ("मोफत लो शू ग्रिड कॅल्क्युलेटर: जन्मतारखेवरून तुमचा ग्रिड, पुन्हा येणारे आणि नसलेले अंक, "
                 "आणि कोणते तल पूर्ण आहेत. वापरलेली पद्धत पानावर लिहिली आहे."),
        "lead": ("लो शू चौरस हा तीन-बाय-तीनचा जादुई ग्रिड आहे - प्रत्येक ओळ, स्तंभ आणि कर्णाची बेरीज 15 "
                 "होते. तुमची जन्मतारीख त्यात अंक ठेवते, आणि काय पुन्हा येते, काय नाही, आणि कोणत्या रेषा "
                 "पूर्ण आहेत - परंपरा हेच वाचते."),
        "grid_heading": "तुमचा ग्रिड",
        "planes_heading": "तल",
        "plane_names": {
            "mental": "मानसिक (4-9-2)", "emotional": "भावनिक (3-5-7)",
            "practical": "व्यावहारिक (8-1-6)", "thought": "विचार (4-3-8)",
            "will": "संकल्प (9-5-1)", "action": "कर्म (2-7-6)",
            "golden": "सुवर्ण (4-5-6)", "silver": "रजत (2-5-8)",
        },
        "complete": "पूर्ण", "incomplete": "अपूर्ण",
        "missing_note": ("एखादा अंक नसणे हा दोष नाही आणि दुरुस्त करण्याची गोष्टही नाही. परंपरा ते असे "
                         "क्षेत्र मानते ज्यावर तुम्ही कष्ट घेता, जे फुकट मिळत नाही."),
        "submit": "माझा ग्रिड काढा",
    },
}


#: THE CONSULTATION BOX, under every numerology result. The calculators stay free; this is the one
#: paid thing on these pages and it uses the chat pack that already exists - no new payment flow.
#:
#: THE PRICE IS ON THE BOX BEFORE ANYBODY STARTS. A reader should know what a thing costs while
#: deciding whether to want it, not after.
ASK = {
    "en": {
        "heading": "Ask the AI about your numbers",
        "lead": ("Your numbers are worked out above. Ask what they mean for a decision you are "
                 "actually facing - the first {free} questions are free, then {messages} questions "
                 "for Rs {price}."),
        "chips": ("What do my numbers say about my career?",
                  "Does the spelling of my name suit my numbers?",
                  "Does my mobile number fit my numbers?",
                  "How do my numbers sit with my partner's?"),
        "cta": "Start the consultation",
        "note": ("The numbers come from the calculator above, not from the AI - it explains them and "
                 "does not change them."),
    },
    "hi": {
        "heading": "अपने अंकों के बारे में AI से पूछिए",
        "lead": ("आपके अंक ऊपर निकाले जा चुके हैं। पूछिए कि वे उस फ़ैसले के लिए क्या कहते हैं जो सचमुच "
                 "आपके सामने है - पहले {free} सवाल मुफ़्त, फिर {messages} सवाल {price} रुपये में।"),
        "chips": ("मेरे अंक करियर के बारे में क्या कहते हैं?",
                  "क्या मेरे नाम की वर्तनी मेरे अंकों से मेल खाती है?",
                  "क्या मेरा मोबाइल नंबर मेरे अंकों से मेल खाता है?",
                  "मेरे अंक मेरे साथी के अंकों के साथ कैसे बैठते हैं?"),
        "cta": "परामर्श शुरू कीजिए",
        "note": ("अंक ऊपर के कैलकुलेटर से आते हैं, AI से नहीं - वह उन्हें समझाता है, बदलता नहीं।"),
    },
    "mr": {
        "heading": "तुमच्या अंकांबद्दल AI ला विचारा",
        "lead": ("तुमचे अंक वर काढलेले आहेत. ते खरोखर समोर असलेल्या निर्णयासाठी काय सांगतात ते विचारा - "
                 "पहिले {free} प्रश्न मोफत, नंतर {messages} प्रश्न {price} रुपयांत."),
        "chips": ("माझे अंक करिअरबद्दल काय सांगतात?",
                  "माझ्या नावाचे स्पेलिंग माझ्या अंकांशी जुळते का?",
                  "माझा मोबाइल नंबर माझ्या अंकांशी जुळतो का?",
                  "माझे अंक जोडीदाराच्या अंकांशी कसे जुळतात?"),
        "cta": "सल्ला सुरू करा",
        "note": ("अंक वरच्या कॅल्क्युलेटरमधून येतात, AI कडून नाही - तो ते समजावतो, बदलत नाही."),
    },
}


#: THE REPORT'S LANDING PAGE. What is inside, a sample of each section so nobody buys blind, the
#: price before the button, and the form that orders it - a name and a date, which is all it uses.
REPORT = {
    "en": {
        "title": "Numerology Report: Your Numbers and Name Spelling",
        "h1": "The numerology report",
        "meta": ("A written numerology report from your name and date of birth: mulank, bhagyank, "
                 "name number, your Lo Shu grid, how your numbers sit with the ones around you, and "
                 "spelling alternatives for your own name. Rs {price}."),
        "lead": ("Everything the free calculators work out, written up properly - and one thing "
                 "they do not do: alternative spellings of your own name, each with the number it "
                 "makes."),
        "whats_inside": "What is in it",
        "sections": (
            ("Your numbers",
             "Your mulank, bhagyank and name number, with the arithmetic shown so you can follow it.",
             "Born on the 3rd: your mulank is 3. The whole date adds to 27, and 2+7 is 9 - that is "
             "your bhagyank."),
            ("What they say",
             "What the tradition associates with these numbers together.",
             "A 3 mulank with a 9 bhagyank tends to start things easily and finish them under "
             "pressure rather than on a schedule."),
            ("Your Lo Shu grid",
             "The grid, what repeats, what is absent, and which planes are complete.",
             "Three 9s in the grid is a strong Will plane. The missing 5 is the centre - an area "
             "the tradition says you work at rather than one that comes free."),
            ("Name spelling",
             "Alternative spellings of your name, each with the number it makes and why somebody "
             "might prefer it. Offered, never prescribed.",
             "KESHAV adds to 22, which reduces to 4. KESHAAV adds to 23 and reduces to 5. Neither "
             "is better; they are different, and the name you have is not a problem."),
            ("The numbers around you",
             "How your mulank and bhagyank sit with your phone, your house, your vehicle.",
             "A phone number reducing to 9 is a strong match with a 9 bhagyank, and neutral with a "
             "3 mulank - no special affinity either way, which is not a reason to change it."),
            ("Working with it",
             "Practical, free things to do with what the numbers suggest.",
             "Nothing in this section costs anything, and nothing in it is a remedy you buy."),
        ),
        "price_line": "Rs {price}, including GST. One report, delivered as a PDF.",
        "order_heading": "Order it",
        # TWO BUTTONS IN A ROW, both saying "order", is a reader not knowing which one buys.
        # The first fills in the details; the second is the one that takes money.
        "continue": "Continue", "change": "Change these details",
        "back_to_free": "Or use the free calculators",
        "order_note": ("A name and a date of birth. This report does not cast a chart, so it does "
                       "not ask for your birth time or your city."),
        "buy": "Get the report - Rs {price}",
        "cta_from_result": "Want this written up properly?",
        "cta_from_result_body": ("The report takes these numbers further: what they mean together, "
                                 "your Lo Shu grid read out, and spelling alternatives for your own "
                                 "name. Rs {price}."),
        "cta_button": "See what is in the report",
    },
    "hi": {
        "title": "अंक ज्योतिष रिपोर्ट | Numerology Report in Hindi",
        "h1": "अंक ज्योतिष रिपोर्ट",
        "meta": ("आपके नाम और जन्मतिथि से लिखी हुई अंक ज्योतिष रिपोर्ट: मूलांक, भाग्यांक, नाम अंक, लो शू "
                 "ग्रिड, आपके आसपास के नंबरों से मेल, और आपके नाम की वैकल्पिक वर्तनी। {price} रुपये।"),
        "lead": ("जो कुछ मुफ़्त कैलकुलेटर निकालते हैं, वह सब ठीक से लिखा हुआ - और एक चीज़ जो वे नहीं करते: "
                 "आपके अपने नाम की वैकल्पिक वर्तनी, हर एक के अंक के साथ।"),
        "whats_inside": "इसमें क्या है",
        "sections": (
            ("आपके अंक", "मूलांक, भाग्यांक और नाम अंक, गणना के साथ ताकि आप उसे जाँच सकें।",
             "3 तारीख़ को जन्म: मूलांक 3। पूरी तारीख़ का योग 27, और 2+7 = 9 - यही भाग्यांक है।"),
            ("वे क्या कहते हैं", "परंपरा इन अंकों को साथ में किससे जोड़ती है।",
             "मूलांक 3 और भाग्यांक 9 वाले लोग काम शुरू आसानी से करते हैं और पूरा दबाव में करते हैं।"),
            ("आपका लो शू ग्रिड", "ग्रिड, क्या दोहराता है, क्या नहीं है, और कौन से तल पूरे हैं।",
             "ग्रिड में तीन 9 यानी मज़बूत संकल्प तल। 5 का न होना केंद्र का न होना है - परंपरा इसे वह "
             "क्षेत्र मानती है जिस पर आप मेहनत करते हैं।"),
            ("नाम की वर्तनी", "आपके नाम की वैकल्पिक वर्तनी, हर एक के अंक और कारण के साथ। सुझाव, आदेश नहीं।",
             "KESHAV का योग 22, जो 4 बनता है। KESHAAV का 23, जो 5 बनता है। कोई बेहतर नहीं; अलग हैं, "
             "और आपका मौजूदा नाम कोई समस्या नहीं है।"),
            ("आपके आसपास के नंबर", "मूलांक और भाग्यांक आपके फ़ोन, घर और गाड़ी के नंबरों से कैसे बैठते हैं।",
             "9 बनने वाला फ़ोन नंबर भाग्यांक 9 से मज़बूत मेल है और मूलांक 3 से तटस्थ - किसी ओर कोई ख़ास "
             "खिंचाव नहीं, और यह नंबर बदलने की वजह नहीं।"),
            ("इसका क्या करें", "अंक जो सुझाते हैं, उसके साथ करने लायक मुफ़्त और व्यावहारिक बातें।",
             "इस हिस्से में कुछ भी ख़र्च का नहीं है, और कोई ऐसा उपाय नहीं जो ख़रीदना पड़े।"),
        ),
        "price_line": "{price} रुपये, GST सहित। एक रिपोर्ट, PDF में।",
        "order_heading": "ऑर्डर कीजिए",
        "continue": "आगे बढ़िए", "change": "ये विवरण बदलिए",
        "back_to_free": "या मुफ़्त कैलकुलेटर इस्तेमाल कीजिए",
        "order_note": ("नाम और जन्मतिथि। यह रिपोर्ट कुंडली नहीं बनाती, इसलिए जन्म का समय या शहर नहीं "
                       "पूछती।"),
        "buy": "रिपोर्ट लीजिए - {price} रुपये",
        "cta_from_result": "इसे ठीक से लिखा हुआ चाहिए?",
        "cta_from_result_body": ("रिपोर्ट इन्हीं अंकों को आगे ले जाती है: साथ में इनका क्या अर्थ है, लो शू "
                                 "ग्रिड का पूरा पाठ, और आपके नाम की वैकल्पिक वर्तनी। {price} रुपये।"),
        "cta_button": "रिपोर्ट में क्या है, देखिए",
    },
    "mr": {
        "title": "अंकज्योतिष अहवाल | Numerology Report Marathi",
        "h1": "अंकज्योतिष अहवाल",
        "meta": ("तुमच्या नावावरून आणि जन्मतारखेवरून लिहिलेला अंकज्योतिष अहवाल: मूलांक, भाग्यांक, नाम अंक, "
                 "लो शू ग्रिड, आजूबाजूच्या नंबरांशी जुळणी, आणि तुमच्या नावाची पर्यायी स्पेलिंग. {price} रुपये."),
        "lead": ("मोफत कॅल्क्युलेटर जे काढतात ते सगळे नीट लिहिलेले - आणि एक गोष्ट जी ते करत नाहीत: "
                 "तुमच्याच नावाची पर्यायी स्पेलिंग, प्रत्येकाच्या अंकासह."),
        "whats_inside": "यात काय आहे",
        "sections": (
            ("तुमचे अंक", "मूलांक, भाग्यांक आणि नाम अंक, गणनेसह जेणेकरून तुम्ही ती तपासू शकाल.",
             "3 तारखेला जन्म: मूलांक 3. संपूर्ण तारखेची बेरीज 27, आणि 2+7 = 9 - हाच भाग्यांक."),
            ("ते काय सांगतात", "परंपरा या अंकांना एकत्रितपणे कशाशी जोडते.",
             "मूलांक 3 आणि भाग्यांक 9 असणारे काम सहज सुरू करतात आणि दबावाखाली पूर्ण करतात."),
            ("तुमचा लो शू ग्रिड", "ग्रिड, काय पुन्हा येते, काय नाही, आणि कोणते तल पूर्ण आहेत.",
             "ग्रिडमध्ये तीन 9 म्हणजे मजबूत संकल्प तल. 5 नसणे म्हणजे केंद्र नसणे - परंपरा ते असे क्षेत्र "
             "मानते ज्यावर तुम्ही कष्ट घेता."),
            ("नावाची स्पेलिंग", "तुमच्या नावाची पर्यायी स्पेलिंग, प्रत्येकाच्या अंकासह आणि कारणासह. सुचवलेली, "
             "सांगितलेली नाही.",
             "KESHAV ची बेरीज 22, जी 4 होते. KESHAAV ची 23, जी 5 होते. कोणतीही चांगली नाही; वेगळ्या "
             "आहेत, आणि तुमचे सध्याचे नाव ही अडचण नाही."),
            ("आजूबाजूचे नंबर", "मूलांक आणि भाग्यांक तुमच्या फोन, घर आणि गाडीच्या नंबरांशी कसे जुळतात.",
             "9 होणारा फोन नंबर भाग्यांक 9 शी मजबूत जुळणी आणि मूलांक 3 शी तटस्थ - कोणत्याही बाजूने "
             "विशेष ओढ नाही, आणि हे नंबर बदलण्याचे कारण नाही."),
            ("याचे काय करायचे", "अंक जे सुचवतात त्याबरोबर करण्यासारख्या मोफत आणि व्यावहारिक गोष्टी.",
             "या भागात काहीही खर्चाचे नाही, आणि विकत घ्यावा लागणारा कोणताही उपाय नाही."),
        ),
        "price_line": "{price} रुपये, GST सह. एक अहवाल, PDF मध्ये.",
        "order_heading": "ऑर्डर करा",
        "continue": "पुढे जा", "change": "हे तपशील बदला",
        "back_to_free": "किंवा मोफत कॅल्क्युलेटर वापरा",
        "order_note": ("नाव आणि जन्मतारीख. हा अहवाल पत्रिका बनवत नाही, म्हणून जन्माची वेळ किंवा शहर "
                       "विचारत नाही."),
        "buy": "अहवाल घ्या - {price} रुपये",
        "cta_from_result": "हे नीट लिहिलेले हवे आहे?",
        "cta_from_result_body": ("अहवाल याच अंकांना पुढे नेतो: एकत्रितपणे त्यांचा अर्थ, लो शू ग्रिडचे पूर्ण "
                                 "वाचन, आणि तुमच्या नावाची पर्यायी स्पेलिंग. {price} रुपये."),
        "cta_button": "अहवालात काय आहे ते पाहा",
    },
}
