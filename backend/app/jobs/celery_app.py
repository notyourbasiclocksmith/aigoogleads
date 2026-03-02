from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "ignite_ads",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
)

celery_app.conf.beat_schedule = {
    "ads-sync-hourly": {
        "task": "app.jobs.tasks.sync_all_ads_hourly",
        "schedule": crontab(minute=0),
    },
    "ads-sync-daily": {
        "task": "app.jobs.tasks.sync_all_ads_daily",
        "schedule": crontab(hour=2, minute=0),
    },
    "diagnostic-run-daily": {
        "task": "app.jobs.tasks.run_all_diagnostics",
        "schedule": crontab(hour=6, minute=0),
    },
    "recommendation-gen-daily": {
        "task": "app.jobs.tasks.generate_all_recommendations",
        "schedule": crontab(hour=7, minute=0),
    },
    "autopilot-apply-daily": {
        "task": "app.jobs.tasks.apply_all_autopilot",
        "schedule": crontab(hour=8, minute=0),
    },
    "serp-scan-weekly": {
        "task": "app.jobs.tasks.run_all_serp_scans",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),
    },
    "website-crawl-weekly": {
        "task": "app.jobs.tasks.crawl_all_websites",
        "schedule": crontab(hour=1, minute=0, day_of_week=0),
    },
    "report-weekly": {
        "task": "app.jobs.tasks.generate_all_weekly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_week=5),
    },
    "report-monthly": {
        "task": "app.jobs.tasks.generate_all_monthly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),
    },
    "learning-aggregate-weekly": {
        "task": "app.jobs.tasks.aggregate_learnings",
        "schedule": crontab(hour=4, minute=0, day_of_week=6),
    },
    # V2 scheduled tasks
    "v2-apply-scheduled-changes": {
        "task": "app.jobs.v2_tasks.apply_due_change_sets",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "v2-rollback-trigger-check": {
        "task": "app.jobs.v2_tasks.evaluate_rollback_triggers",
        "schedule": crontab(minute=0),  # hourly
    },
    "v2-recommendation-outcomes": {
        "task": "app.jobs.v2_tasks.record_recommendation_outcomes",
        "schedule": crontab(hour=5, minute=30),  # daily
    },
    "v2-evaluation-regression": {
        "task": "app.jobs.v2_tasks.check_evaluation_regression",
        "schedule": crontab(hour=6, minute=30, day_of_week=1),  # weekly
    },
}

celery_app.autodiscover_tasks(["app.jobs"])
