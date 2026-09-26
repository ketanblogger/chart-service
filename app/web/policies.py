"""Trust / policy pages: /about /contact /privacy /terms /refund-policy /disclaimer.

Plain MVP texts for a standalone Indian astrology site that sells digital goods through Razorpay (which asks for
these pages before activating live payments). Business details come from app/web/site.py - placeholders in
[SQUARE BRACKETS] until they are filled in. This is sensible default wording, not
legal advice; have it reviewed before launch. A block is a paragraph (str) or a bullet list (list[str]);
`{name}`-style fields are filled from `site` at render time.
"""

from dataclasses import dataclass

from app.web.pages import Section


@dataclass(frozen=True)
class PolicyPage:
    slug: str
    nav_label: str
    title: str
    meta_description: str
    h1: str
    intro: str
    sections: tuple[Section, ...]

    @property
    def path(self) -> str:
        return f"/{self.slug}"


ABOUT = PolicyPage(
    slug="about", nav_label="About", title="About Us",
    meta_description="Who we are and how this site works: Vedic astrology charts calculated with the Swiss Ephemeris, "
                     "with optional AI-written interpretation reports and consultation.",
    h1="About {site_name}",
    intro="{site_name} offers accurate Vedic astrology tools in English, Hindi and Marathi - free to use, without sign-up.",
    sections=(
        Section("What we do", (
            "Every chart, date and degree on this site is calculated with the Swiss Ephemeris using the sidereal zodiac "
            "and the Lahiri ayanamsa followed by Indian panchangs. The janam kundali, kundali matching, mangal dosha and "
            "sade sati tools and all rashifal pages are free.",
            "For those who want more depth we sell a small number of digital products: detailed interpretation reports "
            "delivered as a PDF, and the AI consultation - a set of questions you can ask about your own chart, which "
            "always comes with your detailed Kundali report as a PDF. In these products an AI model explains "
            "the calculated chart in plain language. The AI never calculates positions or dates - it only interprets the "
            "Swiss Ephemeris results - and every report is checked automatically against the chart data before delivery.",
        )),
        Section("Two systems, and only one of them is AI", (
            "Everything here is built out of two layers that never swap jobs. The first is the Swiss Ephemeris - "
            "the astronomical calculation library professional astrology software and observatories use - which "
            "takes your date, time and place of birth and computes the exact positions of the nine grahas, your "
            "lagna, your nakshatra, every Vimshottari dasha date, your mangal dosha status and the exact start and "
            "end of a sade sati. That layer is arithmetic, not opinion: the same birth details give the same "
            "numbers today, next year, and on anybody else's machine.",
            "The second layer is the AI, and it only ever reads what the first layer produced. It explains your "
            "chart in plain English, Hindi or Marathi, the way a knowledgeable astrologer would, and it is not "
            "allowed to work out a position or a date for itself. Every report is checked automatically against "
            "the calculated chart before it is delivered - which is why the dates in a {site_name} report are the "
            "engine's dates and not a sentence an AI wrote.",
            "That split is the whole accuracy claim, and it is worth being plain about why. The mistake a careful "
            "human astrologer can still make is an arithmetic one - a missed minute of birth time, the wrong "
            "ayanamsa, a digit transposed halfway down a page of longhand - and that is precisely the step the "
            "Swiss Ephemeris removes. The AI removes none of the judgement; it only puts a correct chart into "
            "words you can read.",
        )),
        Section("A discipline of precise records", (
            "Indian astrology has always been a discipline of record-keeping. Maharishi Bhrigu, one of the "
            "Saptarishis, is said to have compiled hundreds of thousands of horoscopes by hand, over a lifetime, "
            "to build the body of material predictive astrology still draws on. What took a sage years of manual "
            "calculation, the Swiss Ephemeris now computes in well under a second, without the transcription slips "
            "that even patient hand-work cannot fully avoid.",
            "To be exact about what we are and are not claiming: we do not use the Bhrigu Samhita, and nothing on "
            "this site is drawn from its texts. The continuity we mean is one of precision-mindedness - the same "
            "insistence on getting the numbers exactly right, with better tools for the arithmetic.",
        )),
        Section("What we believe", (
            "Astrology is a traditional, faith-based practice. We present it constructively: no fear, no predictions of "
            "death, illness or disaster, no selling of gemstones or paid rituals. Use what you read here for reflection "
            "and guidance alongside your own judgement, and consult qualified professionals for health, legal or "
            "financial decisions.",
        )),
        Section("Who runs this site", (
            "{site_name} is operated by {legal_entity}, {legal_address}. {gstin_line}. Questions, feedback and "
            "support requests are welcome - see the contact page.",
        )),
        # AGPL section 13: people who use the site over the network are offered its source. Kept short and factual;
        # the position changes if the Swiss Ephemeris professional licence is bought (see LICENSE in the repository).
        Section("Source code and licence", (
            "This website's software is free software under the GNU Affero General Public License, version 3 or "
            "later, because it uses the Swiss Ephemeris through pyswisseph under that licence. The complete "
            "corresponding source code of the version running here is published at {source_url}.",
            "The Swiss Ephemeris itself is by Astrodienst AG, Zurich. If we move to the Swiss Ephemeris "
            "Professional License, this notice will be updated.",
        )),
    ),
)

