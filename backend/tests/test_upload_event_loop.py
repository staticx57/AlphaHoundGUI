"""An upload is analysed in a worker thread: while it runs, the event loop (the live dose stream, every other request) keeps going.
It used to run on the loop itself, so each analysis froze the dose stream for as long as it took (2-3 s under load on the live device)."""
import asyncio
import time

from routers import analysis


class FakeUpload:
    filename = "spectrum.csv"

    async def read(self):
        return b"Energy (keV),Counts\n1,1\n2,2\n"


def test_a_slow_analysis_does_not_block_the_event_loop(monkeypatch):
    def slow_analysis(content, filename):
        time.sleep(0.6)
        return {"counts": [1, 2]}

    monkeypatch.setattr(analysis, "_analyze_csv_upload", slow_analysis)
    gaps = []

    async def ticker(stop):
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(ticker(stop))
        await asyncio.sleep(0.1)
        result = await analysis.upload_file(FakeUpload())
        stop.set()
        await task
        return result

    assert asyncio.run(scenario()) == {"counts": [1, 2]}
    assert max(gaps) < 0.25, f"the event loop was blocked for {max(gaps):.2f} s during the analysis"
