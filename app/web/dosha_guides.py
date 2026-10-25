"""Honest guides to the three doshas people are most frightened about.

THE COMMERCIAL PATTERN THESE PAGES EXIST AGAINST is the oldest one in this field: find a configuration
in somebody's chart, tell them it is dangerous, and sell the remedy. Pitra dosha and kaal sarp in
particular support an entire industry of paid pujas at specific temples, and the people most likely to
pay are the ones least able to afford it.

So each page does four things and refuses a fifth. It says what the configuration actually is. It says
how it is identified, and where astrologers disagree about that. It gives the calm traditional remedies,
which are free or nearly so. It links to the free check where we have one. And it sells nothing, which
is why there is no product on any of these pages and no "consult now" button dressed as a warning.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.web import i18n


@dataclass(frozen=True)
class Guide:
    slug: str
    tool: str | None = None      # the free check, where one exists


DOSHAS = ("mangal", "kaal-sarp", "pitra")
GUIDES = {
    "mangal": Guide("mangal", tool="mangal-dosha"),
    "kaal-sarp": Guide("kaal-sarp"),
    "pitra": Guide("pitra"),
}


#: Hindi first: that is where the demand is and where the fear is sold hardest.
COPY = {
    "hi": {
        "mangal": {
            "title": "मंगल दोष: कैसे जाँचें, और कितना गंभीर है",
            "h1": "मंगल दोष (मांगलिक)",
            "what": "यह है क्या",
            "what_body": (
                "मंगल दोष का अर्थ है कुंडली में मंगल का पहले, दूसरे, चौथे, सातवें, आठवें या बारहवें "
                "भाव में होना। शास्त्र इसे विवाह पर पड़ने वाले दबाव से जोड़ते हैं - मंगल ऊर्जा, "
                "आवेग और टकराव का कारक है, और ये भाव शरीर, कुटुंब, घर, जीवनसाथी, आयु और व्यय के हैं।",
                "यह कोई बीमारी नहीं है और न ही कोई श्राप। यह एक ग्रह-स्थिति है, जो लगभग हर तीन में से "
                "एक कुंडली में मिलती है। अगर यह सचमुच वैसी आपदा होती जैसी बताई जाती है, तो देश की "
                "एक-तिहाई शादियाँ उसका प्रमाण होतीं।",
            ),
            "how": "कैसे जाँचा जाता है - और कहाँ मतभेद है",
            "how_body": (
                "गिनती लग्न से की जाती है। कई परंपराएँ चंद्र से और शुक्र से भी देखती हैं, और तीनों "
                "में उत्तर अलग आ सकता है।",
                "सबसे बड़ा मतभेद दूसरे भाव पर है: उत्तर भारत में उसे प्राय: गिना जाता है, दक्षिण में "
                "प्राय: नहीं। इसका सीधा अर्थ यह है कि एक ही कुंडली एक ज्योतिषी के यहाँ मांगलिक और "
                "दूसरे के यहाँ नहीं हो सकती - और दोनों अपनी परंपरा के भीतर ठीक होंगे।",
                "कई मानक निवारण भी हैं: मंगल का अपनी राशि (मेष, वृश्चिक) या उच्च राशि (मकर) में होना, "
                "गुरु की दृष्टि, और सबसे सामान्य - दोनों पक्षों की कुंडली में दोष का होना, जिसे "
                "परंपरा परस्पर निवारण मानती है।",
            ),
            "remedies": "शांत, पारंपरिक उपाय",
            "remedies_body": (
                "मंगलवार का व्रत। हनुमान चालीसा। लाल मसूर या गुड़ का दान। मंगल के बीज मंत्र का जप।",
                "ये सब नि:शुल्क या लगभग नि:शुल्क हैं, और परंपरा यही कहती है। जो कोई इसे 'काटने' के "
                "लिए महँगा रत्न, विशेष पूजा या किसी ख़ास मंदिर का पैकेज बेचे - वह डर बेच रहा है। "
                "दोष की पहचान करने वाला ही अगर उसका महँगा इलाज भी बेच रहा हो, तो यह इस क्षेत्र का "
                "सबसे पुराना व्यापारिक ढाँचा है।",
            ),
            "check": "अपनी कुंडली में मुफ़्त जाँचिए",
        },
        "kaal-sarp": {
            "title": "काल सर्प दोष: सच क्या है, डर क्या है",
            "h1": "काल सर्प दोष",
            "what": "यह है क्या",
            "what_body": (
                "काल सर्प योग तब बनता है जब सातों शास्त्रीय ग्रह - सूर्य, चंद्र, मंगल, बुध, गुरु, "
                "शुक्र, शनि - राहु और केतु के बीच के आधे हिस्से में आ जाएँ। राहु और केतु सदा "
                "आमने-सामने होते हैं, इसलिए वे कुंडली को दो हिस्सों में बाँटते हैं; अगर सब एक ही "
                "ओर हों, तो यह योग बनता है।",
                "एक बात जो प्राय: नहीं बताई जाती: यह शास्त्रीय ग्रंथों में नहीं है। बृहत् पराशर होरा "
                "शास्त्र में नहीं, वराहमिहिर में नहीं। यह बीसवीं शताब्दी के आसपास की लोकप्रिय "
                "परंपरा का जोड़ है, और विद्वत परंपरा में इसे उतना गंभीर नहीं माना जाता जितना "
                "लोकप्रिय ज्योतिष में।",
            ),
            "how": "कैसे जाँचा जाता है - और कहाँ मतभेद है",
            "how_body": (
                "देखा जाता है कि सातों ग्रह राहु-केतु अक्ष के एक ही ओर हैं या नहीं। बारह प्रकार "
                "गिनाए जाते हैं, राहु किस भाव में है उसके अनुसार, और हर एक का अलग नाम है।",
                "मतभेद यह है कि 'एक ही ओर' का अर्थ क्या है। कुछ इसे कड़ाई से लेते हैं; कुछ कहते हैं "
                "कि एक भी ग्रह अक्ष पर या दूसरी ओर हो तो योग भंग हो जाता है - जिसे आंशिक काल सर्प "
                "कहते हैं। इसी वजह से एक ही कुंडली पर दो उत्तर मिल जाते हैं।",
            ),
            "remedies": "शांत, पारंपरिक उपाय",
            "remedies_body": (
                "नाग पंचमी पर दर्शन। महामृत्युंजय या राहु-केतु के मंत्र का जप। सोमवार को शिव को जल।",
                "काल सर्प के नाम पर बिकने वाली विशेष पूजाएँ इस क्षेत्र का सबसे बड़ा धंधा हैं - "
                "कुछ तीर्थस्थानों पर इसी के लिए पूरा उद्योग खड़ा है। याद रखिए कि यह योग शास्त्रों "
                "में है ही नहीं। जो डर बेचा जा रहा है वह योग से पुराना नहीं, बहुत नया है।",
            ),
            "check": "अपनी कुंडली मुफ़्त बनाइए",
        },
        "pitra": {
            "title": "पितृ दोष: अर्थ, पहचान और उपाय",
            "h1": "पितृ दोष",
            "what": "यह है क्या",
            "what_body": (
                "पितृ दोष का भाव है पूर्वजों से जुड़ा कोई अधूरापन - प्राय: यह कहा जाता है कि किसी "
                "पीढ़ी में अंतिम संस्कार या श्राद्ध ठीक से नहीं हुआ, या परिवार में किसी के साथ "
                "अन्याय हुआ। कुंडली में इसे सूर्य के साथ राहु या केतु की स्थिति से, या नवें भाव "
                "(पिता, पूर्वज) के पीड़ित होने से जोड़ा जाता है।",
                "ध्यान दीजिए कि यह व्याख्या कितनी खुली है। 'नवाँ भाव पीड़ित' की परिभाषा हर परंपरा "
                "में अलग है, और लगभग हर कुंडली में कोई न कोई ऐसी स्थिति मिल ही जाती है जिसे इस "
                "नाम से पुकारा जा सके। यही वजह है कि यह दोष इतनी बार 'मिलता' है।",
            ),
            "how": "कैसे पहचाना जाता है - और कहाँ मतभेद है",
            "how_body": (
                "सबसे आम कसौटी: सूर्य के साथ राहु या केतु की युति, या नवें भाव या नवमेश पर उनका "
                "प्रभाव। कुछ परंपराएँ दूसरे और बारहवें भाव को भी देखती हैं।",
                "कोई एक मानक परिभाषा नहीं है। शास्त्रीय ग्रंथों में 'पितृ दोष' नाम से अलग अध्याय "
                "नहीं है जैसा मंगल दोष के लिए मिलता है। इसलिए दो ज्योतिषी एक ही कुंडली पर अलग "
                "उत्तर दे सकते हैं, और प्राय: देते हैं।",
            ),
            "remedies": "शांत, पारंपरिक उपाय",
            "remedies_body": (
                "पितृ पक्ष में श्राद्ध और तर्पण - जो परिवार वैसे भी करते हैं। अमावस्या पर पूर्वजों "
                "के नाम से दान। कौओं, गाय या ज़रूरतमंदों को भोजन। पीपल को जल।",
                "ये सब आपके अपने हाथ से, बिना किसी बिचौलिए के हो सकते हैं, और परंपरा में यही कहा "
                "गया है। पितृ दोष के नाम पर किसी विशेष स्थान की महँगी पूजा का पैकेज बेचने वाले "
                "बहुत हैं। जो व्यक्ति दोष बताए और उसी का सशुल्क निवारण भी बेचे, उस पर भरोसा करने "
                "से पहले दो बार सोचिए।",
            ),
            "check": "अपनी कुंडली मुफ़्त बनाइए",
        },
    },
}


#: The two doshas a MATCHING result can report, as guides in all three trees. They are a separate set
#: from the three above, and deliberately: those are Hindi-only because that is where the fear is sold
#: hardest, and giving the key an English tree would mean writing English copy for all five. These two
#: are reached from a matching result, which exists in every tree, so they exist in every tree.
MATCH_DOSHAS = ("nadi", "bhakoot")
MATCH_GUIDES = {"nadi": Guide("nadi", tool="matching"), "bhakoot": Guide("bhakoot", tool="matching")}



#: THE TWO DOSHAS A MATCHING RESULT REPORTS. Same four things as the guides above - what it is, how it
#: is identified, the calm remedies, the free check - and the same refusal: nothing is for sale here.
#:
#: Nadi dosha carries eight of the 36 gunas and bhakoot seven, so between them they are where a score
#: collapses. That is exactly why they are the two a frightened couple is most often sold something
#: about, and why the cancellation rules matter more than the dosha does: classical texts list them,
#: and the people selling remedies rarely mention them.
MATCH_COPY = {
    "en": {
        "nadi": {
            "title": "Nadi Dosha in Kundali Matching - What It Means",
            "h1": "Nadi dosha",
            "what": "What nadi dosha is",
            "what_body": (
                "Nadi is the eighth and heaviest koota in Ashtakoota matching, worth 8 of the 36 gunas. When the "
                "boy and the girl share the same nadi, those 8 points are not awarded - and that is nadi dosha.",
                "Every nakshatra belongs to one of three nadis - Aadi, Madhya and Antya - which classical "
                "texts relate to constitution.",
            ),
            "how": "How it is identified, and where it is argued about",
            "how_body": (
                "It is read from the janma nakshatra of each person, so it needs the Moon's position and therefore a birth time. A match done from names alone is reading the nakshatra off a syllable, which is an approximation - the nadi it reports can be wrong.",
                "The texts themselves list cancellations: the same nakshatra for both, the same nakshatra lord, or the Moon signs being in certain relationships. Astrologers disagree about how far these go, and the disagreement is real rather than a technicality - a dosha that cancels is not a dosha.",
            ),
            "remedies": "What the tradition actually prescribes",
            "remedies_body": (
                "The remedies in the classical sources cost nothing: charity, fasting on particular days, and the Mahamrityunjaya mantra. Nothing here requires a paid ritual, and a score of 8 lost out of 36 is not a verdict on two people - it is one factor among eight, and the texts that name it also name the ways it ceases to apply.",
            ),
            "check": "Check nadi dosha free with both birth details",
        },
        "bhakoot": {
            "title": "Bhakoot Dosha in Kundali Matching - What It Means",
            "h1": "Bhakoot dosha",
            "what": "What bhakoot dosha is",
            "what_body": (
                "Bhakoot is the seventh koota, worth 7 of the 36 gunas, and it looks at the distance between the "
                "two Moon signs. When that distance is 6-8, 9-5 or 2-12, the 7 points are not awarded.",
                "The match is then said to carry bhakoot dosha, also called rashi dosha. The texts associate "
                "the three cases with prosperity, children and health.",
            ),
            "how": "How it is identified, and where it is argued about",
            "how_body": (
                "It needs only the two Moon signs, so it is the one koota a name-based match gets right more often - a syllable points at a nakshatra, and a nakshatra sits inside a sign.",
                "The cancellation most often cited is that bhakoot dosha does not apply when the lords of the two Moon signs are friends, or when both Moon signs have the same lord. That is a large exception and it applies frequently.",
            ),
            "remedies": "What the tradition actually prescribes",
            "remedies_body": (
                "The remedies are the ordinary ones: charity, the worship a family already keeps, and patience with the areas the texts name. Seven points out of 36 is a real part of the score and it is not the whole of it - a match that loses them can still clear the usual threshold of 18.",
            ),
            "check": "Check bhakoot dosha free with both birth details",
        },
    },
    "hi": {
        "nadi": {
            "title": "नाड़ी दोष - कुंडली मिलान में क्या मतलब है",
            "h1": "नाड़ी दोष - कुंडली मिलान में",
            "what": "नाड़ी दोष क्या है",
            "what_body": (
                "अष्टकूट मिलान में नाड़ी आठवाँ और सबसे भारी कूट है - 36 में से 8 अंक। वर और कन्या की नाड़ी एक ही "
                "हो तो ये 8 अंक नहीं मिलते - यही नाड़ी दोष है।",
                "हर नक्षत्र तीन नाड़ियों में से एक का होता है: आदि, मध्य और अंत्य। शास्त्र इन्हें प्रकृति से जोड़ते हैं।",
            ),
            "how": "कैसे देखा जाता है, और कहाँ मतभेद है",
            "how_body": (
                "यह दोनों के जन्म नक्षत्र से देखा जाता है, यानी चंद्रमा की स्थिति से, यानी जन्म समय से। सिर्फ़ नाम से किया गया मिलान नक्षत्र को अक्षर से निकालता है - वह अनुमान है और उसकी बताई नाड़ी ग़लत हो सकती है।",
                "शास्त्र स्वयं भंग बताते हैं: दोनों का एक ही नक्षत्र, एक ही नक्षत्र स्वामी, या चंद्र राशियों का विशेष संबंध। इन पर ज्योतिषियों में मतभेद है, और यह मतभेद असली है - जो दोष भंग हो जाए वह दोष नहीं रहता।",
            ),
            "remedies": "परंपरा असल में क्या कहती है",
            "remedies_body": (
                "शास्त्रों के उपाय मुफ़्त हैं: दान, नियत दिनों का व्रत, और महामृत्युंजय मंत्र। यहाँ किसी सशुल्क पूजा की ज़रूरत नहीं है, और 36 में से 8 अंक कम होना दो लोगों पर फ़ैसला नहीं है - यह आठ में से एक कारक है, और जो ग्रंथ इसे बताते हैं वही इसके भंग भी बताते हैं।",
            ),
            "check": "दोनों के जन्म विवरण से नाड़ी दोष मुफ़्त जाँचिए",
        },
        "bhakoot": {
            "title": "भकूट दोष - कुंडली मिलान में क्या मतलब है",
            "h1": "भकूट दोष - कुंडली मिलान में",
            "what": "भकूट दोष क्या है",
            "what_body": (
                "भकूट सातवाँ कूट है - 36 में से 7 अंक - और यह दोनों की चंद्र राशियों के बीच की दूरी देखता है। यह "
                "दूरी 6-8, 9-5 या 2-12 हो तो ये 7 अंक नहीं मिलते।",
                "इसे भकूट दोष या राशि दोष कहते हैं। शास्त्र इन तीनों को क्रमशः समृद्धि, संतान और स्वास्थ्य से जोड़ते हैं।",
            ),
            "how": "कैसे देखा जाता है, और कहाँ मतभेद है",
            "how_body": (
                "इसके लिए सिर्फ़ दोनों की चंद्र राशि चाहिए, इसलिए नाम से किए गए मिलान में यही कूट सबसे ज़्यादा सही बैठता है - अक्षर नक्षत्र बताता है और नक्षत्र राशि के भीतर होता है।",
                "सबसे ज़्यादा बताया जाने वाला भंग यह है कि दोनों चंद्र राशियों के स्वामी मित्र हों, या दोनों का स्वामी एक ही हो, तो भकूट दोष लागू नहीं होता। यह बड़ा अपवाद है और अक्सर लागू होता है।",
            ),
            "remedies": "परंपरा असल में क्या कहती है",
            "remedies_body": (
                "उपाय साधारण हैं: दान, घर की नियमित पूजा, और जिन क्षेत्रों की बात शास्त्र करते हैं उनमें धैर्य। 36 में से 7 अंक कम होना स्कोर का असली हिस्सा है, पूरा स्कोर नहीं - इतने अंक खोकर भी मिलान 18 की सामान्य सीमा पार कर सकता है।",
            ),
            "check": "दोनों के जन्म विवरण से भकूट दोष मुफ़्त जाँचिए",
        },
    },
    "mr": {
        "nadi": {
            "title": "नाडी दोष - पत्रिका जुळवणीत काय अर्थ",
            "h1": "नाडी दोष - पत्रिका जुळवणीत",
            "what": "नाडी दोष म्हणजे काय",
            "what_body": (
                "अष्टकूट जुळवणीत नाडी हा आठवा आणि सर्वांत जड कूट आहे - 36 पैकी 8 गुण. वर आणि वधूची नाडी एकच "
                "असेल तर हे 8 गुण मिळत नाहीत - हाच नाडी दोष.",
                "प्रत्येक नक्षत्र आदि, मध्य किंवा अंत्य यापैकी एका नाडीचे असते आणि शास्त्र त्यांचा संबंध प्रकृतीशी जोडतात.",
            ),
            "how": "कसे पाहतात, आणि मतभेद कुठे आहे",
            "how_body": (
                "हे दोघांच्या जन्मनक्षत्रावरून पाहिले जाते, म्हणजे चंद्रस्थितीवरून, म्हणजे जन्मवेळेवरून. फक्त नावावरून केलेले मेलन नक्षत्र अक्षरावरून काढते - तो अंदाज आहे आणि त्याने सांगितलेली नाडी चुकीची असू शकते.",
                "शास्त्रे स्वतः भंग सांगतात: दोघांचे एकच नक्षत्र, एकच नक्षत्रस्वामी, किंवा चंद्रराशींचा विशिष्ट संबंध. यावर ज्योतिषांत मतभेद आहे, आणि तो खरा मतभेद आहे - भंग झालेला दोष दोष राहत नाही.",
            ),
            "remedies": "परंपरा खरोखर काय सांगते",
            "remedies_body": (
                "शास्त्रातील उपाय मोफत आहेत: दान, ठरावीक दिवसांचा उपवास, आणि महामृत्युंजय मंत्र. इथे कोणत्याही सशुल्क पूजेची गरज नाही, आणि 36 पैकी 8 गुण कमी होणे हा दोन माणसांवरचा निकाल नाही - तो आठांपैकी एक घटक आहे, आणि जी शास्त्रे तो सांगतात तीच त्याचे भंगही सांगतात.",
            ),
            "check": "दोघांच्या जन्मतपशिलावरून नाडी दोष मोफत तपासा",
        },
        "bhakoot": {
            "title": "भकूट दोष - पत्रिका जुळवणीत काय अर्थ",
            "h1": "भकूट दोष - पत्रिका जुळवणीत",
            "what": "भकूट दोष म्हणजे काय",
            "what_body": (
                "भकूट हा सातवा कूट - 36 पैकी 7 गुण - आणि तो दोघांच्या चंद्रराशींमधील अंतर पाहतो. हे अंतर 6-8, "
                "9-5 किंवा 2-12 असेल तर हे 7 गुण मिळत नाहीत.",
                "त्याला भकूट दोष किंवा राशी दोष म्हणतात. शास्त्रे या तिघांचा संबंध अनुक्रमे समृद्धी, संतती आणि आरोग्याशी जोडतात.",
            ),
            "how": "कसे पाहतात, आणि मतभेद कुठे आहे",
            "how_body": (
                "यासाठी फक्त दोघांची चंद्ररास लागते, म्हणून नावावरून केलेल्या मेलनात हाच कूट सर्वाधिक वेळा बरोबर येतो - अक्षर नक्षत्र सांगते आणि नक्षत्र राशीच्या आत असते.",
                "सर्वाधिक सांगितला जाणारा भंग म्हणजे दोन्ही चंद्रराशींचे स्वामी मित्र असतील, किंवा दोघांचा स्वामी एकच असेल, तर भकूट दोष लागू होत नाही. हा मोठा अपवाद आहे आणि तो वारंवार लागू होतो.",
            ),
            "remedies": "परंपरा खरोखर काय सांगते",
            "remedies_body": (
                "उपाय साधेच आहेत: दान, घरात चालणारी नित्य पूजा, आणि शास्त्रे ज्या क्षेत्रांचा उल्लेख करतात तिथे संयम. 36 पैकी 7 गुण कमी होणे हा गुणांचा खरा भाग आहे, पूर्ण गुण नव्हे - इतके गुण गमावूनही मेलन 18 ची सर्वसाधारण मर्यादा ओलांडू शकते.",
            ),
            "check": "दोघांच्या जन्मतपशिलावरून भकूट दोष मोफत तपासा",
        },
    },
}


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["dosha-guide"]:
        for slug in DOSHAS:
            _add(router, page_context, respond, _json_ld, lang, slug)
    for lang in i18n.PAGES["match-dosha"]:
        for slug in MATCH_DOSHAS:
            _add(router, page_context, respond, _json_ld, lang, slug,
                 key="match-dosha", guides=MATCH_GUIDES, copy=MATCH_COPY, siblings=MATCH_DOSHAS)


def _add(router, page_context, respond, _json_ld, lang: str, slug: str, *,
         key: str = "dosha-guide", guides=None, copy=None, siblings=None) -> None:
    guides = guides or GUIDES
    copy = copy or COPY
    siblings = siblings or DOSHAS

    def dosha_page(request: Request):
        from app.web import seo as _seo

        words = copy[lang][slug]
        guide = guides[slug]
        context = page_context(key, lang, dosha=slug)
        path = i18n.url_for(key, lang, dosha=slug)
        context.update(
            words=words,
            # The free check, where we have one. NOT a product: there is nothing for sale on these
            # pages, which is the whole point of them.
            check_href=i18n.url_for(guide.tool or "kundali", lang),
            others=[{"href": i18n.url_for(key, lang, dosha=other),
                     "label": copy[lang][other]["h1"]} for other in siblings if other != slug],
            title=words["title"],
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "dosha_guide.html", context)

    router.add_api_route(i18n.url_for(key, lang, dosha=slug), dosha_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"dosha-{slug}-{lang}")
