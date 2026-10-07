from arq.connections import RedisSettings

from app.core.config import settings as app_settings


def redis_settings() -> RedisSettings:
    """Parse our REDIS_URL into Arq's RedisSettings."""
    return RedisSettings.from_dsn(app_settings.REDIS_URL)


class WorkerSettings:
    """Arq worker configuration.

    Run with:
        python -m arq app.workers.settings.WorkerSettings
    """

    from app.workers.tasks import record_click_task

    functions = [record_click_task]
    redis_settings = redis_settings()

    # Sensible defaults for a small worker
    max_jobs = 10           # concurrent jobs
    job_timeout = 30        # seconds before a job is considered failed
    keep_result = 60        # seconds to keep results in Redis
    max_tries = 3           # retry failed jobs up to 3 times