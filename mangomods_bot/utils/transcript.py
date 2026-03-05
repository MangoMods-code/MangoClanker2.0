from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Iterable

import discord

def _fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def build_html_transcript(
    *,
    guild: discord.Guild,
    channel: discord.TextChannel,
    messages: Iterable[discord.Message],
    website_url: str,
    ticket_title: str,
) -> str:
    """
    Simple, clean HTML transcript including: usernames, avatars, timestamps, message content, attachments.
    """
    css = """
    body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif; background:#0b0f14; color:#e6edf3; margin:0; }
    header { padding:20px; background:#111826; border-bottom:1px solid #263043; }
    header h1 { margin:0 0 6px 0; font-size:18px; }
    header .meta { opacity:.85; font-size:13px; }
    a { color:#7cc4ff; text-decoration:none; }
    .wrap { padding:16px; max-width:1000px; margin:0 auto; }
    .msg { display:flex; gap:12px; padding:10px 8px; border-bottom:1px solid #1c2533; }
    .av { width:40px; height:40px; border-radius:999px; }
    .who { font-weight:700; font-size:14px; }
    .when { opacity:.7; font-size:12px; margin-left:8px; }
    .content { white-space:pre-wrap; line-height:1.35; font-size:14px; }
    .attachments { margin-top:6px; font-size:12px; opacity:.9; }
    .badge { display:inline-block; padding:2px 8px; border:1px solid #263043; border-radius:999px; font-size:12px; opacity:.9; margin-left:8px;}
    """

    header = f"""
    <header>
      <h1>{html.escape(ticket_title)}</h1>
      <div class="meta">
        Server: {html.escape(guild.name)} &nbsp;•&nbsp;
        Channel: #{html.escape(channel.name)} &nbsp;•&nbsp;
        Exported: {html.escape(_fmt_ts(datetime.now(timezone.utc)))} &nbsp;•&nbsp;
        Website: <a href="{html.escape(website_url)}">{html.escape(website_url)}</a>
      </div>
    </header>
    """

    rows = []
    for m in messages:
        author = m.author
        av = getattr(author.display_avatar, "url", "")
        name = getattr(author, "display_name", str(author))
        ts = _fmt_ts(m.created_at)

        content = m.content or ""
        # Include embed summaries if message has no plain content:
        if not content and m.embeds:
            parts = []
            for e in m.embeds:
                t = e.title or ""
                d = e.description or ""
                if t or d:
                    parts.append(f"[EMBED] {t}\n{d}".strip())
            content = "\n\n".join(parts)

        safe_content = html.escape(content)

        attach_lines = []
        for a in m.attachments:
            attach_lines.append(f'<div>📎 <a href="{html.escape(a.url)}">{html.escape(a.filename)}</a></div>')
        attach_html = ""
        if attach_lines:
            attach_html = f'<div class="attachments">{"".join(attach_lines)}</div>'

        bot_badge = ""
        if author.bot:
            bot_badge = '<span class="badge">BOT</span>'

        rows.append(f"""
        <div class="msg">
          <img class="av" src="{html.escape(av)}" alt="avatar" />
          <div>
            <div><span class="who">{html.escape(name)}</span>{bot_badge}<span class="when">{html.escape(ts)}</span></div>
            <div class="content">{safe_content}</div>
            {attach_html}
          </div>
        </div>
        """)

    body = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{html.escape(ticket_title)}</title>
      <style>{css}</style>
    </head>
    <body>
      {header}
      <div class="wrap">
        {''.join(rows)}
      </div>
    </body>
    </html>
    """
    return body