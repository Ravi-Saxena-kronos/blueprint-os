import os

import redis
from rq import Connection, Queue, Worker

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")


def main():
    conn = redis.from_url(REDIS_URL)
    with Connection(conn):
        worker = Worker([Queue("jobs")], connection=conn)
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
