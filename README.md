# SPECTRIX

SPECTRIX is a simulation-based project for comparing spectrum-management
approaches on one shared dynamic wireless environment.

## Current stage

Phase 0/1 establishes the common environment. Phase 2 adds the Standard
baseline and a shared transmission model:

- configurable channels and primary-user occupancy
- secondary-user sensing readings and traffic arrivals
- low, medium, heavy, and stress traffic scenarios
- a deterministic fixed-priority dynamic allocator using sensed-idle channels
- shared packet outcomes for channel conflicts, primary-user occupancy, and
  insufficient SINR
- seeded, repeatable simulation runs

HMM, fuzzy logic, LSTM, reinforcement learning, full experiment metrics, CSV
logging, graphs, and the dashboard have not been added yet.

## Files

- `main.py` runs the Standard baseline and checks that identical seeds replay
  the same allocations and transmission outcomes.
- `baseline/standard.py` implements the conventional allocator.
- `simulator/config.py` defines scenario and transmission assumptions.
- `simulator/models.py` defines sensing, snapshot, and transmission records.
- `simulator/wireless_simulator.py` implements the common environment and
  transmission outcome model.
- `simulator/__init__.py` exposes the simulator interface.

## Run

Requires Python 3.10 or newer. The project uses only the Python standard
library; there are no third-party packages to install.

From the project folder:

```text
python main.py --scenario medium --steps 5 --seed 7
