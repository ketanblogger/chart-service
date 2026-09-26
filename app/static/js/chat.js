/* AI consultation chat (the consultation page, in English / Hindi / Marathi). Two parts:
 *
 * 1. AstroChat - pure functions (no DOM, no fetch): state transitions and HTML for the conversation.
 *    Tested in an embedded V8 by tests/test_consultation_web.py and tests/test_render_i18n.py, like render.js.
 *    User-visible strings come from STRINGS[lang]; the DOM wiring takes lang from <html lang>.
 * 2. DOM wiring - runs only in a browser on a page that has #chat.
 *
 * Flow: app.js posts the birth form to /api/consultation/start and fires `tool:result`; this script
 * opens the chat with that response. Messages go to /api/consultation/message. HTTP 402 (or a reply
 * that leaves no messages) swaps the input for the paywall card, whose button fires the site-wide
 * cancelable `product:purchase` event (see app.js) with detail.sessionId.
 *
 * Phase 6: after a verified payment has been credited server-side (chat_store.credit_session), dispatch
 *   document.dispatchEvent(new CustomEvent("consultation:credited"))
 * and the chat reloads its quota and re-opens the input.
 *
 * Replies are plain text and are always inserted escaped.
 */
(function (root) {
  "use strict";

  var MAX_CHARS = 1000;

  // Every string the chat itself prints, per page language (<html lang>). English is the default. The AI's replies
  // come from the server in the user's language; API error messages are English, so hi / mr map them by code / status.
  var STRINGS = {
    en: {
      wait: "Please wait for the answer to your previous question.", used: "Your free questions are used.",
      empty: "Please type a question.", tooLong: "Please keep your question under {max} characters.",
      offline: "Could not reach the server. Please check your connection and try again.",
      expired: "This consultation has expired. Please start again.",
      server: "Something went wrong on our side. Please try again in a moment.",
      busy: "Your previous question is still being answered. Please wait a moment.",
      rateLimited: "Too many messages in a short time. Please wait a minute and try again.",
      unavailable: "The astrologer is not available right now. Please try again in a little while.",
      quotaBoth: "{free} free + {paid} paid questions left", quotaPaidOne: "{n} question left", quotaPaid: "{n} questions left",
      quotaFreeOne: "{n} free question left", quotaFree: "{n} free questions left",
      hint: "Namaste. Your chart is ready - ask your first question, in English, हिंदी or मराठी.",
      you: "You: ", astrologer: "Astrologer: "
    },
    hi: {
      wait: "कृपया अपने पिछले सवाल के उत्तर की प्रतीक्षा करें।", used: "आपके मुफ़्त सवाल पूरे हो गए हैं।",
      empty: "कृपया अपना सवाल लिखें।", tooLong: "कृपया अपना सवाल {max} अक्षरों से छोटा रखें।",
      offline: "सर्वर से संपर्क नहीं हो सका। कृपया इंटरनेट कनेक्शन जाँचकर फिर कोशिश करें।",
      expired: "यह परामर्श सत्र समाप्त हो गया है। कृपया फिर से शुरू करें।",
      server: "हमारी ओर से कुछ गड़बड़ी हुई। कृपया थोड़ी देर बाद फिर कोशिश करें।",
      busy: "आपके पिछले सवाल का उत्तर अभी लिखा जा रहा है। कृपया थोड़ा रुकें।",
      rateLimited: "कम समय में बहुत अधिक संदेश हो गए। कृपया एक मिनट रुककर फिर कोशिश करें।",
      unavailable: "ज्योतिषी अभी उपलब्ध नहीं है। कृपया थोड़ी देर बाद फिर कोशिश करें।",
      quotaBoth: "{free} मुफ़्त + {paid} खरीदे हुए सवाल बाकी", quotaPaidOne: "{n} सवाल बाकी", quotaPaid: "{n} सवाल बाकी",
      quotaFreeOne: "{n} मुफ़्त सवाल बाकी", quotaFree: "{n} मुफ़्त सवाल बाकी",
      hint: "नमस्ते। आपकी कुंडली तैयार है - अपना पहला सवाल पूछिए, हिंदी, मराठी या English में।",
      you: "आप: ", astrologer: "ज्योतिषी: "
    },
    mr: {
      wait: "कृपया आधीच्या प्रश्नाचे उत्तर येईपर्यंत थांबा.", used: "तुमचे मोफत प्रश्न संपले आहेत.",
      empty: "कृपया तुमचा प्रश्न लिहा.", tooLong: "कृपया तुमचा प्रश्न {max} अक्षरांपेक्षा लहान ठेवा.",
      offline: "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट जोडणी तपासून पुन्हा प्रयत्न करा.",
      expired: "हे सल्लासत्र संपले आहे. कृपया पुन्हा सुरुवात करा.",
      server: "आमच्याकडून काहीतरी चूक झाली. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
      busy: "तुमच्या आधीच्या प्रश्नाचे उत्तर अजून लिहिले जात आहे. कृपया थोडे थांबा.",
      rateLimited: "थोड्या वेळात खूप जास्त संदेश झाले. कृपया एक मिनिट थांबून पुन्हा प्रयत्न करा.",
      unavailable: "ज्योतिषी सध्या उपलब्ध नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
      quotaBoth: "{free} मोफत + {paid} सशुल्क प्रश्न शिल्लक", quotaPaidOne: "{n} प्रश्न शिल्लक", quotaPaid: "{n} प्रश्न शिल्लक",
      quotaFreeOne: "{n} मोफत प्रश्न शिल्लक", quotaFree: "{n} मोफत प्रश्न शिल्लक",
      hint: "नमस्कार. तुमची कुंडली तयार आहे - तुमचा पहिला प्रश्न विचारा, मराठी, हिंदी किंवा English मध्ये.",
      you: "तुम्ही: ", astrologer: "ज्योतिषी: "
    }
  };

  function langOf(value) {
    var code = String(value || "").slice(0, 2).toLowerCase();
    return code === "hi" || code === "mr" ? code : "en";
  }
  function strings(lang) { return STRINGS[langOf(lang)]; }
  function fill(template, values) {
    return template.replace(/\{(\w+)\}/g, function (whole, key) { return values[key] === undefined ? "" : values[key]; });
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  /** Session view from the API -> UI state. */
  function stateFromSession(view) {
    var quota = (view && view.quota) || { free_left: 0, paid_left: 0, messages_left: 0 };
    return {
      sessionId: view.session_id,
      messages: (view.messages || []).map(function (m) { return { role: m.role, content: m.content, kind: m.kind || "ai" }; }),
      quota: quota,
      paywall: view.paywall || (quota.messages_left <= 0 ? {} : null),
      pending: false,
      error: null
    };
  }

  /** null if the text can be sent, else a message for the user. lang: "en" (default) | "hi" | "mr". */
  function validateMessage(state, text, lang) {
    var trimmed = (text || "").trim(), S = strings(lang);
    if (state.pending) return S.wait;
    if (state.paywall) return S.used;
    if (!trimmed) return S.empty;
    if (trimmed.length > MAX_CHARS) return fill(S.tooLong, { max: MAX_CHARS });
    return null;
  }

  function withPending(state, text) {
    return assign(state, { pending: true, error: null, draft: text.trim(),
      messages: state.messages.concat([{ role: "user", content: text.trim(), kind: "pending" }]) });
  }

  /** Apply the HTTP result of POST /api/consultation/message. lang: "en" (default) | "hi" | "mr". */
  function applyResponse(state, status, body, lang) {
    var S = strings(lang), english = langOf(lang) === "en";
    var messages = state.messages.slice(), detail = (body && body.detail) || {};
    var last = messages[messages.length - 1];
    if (status === 200 && body && body.reply) {
      if (last && last.kind === "pending") last = messages[messages.length - 1] = { role: "user", content: last.content, kind: body.reply.kind };
      messages.push({ role: "assistant", content: body.reply.content, kind: body.reply.kind });
      return assign(state, { pending: false, error: null, draft: "", messages: messages, quota: body.quota,
        paywall: body.paywall || (body.quota && body.quota.messages_left <= 0 ? {} : null) });
    }
    if (last && last.kind === "pending") messages.pop(); // not delivered: the question goes back into the box
    if (status === 402) {
      return assign(state, { pending: false, error: null, messages: messages, paywall: detail,
        quota: { free_left: 0, paid_left: 0, messages_left: 0 } });
    }
    // The API words its errors in English: English pages show them, hi / mr pages show our wording for the same case.
    var message = english ? (typeof detail === "string" ? detail : detail.message) : null;
    if (!message) {
      message = status === 0 ? S.offline
        : status === 404 ? S.expired
        : status === 409 ? S.busy
        : status === 422 ? S.empty
        : status === 429 ? S.rateLimited
        : status === 502 || status === 503 ? S.unavailable
        : S.server;
    }
    return assign(state, { pending: false, error: message, messages: messages, expired: status === 404 });
  }

  /** After a send whose RESPONSE was lost: the state to show if the server recorded the exchange, else null.
   *
   * A network failure mid-send is not evidence that nothing happened. The route is synchronous, so a
   * disconnect does not cancel it: the server finishes, spends the message credit and stores both the
   * question and the reply. The browser sees only a failure, and the old behaviour - put the question back
   * in the box - then invites the reader to buy the same answer twice.
   *
   * `delivered` is the number of messages the session held BEFORE the pending question was appended, which
   * is the meaningful quantity: how much of this conversation the server had already recorded when we
   * asked. Measured, and stated because the first version of this comment claimed more: a recorded turn
   * adds TWO messages (the question and its reply) while withPending adds one, so passing the
   * post-pending length would ALSO recover, and the off-by-one is absorbed by that asymmetry. It is
   * therefore not load-bearing today - it is chosen because it does not depend on that coincidence, and
   * because "messages the session held before this send" is the thing the comparison is actually about.
   *
   * Conservative by design, because the two mistakes are not equal. A needless resend costs a credit the
   * reader chose to spend; a wrongly suppressed resend loses an answer they cannot get back. So only a
   * session we have positively seen to contain more than `delivered` messages suppresses the resend, and
   * every other outcome - the re-fetch failing, returning nothing new, or being unreadable - returns null
   * and the question goes back in the box. */
  function recoverFromSession(view, delivered) {
    if (!view || !view.session_id) return null;
    var recovered = stateFromSession(view);
    return recovered.messages.length > delivered ? recovered : null;
  }

  function quotaLabel(state, lang) {
    var q = state.quota || {}, S = strings(lang);
    if (state.paywall) return "";
    if (q.paid_left > 0 && q.free_left > 0) return fill(S.quotaBoth, { free: q.free_left, paid: q.paid_left });
    if (q.paid_left > 0) return fill(q.paid_left === 1 ? S.quotaPaidOne : S.quotaPaid, { n: q.paid_left });
    return fill(q.free_left === 1 ? S.quotaFreeOne : S.quotaFree, { n: q.free_left });
  }

  function messagesHtml(state, lang) {
    var S = strings(lang);
    if (!state.messages.length) {
      return '<li class="chat__msg chat__msg--assistant chat__msg--hint"><p>' + esc(S.hint) + "</p></li>";
    }
    return state.messages.map(function (m) {
      var paragraphs = String(m.content).split(/\n{2,}/).map(function (p) {
        return "<p>" + esc(p).replace(/\n/g, "<br>") + "</p>";
      }).join("");
      return '<li class="chat__msg chat__msg--' + (m.role === "user" ? "user" : "assistant") + '">' +
        '<span class="visually-hidden">' + esc(m.role === "user" ? S.you : S.astrologer) + "</span>" + paragraphs + "</li>";
    }).join("");
  }

  function assign(state, changes) {
    var next = {}, key;
    for (key in state) if (Object.prototype.hasOwnProperty.call(state, key)) next[key] = state[key];
    for (key in changes) if (Object.prototype.hasOwnProperty.call(changes, key)) next[key] = changes[key];
    return next;
  }

  root.AstroChat = {
    MAX_CHARS: MAX_CHARS,
    langOf: langOf,
    strings: strings,
    stateFromSession: stateFromSession,
    validateMessage: validateMessage,
    withPending: withPending,
    applyResponse: applyResponse,
    recoverFromSession: recoverFromSession,
    quotaLabel: quotaLabel,
    messagesHtml: messagesHtml
  };

  /* ---------- DOM wiring ---------- */

  if (typeof document === "undefined" || !document.getElementById("chat")) return;

  var C = root.AstroChat, R = root.AstroRender;
  var SESSION_KEY = "consultation-session";
  var lang = langOf(document.documentElement.getAttribute("lang")); // page language: en | hi | mr
  var resultEl = document.getElementById("result");
  var resultBody = document.getElementById("result-body");
  var log = document.getElementById("chat-log");
  var typing = document.getElementById("chat-typing");
  var errorEl = document.getElementById("chat-error");
  var chatForm = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var sendBtn = document.getElementById("chat-send");
  var quotaEl = document.getElementById("chat-quota");
  var paywallEl = document.getElementById("chat-paywall");
  // every tier offered on the paywall (basic, premium ...); the first one also carries id="chat-buy"
  var buyBtns = paywallEl ? paywallEl.querySelectorAll("[data-product]") : [];
  var resetBtn = document.getElementById("chat-reset");
  var startCard = document.getElementById("chat-start");
  var state = null;

  function store(action, value) {
    try {
      if (action === "set") root.sessionStorage.setItem(SESSION_KEY, value);
      else if (action === "clear") root.sessionStorage.removeItem(SESSION_KEY);
      else return root.sessionStorage.getItem(SESSION_KEY);
    } catch (ignore) { /* storage unavailable: the chat still works, it just is not restored on reload */ }
    return null;
  }

  function render(focusInput) {
    log.innerHTML = C.messagesHtml(state, lang);
    typing.hidden = !state.pending;
    errorEl.hidden = !state.error;
    errorEl.textContent = state.error || "";
    var locked = Boolean(state.paywall);
    chatForm.hidden = locked;
    paywallEl.hidden = !locked;
    quotaEl.textContent = C.quotaLabel(state, lang);
    quotaEl.hidden = locked;
    sendBtn.disabled = state.pending;
    input.readOnly = state.pending;
    // pay.js needs the session on whichever tier is pressed: a purchase credits THIS conversation
    Array.prototype.forEach.call(buyBtns, function (button) { button.setAttribute("data-session-id", state.sessionId); });
    var lastMessage = log.lastElementChild;
    if (lastMessage && lastMessage.scrollIntoView) lastMessage.scrollIntoView({ block: "nearest" });
    if (focusInput && !locked && !state.pending) input.focus({ preventScroll: true });
  }

  function open(view, focusInput) {
    state = C.stateFromSession(view);
    store("set", state.sessionId);
    startCard.hidden = true;
    resultEl.hidden = false;
    render(focusInput);
  }

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (json) {
        return { status: response.status, body: json };
      });
    }).catch(function () { return { status: 0, body: null }; });
  }

  function reload() {
    var sessionId = state ? state.sessionId : store("get");
    if (!sessionId) return;
    api("GET", "/api/consultation/session/" + encodeURIComponent(sessionId)).then(function (result) {
      if (result.status === 200 && result.body) {
        resultBody.innerHTML = R.renderers.consultation(result.body, { lang: lang });
        open(result.body, false);
      } else if (result.status === 404) {
        store("clear");
      }
    });
  }

  // A new consultation was started through the birth form (app.js rendered the chart header already).
  document.addEventListener("tool:result", function (event) {
    if (event.detail && event.detail.response && event.detail.response.session_id) open(event.detail.response, true);
  });

  // Phase 6 payment script: fire this after the pack has been credited on the server.
  document.addEventListener("consultation:credited", reload);

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value, problem = C.validateMessage(state, text, lang);
    if (problem) { state.error = problem; render(true); return; }
    // Counted BEFORE withPending appends the pending question - see recoverFromSession.
    var delivered = state.messages.length;
    var sessionId = state.sessionId;
    state = C.withPending(state, text);
    input.value = "";
    render(false);
    api("POST", "/api/consultation/message", { session_id: sessionId, message: text.trim() }).then(function (result) {
      var draft = state.draft;
      // status 0 is the network itself failing, which is the ONE case where the server may have done the
      // work we did not hear about. Ask it before telling the reader nothing was delivered.
      if (result.status === 0) {
        api("GET", "/api/consultation/session/" + encodeURIComponent(sessionId)).then(function (reread) {
          var recovered = reread.status === 200 ? C.recoverFromSession(reread.body, delivered) : null;
          if (recovered) {
            state = recovered;          // the answer they already paid for, rather than an invitation to pay again
          } else {
            state = C.applyResponse(state, 0, null, lang);
            input.value = draft || "";
          }
          render(true);
        });
        return;
      }
      state = C.applyResponse(state, result.status, result.body, lang);
      if (state.error || (result.status === 402)) input.value = draft || ""; // nothing was delivered: keep the question
      if (state.expired) store("clear");
      render(true);
    });
  });

  // Enter sends, Shift+Enter makes a new line (desktop); on phones the keyboard's send key submits.
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (chatForm.requestSubmit) chatForm.requestSubmit(); else sendBtn.click();
    }
  });

  resetBtn.addEventListener("click", function () {
    store("clear");
    state = null;
    resultEl.hidden = true;
    startCard.hidden = false;
    startCard.scrollIntoView({ block: "start" });
  });

  reload(); // restore the conversation after a page reload
})(typeof window !== "undefined" ? window : globalThis);
