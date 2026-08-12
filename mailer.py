"""Naver SMTP 발송 + 컴팩트 다이제스트 HTML 조립 (신호 색상 + 한눈에 보기)."""
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from html import escape

from config import MAIL_TO, NAVER_PASS, NAVER_USER, SMTP_HOST, SMTP_PORT

KST = timezone(timedelta(hours=9))

# 신호별 색상
SIGNAL_COLOR = {"강세": "#059669", "약세": "#dc2626", "주의": "#d97706", "중립": "#6b7280"}
SIGNAL_EMOJI = {"강세": "📈", "약세": "📉", "주의": "⚠️", "중립": "➡️"}
_SIG_PREFIX = ("📈", "📉", "⚠️", "➡️")


def glance_html(picks):
    """상단 '한눈에 보기': 국기 + 신호 배지 + 한글 헤드라인 한 줄씩."""
    rows = []
    for a in picks:
        sig = a.get("signal", "중립")
        color = SIGNAL_COLOR.get(sig, "#6b7280")
        emoji = SIGNAL_EMOJI.get(sig, "➡️")
        flag = "🇰🇷" if a.get("market") == "KR" else "🇺🇸"
        title = a.get("ko_title") or a.get("title", "")
        rows.append(
            "<div style='margin:5px 0;font-size:13px;line-height:1.5;'>"
            f"<span style='margin-right:4px;'>{flag}</span>"
            f"<span style='display:inline-block;min-width:52px;color:{color};font-weight:700;'>{emoji} {escape(sig)}</span>"
            f"<span style='color:#374151;'>{escape(title)}</span></div>"
        )
    inner = "\n".join(rows)
    return (
        "<div style='border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;margin:14px 0;background:#fff;'>"
        "<div style='font-size:13px;font-weight:700;color:#111827;margin-bottom:8px;'>🔑 오늘 꼭 볼 뉴스</div>"
        f"{inner}</div>"
    )


def block_html(source, market, link, brief_text):
    """3줄 브리핑을 컴팩트 카드로. 첫 줄(신호·헤드라인) 강조, 🎯 메타는 muted."""
    flag = "🇰🇷" if market == "KR" else "🇺🇸"
    out = []
    for raw in brief_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(_SIG_PREFIX):  # 신호 + 헤드라인
            sig = next((s for s in SIGNAL_COLOR if s in line[:6]), "중립")
            color = SIGNAL_COLOR.get(sig, "#111827")
            out.append(
                f"<div style='font-size:15px;font-weight:700;color:{color};margin:0 0 6px;line-height:1.5;'>{escape(line)}</div>"
            )
        elif line.startswith("🎯"):  # 메타(섹터/종목/포인트)
            out.append(
                f"<div style='font-size:12px;color:#6b7280;margin:6px 0 0;line-height:1.55;'>{escape(line)}</div>"
            )
        else:  # 요약 문장
            out.append(
                f"<div style='font-size:13px;color:#374151;margin:0;line-height:1.6;'>{escape(line)}</div>"
            )
    src = (
        f"<a href='{escape(link)}' style='color:#9ca3af;text-decoration:none;font-size:11px;'>{flag} {escape(source)} ↗</a>"
        if link else f"<span style='color:#9ca3af;font-size:11px;'>{flag} {escape(source)}</span>"
    )
    return (
        "<div style='border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;margin:10px 0;background:#fff;'>"
        f"{''.join(out)}"
        f"<div style='margin-top:8px;'>{src}</div></div>"
    )


def build_email(glance, blocks):
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    body = "\n".join(blocks)
    html = f"""
    <div style="max-width:640px;margin:0 auto;padding:8px;font-family:-apple-system,'Apple SD Gothic Neo',system-ui,sans-serif;background:#f9fafb;">
      <h2 style="font-size:19px;color:#111827;margin:4px 0;">📈 오늘의 증시 브리핑 · {date_str}</h2>
      <div style="font-size:12px;color:#9ca3af;margin-bottom:4px;">미국 증시 · 꼭 알아야 할 뉴스만</div>
      {glance}
      {body}
      <div style="font-size:11px;color:#9ca3af;margin:16px 4px;">신호(강세/약세/주의/중립)는 기사가 시사하는 방향을 나타낼 뿐, 특정 종목의 매수·매도 추천이나 투자 자문이 아닙니다.</div>
    </div>
    """
    return date_str, html


def send(subject, html):
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = NAVER_USER
    msg["To"] = MAIL_TO
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.login(NAVER_USER, NAVER_PASS)
        s.sendmail(NAVER_USER, [MAIL_TO], msg.as_string())
