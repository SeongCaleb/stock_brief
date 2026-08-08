"""Naver SMTP 발송 + 다이제스트 HTML 조립."""
import smtplib
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from html import escape

from config import MAIL_TO, NAVER_PASS, NAVER_USER, SMTP_HOST, SMTP_PORT

KST = timezone(timedelta(hours=9))

# 섹션 헤더로 인식할 이모지 (헤드라인 제외). 굵게 렌더링.
SECTION_EMOJIS = ("⚖️", "📊", "🛢️", "📈", "🎯", "🧭", "💾", "💰", "📉", "🏭", "⚡", "🔋", "🛒")


def block_html(source, market, link, digest_text):
    """LLM이 만든 텍스트 블록을 카드형 HTML로 변환."""
    out = []
    seen_headline = False
    for raw in digest_text.splitlines():
        line = raw.strip()
        if not line:
            out.append("<div style='height:8px;'></div>")
            continue
        if line.startswith("출처"):          # 출처는 카드 상단에 이미 표시
            continue
        if not seen_headline:                  # 첫 줄 = 헤드라인
            out.append(
                f"<div style='font-size:16px;font-weight:700;color:#111827;margin:2px 0 8px;line-height:1.5;'>{escape(line)}</div>"
            )
            seen_headline = True
            continue
        if line.startswith("- "):              # 불릿: 긴 문장도 깔끔히 접히도록 hanging indent
            out.append(
                "<div style='margin:4px 0;padding-left:16px;text-indent:-16px;"
                f"color:#374151;line-height:1.6;'>•&nbsp;{escape(line[2:])}</div>"
            )
        elif any(line.startswith(e) for e in SECTION_EMOJIS):  # 섹션 헤더
            out.append(
                f"<div style='margin:14px 0 4px;font-weight:600;color:#111827;line-height:1.55;'>{escape(line)}</div>"
            )
        else:                                  # 리드/본문 문장
            out.append(
                f"<div style='margin:6px 0;color:#111827;line-height:1.7;'>{escape(line)}</div>"
            )
    inner = "\n".join(out)
    tag = "🇺🇸 미국"
    src = (
        f"<a href='{escape(link)}' style='color:#6b7280;text-decoration:none;'>{escape(source)} ↗</a>"
        if link else escape(source)
    )
    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;margin:14px 0;background:#fff;">
      <div style="font-size:12px;color:#9ca3af;margin-bottom:10px;">{tag} · {src}</div>
      <div style="font-size:15px;">{inner}</div>
    </div>
    """


def build_email(blocks):
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    body = "\n".join(blocks)
    html = f"""
    <div style="max-width:680px;margin:0 auto;padding:8px;font-family:-apple-system,'Apple SD Gothic Neo',system-ui,sans-serif;background:#f9fafb;">
      <h2 style="font-size:20px;color:#111827;margin:4px 0;">📈 오늘의 증시 브리핑 · {date_str}</h2>
      <div style="font-size:12px;color:#9ca3af;margin-bottom:6px;">Axios Smart Brevity 스타일 · 미국 증시</div>
      {body}
      <div style="font-size:11px;color:#9ca3af;margin:18px 4px;">본 요약과 '관심 포인트'는 기사에서 도출된 참고 정보이며, 특정 종목의 매수·매도 추천이나 투자 자문이 아닙니다.</div>
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
