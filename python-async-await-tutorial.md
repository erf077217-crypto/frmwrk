# Python Async/Await: A Deep Dive

Python's `async`/`await` syntax (introduced in Python 3.5 via PEP 492) provides a native way to write concurrent code using an event loop. This tutorial covers the four fundamental concepts: **event loops**, **coroutines**, **tasks**, and **futures**.

---

## 1. The Event Loop

The event loop is the core of every async Python program. It's a loop that:

- Listens for and dispatches events
- Manages a queue of work (callbacks, coroutines, I/O waits)
- Decides which piece of code runs next
- Suspends code that's waiting (e.g., for a network response) and resumes it later

Think of it as a traffic controller for concurrent operations.

### How the event loop works

```python
import asyncio


def naive_event_loop():
    """Conceptual model of an event loop."""
    queue = []

    def schedule(coro):
        queue.append(coro)

    async def work(name, seconds):
        print(f"  {name}: starting")
        # In a real loop, this would yield control
        await asyncio.sleep(seconds)
        print(f"  {name}: done after {seconds}s")

    schedule(work("A", 2))
    schedule(work("B", 1))
    schedule(work("C", 0.5))

    while queue:
        coro = queue.pop(0)
        try:
            coro.send(None)
        except StopIteration:
            pass
        else:
            queue.append(coro)


# Real event loop
async def demo_loop():
    print("1. Getting event loop")
    loop = asyncio.get_running_loop()
    print(f"   Loop: {loop}")
    print(f"   Time: {loop.time()}")
    return loop


asyncio.run(demo_loop())
```

### Getting the event loop

```python
import asyncio

# Python 3.10+
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(asyncio.sleep(1))
finally:
    loop.close()

# Modern approach (preferred) — creates a new loop and closes it:
async def main():
    loop = asyncio.get_running_loop()
    print(f"Running loop: {loop}")
    print(f"Default executor: {loop._default_executor}")

asyncio.run(main())
```

> **Note:** `asyncio.run()` is the recommended way to run async code. It creates a fresh event loop, runs your coroutine, and cleans up. Never call `get_running_loop()` outside a running coroutine — it raises `RuntimeError`.

### The event loop's lifecycle

```python
import asyncio


async def show_lifecycle():
    loop = asyncio.get_running_loop()
    print(f"Loop is running: {loop.is_running()}")

    # Schedule a callback
    loop.call_soon(lambda: print("  Callback fired!"))

    # Schedule a delayed callback
    loop.call_later(0.5, lambda: print("  Delayed callback (0.5s)"))

    # Schedule at a specific time
    when = loop.time() + 1.0
    loop.call_at(when, lambda: print(f"  Called at time {when:.2f}"))

    await asyncio.sleep(1.2)
    print("Done")


asyncio.run(show_lifecycle())
```

---

## 2. Coroutines

A **coroutine** is a function declared with `async def`. When called, it returns a **coroutine object** — nothing executes until the object is awaited or scheduled on an event loop.

```python
import asyncio


async def greet(name: str) -> str:
    print(f"  Hello, {name}!")
    await asyncio.sleep(0.5)
    print(f"  Goodbye, {name}!")
    return f"Done with {name}"


# Calling a coroutine function returns a coroutine object — it does NOT run
coro = greet("Alice")
print(f"Type: {type(coro)}")  # <class 'coroutine'>

# It runs only when awaited:
async def main():
    result = await coro
    print(f"Result: {result}")


asyncio.run(main())
```

### Coroutine internals — generators under the hood

Historically, coroutines were built on generators. The `await` keyword is conceptually similar to `yield from`.

```python
# Coroutines are based on generators:
import asyncio

# This is roughly equivalent to an async function
@asyncio.coroutine
def old_style_coro():
    yield from asyncio.sleep(0.5)
    return "done"


async def native_coro():
    await asyncio.sleep(0.5)
    return "done"


async def compare():
    r1 = await old_style_coro()
    r2 = await native_coro()
    print(f"Old style: {r1}")
    print(f"Native:    {r2}")


asyncio.run(compare())
```

### Awaitable objects

An object is **awaitable** if it is:
- A coroutine
- A `Task`
- A `Future`
- An object implementing `__await__()` (returning an iterator)

```python
import asyncio


class Waitable:
    """Custom awaitable using __await__."""

    def __init__(self, delay: float):
        self.delay = delay

    def __await__(self):
        yield from asyncio.sleep(self.delay).__await__()
        return f"waited {self.delay}s"


async def use_custom_awaitable():
    result = await Waitable(0.3)
    print(result)


asyncio.run(use_custom_awaitable())
```

