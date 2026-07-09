"""MinutesResult を日英バイリンガル議事録 Markdown / Slack Block Kit に整形する。"""

from __future__ import annotations

from .models import ActionItem, MinutesResult, Summary


def _action_item_line(item: ActionItem, lang: str = "ja") -> str:
    owner_label, due_label = ("担当", "期限") if lang == "ja" else ("Owner", "Due")
    parts = [item.description]
    if item.assignee:
        parts.append(f"（{owner_label}: {item.assignee}）")
    if item.due:
        parts.append(f"（{due_label}: {item.due}）")
    return "".join(parts)


def _summary_section(summary: Summary, heading_lang: str = "ja") -> list[str]:
    h = {
        "ja": ("概要", "要点", "決定事項", "アクションアイテム"),
        "en": ("Overview", "Key Points", "Decisions", "Action Items"),
    }[heading_lang]
    lines: list[str] = []
    if summary.overview:
        lines += [f"### {h[0]}", "", summary.overview, ""]
    if summary.key_points:
        lines += [f"### {h[1]}", ""] + [f"- {p}" for p in summary.key_points] + [""]
    if summary.decisions:
        lines += [f"### {h[2]}", ""] + [f"- {d}" for d in summary.decisions] + [""]
    if summary.action_items:
        lines += [f"### {h[3]}", ""] + [
            f"- [ ] {_action_item_line(item, heading_lang)}" for item in summary.action_items
        ] + [""]
    return lines


def to_markdown(result: MinutesResult) -> str:
    lines = [
        f"# 議事録 / Meeting Minutes — {result.source_file}",
        "",
        f"作成日時: {result.created_at:%Y-%m-%d %H:%M:%S}",
        "",
        "## 🇯🇵 日本語",
        "",
    ]
    lines += _summary_section(result.summary, "ja")

    if result.summary_en:
        lines += ["## 🇺🇸 English", ""]
        lines += _summary_section(result.summary_en, "en")

    lines += ["## 全文文字起こし / Full Transcript", ""]
    if result.transcript.segments:
        for seg in result.transcript.segments:
            speaker = f"**{seg.speaker}**: " if seg.speaker else ""
            lines.append(f"{speaker}{seg.text}")
            lines.append("")
    else:
        lines += [result.transcript.text, ""]

    if result.full_translation:
        lines += ["## Full Transcript (English)", "", result.full_translation, ""]

    return "\n".join(lines)


def to_slack_blocks(result: MinutesResult) -> list[dict]:
    """Slack Block Kit 形式。要約とアクションアイテムに絞る（全文はMarkdownファイル側）。"""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📝 議事録: {result.source_file}", "emoji": True},
        }
    ]
    if result.summary.overview:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*概要*\n{result.summary.overview}"}}
        )
    if result.summary.decisions:
        decisions = "\n".join(f"• {d}" for d in result.summary.decisions)
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*決定事項*\n{decisions}"}}
        )
    if result.summary.action_items:
        items = "\n".join(f"☐ {_action_item_line(i)}" for i in result.summary.action_items)
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*アクションアイテム*\n{items}"}}
        )
    if result.summary_en and result.summary_en.overview:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Overview (EN)*\n{result.summary_en.overview}"},
            }
        )
    return blocks
