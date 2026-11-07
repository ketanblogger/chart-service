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
        "mulank_chips_label": "Meaning of each mulank:",
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
        "mulank_chips_label": "हर मूलांक का अर्थ:",
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
        "mulank_chips_label": "प्रत्येक मूलांकाचा अर्थ:",
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
        # WHAT EACH PAYMENT ACTUALLY GIVES, said in full and said the same way everywhere.
        #
        # This used to promise that the pack "also includes a short kundali report, which needs your
        # birth time and city" - true of the chart consultation's Rs 119 tier, and false here. A
        # numerology consultation is started from a name and a date, so it cannot cast that chart at
        # all: the purchase was a wrong promise AND a 500 at the till. The product decision of
        # 2026-11-04 is that a numerology chat sells questions and nothing else, and that the
        # Rs {report_price} report stays a separate thing a reader may choose.
        #
        # Every number here is formatted in from the catalogue, so none of them can drift from what
        # the till charges.
        "lead": ("Your numbers are worked out above. Ask what they mean for a decision you are "
                 "actually facing - the first {free} questions are free. After that, Rs {mini_price} "
                 "buys {mini_messages} questions and Rs {pack_price} buys {pack_messages}. Questions "
                 "only: no report is included. The full numerology report is a separate purchase, at "
                 "Rs {report_price}."),
        # The same box sits on the nine mulank pages, which have no calculator on them - so the
        # first sentence cannot say the numbers are "worked out above" there.
        "lead_mulank": ("Ask what this number means for a decision you are actually facing - the "
                        "first {free} questions are free. After that, Rs {mini_price} buys "
                        "{mini_messages} questions and Rs {pack_price} buys {pack_messages}. "
                        "Questions only: no report is included. The full numerology report is a "
                        "separate purchase, at Rs {report_price}."),
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
                 "आपके सामने है - पहले {free} सवाल मुफ़्त। उसके बाद {mini_price} रुपये में "
                 "{mini_messages} सवाल और {pack_price} रुपये में {pack_messages} सवाल। सिर्फ़ सवाल: "
                 "कोई रिपोर्ट इसमें शामिल नहीं है। पूरी अंक ज्योतिष रिपोर्ट अलग से ख़रीदी जाती है, "
                 "{report_price} रुपये में।"),
        "lead_mulank": ("पूछिए कि यह अंक उस फ़ैसले के लिए क्या कहता है जो सचमुच आपके सामने है - पहले "
                        "{free} सवाल मुफ़्त। उसके बाद {mini_price} रुपये में {mini_messages} सवाल और "
                        "{pack_price} रुपये में {pack_messages} सवाल। सिर्फ़ सवाल: कोई रिपोर्ट इसमें "
                        "शामिल नहीं है। पूरी अंक ज्योतिष रिपोर्ट अलग से ख़रीदी जाती है, "
                        "{report_price} रुपये में।"),
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
                 "पहिले {free} प्रश्न मोफत. त्यानंतर {mini_price} रुपयांत {mini_messages} प्रश्न आणि "
                 "{pack_price} रुपयांत {pack_messages} प्रश्न. फक्त प्रश्न: कोणताही अहवाल यात "
                 "समाविष्ट नाही. संपूर्ण अंकज्योतिष अहवाल वेगळा विकत घ्यावा लागतो, {report_price} "
                 "रुपयांत."),
        "lead_mulank": ("हा अंक खरोखर समोर असलेल्या निर्णयासाठी काय सांगतो ते विचारा - पहिले {free} "
                        "प्रश्न मोफत. त्यानंतर {mini_price} रुपयांत {mini_messages} प्रश्न आणि "
                        "{pack_price} रुपयांत {pack_messages} प्रश्न. फक्त प्रश्न: कोणताही अहवाल यात "
                        "समाविष्ट नाही. संपूर्ण अंकज्योतिष अहवाल वेगळा विकत घ्यावा लागतो, "
                        "{report_price} रुपयांत."),
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
                 "spelling alternatives for your name. Rs {price}."),
        "lead": ("Everything the free calculators work out, written up properly - and one thing "
                 "they do not do: spelling alternatives for your name, each with the number it "
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
             "Spelling alternatives for your name, each with the number it makes and why somebody "
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
                                 "your Lo Shu grid read out, and spelling alternatives for your name. Rs {price}."),
        "cta_button": "See what is in the report",
        # THE PRIMARY BUTTON names the thing and its price together. "See what is in the report" is
        # still the label on a mulank page, where there is no calculation to call "my report".
        "preview_alt": "A page from the numerology report, written for a sample person",
        "cta_button_primary": "Get my report - Rs {price}",
        "bar": "Your full report Rs {price}",
        "bar_dismiss": "Hide this",
    },
    "hi": {
        "title": "अंक ज्योतिष रिपोर्ट | Numerology Report in Hindi",
        "h1": "अंक ज्योतिष रिपोर्ट",
        "meta": ("आपके नाम और जन्मतिथि से लिखी हुई अंक ज्योतिष रिपोर्ट: मूलांक, भाग्यांक, नाम अंक, लो शू "
                 "ग्रिड, आपके आसपास के नंबरों से मेल, और आपके नाम की वर्तनी के विकल्प। {price} रुपये।"),
        "lead": ("जो कुछ मुफ़्त कैलकुलेटर निकालते हैं, वह सब ठीक से लिखा हुआ - और एक चीज़ जो वे नहीं करते: "
                 "आपके नाम की वर्तनी के विकल्प, हर एक के अंक के साथ।"),
        "whats_inside": "इसमें क्या है",
        "sections": (
            ("आपके अंक", "मूलांक, भाग्यांक और नाम अंक, गणना के साथ ताकि आप उसे जाँच सकें।",
             "3 तारीख़ को जन्म: मूलांक 3। पूरी तारीख़ का योग 27, और 2+7 = 9 - यही भाग्यांक है।"),
            ("वे क्या कहते हैं", "परंपरा इन अंकों को साथ में किससे जोड़ती है।",
             "मूलांक 3 और भाग्यांक 9 वाले लोग काम शुरू आसानी से करते हैं और पूरा दबाव में करते हैं।"),
            ("आपका लो शू ग्रिड", "ग्रिड, क्या दोहराता है, क्या नहीं है, और कौन से तल पूरे हैं।",
             "ग्रिड में तीन 9 यानी मज़बूत संकल्प तल। 5 का न होना केंद्र का न होना है - परंपरा इसे वह "
             "क्षेत्र मानती है जिस पर आप मेहनत करते हैं।"),
            ("नाम की वर्तनी", "आपके नाम की वर्तनी के विकल्प, हर एक के अंक और कारण के साथ। सुझाव, आदेश नहीं।",
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
                                 "ग्रिड का पूरा पाठ, और आपके नाम की वर्तनी के विकल्प। {price} रुपये।"),
        "cta_button": "रिपोर्ट में क्या है, देखिए",
        "preview_alt": "अंक ज्योतिष रिपोर्ट का एक पन्ना, एक नमूना व्यक्ति के लिए लिखा हुआ",
        "cta_button_primary": "मेरी रिपोर्ट लीजिए - {price} रुपये",
        "bar": "आपकी पूरी रिपोर्ट {price} रुपये",
        "bar_dismiss": "इसे छिपाएँ",
    },
    "mr": {
        "title": "अंकज्योतिष अहवाल | Numerology Report Marathi",
        "h1": "अंकज्योतिष अहवाल",
        "meta": ("तुमच्या नावावरून आणि जन्मतारखेवरून लिहिलेला अंकज्योतिष अहवाल: मूलांक, भाग्यांक, नाम अंक, "
                 "लो शू ग्रिड, आजूबाजूच्या नंबरांशी जुळणी, आणि तुमच्या नावाच्या स्पेलिंगचे पर्याय. {price} रुपये."),
        "lead": ("मोफत कॅल्क्युलेटर जे काढतात ते सगळे नीट लिहिलेले - आणि एक गोष्ट जी ते करत नाहीत: "
                 "तुमच्या नावाच्या स्पेलिंगचे पर्याय, प्रत्येकाच्या अंकासह."),
        "whats_inside": "यात काय आहे",
        "sections": (
            ("तुमचे अंक", "मूलांक, भाग्यांक आणि नाम अंक, गणनेसह जेणेकरून तुम्ही ती तपासू शकाल.",
             "3 तारखेला जन्म: मूलांक 3. संपूर्ण तारखेची बेरीज 27, आणि 2+7 = 9 - हाच भाग्यांक."),
            ("ते काय सांगतात", "परंपरा या अंकांना एकत्रितपणे कशाशी जोडते.",
             "मूलांक 3 आणि भाग्यांक 9 असणारे काम सहज सुरू करतात आणि दबावाखाली पूर्ण करतात."),
            ("तुमचा लो शू ग्रिड", "ग्रिड, काय पुन्हा येते, काय नाही, आणि कोणते तल पूर्ण आहेत.",
             "ग्रिडमध्ये तीन 9 म्हणजे मजबूत संकल्प तल. 5 नसणे म्हणजे केंद्र नसणे - परंपरा ते असे क्षेत्र "
             "मानते ज्यावर तुम्ही कष्ट घेता."),
            ("नावाची स्पेलिंग", "तुमच्या नावाच्या स्पेलिंगचे पर्याय, प्रत्येकाच्या अंकासह आणि कारणासह. सुचवलेली, "
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
                                 "वाचन, आणि तुमच्या नावाच्या स्पेलिंगचे पर्याय. {price} रुपये."),
        "cta_button": "अहवालात काय आहे ते पाहा",
        "preview_alt": "अंकज्योतिष अहवालाचे एक पान, नमुना व्यक्तीसाठी लिहिलेले",
        "cta_button_primary": "माझा अहवाल घ्या - {price} रुपये",
        "bar": "तुमचा संपूर्ण अहवाल {price} रुपये",
        "bar_dismiss": "हे लपवा",
    },
}

#: INLINE ERRORS. A date the calendar does not have - 31 February, 30 February, day 0 - produced
#: nothing at all: the page re-rendered with the fields still filled, no result and no message, so a
#: reader could only conclude the button was broken. Every form that takes a date says this now.
ERRORS = {
    "en": {
        "bad_date": "That date does not exist. Check the day and the month - February has 28 days, "
                    "or 29 in a leap year.",
        "no_date": "Enter a day, a month and a year.",
        "bad_number": "Enter a number with at least one digit.",
    },
    "hi": {
        "bad_date": "यह तारीख़ मौजूद नहीं है। दिन और महीना जाँच लीजिए - फ़रवरी में 28 दिन होते हैं, "
                    "लीप वर्ष में 29।",
        "no_date": "दिन, महीना और वर्ष भरिए।",
        "bad_number": "कम से कम एक अंक वाला नंबर भरिए।",
    },
    "mr": {
        "bad_date": "ही तारीख अस्तित्वात नाही. दिवस आणि महिना तपासा - फेब्रुवारीत 28 दिवस असतात, "
                    "लीप वर्षात 29.",
        "no_date": "दिवस, महिना आणि वर्ष भरा.",
        "bad_number": "कमीत कमी एक अंक असलेला नंबर भरा.",
    },
}


# ---- the mulank pages: section headings, planet names, and the FAQ ---------------------------------
#
# WHY THESE EXIST. A mulank page was six paragraphs in a row with no headings between them, so a
# reader looking for "what work suits this number" had to read all of it to find out whether the
# answer was there. The text is unchanged - it is grouped under headings, which is what the QA round
# asked for.

#: The planet behind each number, in the language of the page it is read on. The page printed
#: core.RULERS straight out, so a Hindi reader was told their number is ruled by "Moon".
PLANETS = {
    "en": {1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu", 5: "Mercury", 6: "Venus", 7: "Ketu",
           8: "Saturn", 9: "Mars"},
    "hi": {1: "सूर्य", 2: "चंद्र", 3: "गुरु", 4: "राहु", 5: "बुध", 6: "शुक्र", 7: "केतु",
           8: "शनि", 9: "मंगल"},
    "mr": {1: "सूर्य", 2: "चंद्र", 3: "गुरू", 4: "राहू", 5: "बुध", 6: "शुक्र", 7: "केतू",
           8: "शनी", 9: "मंगळ"},
}

#: One heading per paragraph the page already had, plus the FAQ's own.
SECTIONS = {
    "en": {"personality": "Personality", "work": "Career and work",
           "compatible": "Which numbers it goes with", "lucky": "Lucky colours and days",
           "bhagyank": "Mulank and bhagyank together", "faq": "Common questions",
           "ruled_by": "Ruled by"},
    "hi": {"personality": "व्यक्तित्व", "work": "करियर और काम",
           "compatible": "किन अंकों से मेल", "lucky": "शुभ रंग और दिन",
           "bhagyank": "मूलांक और भाग्यांक साथ में", "faq": "आम सवाल",
           "ruled_by": "स्वामी ग्रह"},
    "mr": {"personality": "व्यक्तिमत्त्व", "work": "करिअर आणि काम",
           "compatible": "कोणत्या अंकांशी जुळते", "lucky": "शुभ रंग आणि दिवस",
           "bhagyank": "मूलांक आणि भाग्यांक एकत्र", "faq": "सामान्य प्रश्न",
           "ruled_by": "स्वामी ग्रह"},
}

#: THE FAQ IS DERIVED, NEVER WRITTEN PER NUMBER. Every answer is assembled from data that is already
#: on the page - the dates, the ruling planet, and the compatibility table that is the single source
#: for every number pairing on this site - so nine pages in three languages cannot drift from the
#: page they sit on, and the compatibility symmetry test covers these answers too.
FAQ = {
    "en": {
        "dates": ("Which birth dates give mulank {number}?",
                  "Anybody born on the {days} of any month, in any year. The mulank is the day of "
                  "the month reduced to one digit, so the month and the year do not change it."),
        "planet": ("Which planet rules mulank {number}?",
                   "{planet}. The numbers this mulank is said to suit follow from that planet's "
                   "friendships, which is why the pairings are not arbitrary."),
        "suits": ("Which numbers suit mulank {number}?",
                  "Closest with {strong}; it also goes well with {good}. With {neutral} it is "
                  "neither helped nor hindered."),
        "difference": ("What is the difference between a mulank and a bhagyank?",
                       "The mulank uses only the day of the month; the bhagyank uses every digit of "
                       "the whole date of birth. Two people born on the same day of different "
                       "months share a mulank but not usually a bhagyank."),
    },
    "hi": {
        "dates": ("मूलांक {number} किन जन्म तिथियों से बनता है?",
                  "किसी भी महीने की {days} तारीख को जन्मे लोगों का, किसी भी साल। मूलांक महीने की "
                  "तारीख को एक अंक में जोड़कर निकलता है, इसलिए महीना और साल इसे नहीं बदलते।"),
        "planet": ("मूलांक {number} का स्वामी ग्रह कौन है?",
                   "{planet}। यह मूलांक किन अंकों से मेल खाता है, यह उसी ग्रह की मित्रता से तय "
                   "होता है - इसीलिए ये जोड़ियाँ मनमानी नहीं हैं।"),
        "suits": ("मूलांक {number} किन अंकों से मेल खाता है?",
                  "{strong} से सबसे अधिक; {good} से भी अच्छा मेल है। {neutral} से न मदद मिलती है "
                  "न अड़चन आती है।"),
        "difference": ("मूलांक और भाग्यांक में क्या अंतर है?",
                       "मूलांक में सिर्फ़ महीने की तारीख लेते हैं; भाग्यांक में पूरी जन्मतिथि के "
                       "सभी अंक। अलग-अलग महीनों की एक ही तारीख को जन्मे दो लोगों का मूलांक एक "
                       "होता है, भाग्यांक आम तौर पर नहीं।"),
    },
    "mr": {
        "dates": ("मूलांक {number} कोणत्या जन्मतारखांचा होतो?",
                  "कोणत्याही महिन्याच्या {days} तारखेला जन्मलेल्यांचा, कोणत्याही वर्षी. मूलांक "
                  "महिन्याची तारीख एका अंकात बेरीज करून येतो, म्हणून महिना आणि वर्ष तो बदलत नाहीत."),
        "planet": ("मूलांक {number} चा स्वामी ग्रह कोण?",
                   "{planet}. हा मूलांक कोणत्या अंकांशी जुळतो हे त्याच ग्रहाच्या मैत्रीवरून ठरते - "
                   "म्हणूनच या जोड्या मनमानी नाहीत."),
        "suits": ("मूलांक {number} कोणत्या अंकांशी जुळतो?",
                  "{strong} शी सर्वाधिक; {good} शीही चांगले जुळते. {neutral} शी मदतही होत नाही "
                  "आणि अडथळाही येत नाही."),
        "difference": ("मूलांक आणि भाग्यांक यात काय फरक आहे?",
                       "मूलांकात फक्त महिन्याची तारीख घेतात; भाग्यांकात पूर्ण जन्मतारखेचे सगळे "
                       "अंक. वेगवेगळ्या महिन्यांच्या एकाच तारखेला जन्मलेल्या दोघांचा मूलांक एक "
                       "असतो, भाग्यांक सामान्यतः नाही."),
    },
}


# ---- the paid report's card, personalised from the reader's own grid -------------------------------
#
# FACTUAL, AND ONLY ABOUT WHAT THE REPORT CONTAINS. The sentence is assembled from the calculation
# the reader is looking at, and names the two sections that speak to it: the Lo Shu reading and the
# spelling alternatives. It makes no promise of a NUMBER of spellings, because app/ai/products.py
# asks the writer for alternatives without fixing how many, and a card that says "3 options" when
# the report happens to give two is a card that lied for money.
#
# IT DOES NOT SELL BY FEAR. A missing number is stated as missing and nothing more - the product
# brief and LO_SHU's own missing_note both say a missing number is an area somebody works at, never
# a fault and never something to fix, and a card that implied otherwise would contradict the
# document it is selling.
CARD = {
    "en": {
        "missing": "Your grid is missing {numbers}",
        "missing_none": "Your grid has all nine numbers",
        "planes": ", and the {planes} {plane_word} complete",
        "planes_none": ", and no plane is complete",
        "plane_word_one": "plane is",
        "plane_word_many": "planes are",
        "tail": (". The report reads each of these out - what the tradition makes of the numbers you "
                 "have and of the ones you do not - and offers spelling alternatives for your name, "
                 "each with the number it makes."),
        "and": "and",
    },
    "hi": {
        "missing": "आपके ग्रिड में {numbers} नहीं हैं",
        "missing_none": "आपके ग्रिड में नौ के नौ अंक हैं",
        "planes": ", और {planes} {plane_word} पूर्ण {plane_verb}",
        "planes_none": ", और कोई तल पूर्ण नहीं है",
        "plane_word_one": "तल",
        "plane_word_many": "तल",
        "tail": ("। रिपोर्ट इन सभी को खोलकर बताती है - परंपरा आपके पास मौजूद अंकों के बारे में क्या "
                 "कहती है और जो नहीं हैं उनके बारे में क्या - और आपके नाम की वर्तनी के विकल्प "
                 "देती है, हर एक के साथ उससे बनने वाला अंक।"),
        "and": "और",
    },
    "mr": {
        "missing": "तुमच्या ग्रिडमध्ये {numbers} नाहीत",
        "missing_none": "तुमच्या ग्रिडमध्ये नऊही अंक आहेत",
        "planes": ", आणि {planes} {plane_word} पूर्ण {plane_verb}",
        "planes_none": ", आणि कोणताही तल पूर्ण नाही",
        "plane_word_one": "तल",
        "plane_word_many": "तल",
        "tail": (". अहवाल यांतील प्रत्येक गोष्ट उलगडून सांगतो - तुमच्याकडे असलेल्या अंकांविषयी आणि "
                 "नसलेल्यांविषयी परंपरा काय सांगते - आणि तुमच्या नावाच्या स्पेलिंगचे पर्याय देतो, "
                 "प्रत्येकासोबत त्यातून निघणारा अंक."),
        "and": "आणि",
    },
}

#: Hindi and Marathi need the verb to agree with the number of planes; English folds it into
#: plane_word. Kept as data rather than code so a translator can change the agreement.
PLANE_VERB = {"en": {"one": "", "many": ""},
              "hi": {"one": "है", "many": "हैं"},
              "mr": {"one": "आहे", "many": "आहेत"}}
