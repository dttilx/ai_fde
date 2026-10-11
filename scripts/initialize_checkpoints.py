import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.diagnosis.checkpoints import initialize_checkpoints

initialize_checkpoints()
print("PostgreSQL checkpoint schema initialized with administrative credentials.")
