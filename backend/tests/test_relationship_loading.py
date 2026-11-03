"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Relationship loading strategy

Why this exists:
    Listing fifteen satellite images issued 278 SQL
    statements and took 4.2 seconds. The database was not
    at fault: every table is small and every foreign key is
    indexed. The cost came from the models themselves.

    Each collection in the chain

        satellite_image -> analysis_jobs
        analysis_job    -> detections
        detection       -> alerts
        alert           -> recipients, email_queue, sms_queue

    was declared lazy="selectin", so loading one row pulled
    its jobs, their detections, those detections' alerts and
    every queued message behind them. None of it appears in
    any list response.

    forest_area.py had already met this and carries a note
    explaining why its relationships use lazy="select". This
    test holds the rest of the chain to the same rule, so
    the avalanche cannot be reintroduced by a one-word
    change that looks harmless in review.

What it does NOT assert:
    That these relationships are never eagerly loaded
    anywhere. An endpoint that genuinely needs a collection
    should ask for it at the query, with selectinload() or
    joinedload(), where the cost is visible and scoped to
    that endpoint. What is forbidden is paying for it on
    every query of the parent.
===========================================================
"""

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.alert import Alert
from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage


# Every collection that sat on the cascade, with the model
# that owns it.
CASCADING_COLLECTIONS = [
    (SatelliteImage, "analysis_jobs"),
    (SatelliteImage, "detections"),
    (AnalysisJob, "detections"),
    (Detection, "alerts"),
    (Alert, "recipients"),
    (Alert, "email_queue"),
    (Alert, "sms_queue"),
    (ForestArea, "satellite_images"),
    (ForestArea, "detections"),
]

EAGER_STRATEGIES = {"joined", "selectin", "subquery", "immediate"}


@pytest.mark.parametrize(
    "model,relationship_name",
    CASCADING_COLLECTIONS,
    ids=[f"{m.__name__}.{n}" for m, n in CASCADING_COLLECTIONS],
)
def test_collections_are_not_loaded_with_their_parent(
    model, relationship_name
):
    """
    A collection must not be fetched just because its parent
    was. This is the rule that keeps a list endpoint's query
    count independent of how much history a record has.
    """

    relationships = sa_inspect(model).relationships

    assert relationship_name in relationships, (
        f"{model.__name__}.{relationship_name} no longer exists. "
        "If it was renamed, update this test; if it was removed, "
        "delete its entry."
    )

    strategy = relationships[relationship_name].lazy

    assert strategy not in EAGER_STRATEGIES, (
        f'{model.__name__}.{relationship_name} is lazy="{strategy}". '
        "Eager loading on this chain is what made listing "
        "fifteen satellite images cost 278 queries. If an "
        "endpoint needs this collection, ask for it at the "
        "query with selectinload() instead."
    )


def test_the_whole_cascade_chain_is_broken():
    """
    The individual checks above can each pass while the
    chain as a whole still cascades, if a link is added
    later. This states the property that actually matters:
    loading a satellite image reaches no collection.
    """

    chain = [
        (SatelliteImage, "analysis_jobs"),
        (AnalysisJob, "detections"),
        (Detection, "alerts"),
        (Alert, "recipients"),
    ]

    eager_links = [
        f"{model.__name__}.{name}"
        for model, name in chain
        if sa_inspect(model).relationships[name].lazy
        in EAGER_STRATEGIES
    ]

    assert not eager_links, (
        "These links still load with their parent, so one "
        "satellite image pulls the records behind it: "
        + ", ".join(eager_links)
    )
