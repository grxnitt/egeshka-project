"""One line per thing done in the console. Details never hold a student's name, contact, email or IP."""
from .models import AdminLog


async def record(session, action: str, target: str = "", detail: str = "") -> None:
    session.add(AdminLog(action=action[:60], target=str(target)[:120], detail=str(detail)[:500]))
    await session.flush()
