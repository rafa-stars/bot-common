"""Engagement-to-curation feedback loop utilities.

Provides functions to:
1. Calculate attribute-engagement correlations
2. Generate prompt weight recommendations based on historical performance
3. Export feedback as JSON for consumption by curation/writer modules

Designed to be imported by any bot project via the bot-common submodule.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PostRecord:
    """A post with its attributes and engagement metrics."""
    post_id: str
    posted_at: datetime
    attributes: dict[str, str]  # e.g. {"theme": "education", "tone": "casual", "pattern": "list"}
    engagement: dict[str, float]  # e.g. {"views": 100, "likes": 5, "replies": 2, "reposts": 1}


@dataclass
class CorrelationResult:
    """Correlation between an attribute value and engagement."""
    attribute: str
    value: str
    sample_count: int
    avg_engagement_score: float
    avg_views: float


@dataclass
class FeedbackReport:
    """Generated feedback for curation/writer modules."""
    generated_at: str
    window_days: int
    total_posts: int
    top_performers: list[CorrelationResult] = field(default_factory=list)
    low_performers: list[CorrelationResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def calculate_engagement_score(metrics: dict[str, float]) -> float:
    """Calculate weighted engagement score.

    Weights: views=0.1, likes=1.0, replies=3.0, reposts=2.0, clicks=2.0
    Normalized by views (if > 0) to get engagement rate.
    """
    views = metrics.get("views", 0)
    likes = metrics.get("likes", 0)
    replies = metrics.get("replies", 0)
    reposts = metrics.get("reposts", 0)
    clicks = metrics.get("clicks", 0)

    raw = likes * 1.0 + replies * 3.0 + reposts * 2.0 + clicks * 2.0
    if views > 0:
        return raw / views * 100  # percentage
    return raw


def compute_correlations(
    posts: list[PostRecord],
    attribute_key: str,
    min_samples: int = 3,
) -> list[CorrelationResult]:
    """Compute average engagement by attribute value.

    Args:
        posts: List of post records with attributes and engagement.
        attribute_key: Which attribute to group by (e.g. "theme", "tone").
        min_samples: Minimum posts per group to include in results.

    Returns:
        Sorted list of CorrelationResult (highest engagement first).
    """
    groups: dict[str, list[PostRecord]] = defaultdict(list)
    for p in posts:
        val = p.attributes.get(attribute_key)
        if val:
            groups[val].append(p)

    results = []
    for value, group_posts in groups.items():
        if len(group_posts) < min_samples:
            continue

        scores = [calculate_engagement_score(p.engagement) for p in group_posts]
        avg_views = sum(p.engagement.get("views", 0) for p in group_posts) / len(group_posts)

        results.append(CorrelationResult(
            attribute=attribute_key,
            value=value,
            sample_count=len(group_posts),
            avg_engagement_score=sum(scores) / len(scores),
            avg_views=avg_views,
        ))

    return sorted(results, key=lambda r: r.avg_engagement_score, reverse=True)


def generate_feedback(
    posts: list[PostRecord],
    attribute_keys: list[str],
    window_days: int = 30,
    top_n: int = 3,
    min_samples: int = 3,
) -> FeedbackReport:
    """Generate a feedback report from historical post data.

    Args:
        posts: All post records.
        attribute_keys: Attributes to analyze (e.g. ["theme", "tone", "pattern"]).
        window_days: Only include posts from the last N days.
        top_n: Number of top/bottom performers to include.
        min_samples: Minimum posts per group.

    Returns:
        FeedbackReport with top/low performers and recommendations.
    """
    cutoff = datetime.now() - timedelta(days=window_days)
    recent = [p for p in posts if p.posted_at >= cutoff]

    report = FeedbackReport(
        generated_at=datetime.now().isoformat(),
        window_days=window_days,
        total_posts=len(recent),
    )

    if len(recent) < min_samples:
        report.recommendations.append(
            f"Insufficient data ({len(recent)} posts in {window_days} days). "
            f"Need at least {min_samples}."
        )
        return report

    all_correlations: list[CorrelationResult] = []
    for key in attribute_keys:
        correlations = compute_correlations(recent, key, min_samples)
        all_correlations.extend(correlations)

    all_sorted = sorted(all_correlations, key=lambda r: r.avg_engagement_score, reverse=True)
    report.top_performers = all_sorted[:top_n]
    report.low_performers = all_sorted[-top_n:] if len(all_sorted) > top_n else []

    for top in report.top_performers:
        report.recommendations.append(
            f"Increase {top.attribute}={top.value} "
            f"(avg engagement: {top.avg_engagement_score:.2f}, n={top.sample_count})"
        )
    for low in report.low_performers:
        if low.avg_engagement_score < report.top_performers[0].avg_engagement_score * 0.5:
            report.recommendations.append(
                f"Reduce {low.attribute}={low.value} "
                f"(avg engagement: {low.avg_engagement_score:.2f}, n={low.sample_count})"
            )

    return report


def save_feedback(report: FeedbackReport, output_path: Path) -> None:
    """Save feedback report as JSON file."""
    data = {
        "generated_at": report.generated_at,
        "window_days": report.window_days,
        "total_posts": report.total_posts,
        "top_performers": [
            {"attribute": r.attribute, "value": r.value,
             "sample_count": r.sample_count, "avg_score": round(r.avg_engagement_score, 2)}
            for r in report.top_performers
        ],
        "low_performers": [
            {"attribute": r.attribute, "value": r.value,
             "sample_count": r.sample_count, "avg_score": round(r.avg_engagement_score, 2)}
            for r in report.low_performers
        ],
        "recommendations": report.recommendations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Feedback report saved to %s", output_path)
