from functools import lru_cache

from aiogram import Router

from app.bot.handlers import (
    accessories,
    admin,
    builds,
    common,
    compare,
    configurator,
    errors,
    fallback,
    ready_builds,
    visual,
)


@lru_cache(maxsize=1)
def build_router() -> Router:
    """Root router.

    Cached because the per-module routers are singletons: aiogram forbids
    attaching a router to a second parent, so building the tree twice in one
    process would raise. Order matters - ``fallback`` must always come last.
    """
    root = Router(name="root")
    root.include_router(errors.router)
    root.include_router(common.router)
    root.include_router(configurator.router)
    root.include_router(builds.router)
    root.include_router(ready_builds.router)
    root.include_router(compare.router)
    root.include_router(accessories.router)
    root.include_router(visual.router)
    root.include_router(admin.router)
    root.include_router(fallback.router)
    return root


__all__ = ["build_router"]
