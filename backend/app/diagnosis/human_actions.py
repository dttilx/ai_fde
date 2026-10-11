from sqlalchemy import select

from app.diagnosis.models import PendingHumanAction


def ensure_expert_action(db, run, snapshot, reasons):
    action = db.scalar(
        select(PendingHumanAction).where(
            PendingHumanAction.run_id == run.id,
            PendingHumanAction.snapshot_hash == snapshot.content_hash,
            PendingHumanAction.kind == "EXPERT",
        )
    )
    if action is None:
        action = PendingHumanAction(
            run_id=run.id, snapshot_hash=snapshot.content_hash, kind="EXPERT", reasons=list(reasons)
        )
        db.add(action)
        db.flush()
    return action
