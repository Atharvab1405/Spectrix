"""Run the SPECTRIX shared simulator with the Standard baseline."""

import argparse

from baseline import StandardAllocator
from simulator import (
    SCENARIO_NAMES,
    ScenarioConfig,
    SimulationSnapshot,
    TransmissionResult,
    WirelessSpectrumSimulator,
)


SlotRecord = tuple[
    SimulationSnapshot,
    tuple[int | None, ...],
    tuple[TransmissionResult, ...],
]


def _collect_run(
    scenario: ScenarioConfig, seed: int, number_of_slots: int
) -> tuple[SlotRecord, ...]:
    simulator = WirelessSpectrumSimulator(scenario, seed=seed)
    allocator = StandardAllocator()
    snapshot = simulator.reset()
    records: list[SlotRecord] = []

    for slot_index in range(number_of_slots):
        selected_channels = allocator.choose_channels(snapshot)
        transmission_results = simulator.transmit(snapshot, selected_channels)
        records.append((snapshot, selected_channels, transmission_results))
        if slot_index + 1 < number_of_slots:
            snapshot = simulator.step()

    return tuple(records)


def _format_allocations(selected_channels: tuple[int | None, ...]) -> str:
    parts = []
    for user_id, channel_id in enumerate(selected_channels):
        selection = "defer" if channel_id is None else f"CH{channel_id}"
        parts.append(f"SU{user_id}->{selection}")
    return ",".join(parts)


def _format_transmissions(results: tuple[TransmissionResult, ...]) -> str:
    return ",".join(
        f"SU{result.secondary_user_id}:{result.outcome}"
        f"({result.packets_delivered}/{result.packets_generated})"
        for result in results
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the SPECTRIX Standard baseline on the shared simulator."
    )
    parser.add_argument(
        "--scenario", choices=SCENARIO_NAMES, default="medium",
        help="traffic profile to simulate (default: medium)",
    )
    parser.add_argument(
        "--steps", type=int, default=5,
        help="number of snapshots to print, including the initial slot (default: 5)",
    )
    parser.add_argument(
        "--seed", type=int, default=7,
        help="integer seed for repeatable scenario generation (default: 7)",
    )
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be at least 1")

    scenario = ScenarioConfig.preset(args.scenario)
    run_records = _collect_run(scenario, args.seed, args.steps)

    print(
        "SPECTRIX Standard baseline | "
        f"scenario={scenario.name} | seed={args.seed} | slots={args.steps}"
    )
    print(
        "Transmission assumptions: "
        f"packet_size={scenario.packet_size_bits} bits, "
        f"minimum_SINR={scenario.minimum_sinr_db:.1f} dB"
    )
    for snapshot, selected_channels, results in run_records:
        busy_count = sum(snapshot.primary_occupancy)
        sensed_busy_count = sum(
            reading.sensed_busy for reading in snapshot.sensing_readings
        )
        arrivals = ",".join(str(count) for count in snapshot.packet_arrivals)
        delivered_packets = sum(result.packets_delivered for result in results)
        print(
            f"slot={snapshot.time_slot:02d} "
            f"PU_busy={busy_count}/{scenario.num_channels} "
            f"sensed_busy={sensed_busy_count}/{len(snapshot.sensing_readings)} "
            f"arrivals_by_SU=[{arrivals}] "
            f"allocation=[{_format_allocations(selected_channels)}] "
            f"events=[{_format_transmissions(results)}] "
            f"delivered={delivered_packets} packets"
        )

    replay = _collect_run(scenario, args.seed, args.steps)
    replay_status = "PASS" if run_records == replay else "FAIL"
    print(f"same-seed allocation/transmission replay: {replay_status}")
    if run_records != replay:
        raise SystemExit("same-seed replay did not reproduce identical results")


if __name__ == "__main__":
    main()