"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
what `Base.metadata.create_all()` (tests, dev bootstrap) and Alembic
autogenerate rely on.
"""

from app.models.elo_history import EloHistory
from app.models.injury import Injury
from app.models.match import Match
from app.models.model_version import ModelVersion
from app.models.prediction import Prediction, PredictionHistory
from app.models.team import Team
from app.models.training_run import TrainingRun

__all__ = [
    "Team",
    "Match",
    "EloHistory",
    "Prediction",
    "PredictionHistory",
    "ModelVersion",
    "TrainingRun",
    "Injury",
]
