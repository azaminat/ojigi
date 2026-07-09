"""Translator API（翻訳）クライアント。

制約: 英語との双方向のみ / Fast は 4,000文字・単一ターゲット言語。
"""

from __future__ import annotations

from .base import BaseClient

_FAST_CHAR_LIMIT = 4000


class TranslatorClient(BaseClient):
    api_name = "translator"

    def translate(self, text: str, source: str = "ja", target: str = "en") -> str:
        """長文は段落単位で4,000文字以内のチャンクに分割して翻訳する。"""
        chunks = self._split(text, _FAST_CHAR_LIMIT)
        return "\n\n".join(self._translate_chunk(c, source, target) for c in chunks if c.strip())

    def translate_batch(self, texts: list[str], source: str = "ja", target: str = "en") -> list[str]:
        """短文リストを個別に翻訳する（結合すると行対応が崩れるため1件ずつ投げる）。"""
        return [self._translate_chunk(t, source, target) if t.strip() else "" for t in texts]

    def _translate_chunk(self, text: str, source: str, target: str) -> str:
        src, tgt = _to_locale(source), _to_locale(target)
        data = self._request(
            "POST",
            "/aiservices/translator/translate",
            json={"text": text, "config": {"source_language": src, "target_languages": [tgt]}},
        )
        translations = (data.get("result") or {}).get("translations") or {}
        return translations.get(tgt, "")

    @staticmethod
    def _split(text: str, limit: int) -> list[str]:
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        current = ""
        for para in text.split("\n"):
            if len(current) + len(para) + 1 > limit:
                if current:
                    chunks.append(current)
                # 1段落が上限を超える場合はさらに文字数で強制分割
                while len(para) > limit:
                    chunks.append(para[:limit])
                    para = para[limit:]
                current = para
            else:
                current = f"{current}\n{para}" if current else para
        if current:
            chunks.append(current)
        return chunks


# ロケールは完全な BCP-47 形式が必須（"ja" は 400 になる）
_LOCALES = {
    "ja": "ja-JP",
    "en": "en-US",
    "zh": "zh-CN",
    "ko": "ko-KR",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "pt": "pt-BR",
    "it": "it-IT",
}


def _to_locale(lang: str) -> str:
    return _LOCALES.get(lang, lang)