CONTACT = PolicyPage(
    slug="contact", nav_label="Contact", title="Contact Us",
    meta_description="Contact and support details: e-mail, phone and postal address, and what to include when you write "
                     "about a payment or a report.",
    h1="Contact us",
    intro="We usually reply within two working days.",
    sections=(
        Section("How to reach us", (
            ["E-mail: {support_email}", "{support_phone_line}",
             "Postal address: {legal_entity}, {legal_address}", "{gstin_line}"],
        )),
        Section("About a payment or a report", (
            "Please include the order reference shown on your order page (it starts with order_) and the e-mail or "
            "phone number you entered while paying. Never send card numbers, UPI PINs or OTPs - we will never ask for them.",
            "If you paid but your report or questions did not arrive, write to us: every payment is recorded on our side "
            "and we will either deliver your purchase or refund it, as described in the refund policy.",
        )),
    ),
)

PRIVACY = PolicyPage(
    slug="privacy", nav_label="Privacy Policy", title="Privacy Policy",
    meta_description="What personal information this site collects - birth details, contact details for payments, chat "
                     "messages - why, who processes it, how long it is kept and how to have it deleted.",
    h1="Privacy policy",
    intro="This policy explains what information {site_name} (operated by {legal_entity}) collects, why, and what "
          "choices you have. Last updated: {policies_updated}.",
    sections=(
        Section("Information you give us", (
            ["Birth details (date, time and place of birth) and, optionally, a name. They are used to calculate your "
             "chart. For the free tools they are processed in memory to answer your request and are not stored with your "
             "identity.",
             "When you buy a report: the birth details, the language and the optional name for that report are stored "
             "with your order so that we can generate the report and let you download it again.",
             "When you use the AI consultation: your birth details and the messages of the conversation are stored so that "
             "the conversation can continue and your remaining questions can be counted. The chart itself is computed "
             "on our own servers with the Swiss Ephemeris, not by the AI.",
             "Your e-mail address, which checkout requires. We send you one message per purchase: the permanent "
             "link to your order, so that you can download your report again on any device. It is also how we "
             "reach you about that purchase if something goes wrong. The mobile number beside it stays optional.",
             "A mobile number, if you choose to give one, for your payment receipt and for support."],
        )),
        Section("Information collected automatically", (
            ["A first-party cookie named uid that holds a random identifier. It remembers your free and paid consultation "
             "questions and your purchases. It is not used for advertising or cross-site tracking.",
             "Google Analytics cookies, named _ga and _ga_ followed by the property's identifier, set by Google's "
             "measurement script on every page. They count visits and show us which pages are used, on what kind of "
             "device, and the general region a visit came from. They hold a random identifier, not your name, and we "
             "do not use them for advertising or to build a profile of you. Google's own privacy policy applies to "
             "what its script collects. Any content blocker, or your browser's Do Not Track setting where Google "
             "honours it, stops the script; the site works exactly the same without it.",
             "Your browser's local storage keeps your last entered birth details and chat session on your own device for "
             "convenience; it is not sent anywhere except with your own requests.",
             "Server logs (IP address, time, page requested, browser type) kept for security and troubleshooting. For "
             "rate limiting we store only a keyed hash of your network address, never the address itself.",
             "Your location, and only if you tap \u201cUse My Location\u201d on one of the tool pages. Your browser asks "
             "your permission first. The coordinates it returns are used on your own device, to pick the nearest city "
             "from the public list of cities this site has already sent to your browser. Those coordinates are never "
             "transmitted to us or to anyone else, we never see them and we do not store them - the only thing "
             "submitted with your chart request is the city name you end up with, exactly as if you had typed it. The "
             "button is never required: typing the city does the same thing."],
        )),
        Section("Payments", (
            "Payments are processed by Razorpay. Card, UPI, netbanking and wallet details are entered on Razorpay's secure "
            "checkout and never reach our servers. We receive and store the payment and order identifiers, the amount and "
            "the payment status. Razorpay's own privacy policy applies to the information you give them.",
        )),
        Section("AI processing", (
            "Your chart is never written by an AI: it is calculated on our own servers with the Swiss Ephemeris. "
            "For paid reports and the AI consultation, the calculated chart data and (for the consultation) your messages "
            "are sent to our AI provider, Anthropic, to write the interpretation. Your name, e-mail address and phone "
            "number are not sent to the AI provider. Rashifal pages are general readings and involve no personal data.",
        )),
        Section("How we use and share information", (
            ["To provide the tools, reports and consultation you ask for, and to give you access to what you bought.",
             "To prevent abuse, keep the service secure and meet legal and tax obligations.",
             "We do not sell personal information. We share it only with the service providers needed to run the site "
             "(hosting, Razorpay for payments, Anthropic for AI interpretation of the chart the Swiss Ephemeris has already "
             "calculated here, Google Analytics for measuring traffic, Resend for sending that one e-mail) and "
             "when the law requires it.",
             "If advertising is shown on free pages in the future, this policy will be updated before it starts to name "
             "the advertising partner and the cookies involved."],
        )),
        Section("Retention and your choices", (
            "Order records are kept for as long as tax and accounting law requires. Purchased reports stay available from "
            "your order page so that you can download them again. Consultation conversations are kept so that you can "
            "return to them.",
            "You can ask us to delete your consultation conversations, the birth details attached to your orders, or your "
            "contact details by writing to {support_email}. We will act on the request within 30 days, except where we are "
            "legally required to keep a record. You can clear the cookie and local storage in your browser at any time; "
            "keep your order page link, because it is what lets you reach a purchase without the cookie.",
        )),
        Section("Children", (
            "The paid services are intended for adults (18 and over). A parent or guardian may create a child's chart.",
        )),
        Section("Contact and grievances", (
            "For any privacy question or complaint, contact the grievance officer at {legal_entity}: "
            "{contact_details}.",
        )),
    ),
)

