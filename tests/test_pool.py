import asyncio

from sparky.agent import SessionPool


class FakeSession:
    made = 0

    def __init__(self):
        FakeSession.made += 1
        self.connected = False
        self.closed = False

    async def connect(self):
        await asyncio.sleep(0)
        self.connected = True

    async def close(self):
        self.closed = True


async def test_take_returns_connected_session_and_refills():
    FakeSession.made = 0
    pool = SessionPool(factory=FakeSession)
    pool.warm()
    pool.warm()  # idempotent: still one warm session
    first = await pool.take()
    assert first.connected and FakeSession.made == 2  # one handed out, next already warming
    second = await pool.take()
    assert second is not first and second.connected
    await pool.close()


async def test_take_without_warm_and_after_failed_warm_falls_back():
    class Boom(FakeSession):
        async def connect(self):
            raise RuntimeError("login pending")

    pool = SessionPool(factory=Boom)
    pool.warm()
    s = await pool.take()  # warm task failed -> cold fallback, not an exception
    assert isinstance(s, Boom) and not s.connected
    await pool.close()
