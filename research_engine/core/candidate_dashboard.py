"""Candidate Dashboard State Model.

Maintains live-progress state and status details for the discovery run,
supporting simultaneous tracking across multiple candidates.
"""

from pathlib import Path
from typing import Dict
import datetime
import json


class CandidateDashboard:
    """Manages tracking status writes to the shared dashboard state file."""

    def __init__(self, state_file_path: Path) -> None:
        """Initialize with path to write status updates."""
        self.state_file_path: Path = state_file_path
        self._initialize_state_file()

    def _initialize_state_file(self) -> None:
        """Create initial state JSON structure if missing."""
        if not self.state_file_path.exists():
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump({"last_updated": "", "candidates": {}}, f, indent=2)

    def update_candidate_progress(self, 
                                  candidate_id: str, 
                                  stage: str, 
                                  status: str, 
                                  progress_pct: float,
                                  current_experiment: str = None,
                                  notes: str = "") -> None:
        """Write current active run status for the designated candidate.
        
        Args:
            candidate_id (str): Strategy candidate under sweep.
            stage (str): Phase description (e.g. 'Discovery Sweep').
            status (str): Operational status (e.g. 'RUNNING', 'FAILED', 'COMPLETED').
            progress_pct (float): Completion percentage indicator (0.0 to 100.0).
            current_experiment (str): The active C{ID}-E{ID} index.
            notes (str): Informational tracing text.
        """
        state = {"last_updated": "", "candidates": {}}
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

        candidates = state.get("candidates", {})
        cand_state = candidates.get(candidate_id, {})
        
        cand_state["name"] = candidate_id
        cand_state["stage"] = stage
        cand_state["status"] = status
        cand_state["progress_pct"] = progress_pct
        if current_experiment:
            cand_state["current_experiment"] = current_experiment
        cand_state["notes"] = notes
        
        # Track start / end times
        now_str = datetime.datetime.utcnow().isoformat() + "Z"
        if status == "RUNNING" and not cand_state.get("start_time"):
            cand_state["start_time"] = now_str
            cand_state["end_time"] = None
        elif status in ["COMPLETED", "FAILED", "TERMINATED", "INVALID_CONFIGURATION"]:
            cand_state["end_time"] = now_str

        candidates[candidate_id] = cand_state
        state["candidates"] = candidates
        state["last_updated"] = now_str

        with open(self.state_file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def get_dashboard_state(self) -> dict:
        """Read and return the complete multi-candidate status dictionary."""
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