---

## 3. Tasks

A **Task** wraps a coroutine and schedules it for execution on the event loop. Unlike a raw coroutine, a task runs **concurrently** — it doesn't block the code that created it.

```python
import asyncio


async def slow_operation(n: int):
    print(f"  Task {n}: start")
    await asyncio.sleep(n)
    print(f"  Task {n}: done")
    return n * 2


async def main():
    # Creating tasks schedules them for concurrent execution
    t1 = asyncio.create_task(slow_operation(2))
    t2 = asyncio.create_task(slow_operation(1))

    print("Tasks created, now awaiting...")

    # Await results
    r1 = await t1
    r2 = await t2

    print(f"Results: {r1}, {r2}")


asyncio.run(main())
```

### Task internals

```python
import asyncio


async def inspect_task():
    task = asyncio.current_task()
    print(f"Current task: {task}")
    print(f"  Name:  {task.get_name()}")
    print(f"  Done:  {task.done()}")
    print(f"  Cancelled: {task.cancelled()}")

    all_tasks = asyncio.all_tasks()
    print(f"All tasks ({len(all_tasks)}):")
    for t in all_tasks:
        print(f"  - {t.get_name()}: {t}")


async def demo():
    t = asyncio.create_task(inspect_task(), name="inspector")
    await t


asyncio.run(demo())
```

### Task groups (Python 3.11+)

```python
import asyncio


async def fetch(n: int) -> str:
    await asyncio.sleep(n)
    if n == 2:
        raise ValueError(f"Error in task {n}")
    return f"Data {n}"


async def main():
    # If any task raises, the group cancels all others
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fetch(1), name="fetch-1")
            tg.create_task(fetch(2), name="fetch-2")
            tg.create_task(fetch(3), name="fetch-3")
    except* ValueError as eg:
        print(f"Errors: {eg.exceptions}")

        for task in asyncio.all_tasks():
            if task.done() and not task.cancelled():
                try:
                    print(f"  {task.get_name()}: {task.result()}")
                except Exception as e:
                    print(f"  {task.get_name()}: error={e}")


asyncio.run(main())
```

### Cancelling tasks

```python
import asyncio


async def worker():
    try:
        for i in range(10):
            print(f"  Working... {i}")
            await asyncio.sleep(0.3)
    except asyncio.CancelledError:
        print("  Worker was cancelled!")
        # Do cleanup here
        raise  # Re-raise to acknowledge cancellation


async def main():
    task = asyncio.create_task(worker())
    await asyncio.sleep(0.5)
    print("Cancelling worker...")
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("Main: worker cancelled successfully")


asyncio.run(main())
```

### `asyncio.gather` vs `asyncio.wait` vs `asyncio.as_completed`

```python
import asyncio


async def work(n: int) -> str:
    await asyncio.sleep(n)
    return f"done in {n}s"


async def demo_gather():
    """gather - run concurrently, return all results in order."""
    results = await asyncio.gather(work(3), work(1), work(2))
    print(f"gather: {results}")


async def demo_wait():
    """wait - more control, returns done/pending sets."""
    tasks = [asyncio.create_task(work(t)) for t in [3, 1, 2]]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    print(f"wait: {len(done)} done, {len(pending)} pending")
    for t in done:
        print(f"  {t.result()}")


async def demo_as_completed():
    """as_completed - iterate as each task finishes."""
    tasks = [asyncio.create_task(work(t)) for t in [3, 1, 2]]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        print(f"as_completed: {result}")


async def main():
    print("=== gather ===")
    await demo_gather()
    print("\n=== wait ===")
    await demo_wait()
    print("\n=== as_completed ===")
    await demo_as_completed()


asyncio.run(main())
```

---

## 4. Futures

A **Future** is a low-level awaitable that represents a result that will be available at some point. A `Task` is a subclass of `Future`.

You rarely use bare `Future` objects directly — they're mostly used when integrating with callback-based code or implementing low-level protocols.

```python
import asyncio


async def future_basics():
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    print(f"Empty future: {future}")
    print(f"Done: {future.done()}")

    # Schedule resolution in 1 second
    loop.call_later(1, future.set_result, "hello from future")

    result = await future
    print(f"Result: {result}")
    print(f"Done:   {future.done()}")


asyncio.run(future_basics())
```

### Future with callback integration

This pattern is useful when wrapping callback-based libraries (e.g., file I/O, sockets):

