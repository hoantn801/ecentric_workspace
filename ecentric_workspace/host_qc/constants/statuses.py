# Copyright (c) 2026, eCentric and contributors
"""Trang thai / gia tri chon cua Host QC - dung Enum, khong dung chuoi roi."""
from enum import Enum


class SessionStatus(str, Enum):
    DRAFT = "Draft"
    READY = "Ready"
    RUNNING = "Running"
    CLOSED = "Closed"
    CANCELLED = "Cancelled"


class Review(str, Enum):
    PENDING = "Pending"
    NEED_REVIEW = "Need Review"
    VALID = "Valid Violation"
    FALSE_POSITIVE = "False Positive"


class Severity(str, Enum):
    MINOR = "Minor"
    MAJOR = "Major"
    CRITICAL = "Critical"


class Color(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ClipStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"      # da luu tam tren ERP, cho day SharePoint (dot 2)
    UPLOADED = "uploaded"
    FAILED = "failed"
    EXPIRED = "expired"


class SessionSource(str, Enum):
    PLANNED = "planned"
    UNPLANNED = "unplanned"


class AlertReason(str, Enum):
    MINOR = "minor_threshold"
    MAJOR = "major_threshold"
    CRITICAL = "critical"
    OFFLINE = "machine_offline"
    LOAD = "load_reduced"


REVIEWS = tuple(r.value for r in Review)
SEVERITIES = tuple(s.value for s in Severity)
APP_SET_REVIEWS = (Review.PENDING.value, Review.NEED_REVIEW.value)   # app chi duoc dat luc tao loi
