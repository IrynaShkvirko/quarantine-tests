import pytest
from procrastinate import PsycopgConnector
from procrastinate.jobs import Status

from app.workers import queue

pytestmark = pytest.mark.integration


async def test_deferred_ping_is_run_by_a_worker_and_completes(test_database_url: str) -> None:
    dsn = test_database_url.replace("+psycopg", "", 1)
    with queue.app.replace_connector(PsycopgConnector(conninfo=dsn)):
        async with queue.app.open_async():
            job_id = await queue.ping.defer_async()
            # wait=False: process what is queued, then return instead of waiting for more.
            await queue.app.run_worker_async(wait=False)

            jobs = list(await queue.app.job_manager.list_jobs_async(id=job_id))
            await queue.app.job_manager.delete_old_jobs(nb_hours=0, include_failed=True)

    assert [job.status for job in jobs] == [Status.SUCCEEDED.value]
