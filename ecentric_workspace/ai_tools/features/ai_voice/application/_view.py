# Copyright (c) 2026, eCentric and contributors
"""Rut gon ban ghi cho trang /ai-voice (khong lo truong noi bo / token)."""

JOB_KEYS = ("name", "title", "voice_label", "voice_key", "quality", "speed", "language", "status", "progress",
            "position", "chars", "seconds", "gen_seconds", "error", "owner", "creation", "submitted_at",
            "finished_at", "cancel_requested")


def job(row, with_text=False):
    if not row:
        return None
    d = {k: row.get(k) for k in JOB_KEYS}
    d["has_audio"] = bool(row.get("audio_file"))
    if with_text:
        d["text"] = row.get("text") or ""
    return d


def profile(row, manager=False):
    if not row:
        return None
    d = {k: row.get(k) for k in ("name", "voice_id", "voice_name", "gender", "description", "brand", "restricted",
                                 "status", "owner_user", "clip_seconds", "missing_on_server")}
    d["has_consent"] = bool(row.get("consent_by") and row.get("consent_date"))
    if manager:
        d.update({k: row.get(k) for k in ("source", "consent_by", "consent_date", "consent_note", "consent_file",
                                          "ref_text", "upload_error", "last_synced", "creation")})
    return d
