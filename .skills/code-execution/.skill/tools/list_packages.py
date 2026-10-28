"""list_packages — list installed Python packages."""
import sys, importlib.metadata as md, asyncio


async def list_packages(filter: str = None) -> dict:
    """
    List packages installed in the current interpreter.

    Args:
        filter: optional substring to filter by name

    Returns:
        {"ok": True, "count": int, "packages": {name: version}}
    """
    def _scan():
        pkgs = {}
        for dist in md.distributions():
            name = dist.metadata.get("Name")
            if not name:
                continue
            if filter and filter.lower() not in name.lower():
                continue
            pkgs[name] = dist.version
        return pkgs
    pkgs = await asyncio.get_event_loop().run_in_executor(None, _scan)
    return {"ok": True, "count": len(pkgs), "python": sys.version.split()[0],
            "packages": dict(sorted(pkgs.items()))}
