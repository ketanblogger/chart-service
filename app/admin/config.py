"""Admin dashboard settings. Every one is an environment variable with a default, like app/ai/config.py.

| Env var | Default | Meaning |
|---|---|---|
| `ADMIN_USER` | `admin` | HTTP basic auth user name |
| `ADMIN_PASSWORD` | - | HTTP basic auth password. **Empty = /admin is closed** (401 to everyone) |
| `ADMIN_SESSION_HOURS` | `12` | How long one signed admin session cookie is accepted |
| `ADMIN_LOGIN_MAX_FAILURES` | `5` | Failed logins from one network before it is locked out |
| `ADMIN_LOGIN_WINDOW_MINUTES` | `15` | The window those failures are counted in, and the length of the lockout |
| `ADMIN_LOGIN_MAX_FAILURES_ALL` | `30` | Failed logins from ALL networks together before everyone is locked out |
| `PAYMENT_FEE_PERCENT` | `2.0` | Razorpay's percentage of a domestic payment |
| `PAYMENT_FEE_GST_PERCENT` | `18.0` | GST charged on that fee (so the default effective rate is 2.36%) |
| `AI_DAILY_LIMIT_INR` | `300` | Daily AI spend that raises an alert |
| `ALERT_COST_LIMIT_BOOK_INR` | `150` | A detailed book that costs more than this raises an alert |
| `ALERT_COST_LIMIT_REPORT_INR` | `40` | A simple report that costs more than this raises an alert |
| `ALERT_READY_MINUTES` | `15` | A paid order still not ready this long after payment raises an alert |
| `ALERT_5XX_IN_10_MIN` | `5` | Server errors in ten minutes that raise an alert |
| `ALERT_EMAIL_TO` | `SUPPORT_EMAIL` | Where alerts and the digest are sent (app/mailer.py does the sending) |
| `ADMIN_ERROR_CAPTURE` | `1` | `0` turns off the logging handler that records errors for the health page |
| `ADMIN_ALERTS_ON_VIEW` | `1` | `0` = opening the overview only DISPLAYS the alerts; delivery is then whatever calls `python -m app.admin.alerts` |
| `ADMIN_SMOKE_MARKER` | `var/smoke-check.log` | File whose mtime is shown as "last smoke check" |

WHY THE FEE IS TWO NUMBERS AND NOT ONE. The margin has to be a figure the operator can act on, and the
real per-payment fee only exists in Razorpay's settlement report, which this app does not import. So the
fee here is MODELLED: percentage plus the GST charged on it. Every page that shows it says so, because a
modelled fee presented as a measured one is the kind of number that gets believed and then budgeted on.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdminSettings:
    user: str
    password: str
    session_hours: float
    login_max_failures: int
    login_window_minutes: int
    login_max_failures_all: int
    payment_fee_percent: float
    payment_fee_gst_percent: float
    ai_daily_limit_inr: float
    cost_limit_book_inr: float
    cost_limit_report_inr: float
    ready_minutes: float
    errors_in_10_min: int
    alert_email_to: str
    error_capture: bool
    alerts_on_view: bool
    smoke_marker: str

    @property
    def configured(self) -> bool:
        """False = nobody can sign in. A dashboard with a default password is worse than no dashboard: it
        reads as protected while publishing every order on the site, so an unset password closes the door
        rather than opening it with a guessable key."""
        return bool(self.password)

    @property
    def fee_rate(self) -> float:
        """Fraction of a payment that the gateway keeps, GST on the fee included."""
        return self.payment_fee_percent / 100 * (1 + self.payment_fee_gst_percent / 100)


def get_admin_settings() -> AdminSettings:
    """Read at call time, not import time, so tests and a restart-free config change both work."""
    from app.web import site  # loads .env, and holds the support address the alerts default to

    return AdminSettings(
        user=os.getenv("ADMIN_USER", "admin").strip() or "admin",
        password=os.getenv("ADMIN_PASSWORD", "").strip(),
        session_hours=float(os.getenv("ADMIN_SESSION_HOURS", "12")),
        login_max_failures=max(1, int(os.getenv("ADMIN_LOGIN_MAX_FAILURES", "5"))),
        login_window_minutes=max(1, int(os.getenv("ADMIN_LOGIN_WINDOW_MINUTES", "15"))),
        login_max_failures_all=max(1, int(os.getenv("ADMIN_LOGIN_MAX_FAILURES_ALL", "30"))),
        payment_fee_percent=float(os.getenv("PAYMENT_FEE_PERCENT", "2.0")),
        payment_fee_gst_percent=float(os.getenv("PAYMENT_FEE_GST_PERCENT", "18.0")),
        ai_daily_limit_inr=float(os.getenv("AI_DAILY_LIMIT_INR", "300")),
        cost_limit_book_inr=float(os.getenv("ALERT_COST_LIMIT_BOOK_INR", "150")),
        cost_limit_report_inr=float(os.getenv("ALERT_COST_LIMIT_REPORT_INR", "40")),
        ready_minutes=float(os.getenv("ALERT_READY_MINUTES", "15")),
        errors_in_10_min=max(1, int(os.getenv("ALERT_5XX_IN_10_MIN", "5"))),
        alert_email_to=os.getenv("ALERT_EMAIL_TO", "").strip() or site.SUPPORT_EMAIL,
        error_capture=os.getenv("ADMIN_ERROR_CAPTURE", "1").strip() != "0",
        alerts_on_view=os.getenv("ADMIN_ALERTS_ON_VIEW", "1").strip() != "0",
        smoke_marker=os.getenv("ADMIN_SMOKE_MARKER", "var/smoke-check.log"),
    )
