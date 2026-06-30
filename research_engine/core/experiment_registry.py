"""Experiment Registry database layer.

Logs and retrieves historical experiments, indexing manifests and metrics
to prevent duplicate work and allow fast search.
"""

from pathlib import Path
from typing import List, Dict
import json


class ExperimentRegistry:
    """Manages index operations for historical strategy runs using a JSON registry."""

    def __init__(self, database_path: Path) -> None:
        """Initialize connection to metadata database or index file."""
        self.database_path: Path = database_path
        self._initialize_registry()

    def _initialize_registry(self) -> None:
        """Create empty registry JSON if not present."""
        if not self.database_path.exists():
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.database_path, "w", encoding="utf-8") as f:
                json.dump({"experiments": []}, f, indent=2)

    def register_experiment(self, 
                            candidate_id: str, 
                            experiment_id: str, 
                            manifest: dict, 
                            metrics: dict) -> None:
        """Write a new index entry storing manifest details and performance results.
        
        Args:
            candidate_id (str): Strategy candidate folder code.
            experiment_id (str): Padded identifier index.
            manifest (dict): Full metadata parameters.
            metrics (dict): Extracted performance ratios.
        """
        registry = {"experiments": []}
        try:
            with open(self.database_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            pass

        # Check if already exists, replace if so
        experiments = registry.get("experiments", [])
        new_entry = {
            "candidate_id": candidate_id,
            "experiment_id": experiment_id,
            "manifest": manifest,
            "metrics": metrics
        }
        
        # Filter out existing with same ID
        experiments = [e for e in experiments if e.get("experiment_id") != experiment_id]
        experiments.append(new_entry)
        registry["experiments"] = experiments

        with open(self.database_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)

    def check_duplicate_experiment(self, candidate_id: str, parameters: dict) -> str:
        """Query index to see if an identical parameter set was already computed.
        
        Args:
            candidate_id (str): Strategy candidate folder code.
            parameters (dict): Active configuration to search.
            
        Returns:
            str: Existing experiment ID if match found, empty string otherwise.
        """
        try:
            with open(self.database_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            return ""

        for entry in registry.get("experiments", []):
            if entry.get("candidate_id") == candidate_id:
                # Compare parameter dicts
                entry_params = entry.get("manifest", {}).get("parameters", {})
                if entry_params == parameters:
                    return entry.get("experiment_id", "")
        return ""

    def query_registry_by_metric(self, candidate_id: str, target_metric: str, threshold: float) -> List[dict]:
        """Retrieve historical runs exceeding a specific benchmark threshold.
        
        Args:
            candidate_id (str): Target strategy candidate.
            target_metric (str): Performance column name (e.g. 'profit_factor').
            threshold (float): Lower value bound.
            
        Returns:
            list: List of matching manifest registries.
        """
        matches = []
        try:
            with open(self.database_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            return []

        for entry in registry.get("experiments", []):
            if entry.get("candidate_id") == candidate_id:
                metric_val = entry.get("metrics", {}).get(target_metric)
                if metric_val is not None:
                    # Handle max drawdown sub-dicts or simple floats
                    if isinstance(metric_val, dict) and "drawdown_pct" in metric_val:
                        metric_val = metric_val["drawdown_pct"]
                    try:
                        if float(metric_val) >= float(threshold):
                            matches.append(entry)
                    except ValueError:
                        pass
        return matches
