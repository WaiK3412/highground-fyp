from django.apps import AppConfig


class PriorityConfig(AppConfig):
    """The priority-class rules (classes-1.0).

    The package was called `scoring` while it held the retired weighted score.
    The app label stays "scoring" so the existing migration history and
    database records still match after the rename.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'priority'
    label = 'scoring'
