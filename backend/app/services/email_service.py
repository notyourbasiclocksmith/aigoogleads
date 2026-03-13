"""
Email service using SendGrid.

Provides:
  - send_email()          — low-level: send any email via SendGrid
  - send_tenant_alert()   — high-level: send notification respecting tenant prefs
"""
import logging
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    plain_text: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: str = "IgniteAds AI",
) -> Dict[str, Any]:
    """Send an email via SendGrid."""
    api_key = settings.EMAIL_PROVIDER_KEY
    if not api_key:
        logger.warning("email_skip: EMAIL_PROVIDER_KEY not set")
        return {"success": False, "error": "EMAIL_PROVIDER_KEY not configured"}
    if not to_email:
        return {"success": False, "error": "No recipient email"}

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email or settings.EMAIL_FROM, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_text or subject},
            {"type": "text/html", "value": html_body},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SENDGRID_API_URL, json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
        if resp.status_code in (200, 201, 202):
            logger.info(f"email_sent: to={to_email} subject={subject}")
            return {"success": True}
        err = resp.text[:300]
        logger.error(f"email_failed: status={resp.status_code} body={err}")
        return {"success": False, "error": f"SendGrid {resp.status_code}: {err}"}
    except Exception as e:
        logger.error(f"email_exception: {e}")
        return {"success": False, "error": str(e)}


def _wrap_html(title: str, body_html: str) -> str:
    return (
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;">'
        f'<div style="background:linear-gradient(135deg,#1e293b,#334155);color:#fff;padding:24px 28px;border-radius:8px 8px 0 0;">'
        f'<h2 style="margin:0;font-size:18px;">{title}</h2></div>'
        f'<div style="padding:24px 28px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">'
        f'{body_html}'
        f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">'
        f'<p style="font-size:11px;color:#94a3b8;">Sent by IgniteAds AI &bull; '
        f'<a href="{settings.APP_URL}/settings" style="color:#3b82f6;">Manage preferences</a></p>'
        f'</div></div>'
    )


def build_alert_html(alert_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> str:
    icons = {"budget": "💰", "campaign_error": "🚨", "recommendation": "💡", "wasted_spend": "⚠️", "performance": "📊"}
    icon = icons.get(alert_type, "🔔")
    body = f'<p style="font-size:15px;line-height:1.6;color:#334155;">{icon} {message}</p>'
    if details:
        body += '<table style="width:100%;border-collapse:collapse;margin:12px 0;">'
        for k, v in details.items():
            body += (
                f'<tr><td style="padding:6px 8px;font-size:13px;color:#64748b;border-bottom:1px solid #f1f5f9;font-weight:600;">{k}</td>'
                f'<td style="padding:6px 8px;font-size:13px;color:#334155;border-bottom:1px solid #f1f5f9;">{v}</td></tr>'
            )
        body += '</table>'
    return _wrap_html(f"Alert: {alert_type.replace('_', ' ').title()}", body)


def build_weekly_report_html(business_name: str, period: str, metrics: Dict[str, Any], highlights: List[str]) -> str:
    body = f'<p style="font-size:14px;color:#64748b;margin:0 0 16px;">Performance for <strong>{business_name}</strong> — {period}</p>'
    body += '<table style="width:100%;border-collapse:collapse;margin:0 0 16px;">'
    for k, v in metrics.items():
        body += (
            f'<tr><td style="padding:10px 12px;font-size:14px;color:#64748b;border-bottom:1px solid #f1f5f9;">{k}</td>'
            f'<td style="padding:10px 12px;font-size:16px;font-weight:600;color:#1e293b;border-bottom:1px solid #f1f5f9;text-align:right;">{v}</td></tr>'
        )
    body += '</table>'
    if highlights:
        body += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px 16px;">'
        for h in highlights:
            body += f'<p style="font-size:13px;color:#15803d;margin:4px 0;">✓ {h}</p>'
        body += '</div>'
    body += f'<p style="margin:16px 0 0;"><a href="{settings.APP_URL}/dashboard" style="display:inline-block;background:#3b82f6;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;">View Dashboard →</a></p>'
    return _wrap_html("📊 Weekly Performance Report", body)


async def get_tenant_notification_prefs(db, tenant_id: str) -> Dict[str, Any]:
    """Read notification prefs from BusinessProfile.constraints_json."""
    from sqlalchemy import select
    from app.models.business_profile import BusinessProfile
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id))
    profile = result.scalar_one_or_none()
    if not profile:
        return {}
    n = (profile.constraints_json or {}).get("notifications", {})
    return {
        "notification_email": n.get("notification_email", ""),
        "email_alerts": n.get("email_alerts", True),
        "weekly_report": n.get("weekly_report", True),
        "recommendation_alerts": n.get("recommendation_alerts", True),
        "budget_alerts": n.get("budget_alerts", True),
    }


async def send_tenant_alert(
    db, tenant_id: str, alert_type: str, message: str, details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send alert email to tenant, respecting their prefs. alert_type: email_alerts|recommendation_alerts|budget_alerts"""
    prefs = await get_tenant_notification_prefs(db, tenant_id)
    email = prefs.get("notification_email")
    if not email:
        return {"success": False, "error": "No notification email set"}
    if not prefs.get(alert_type, True):
        return {"success": False, "error": f"{alert_type} disabled by user"}
    html = build_alert_html(alert_type, message, details)
    subject = f"[IgniteAds] {alert_type.replace('_', ' ').title()}: {message[:80]}"
    return await send_email(to_email=email, subject=subject, html_body=html, plain_text=message)


async def send_tenant_weekly_report(
    db, tenant_id: str, business_name: str, period: str, metrics: Dict[str, Any], highlights: List[str],
) -> Dict[str, Any]:
    """Send weekly report email if tenant has weekly_report enabled."""
    prefs = await get_tenant_notification_prefs(db, tenant_id)
    email = prefs.get("notification_email")
    if not email:
        return {"success": False, "error": "No notification email set"}
    if not prefs.get("weekly_report", True):
        return {"success": False, "error": "weekly_report disabled by user"}
    html = build_weekly_report_html(business_name, period, metrics, highlights)
    return await send_email(to_email=email, subject=f"[IgniteAds] Weekly Report — {business_name}", html_body=html)
