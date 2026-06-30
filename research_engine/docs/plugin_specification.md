# QRP Framework v2.0 — Strategy Plugin Specification

This document defines the strict API contract that all strategy plugins must satisfy to run within the **Quantitative Research Platform (QRP) Framework v2.0**.

---

## 1. Plugin Philosophy & Architecture

Every quantitative candidate under research is represented as a strategy plugin. The plugin contains the strategy's mathematical formula, configuration parameters, and signal generation rules. It is entirely decoupled from execution mechanics (data loading, performance calculations, accounting, transaction fees, database storage, and dashboard reporting).

To register with the framework, the plugin must:
1. Exist as a Python module within the candidate directory: `research/candidate_{id}/code/strategy_plugin.py`.
2. Expose a single class named `StrategyPlugin` that inherits from the framework's `BaseStrategyPlugin` class.
3. Be written in a strategy-agnostic way (no hardcoding of timeframes, universe lists, or backtesting dates).

---

## 2. Dynamic Interface Definition

The abstract base class `BaseStrategyPlugin` (defined in `research_engine/core/strategy_interface.py`) outlines the API contract:

```python
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategyPlugin(ABC):
    """
    Abstract Base Class defining the contract for QRP v2.0 Strategy Plugins.
    """

    @property
    @abstractmethod
    def metadata(self) -> dict:
        """
        Return plugin metadata dictionary.
        Required keys:
            - 'candidate_id': str (e.g., 'Candidate-01')
            - 'name': str (e.g., 'Relative Strength')
            - 'version': str (e.g., '1.0.0')
            - 'author': str (e.g., 'Quant Team')
            - 'description': str
        """
        pass

    @property
    @abstractmethod
    def parameter_space(self) -> dict:
        """
        Return the dictionary defining the parameter sweep ranges.
        Format: { "parameter_name": [list_of_values] }
        Example: { "lookback": [10, 20, 50], "threshold": [0.1, 0.2] }
        """
        pass

    def preprocess(self, universe_data: dict) -> dict:
        """
        Optional Hook. Perform asset-level preprocessing (e.g. data alignment, 
        imputation, or global metrics calculations).
        
        Args:
            universe_data (dict): Dict mapping asset symbols (str) to pandas DataFrames.
                                  Each DataFrame contains OHLCV bars.
                                  
        Returns:
            dict: Processed dictionary of DataFrames matching the input format.
        """
        return universe_data

    @abstractmethod
    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """
        Core logic method. Accepts the preprocessed data and one instance of the
        parameter configuration dictionary, returning the raw signals for all assets.
        
        Args:
            universe_data (dict): Dict mapping asset symbols (str) to pandas DataFrames.
            parameters (dict): Specific parameter configuration (e.g. {"lookback": 50}).
            
        Returns:
            dict: Dict mapping asset symbols (str) to pandas DataFrames.
                  Each DataFrame MUST return the original candles containing 
                  at least one additional column:
                    - 'signal': float / int (0 = flat/no position, 1 = long, -1 = short)
        """
        pass
```

---

## 3. Data Contracts & Formatting

### A. Preprocessing Hook Input/Output
The `preprocess` method accepts a dictionary of historical dataframes:
```python
universe_data = {
    "BTC": pd.DataFrame,  # columns: ['open', 'high', 'low', 'close', 'volume']
    "ETH": pd.DataFrame,
    # ...
}
```
*Purpose*: Allows cross-sectional alignment (e.g., aligning datetime indices) or global index calculation (e.g., creating a market index DataFrame representing the average price movement of the 25 assets to filter signals).

### B. Signal Output Requirements
The `generate_signals` method returns a modified dictionary of DataFrames.
For every asset DataFrame:
* The index must remain `timestamp` (UTC timezone-aware).
* A `signal` column must be present.
* Signals must only look at historical data (index $\le t$) to prevent **look-ahead bias**. Calculations for candle $t$ must only utilize values available at the close of candle $t$, representing action taken at the open of candle $t+1$.

---

## 4. Parameter Space Schema

The `parameter_space` dictionary allows researchers to specify the exact grid sweep values. The `ExperimentManager` will dynamically construct the Cartesian product of all listed parameter ranges:

```python
# Example dictionary returned by the plugin:
parameter_space = {
    "lookback": [10, 20, 50, 100],
    "max_positions": [1, 3, 5],
    "atr_stop_multiplier": [2.0, 3.0]
}

# The ExperimentManager converts this into 24 distinct configurations:
# Config 1: {"lookback": 10, "max_positions": 1, "atr_stop_multiplier": 2.0}
# Config 2: {"lookback": 10, "max_positions": 1, "atr_stop_multiplier": 3.0}
# ...
```

---

## 5. Plugin Constraints

To maintain framework stability, plugins are bound by the following structural rules:
1. **No Disk Operations**: Strategy plugins must not attempt to read or write local database/CSV files directly. All inputs and outputs must pass through the method arguments.
2. **No Network Requests**: Plugins are strictly sandboxed. They cannot query web APIs for live funding rates, sentiment scores, or updates.
3. **No Indicator Libraries Dependency**: To prevent library mismatch across deployment machines, plugins should rely on standard mathematical implementations (e.g., Pandas and NumPy operations) rather than complex external indicator libraries, unless approved under the version manifest.
