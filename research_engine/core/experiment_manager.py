"""Experiment Manager.

Allocates immutable experiment IDs, generates parameter combinations,
and writes reproducibility manifests.
"""

from pathlib import Path
from typing import List, Dict
import itertools
import datetime
import json


class ExperimentManager:
    """Manages quantitative experiment parameters, IDs, and manifests."""

    def __init__(self, candidate_id: str, framework_version: str = "QRP Framework v2.0") -> None:
        """Initialize with candidate metadata."""
        self.candidate_id: str = candidate_id
        self.framework_version: str = framework_version
        self.candidate_version: str = "v0.1"

    def assign_experiment_id(self, last_id: int) -> str:
        """Allocate a unique, padded experiment ID.
        
        Args:
            last_id (int): Last recorded experiment integer index.
            
        Returns:
            str: Unique string ID (e.g. 'C001-E00001').
        """
        # We strip non-digits from Candidate ID to extract the numeric part if any
        num_str = "".join([c for c in self.candidate_id if c.isdigit()])
        cand_num = int(num_str) if num_str else 1
        return f"C{cand_num:03d}-E{last_id:05d}"

    def generate_sweep_matrix(self, parameter_space: dict) -> List[dict]:
        """Construct the Cartesian product of all parameters defined in parameter_space.
        
        Args:
            parameter_space (dict): Map of parameter name to lists.
            
        Returns:
            list: List of parameter dictionary configurations.
        """
        keys = list(parameter_space.keys())
        values = list(parameter_space.values())
        
        combinations = list(itertools.product(*values))
        
        sweep_matrix = []
        for combo in combinations:
            sweep_matrix.append(dict(zip(keys, combo)))
            
        return sweep_matrix

    def create_manifest(self, 
                        experiment_id: str, 
                        parameters: dict, 
                        timeframe: str,
                        universe: List[str],
                        git_commit: str = None,
                        termination_status: str = "N/A",
                        termination_reason: str = "N/A") -> dict:
        """Create the reproducibility manifest metadata dictionary.
        
        Args:
            experiment_id (str): Assigned ID.
            parameters (dict): Active configuration.
            timeframe (str): Active candle resolution.
            universe (list): Symbols array.
            git_commit (str): Git HEAD SHA.
            termination_status (str): Running termination outcome.
            termination_reason (str): Explicit audit reason.
            
        Returns:
            dict: The manifest metadata structure.
        """
        return {
            "experiment_id": experiment_id,
            "candidate_id": self.candidate_id,
            "framework_version": self.framework_version,
            "candidate_version": self.candidate_version,
            "git_commit": git_commit or "N/A",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "timeframe": timeframe,
            "universe": {
                "asset_class": "crypto",
                "symbols": universe
            },
            "parameters": parameters,
            "termination_status": termination_status,
            "termination_reason": termination_reason,
            "framework_safety_version": "QRP Framework v2.0.1",
            "regression_test_version": "v1.0.0"
        }

    def save_manifest(self, output_dir: Path, manifest: dict) -> Path:
        """Save the manifest dictionary to disk as JSON.
        
        Args:
            output_dir (Path): Output directory path.
            manifest (dict): Manifest metadata.
            
        Returns:
            Path: Filepath to the saved manifest.json.
        """
        manifest_dir = output_dir / "manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        file_path = manifest_dir / "experiment_manifest.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            
        return file_path
