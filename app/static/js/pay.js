/* Razorpay payments for the paid products (Phase 6).
 *
 * Listens for the site-wide cancelable `product:purchase` event (see app.js) and, when payments are
 * configured on the server (<script data-pay data-enabled="1">), takes it over:
 *   report products  -> small panel (report language, optional e-mail / phone) -> POST /api/payments/order
 *                       -> Razorpay Checkout -> POST /api/payments/verify -> "preparing your report" (polls
 *                       GET /api/payments/order/{id}) -> PDF download button + permanent /order/{token} link
 *   consultation (₹ pack price; ALWAYS includes the Kundali PDF report for that consultation's birth details)
 *                     -> order -> Checkout -> verify -> `consultation:credited` (chat.js reloads the quota) and a status
 *                        box above the paywall: "questions added, your Kundali PDF is being prepared" -> PDF button
 * When payments are not configured the event is left alone and app.js shows its "launching soon" note.
 *
 * The amount is never sent from here: the server prices the product from its own catalogue. Nothing is unlocked
 * by this script either - the server verifies Razorpay's signature; this file only shows what the server says.
 * The ONE external URL of the whole site is Razorpay's checkout.js, loaded lazily on the first Pay click.
 * The same file drives the status box of the /order/{token} page.
 */
(function (root) {
  "use strict";

  var CHECKOUT_URL = "https://checkout.razorpay.com/v1/checkout.js";
  var LANGUAGES = [["en", "English"], ["hi", "हिंदी"], ["mr", "मराठी"]];
  // The wait we promise, mirrored from order_page.WAIT_RANGE (tests/test_payments.py asserts they agree).
  // The server sends `report_wait` on every order view, so this table is only for the panel shown BEFORE an
  // order exists - the one moment the client has nothing to read it off.
  var WAIT = { "kundali-report-simple": "3-5" }, WAIT_DEFAULT = "5-10";
  function waitFor(product) { return WAIT[product] || WAIT_DEFAULT; }

  // How long to keep polling. DERIVED from the promise rather than set beside it: the two drifted apart
  // before, when the copy said "1-3 minutes" and this said 12 - four times the headroom, until the book grew
  // to twelve calls and measured 8.8 minutes, leaving 1.4x. Polling then simply STOPS, and the spinner spins
  // for ever with no message, so the page lies rather than merely being slow. Nothing is lost when it happens
  // (the order page link is in the copy right above it), but nothing says so either. Twice the top of what we
  // promised, floor ten minutes - so it can only drift if someone changes the promise, which changes this too.
  var POLL_MS = 4000;
  function pollLimitMs(wait) {
    var top = parseInt(String(wait || WAIT_DEFAULT).split("-").pop(), 10);
    return Math.max(10, (isFinite(top) ? top : 10) * 2) * 60 * 1000;
  }

  // Page language (html lang): Marathi (/mr/...) and Hindi (/hi/...) pages get a purchase panel in that language and
  // default the REPORT language to it; everything else is English. All three dictionaries have the same keys (tested).
  // Vocabulary follows the page copy of each tree (app/web/content): Hindi says सवाल, Marathi says प्रश्न.
  var TEXT = {
    en: {
      language: "Report language", email: "E-mail", emailConfirm: "Confirm e-mail",
      emailHint: "We send your permanent download link here. Please check it: a typo means the link goes to someone else.",
      phone: "Mobile number (optional)", pay: "Pay ₹{price} securely",
      methods: "UPI, cards, netbanking and wallets via Razorpay. The report is prepared in {wait} minutes after payment.",
      badEmail: "Please check the e-mail address.", noEmail: "Please enter your e-mail address.",
      emailMismatch: "The two e-mail addresses do not match.",
      badPhone: "Please enter a 10-digit mobile number, or leave it empty.",
      opening: "Opening secure payment…", confirming: "Confirming your payment…",
      startFailed: "We could not start the payment. Please try again.",
      stillConfirming: "We are confirming your payment. This page will update by itself.",
      closed: "Payment window closed - the payment was not completed. You can try again whenever you like.",
      failed: "The payment did not go through. You can try again or use another method.",
      blocked: "The payment window could not be loaded. Please check your connection (or ad blocker) and try again.",
      offline: "Could not reach the server. Please check your connection and try again.",
      download: "Download your PDF", orderPage: "Your order page (bookmark it to download again): ", reference: "Order reference: ",
      unpaidTitle: "Payment not completed",
      unpaidText: "No payment has been confirmed for this order. If money was deducted it will be confirmed here automatically within a few minutes.",
      creditedTitle: "Payment received - thank you", creditedText: "{n} questions have been added to your consultation.",
      bundlePreparingTitle: "Payment received - {n} questions added",
      bundlePreparingText: "You can continue your consultation now. Your Kundali PDF report, which is included, is being written " +
        "from your exact chart - this takes {wait} minutes. It will appear here and on your order page.",
      bundleReadyTitle: "{n} questions added - your Kundali PDF is ready",
      bundleReadyText: "Payment received - thank you. Download your Kundali report below; you can download it again at any time from your order page.",
      bundleDelayedTitle: "{n} questions added - your Kundali PDF is delayed",
      bundleDelayedText: "Your payment is safe and your questions are ready to use. Preparing the included Kundali report is taking " +
        "longer than it should; we will complete it and it will appear on your order page. Please keep the link below.",
      readyTitle: "Your report is ready",
      readyText: "Payment received - thank you. Download your PDF below. You can download it again at any time from your order page.",
      delayedTitle: "Payment received - your report is delayed",
      delayedText: "Your payment is safe and recorded. Preparing the report is taking longer than it should; we will complete it " +
        "and it will appear on your order page. Please keep the link below.",
      stages: ["Calculating your exact chart", "Writing your highlights",
               "Writing your life timeline", "Preparing your PDF"],
      emailCopy: "We have e-mailed your permanent download link to {email}. It works even if you close this page.",
      preparingTitle: "Payment received - preparing your report",
      preparingText: "Your report is being written from your exact chart. This takes {wait} minutes. You can keep this page open, " +
        "or come back later using your order page link below."
    },
    mr: {
      language: "अहवालाची भाषा", email: "ई-मेल", emailConfirm: "ई-मेल पुन्हा लिहा",
      emailHint: "तुमचा कायमचा डाउनलोड दुवा याच पत्त्यावर पाठवला जातो. पत्ता तपासून घ्या: चूक झाल्यास दुवा दुसऱ्याकडे जाईल.",
      phone: "मोबाइल क्रमांक (ऐच्छिक)", pay: "₹{price} सुरक्षितपणे भरा",
      methods: "Razorpay द्वारे UPI, कार्ड, नेटबँकिंग आणि वॉलेट. पेमेंटनंतर {wait} मिनिटांत अहवाल तयार होतो.",
      badEmail: "कृपया ई-मेल पत्ता तपासा.", noEmail: "कृपया तुमचा ई-मेल पत्ता लिहा.",
      emailMismatch: "दोन्ही ई-मेल पत्ते जुळत नाहीत.",
      badPhone: "कृपया 10 अंकी मोबाइल क्रमांक भरा, किंवा तो रिकामा ठेवा.",
      opening: "सुरक्षित पेमेंट उघडत आहे…", confirming: "तुमच्या पेमेंटची खात्री करत आहोत…",
      startFailed: "पेमेंट सुरू करता आले नाही. कृपया पुन्हा प्रयत्न करा.",
      stillConfirming: "तुमच्या पेमेंटची खात्री करत आहोत. हे पान आपोआप अद्ययावत होईल.",
      closed: "पेमेंटची खिडकी बंद झाली - पेमेंट पूर्ण झाले नाही. तुम्ही केव्हाही पुन्हा प्रयत्न करू शकता.",
      failed: "पेमेंट होऊ शकले नाही. पुन्हा प्रयत्न करा किंवा दुसरी पद्धत वापरा.",
      blocked: "पेमेंटची खिडकी उघडता आली नाही. कृपया इंटरनेट जोडणी (किंवा ad blocker) तपासून पुन्हा प्रयत्न करा.",
      offline: "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट जोडणी तपासून पुन्हा प्रयत्न करा.",
      download: "तुमचा PDF डाउनलोड करा", orderPage: "तुमच्या ऑर्डरचे पान (पुन्हा डाउनलोड करण्यासाठी जपून ठेवा): ", reference: "ऑर्डर क्रमांक: ",
      unpaidTitle: "पेमेंट पूर्ण झाले नाही",
      unpaidText: "या ऑर्डरसाठी कोणत्याही पेमेंटची खात्री झालेली नाही. पैसे कापले गेले असतील तर काही मिनिटांत येथे आपोआप नोंद होईल.",
      creditedTitle: "पेमेंट मिळाले - धन्यवाद", creditedText: "तुमच्या सल्लामसलतीत {n} प्रश्न जमा झाले आहेत.",
      bundlePreparingTitle: "पेमेंट मिळाले - {n} प्रश्न जमा झाले",
      bundlePreparingText: "तुम्ही आता सल्लामसलत पुढे सुरू ठेवू शकता. यासोबत मिळणारा तुमचा कुंडली PDF अहवाल तुमच्या नेमक्या कुंडलीवरून " +
        "लिहिला जात आहे - याला {wait} मिनिटे लागतात. तो येथे आणि तुमच्या ऑर्डरच्या पानावर दिसेल.",
      bundleReadyTitle: "{n} प्रश्न जमा झाले - तुमचा कुंडली PDF तयार आहे",
      bundleReadyText: "पेमेंट मिळाले - धन्यवाद. खालील बटणाने कुंडली अहवाल डाउनलोड करा; ऑर्डरच्या पानावरून तो केव्हाही पुन्हा डाउनलोड करता येईल.",
      bundleDelayedTitle: "{n} प्रश्न जमा झाले - कुंडली PDF ला उशीर होत आहे",
      bundleDelayedText: "तुमचे पेमेंट सुरक्षित आहे आणि तुमचे प्रश्न वापरासाठी तयार आहेत. सोबतचा कुंडली अहवाल तयार होण्यास अपेक्षेपेक्षा जास्त " +
        "वेळ लागत आहे; आम्ही तो पूर्ण करू आणि तो तुमच्या ऑर्डरच्या पानावर दिसेल. कृपया खालील दुवा जपून ठेवा.",
      readyTitle: "तुमचा अहवाल तयार आहे",
      readyText: "पेमेंट मिळाले - धन्यवाद. खालील बटणाने PDF डाउनलोड करा. तुमच्या ऑर्डरच्या पानावरून तो केव्हाही पुन्हा डाउनलोड करता येईल.",
      delayedTitle: "पेमेंट मिळाले - अहवालाला उशीर होत आहे",
      delayedText: "तुमचे पेमेंट सुरक्षित आहे आणि त्याची नोंद झाली आहे. अहवाल तयार होण्यास अपेक्षेपेक्षा जास्त वेळ लागत आहे; आम्ही तो पूर्ण करू " +
        "आणि तो तुमच्या ऑर्डरच्या पानावर दिसेल. कृपया खालील दुवा जपून ठेवा.",
      stages: ["तुमची नेमकी कुंडली मांडत आहे", "ठळक मुद्दे लिहीत आहे",
               "तुमचा जीवनपट लिहीत आहे", "तुमचा PDF तयार करत आहे"],
      emailCopy: "तुमचा कायमचा डाउनलोड दुवा आम्ही {email} या पत्त्यावर ई-मेलने पाठवला आहे. हे पान बंद केले तरी तो चालतो.",
      preparingTitle: "पेमेंट मिळाले - तुमचा अहवाल तयार होत आहे",
      preparingText: "तुमच्या नेमक्या कुंडलीवरून अहवाल लिहिला जात आहे. याला {wait} मिनिटे लागतात. हे पान उघडे ठेवा, किंवा खालील " +
        "ऑर्डरच्या पानाच्या दुव्यावरून नंतर परत या."
    }
  };
  TEXT.hi = {
    language: "रिपोर्ट की भाषा", email: "ई-मेल", emailConfirm: "ई-मेल दोबारा लिखें",
    emailHint: "आपका स्थायी डाउनलोड लिंक इसी पते पर भेजा जाता है। पता जाँच लें: ग़लती होने पर लिंक किसी और के पास चला जाएगा।",
    phone: "मोबाइल नंबर (वैकल्पिक)", pay: "₹{price} सुरक्षित रूप से चुकाएँ",
    methods: "Razorpay के ज़रिए UPI, कार्ड, नेटबैंकिंग और वॉलेट। भुगतान के बाद {wait} मिनट में रिपोर्ट तैयार होती है।",
    badEmail: "कृपया ई-मेल पता जाँचें।", noEmail: "कृपया अपना ई-मेल पता भरें।",
    emailMismatch: "दोनों ई-मेल पते एक जैसे नहीं हैं।",
    badPhone: "कृपया 10 अंकों का मोबाइल नंबर भरें, या इसे खाली छोड़ दें।",
    opening: "सुरक्षित भुगतान खुल रहा है…", confirming: "आपके भुगतान की पुष्टि हो रही है…",
    startFailed: "भुगतान शुरू नहीं हो सका। कृपया दोबारा कोशिश करें।",
    stillConfirming: "हम आपके भुगतान की पुष्टि कर रहे हैं। यह पेज अपने आप अपडेट हो जाएगा।",
    closed: "भुगतान की विंडो बंद हो गई - भुगतान पूरा नहीं हुआ। आप जब चाहें दोबारा कोशिश कर सकते हैं।",
    failed: "भुगतान नहीं हो सका। दोबारा कोशिश करें या कोई और तरीका चुनें।",
    blocked: "भुगतान की विंडो नहीं खुल सकी। कृपया इंटरनेट कनेक्शन (या ad blocker) जाँचकर दोबारा कोशिश करें।",
    offline: "सर्वर से संपर्क नहीं हो सका। कृपया इंटरनेट कनेक्शन जाँचकर दोबारा कोशिश करें।",
    download: "अपना PDF डाउनलोड करें", orderPage: "आपके ऑर्डर का पेज (दोबारा डाउनलोड के लिए सँभालकर रखें): ", reference: "ऑर्डर संदर्भ: ",
    unpaidTitle: "भुगतान पूरा नहीं हुआ",
    unpaidText: "इस ऑर्डर के लिए किसी भुगतान की पुष्टि नहीं हुई है। अगर पैसे कट गए हैं तो कुछ मिनटों में यहाँ अपने आप दर्ज हो जाएगा।",
    creditedTitle: "भुगतान मिल गया - धन्यवाद", creditedText: "आपकी बातचीत में {n} सवाल जोड़ दिए गए हैं।",
    bundlePreparingTitle: "भुगतान मिल गया - {n} सवाल जोड़ दिए गए",
    bundlePreparingText: "अब आप अपनी बातचीत जारी रख सकते हैं। इसके साथ मिलने वाली आपकी कुंडली PDF रिपोर्ट आपकी सटीक कुंडली से लिखी जा रही है - " +
      "इसमें {wait} मिनट लगते हैं। यह यहाँ और आपके ऑर्डर के पेज पर दिखेगी।",
    bundleReadyTitle: "{n} सवाल जोड़ दिए गए - आपकी कुंडली PDF तैयार है",
    bundleReadyText: "भुगतान मिल गया - धन्यवाद। नीचे से अपनी कुंडली रिपोर्ट डाउनलोड करें; ऑर्डर के पेज से इसे कभी भी दोबारा डाउनलोड किया जा सकता है।",
    bundleDelayedTitle: "{n} सवाल जोड़ दिए गए - कुंडली PDF में देर हो रही है",
    bundleDelayedText: "आपका भुगतान सुरक्षित है और आपके सवाल उपयोग के लिए तैयार हैं। साथ की कुंडली रिपोर्ट बनने में अपेक्षा से अधिक समय लग रहा है; " +
      "हम इसे पूरा करेंगे और यह आपके ऑर्डर के पेज पर दिखेगी। कृपया नीचे दिया लिंक सँभालकर रखें।",
    readyTitle: "आपकी रिपोर्ट तैयार है",
    readyText: "भुगतान मिल गया - धन्यवाद। नीचे से अपना PDF डाउनलोड करें। ऑर्डर के पेज से इसे कभी भी दोबारा डाउनलोड किया जा सकता है।",
    delayedTitle: "भुगतान मिल गया - रिपोर्ट में देर हो रही है",
    delayedText: "आपका भुगतान सुरक्षित है और दर्ज हो चुका है। रिपोर्ट बनने में अपेक्षा से अधिक समय लग रहा है; हम इसे पूरा करेंगे " +
      "और यह आपके ऑर्डर के पेज पर दिखेगी। कृपया नीचे दिया लिंक सँभालकर रखें।",
    stages: ["आपकी सटीक कुंडली बनाई जा रही है", "मुख्य बातें लिखी जा रही हैं",
             "आपका जीवन-कालक्रम लिखा जा रहा है", "आपकी PDF तैयार की जा रही है"],
    emailCopy: "आपका स्थायी डाउनलोड लिंक हमने {email} पर ई-मेल कर दिया है। यह पेज बंद करने पर भी वह काम करता है।",
    preparingTitle: "भुगतान मिल गया - आपकी रिपोर्ट तैयार हो रही है",
    preparingText: "आपकी सटीक कुंडली से रिपोर्ट लिखी जा रही है। इसमें {wait} मिनट लगते हैं। यह पेज खुला रखें, या नीचे दिए " +
      "ऑर्डर के पेज के लिंक से बाद में लौटें।"
  };
  function text(lang) { return TEXT[lang === "mr" || lang === "hi" ? lang : "en"]; }

  /** Report language offered first: a Marathi / Hindi page decides; otherwise what this visitor chose last; else English. */
  function defaultReportLanguage(pageLang, saved) {
    if (pageLang === "mr" || pageLang === "hi") return pageLang;
    return saved === "mr" || saved === "hi" || saved === "en" ? saved : "en";
  }

  /* ---------- pure helpers (also run by tests/test_payments.py in an embedded V8) ---------- */

  /** Every consultation tier ("consultation-basic", "consultation-premium", ...) buys questions for a chat
   * session rather than a report for birth details, so the panel and the body differ. Matching on the family
   * rather than on one id means a new tier needs no change here. */
  function isConsultation(product) {
    return typeof product === "string" && product.indexOf("consultation-") === 0;
  }

  /** `product:purchase` detail + the panel's form values -> body of POST /api/payments/order. No amount, ever. */
  function orderBody(detail, form) {
    form = form || {};
    var body = { product: detail.product };
    // The address goes on EVERY body, consultation included: it is required by the API for every
    // product, and this used to return early for consultations, which would refuse the purchase.
    var contact = (form.email || "").trim();
    if (contact) body.email = contact;
    if (isConsultation(detail.product)) {
      body.session_id = detail.sessionId || null;
      return body;
    }
    var request = detail.request || {};
    body.language = form.language || "en";
    if (request.boy || request.girl) {
      body.boy = request.boy; body.girl = request.girl;
      var names = detail.name && typeof detail.name === "object" ? detail.name : {};
      if (names.boy) body.boy_name = names.boy;
      if (names.girl) body.girl_name = names.girl;
    } else {
      body.birth = request;
      if (detail.name && typeof detail.name === "string") body.name = detail.name;
    }
    var phone = (form.phone || "").replace(/[\s-]/g, "");
    if (phone) body.phone = phone;
    return body;
  }

  /** Problems with the contact fields, as [{field, message}]. E-mail is required and typed twice.

     The address is where the permanent order link goes, so a buyer who skips it is exactly the buyer
     who cannot be helped after closing the tab. It is confirmed because a typo does not just lose a
     receipt: the link opens the order, and whoever owns the address actually typed can use it. */
  function validateForm(form, lang) {
    var T = text(lang), errors = [], email = (form.email || "").trim(), phone = (form.phone || "").replace(/[\s-]/g, "");
    var confirm = (form.emailConfirm || "").trim();
    if (!email) errors.push({ field: "email", message: T.noEmail });
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) errors.push({ field: "email", message: T.badEmail });
    else if (confirm.toLowerCase() !== email.toLowerCase()) {
      errors.push({ field: "emailConfirm", message: T.emailMismatch });
    }
    if (phone && !/^\+?[0-9]{10,13}$/.test(phone)) errors.push({ field: "phone", message: T.badPhone });
    return errors;
  }

  /** Server order (POST /api/payments/order response) -> options for `new Razorpay(options)`. */
  function checkoutOptions(order, siteName, handlers) {
    return {
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: siteName,
      description: order.description,
      order_id: order.order_id,
      prefill: order.prefill || {},
      // INDIGO, NEVER GOLD - the brand rule for third-party widgets.
      // Razorpay paints its Checkout header with this colour and writes the header text on it in WHITE,
      // and there is no option to change that text. So whatever goes here is judged against white, on
      // the one screen where a customer types card details:
      //     --color-primary #241B54  15.44:1   <- this
      //     --color-card    #2E2660  13.44:1
      //     --color-accent  #E0A526   2.19:1   <- the Brand section 2 failure, and the tempting edit
      //     --color-saffron #D2691E   3.63:1
      // "The accent is for CTAs, and Checkout is a CTA" is the plausible-looking change that breaks it.
      // tests/test_payments.py asserts the CONTRAST rather than the hex, so re-branding stays possible
      // and gold stays impossible. No stylesheet test can see this: it is a JS literal handed to a
      // widget that renders outside our CSS and our CSP.
      theme: { color: "#241B54" },
      handler: handlers.success,
      modal: { ondismiss: handlers.dismiss, confirm_close: true }
    };
  }

  /** Order status from the server -> what to show: {state, title, text, done}. lang: "en" (default) | "mr". */
  function describe(view, lang) {
    var T = text(lang);
    // The server decides how long to promise - it knows which tier the order entitles. Anything unknown
    // falls back to the LONGER wait, never the shorter, so we can only ever over-state it.
    var wait = (view && view.report_wait) || WAIT_DEFAULT;
    function w(s) { return String(s).replace("{wait}", wait); }
    if (!view || view.status !== "paid") return { state: "unpaid", done: true, title: T.unpaidTitle, text: T.unpaidText };
    if (view.kind === "pack" && !view.includes_report) {
      return { state: "credited", done: true, title: T.creditedTitle, text: T.creditedText.replace("{n}", view.messages) };
    }
    if (view.kind === "pack") { // the consultation purchase: questions are already credited, the Kundali PDF follows
      var n = view.messages;
      if (view.fulfilment === "ready") return { state: "ready", done: true, title: T.bundleReadyTitle.replace("{n}", n), text: T.bundleReadyText };
      if (view.fulfilment === "failed" && !view.retrying) return { state: "delayed", done: true, title: T.bundleDelayedTitle.replace("{n}", n), text: T.bundleDelayedText };
      return { state: "preparing", done: false, title: T.bundlePreparingTitle.replace("{n}", n), text: w(T.bundlePreparingText) };
    }
    if (view.fulfilment === "ready") return { state: "ready", done: true, title: T.readyTitle, text: T.readyText };
    if (view.fulfilment === "failed" && !view.retrying) return { state: "delayed", done: true, title: T.delayedTitle, text: T.delayedText };
    return { state: "preparing", done: false, title: T.preparingTitle, text: w(T.preparingText) };
  }

  // Where each stage STARTS, as a fraction of the wait the server quoted. Reassurance, not telemetry: the
  // server reports one bit for this order ("ready" or not), so nothing here can know which part is being
  // written. It is built so it cannot lie in the way that would matter - THE LAST STAGE NEVER COMPLETES ON
  // A TIMER. Only `fulfilment === "ready"` completes it, and by then this box has been replaced by the ready
  // state, so the customer never sees four ticks and no download. Stages cannot rewind either: they are a
  // function of elapsed time, and elapsed comes from `paid_at`, so a reload or another device resumes where
  // the work actually is rather than restarting the theatre.
  var STAGE_START = [0, 0.08, 0.35, 0.8];

  function elapsedSincePaid(view) {
    var paid = view && view.paid_at;
    if (!paid) return 0;   // no paid_at: stage one is active, which is where a fresh payment is anyway
    var ms = typeof paid === "number" ? paid * 1000 : Date.parse(paid);
    return isNaN(ms) ? 0 : Math.max(0, Date.now() - ms);
  }

  /** [{label, state}] for the waiting screen; state is "done" | "active" | "waiting". Pure. */
  function reportStages(view, lang, elapsedMs) {
    var labels = text(lang).stages, out = [];
    var top = parseInt(String((view && view.report_wait) || WAIT_DEFAULT).split("-").pop(), 10) * 60000;
    var ready = Boolean(view && view.fulfilment === "ready");
    var elapsed = Math.max(0, elapsedMs || 0);
    for (var i = 0; i < labels.length; i++) {
      var started = ready || elapsed >= STAGE_START[i] * top;
      var last = i === labels.length - 1;
      var next = !last && (ready || elapsed >= STAGE_START[i + 1] * top);
      out.push({ label: labels[i], state: !started ? "waiting" : (ready || next ? "done" : "active") });
    }
    return out;
  }

  root.AstroPay = { orderBody: orderBody, validateForm: validateForm, checkoutOptions: checkoutOptions, describe: describe,
    reportStages: reportStages, elapsedSincePaid: elapsedSincePaid, textFor: text,
    defaultReportLanguage: defaultReportLanguage, waitFor: waitFor, pollLimitMs: pollLimitMs, WAIT: WAIT,
    CHECKOUT_URL: CHECKOUT_URL };
  if (typeof document === "undefined") return;

  /* ---------- DOM ---------- */

  var scriptTag = document.querySelector("script[data-pay]");
  var enabled = Boolean(scriptTag && scriptTag.getAttribute("data-enabled") === "1");
  var PENDING_KEY = "pending-order";
  var siteNameMeta = document.querySelector('meta[property="og:site_name"]');
  var siteName = siteNameMeta ? siteNameMeta.getAttribute("content") : document.title;
  var pageLang = (document.documentElement.getAttribute("lang") || "en").slice(0, 2);
  var T = text(pageLang);

  function api(method, url, body) {
    return fetch(url, {
      method: method, credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (data) {
        return { ok: response.ok, status: response.status, body: data };
      });
    }).catch(function () { return { ok: false, status: 0, body: null }; });
  }

  function errorMessage(result, fallback) {
    var detail = result && result.body && result.body.detail;
    if (detail && typeof detail === "object" && detail.message) return detail.message;
    if (result && result.status === 0) return T.offline;
    return fallback;
  }

  function node(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  }

  function remember(value) {
    try {
      if (value) window.localStorage.setItem(PENDING_KEY, JSON.stringify(value));
      else window.localStorage.removeItem(PENDING_KEY);
    } catch (ignore) { /* storage unavailable: only the "come back later" banner is lost */ }
  }

  var checkoutPromise = null;
  function loadCheckout() {
    if (root.Razorpay) return Promise.resolve();
    if (!checkoutPromise) {
      checkoutPromise = new Promise(function (resolve, reject) {
        var script = document.createElement("script");
        script.src = CHECKOUT_URL;
        script.onload = function () { if (root.Razorpay) resolve(); else reject(new Error("checkout.js loaded without Razorpay")); };
        script.onerror = function () { checkoutPromise = null; reject(new Error("checkout.js failed to load")); };
        document.head.appendChild(script);
      });
    }
    return checkoutPromise;
  }

  /* ---------- status box (after payment, and on /order/{token}) ---------- */

  function renderStatus(box, view, extra) {
    var info = describe(view, pageLang);
    box.innerHTML = "";
    box.className = "pay-status pay-status--" + info.state;
    box.setAttribute("data-state", info.state);
    box.appendChild(node("p", "pay-status__title", info.title));
    box.appendChild(node("p", null, info.text));
    if (info.state === "preparing") {
      // The stage list replaces the bare spinner: same reassurance, but it says WHAT is happening. It
      // re-renders on every status poll, which is what advances it - no timer of its own to leak.
      var list = node("ol", "pay-stages");
      var stages = reportStages(view, pageLang, elapsedSincePaid(view));
      for (var s = 0; s < stages.length; s++) {
        var row = node("li", "pay-stages__step is-" + stages[s].state);
        var mark = node("span", "pay-stages__mark", stages[s].state === "done" ? "\u2713" : "");
        mark.setAttribute("aria-hidden", "true");
        row.appendChild(mark);
        row.appendChild(node("span", "pay-stages__label", stages[s].label));
        if (stages[s].state === "active") row.setAttribute("aria-current", "step");
        list.appendChild(row);
      }
      box.appendChild(list);
      if (view && view.email_copy) {
        box.appendChild(node("p", "pay-status__email small", T.emailCopy.replace("{email}", view.email_copy)));
      }
    }
    if (view && view.pdf_url) {
      var download = node("a", "btn btn--cta pay-status__download", T.download);
      download.setAttribute("href", view.pdf_url);
      download.setAttribute("download", "");
      box.appendChild(download);
    }
    if (view && view.order_url && !(extra && extra.onOrderPage)) {
      var keep = node("p", "pay-status__link small", T.orderPage);
      var link = node("a", null, window.location.origin + view.order_url);
      link.setAttribute("href", view.order_url);
      keep.appendChild(link);
      box.appendChild(keep);
    }
    if (view && view.status === "paid") box.appendChild(node("p", "small pay-status__id", T.reference + view.order_id));
    return info;
  }

  function poll(box, orderId, token, extra) {
    var started = Date.now(), limit = pollLimitMs(null);
    function tick() {
      api("GET", "/api/payments/order/" + encodeURIComponent(orderId) + (token ? "?token=" + encodeURIComponent(token) : "")).then(function (result) {
        if (result.ok && result.body) {
          limit = pollLimitMs(result.body.report_wait);  // the promise this order was actually given
          var info = renderStatus(box, result.body, extra);
          if (info.done) { if (info.state !== "unpaid") remember(null); return; }
        }
        if (Date.now() - started < limit) window.setTimeout(tick, POLL_MS);
      });
    }
    window.setTimeout(tick, POLL_MS);
  }

  /* ---------- order page ---------- */

  var orderBox = document.getElementById("order-status");
  if (orderBox) {
    // Always ask the server once: the first paint is server-rendered and may not know about the report that comes
    // with a consultation purchase, or about a job that finished since. Keeps polling only while something is pending.
    (function () {
      var id = orderBox.getAttribute("data-order-id"), token = orderBox.getAttribute("data-order-token");
      api("GET", "/api/payments/order/" + encodeURIComponent(id) + (token ? "?token=" + encodeURIComponent(token) : "")).then(function (result) {
        var info = result.ok && result.body ? renderStatus(orderBox, result.body, { onOrderPage: true }) : null;
        if (!info || !info.done) poll(orderBox, id, token, { onOrderPage: true });
      });
    })();
  }

  /* ---------- buying ---------- */

  function panelFor(button) {
    var holder = button.parentNode, panel = holder.querySelector(".pay");
    if (!panel) {
      panel = node("div", "pay");
      holder.insertBefore(panel, button.nextSibling);
    }
    return panel;
  }

  function say(panel, text, tone) {
    var message = panel.querySelector(".pay__message");
    if (!message) { message = node("p", "pay__message"); message.setAttribute("role", "status"); panel.appendChild(message); }
    message.textContent = text || "";
    message.className = "pay__message" + (tone ? " pay__message--" + tone : "");
    message.hidden = !text;
  }

  function afterPayment(panel, button, view) {
    var info = describe(view, pageLang), box = node("div", "pay-status");
    box.setAttribute("role", "status");
    if (view.kind === "pack" && !view.already_paid) {
      document.dispatchEvent(new CustomEvent("consultation:credited", { detail: view })); // chat.js re-opens the input
      if (!view.includes_report) { remember(null); say(panel, info.title + ". " + info.text, "ok"); return; }
      // The paywall card (where the button and panel live) disappears once the chat re-opens, so the report status
      // goes just above it, outside the card.
      var card = button.closest ? button.closest("aside") : null;
      var old = document.getElementById("pay-bundle-status");
      if (old && old.parentNode) old.parentNode.removeChild(old);
      box.id = "pay-bundle-status";
      say(panel, "");
      if (card && card.parentNode) card.parentNode.insertBefore(box, card); else panel.appendChild(box);
      renderStatus(box, view);
      if (!info.done) poll(box, view.order_id, null); else remember(null);
      return;
    }
    button.hidden = true;
    panel.innerHTML = "";
    panel.appendChild(box);
    renderStatus(box, view);
    if (!info.done) poll(box, view.order_id, null);
    else remember(null);
  }

  function pay(panel, button, detail, form, trigger) {
    trigger.disabled = true;
    say(panel, T.opening);
    function fail(text) { trigger.disabled = false; say(panel, text, "error"); }

    api("POST", "/api/payments/order", orderBody(detail, form)).then(function (created) {
      if (created.status === 503 && created.body && created.body.detail && created.body.detail.error === "payments_not_configured") {
        return fail(button.getAttribute("data-notice") || "Online payment is launching soon. Your free result above is complete and yours to keep.");
      }
      if (!created.ok || !created.body) return fail(errorMessage(created, T.startFailed));
      var order = created.body;
      if (order.already_paid) { trigger.disabled = false; return afterPayment(panel, button, order); }
      remember({ order_id: order.order_id, product: order.product, at: Date.now() });

      loadCheckout().then(function () {
        var checkout = new root.Razorpay(checkoutOptions(order, siteName, {
          success: function (payment) {
            say(panel, T.confirming);
            api("POST", "/api/payments/verify", {
              razorpay_order_id: payment.razorpay_order_id,
              razorpay_payment_id: payment.razorpay_payment_id,
              razorpay_signature: payment.razorpay_signature
            }).then(function (verified) {
              trigger.disabled = false;
              if (verified.ok && verified.body && verified.body.status === "paid") return afterPayment(panel, button, verified.body);
              // The webhook may still confirm it: keep watching the order instead of telling a payer "failed".
              say(panel, errorMessage(verified, T.stillConfirming), "error");
              var box = node("div", "pay-status"); panel.appendChild(box);
              poll(box, order.order_id, null);
            });
          },
          dismiss: function () {
            // UPI apps sometimes finish after the window is closed: ask the server once before saying "not completed".
            api("GET", "/api/payments/order/" + encodeURIComponent(order.order_id)).then(function (current) {
              trigger.disabled = false;
              if (current.ok && current.body && current.body.status === "paid") return afterPayment(panel, button, current.body);
              remember(null);
              say(panel, T.closed, "error");
            });
          }
        }));
        checkout.on("payment.failed", function (response) {
          var reason = response && response.error && response.error.description;
          say(panel, (reason ? reason + " " : "") + T.failed, "error");
        });
        say(panel, "");
        checkout.open();
      }).catch(function () {
        fail(T.blocked);
      });
    });
  }

  function openReportPanel(button, detail) {
    var panel = panelFor(button);
    if (panel.getAttribute("data-open") === "1") { var first = panel.querySelector("select"); if (first) first.focus(); return; }
    panel.setAttribute("data-open", "1");
    panel.innerHTML = "";
    var saved = null;
    try { saved = window.localStorage.getItem("report-language"); } catch (ignore) { /* default */ }
    saved = defaultReportLanguage(pageLang, saved);

    function field(id, labelText, control, hint) {
      var wrap = node("div", "pay__field"), label = node("label", null, labelText);
      label.setAttribute("for", id); control.id = id;
      wrap.appendChild(label); wrap.appendChild(control);
      if (hint) wrap.appendChild(node("span", "pay__hint", hint));
      panel.appendChild(wrap);
      return control;
    }

    var language = document.createElement("select");
    LANGUAGES.forEach(function (entry) {
      var option = node("option", null, entry[1]);
      option.value = entry[0];
      if (entry[0] === saved) option.selected = true;
      language.appendChild(option);
    });
    field("pay-language", T.language, language);
    var email = document.createElement("input"); email.type = "email"; email.autocomplete = "email"; email.maxLength = 120;
    email.required = true;
    field("pay-email", T.email, email, T.emailHint);
    // Second box, and deliberately NOT autofilled: the point is that it is typed again, so a browser
    // repeating the first one would confirm nothing.
    var emailConfirm = document.createElement("input");
    emailConfirm.type = "email"; emailConfirm.autocomplete = "off"; emailConfirm.maxLength = 120;
    emailConfirm.required = true;
    field("pay-email-confirm", T.emailConfirm, emailConfirm);
    var phone = document.createElement("input"); phone.type = "tel"; phone.autocomplete = "tel"; phone.inputMode = "numeric"; phone.maxLength = 16;
    field("pay-phone", T.phone, phone);

    var go = node("button", "btn btn--cta pay__go", T.pay.replace("{price}", detail.priceInr));
    go.type = "button";
    panel.appendChild(go);
    panel.appendChild(node("p", "pay__hint", T.methods.replace("{wait}", waitFor(detail.product))));
    go.addEventListener("click", function () {
      var form = { language: language.value, email: email.value, emailConfirm: emailConfirm.value,
                   phone: phone.value };
      var problems = validateForm(form, pageLang);
      if (problems.length) { say(panel, problems[0].message, "error"); (problems[0].field === "email" ? email : phone).focus(); return; }
      try { window.localStorage.setItem("report-language", language.value); } catch (ignore) { /* fine */ }
      pay(panel, button, detail, form, go);
    });
    language.focus();
  }

  if (enabled) {
    document.addEventListener("product:purchase", function (event) {
      var detail = event.detail || {}, button = event.target;
      if (!detail.product || !button || !button.getAttribute) return;
      event.preventDefault(); // payments are on: app.js must not show its "launching soon" note
      var notice = document.getElementById("cta-notice");
      if (notice) notice.hidden = true;
      if (isConsultation(detail.product)) {
        if (!detail.sessionId) return;
        pay(panelFor(button), button, detail, {}, button);
      } else if (detail.request) {
        openReportPanel(button, detail);
      }
    });

    // Came back after paying (tab closed during payment, UPI app switch ...): point to the order page.
    try {
      var pending = JSON.parse(window.localStorage.getItem(PENDING_KEY) || "null");
      if (pending && pending.order_id && Date.now() - pending.at < 24 * 3600 * 1000 && !orderBox) {
        api("GET", "/api/payments/order/" + encodeURIComponent(pending.order_id)).then(function (result) {
          if (!result.ok || !result.body || result.body.status !== "paid") { if (result.status === 404) remember(null); return; }
          remember(null);
          // a plain pack has nothing to download (chat.js shows the new balance by itself); the consultation purchase has its PDF
          if (!result.body.order_url || (result.body.kind === "pack" && !result.body.includes_report)) return;
          var main = document.getElementById("main"), banner = node("div", "wrap pay-banner");
          banner.setAttribute("role", "status");
          banner.appendChild(node("span", null, "Your payment for " + result.body.product_name + " was received. "));
          var link = node("a", null, "Open your order page");
          link.setAttribute("href", result.body.order_url);
          banner.appendChild(link);
          if (main) main.insertBefore(banner, main.firstChild);
        });
      } else if (pending && !orderBox) {
        remember(null);
      }
    } catch (ignore) { /* no storage */ }
  }
})(typeof window !== "undefined" ? window : globalThis);