TERMS = PolicyPage(
    slug="terms", nav_label="Terms of Use", title="Terms of Use",
    meta_description="Terms for using the free astrology tools and buying digital reports and consultation questions: "
                     "prices in INR, delivery, acceptable use, liability and governing law.",
    h1="Terms of use",
    intro="By using {site_name} you agree to these terms. The site is operated by {legal_entity}. "
          "Last updated: {policies_updated}.",
    sections=(
        Section("Who you are buying from", (
            "{site_name} is a service of {legal_entity}, {legal_address}. {gstin_line}. Support is by e-mail at "
            "{support_email}; all prices on this site are in Indian rupees (INR) and include any applicable taxes.",
        )),
        Section("The service", (
            "{site_name} provides Vedic astrology calculations made with the Swiss Ephemeris (sidereal zodiac, Lahiri "
            "ayanamsa), general rashifal readings, AI-written interpretation reports of those calculations and an "
            "AI consultation chat. Astrology is a traditional, faith-based practice: the content is offered "
            "for guidance and reflection only. It is not a prediction of certain events and not medical, legal, "
            "financial or psychological advice. Decisions you take remain your own responsibility.",
        )),
        Section("Accuracy", (
            "Planetary positions are computed with the Swiss Ephemeris and depend on the birth details you enter; a wrong "
            "birth time or place gives a different chart. Interpretations are written by an AI model from that chart and "
            "checked automatically, but they may still contain mistakes. Tell us if you find one.",
        )),
        Section("Paid products, prices and delivery", (
            ["Prices are shown in Indian rupees (INR) and include applicable taxes unless stated otherwise.",
             "Reports are digital goods delivered as a PDF download, normally within a few minutes of a successful payment. "
             "Your order page is the permanent link to your purchase - please keep it.",
             "A consultation purchase adds a fixed number of questions to your consultation in this browser and includes "
             "the detailed Kundali report (PDF) for the birth details of that consultation. Questions do not expire.",
             "Payments are handled by Razorpay. Refunds are described in the refund policy.",
             "Purchased content is for your personal, non-commercial use."],
        )),
        Section("Acceptable use", (
            ["Do not misuse the site: no automated scraping or bulk requests, no attempts to bypass payment, quotas or "
             "security, no unlawful, abusive or harmful content in the consultation.",
             "Enter birth details of other people only with their knowledge.",
             "We may limit or suspend access that harms the service or other users."],
        )),
        Section("Intellectual property", (
            "The site, its texts, design and software belong to {legal_entity} or its licensors. Astronomical calculations "
            "use the Swiss Ephemeris by Astrodienst AG under its licence terms.",
        )),
        Section("Liability", (
            "The service is provided as is. To the extent the law allows, {legal_entity} is not liable for indirect or "
            "consequential loss, and its total liability for a paid product is limited to the amount you paid for it.",
        )),
        Section("Changes, governing law and contact", (
            "We may update these terms; the date above shows the latest version. These terms are governed by the laws of "
            "India, and the courts at {jurisdiction} have jurisdiction. Contact: {legal_entity}, "
            "{contact_details}.",
        )),
    ),
)