```python
import asyncio
import random


def callback_based_api(on_done, on_error):
    """Simulates a callback-based function (e.g., a socket library)."""
    delay = random.uniform(0.3, 1.0)

    def _work():
        try:
            import time
            time.sleep(delay)
            if random.random() < 0.2:
                raise RuntimeError("random failure")
            on_done(f"result after {delay:.2f}s")
        except Exception as e:
            on_error(e)

    # Simulate async callback (using thread pool)
    import threading
    threading.Thread(target=_work, daemon=True).start()


async def async_wrapper() -> str:
    """Wrap a callback API into an awaitable."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def on_done(result: str):
        # Must call from the event loop's thread
        loop.call_soon_threadsafe(future.set_result, result)

    def on_error(error: Exception):
        loop.call_soon_threadsafe(future.set_exception, error)

    callback_based_api(on_done, on_error)
    return await future


async def demo():
    try:
        result = await async_wrapper()
        print(f"Got: {result}")
    except Exception as e:
        print(f"Error: {e}")


asyncio.run(demo())
```

### Task is a Future — the relationship

```python
import asyncio


async def explain_relation():
    # Task inherits from Future
    print(f"Task is Future subclass: {issubclass(asyncio.Task, asyncio.Future)}")

    t = asyncio.create_task(asyncio.sleep(0.5))
    print(f"Is task a Future? {isinstance(t, asyncio.Future)}")

    # You can use Future methods on a Task
    t.add_done_callback(lambda f: print(f"  Callback: task done = {f.done()}"))
    await t
    print(f"Task result: {t.result()}")


asyncio.run(explain_relation())
```

---

## Putting It All Together

A realistic example combining event loop, coroutines, tasks, and futures:

```python
import asyncio
import random


async def fetch_url(name: str, delay: float) -> dict:
    """Simulate fetching a URL."""
    print(f"  [{name}] fetching... (will take {delay:.1f}s)")
    await asyncio.sleep(delay)

    if random.random() < 0.15:
        raise ConnectionError(f"Failed to fetch {name}")

    data = {"url": name, "status": 200, "content_length": random.randint(100, 1000)}
    print(f"  [{name}] done: {data}")
    return data


async def supervisor(urls: list[str]):
    """Supervisor that manages fetches with timeout and error handling."""
    results = []
    errors = []

    async def wrapped_fetch(url: str) -> dict | None:
        """Wrap fetch with timeout and error handling."""
        try:
            delay = random.uniform(0.2, 1.5)
            result = await asyncio.wait_for(fetch_url(url, delay), timeout=2.0)
            return result
        except asyncio.TimeoutError:
            errors.append((url, "timeout"))
            return None
        except ConnectionError as e:
            errors.append((url, str(e)))
            return None

    # Schedule all fetches concurrently
    tasks = [asyncio.create_task(wrapped_fetch(url)) for url in urls]

    # Process as they complete
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is not None:
            results.append(result)

    return results, errors


async def main():
    urls = [f"https://api.example.com/endpoint/{i}" for i in range(8)]

    print("Starting concurrent fetches...")
    print(f"Event loop: {asyncio.get_running_loop()}")
    print(f"All tasks initially: {len(asyncio.all_tasks())}")

    results, errors = await supervisor(urls)

    print(f"\nSucceeded: {len(results)}")
    for r in results:
        print(f"  {r['url']}: {r['status']} ({r['content_length']} bytes)")

    print(f"\nFailed: {len(errors)}")
    for url, err in errors:
        print(f"  {url}: {err}")


asyncio.run(main())
```

---

## Summary

| Concept | Role | User-facing? |
|---------|------|-------------|
| **Event Loop** | Orchestrator — schedules and runs all async code | Rarely (use `asyncio.run()`) |
| **Coroutine** | `async def` function — a suspendable computation | Yes |
| **Task** | Wraps a coroutine for concurrent execution | Yes (`asyncio.create_task`) |
| **Future** | A read-only promise of a future result | Mostly internal; Task is a Future |

### Quick reference

```python
import asyncio

# Run a single coroutine
asyncio.run(my_coro())

# Run concurrently
task = asyncio.create_task(other_coro())
await task

# Wait for multiple
results = await asyncio.gather(coro1(), coro2())

# Wait with first-completed semantics
done, pending = await asyncio.wait({t1, t2}, return_when=FIRST_COMPLETED)

# Custom future
loop = asyncio.get_running_loop()
fut = loop.create_future()
loop.call_later(1, fut.set_result, "done")
result = await fut

# Task group (Python 3.11+)
async with asyncio.TaskGroup() as tg:
    tg.create_task(coro1())
    tg.create_task(coro2())
```
