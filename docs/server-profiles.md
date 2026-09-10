# The server's two startup profiles

Review item 2 (2026-09-10). `bin/server.py` is one FastAPI module that can come up two ways. Both register the same routes and the same startup handlers, because everything that registers anything sits at module level; the only thing under the `if __name__ == "__main__":` guard is the `uvicorn.run(app, host="0.0.0.0", port=8500)` call itself. The test `broker/tests/test_release_profile.py` asserts that by reading the module's AST: no route decorator, no `@app.on_event`, no `app.mount` and no `app.include_router` under the guard.

| Profile | How it starts | Who uses it | What registers |
|---|---|---|---|
| **direct** | `python3 bin/server.py` (or the installed copy at `~/.vintos/workspace/bin/server.py`) | the house unit on Aegis today (`vintos-server`, per the deploy script's restart and health confirmation on 8500) | every module-level `@app.*` route, startup handlers, static mounts, then `uvicorn.run` binds 0.0.0.0:8500 |
| **imported ASGI** | `uvicorn server:app --host 0.0.0.0 --port 8500` from the bin directory, or any ASGI host importing `server.app` | a unit that prefers uvicorn's own process management, tests that import the module, the route inventory | exactly the same registrations; `uvicorn.run` is not reached |

History: until 5 September the direct launch sat *above* a block of route definitions and the context builder, so the two profiles registered different sets (review batch 1 moved the launch to the end of the module; the hoisted routes carry a comment saying so). The remaining shadowed routes (`/api/thirveel/*`) are commented out by Gloria's word and register under neither profile.

Rules that keep the two equivalent:

1. Nothing but `import uvicorn` and `uvicorn.run(...)` goes under the `__main__` guard.
2. A route added after the guard is a bug the release-profile test catches.
3. Environment that changes behaviour (`VINTOS_SECRET`, `VINTOS_MODEL_PROFILE`, `VINTOS_ROUTE_BUDGET_S`) is read at module import, so it applies to both profiles the same way.