REFUND = PolicyPage(
    slug="refund-policy", nav_label="Refund & Cancellation", title="Refund and Cancellation Policy",
    meta_description="Refund and cancellation policy for digital reports and consultation packs: full refund when a paid "
                     "purchase cannot be delivered, how to ask, and how long refunds take.",
    h1="Refund and cancellation policy",
    intro="Our paid products are digital and are delivered immediately, so this policy is simple. "
          "Last updated: {policies_updated}.",
    sections=(
        Section("When we refund", (
            ["We could not deliver what you paid for: if your report cannot be generated within 24 hours of payment, or "
             "your consultation questions were not added, we refund the full amount. For a consultation purchase whose "
             "questions were added but whose included Kundali report could not be generated, we refund the price of the "
             "report.",
             "You were charged more than once for the same order.",
             "The report has a clear technical fault (for example it is for different birth details than you entered, is "
             "unreadable, or is in the wrong language) and we cannot correct it within 3 working days of your message."],
        )),
        Section("When we do not refund", (
            ["A report that has been delivered correctly, or consultation questions that have been used. As with other "
             "digital content, a delivered report cannot be returned.",
             "Disagreement with an astrological interpretation. Astrology is a faith-based practice and we do not promise "
             "outcomes.",
             "Wrong birth details entered by the customer. Write to us within 7 days and we will regenerate the report "
             "once with the corrected details at no charge."],
        )),
        Section("Cancellation", (
            "An order can be cancelled any time before payment simply by closing the payment window - nothing is charged. "
            "After payment, delivery starts at once, so an order cannot be cancelled; the refund rules above apply. There "
            "are no subscriptions and no recurring charges.",
        )),
        Section("How to ask and how long it takes", (
            "Write to {support_email} within 7 days of payment with your order reference (it starts with order_). We reply "
            "within 2 working days. Approved refunds are made to the original payment method through Razorpay and "
            "normally reach your account within 5 to 7 working days, depending on your bank.",
            "If money was deducted but the payment failed or the page showed an error, your bank or Razorpay usually "
            "reverses it automatically within 5 to 7 working days; write to us if it does not.",
        )),
        Section("Shipping", (
            "All products are digital and delivered online. Nothing is shipped physically.",
        )),
    ),
)

DISCLAIMER_PAGE = PolicyPage(
    slug="disclaimer", nav_label="Disclaimer", title="Disclaimer",
    meta_description="Astrology is a traditional faith-based practice. Content on this site is for guidance and "
                     "reflection only and is not medical, legal or financial advice.",
    h1="Disclaimer",
    intro="Please read this before relying on anything you find on {site_name}.",
    sections=(
        Section("A faith-based practice", (
            "Jyotish (Vedic astrology) is a traditional, faith-based practice. Its statements cannot be verified "
            "scientifically. Charts, rashifal readings, reports and consultation answers on this site are offered for "
            "reflection, cultural interest and guidance only. They are not predictions of certain events and come with "
            "no guarantee of any outcome.",
        )),
        Section("Not professional advice", (
            "Nothing on this site is medical, psychological, legal, financial or investment advice. Do not start, stop or "
            "delay medical treatment, make investments, sign contracts or take legal steps because of astrological "
            "content. For such matters please consult a qualified professional.",
        )),
        Section("What we deliberately do not do", (
            ["We never predict death, lifespan, serious illness, accidents or similar events.",
             "We never tell anyone to marry or not to marry a particular person; guna milan is one traditional input.",
             "We do not sell gemstones, yantras, pujas or paid rituals, and we earn nothing from any recommendation. "
             "A detailed report names the stone the classical rule points to for that chart, as tradition's "
             "suggestion and entirely optional, with no weight, price, seller or promised result attached.",
             "Remedies we suggest are free or nearly free: mantras, charity, service, simple habits."],
        )),
        Section("Calculations and AI", (
            "Planetary positions and dates are calculated with the Swiss Ephemeris (sidereal zodiac, Lahiri ayanamsa, "
            "whole-sign houses) and depend on the birth details entered. Interpretations in paid reports, the consultation "
            "and rashifal pages are written by an AI model from those calculations and checked automatically; they can "
            "still contain errors. You remain responsible for your own decisions.",
        )),
    ),
)

POLICY_PAGES: dict[str, PolicyPage] = {p.slug: p for p in (ABOUT, CONTACT, PRIVACY, TERMS, REFUND, DISCLAIMER_PAGE)}
