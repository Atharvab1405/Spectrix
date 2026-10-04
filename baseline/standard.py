"""Deterministic energy-detection baseline for the shared simulator."""

from simulator.models import SimulationSnapshot


class StandardAllocator:
    """Fixed-priority dynamic allocation using sensed-idle channels.

    Secondary users are considered in ascending ID order. Each active user
    receives the unreserved sensed-idle channel with the highest projected
    SINR; ties go to the lower channel ID. This is a simple, reproducible
    conventional baseline rather than a claim about a deployed scheduler.
    """

    def choose_channels(
        self, snapshot: SimulationSnapshot
    ) -> tuple[int | None, ...]:
        if len(snapshot.packet_arrivals) == 0:
            raise ValueError("snapshot must contain at least one secondary user")

        selected: list[int | None] = [None] * len(snapshot.packet_arrivals)
        reserved_channels: set[int] = set()

        for user_id, packets_generated in enumerate(snapshot.packet_arrivals):
            if packets_generated == 0:
                continue

            candidates = [
                reading
                for reading in snapshot.readings_for_user(user_id)
                if not reading.sensed_busy
                and reading.channel_id not in reserved_channels
            ]
            if not candidates:
                continue

            best_reading = max(
                candidates,
                key=lambda reading: (reading.sinr_db, -reading.channel_id),
            )
            selected[user_id] = best_reading.channel_id
            reserved_channels.add(best_reading.channel_id)

        return tuple(selected)