"""Strategy Plugin Interface Contract.

All research candidates must expose a subclass of BaseStrategyPlugin named StrategyPlugin
in their source code files (research/candidate_{id}/code/strategy_plugin.py).
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategyPlugin(ABC):
    """Abstract Base Class for QRP Framework v2.0 Strategy Plugins."""

    @property
    @abstractmethod
    def metadata(self) -> dict:
        """Return metadata details.
        
        Required Keys:
            - candidate_id (str)
            - name (str)
            - version (str)
            - author (str)
            - description (str)
        """
        pass

    @property
    @abstractmethod
    def parameter_space(self) -> dict:
        """Return the dictionary mapping parameter names to lists of values to sweep.
        
        Example:
            return {
                "lookback": [10, 20, 50, 100],
                "portfolio_size": [1, 3, 5]
            }
        """
        pass

    def preprocess(self, universe_data: dict) -> dict:
        """Optional hook to run asset-level data alignment, normalization, or global index calculations.
        
        Args:
            universe_data (dict): Dictionary mapping asset symbols (str) to OHLCV DataFrames.
            
        Returns:
            dict: Aligned or modified dictionary of OHLCV DataFrames.
        """
        return universe_data

    @abstractmethod
    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """Core signal generation logic. Must compute signals without look-ahead bias.
        
        Args:
            universe_data (dict): Dict mapping asset symbols (str) to OHLCV DataFrames.
            parameters (dict): Mapped configuration values (e.g. {"lookback": 20}).
            
        Returns:
            dict: Dict mapping asset symbols (str) to DataFrames. Each DataFrame
                  must contain a 'signal' column (0 = flat, 1 = long, -1 = short)
                  calculated on the close of candle t, executable at open of t+1.
        """
        pass
class InterfaceValidationError(Exception):
    """Raised when a strategy plugin does not conform to the BaseStrategyPlugin contract."""
    pass
