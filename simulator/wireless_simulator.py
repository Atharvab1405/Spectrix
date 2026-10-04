"""Shared, reproducible wireless-spectrum simulation foundation.

This shared model generates channel occupancy, traffic arrivals, and sensing
readings. It also applies selected channel actions to one common transmission
model, so later approaches can use the same outcome rules.
"""

import math
import random
from collections.abc import Sequence

from .config import ScenarioConfig
from .models import SensingReading, SimulationSnapshot, TransmissionResult


class WirelessSpectrumSimulator:
    """One common environment that later approaches can observe and use."""

    def __init__(self, scenario: ScenarioConfig | None = None, seed: int = 7) -> None:
        self.scenario = scenario or ScenarioConfig.preset("medium")
        self.seed = self._validate_seed(seed)
        self._reset_random_streams()
        self._time_slot = 0
        self._primary_occupancy = tuple(
            self._occupancy_rng.random() < self.scenario.initial_busy_probability
            for _ in range(self.scenario.num_channels)
        )

    @staticmethod
    def _validate_seed(seed: int) -> int:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")
        return seed

    def _reset_random_streams(self) -> None:
        """Use independent streams so traffic/sensing draws do not shift PU state."""

        seed_source = random.Random(self.seed)
        self._occupancy_rng = random.Random(seed_source.getrandbits(64))
        self._traffic_rng = random.Random(seed_source.getrandbits(64))
        self._sensing_rng = random.Random(seed_source.getrandbits(64))

    def reset(self, seed: int | None = None) -> SimulationSnapshot:
        """Restart this scenario; omitting seed repeats the current seed."""

        if seed is not None:
            self.seed = self._validate_seed(seed)
        self._reset_random_streams()
        self._time_slot = 0
        self._primary_occupancy = tuple(
            self._occupancy_rng.random() < self.scenario.initial_busy_probability
            for _ in range(self.scenario.num_channels)
        )
        return self._make_snapshot()

    def step(self) -> SimulationSnapshot:
        """Advance the primary-user Markov chains by one slot."""

        next_occupancy: list[bool] = []
        for is_busy in self._primary_occupancy:
            if is_busy:
                remains_busy = (
                    self._occupancy_rng.random()
                    >= self.scenario.busy_to_idle_probability
                )
                next_occupancy.append(remains_busy)
            else:
                becomes_busy = (
                    self._occupancy_rng.random()
                    < self.scenario.idle_to_busy_probability
                )
                next_occupancy.append(becomes_busy)

        self._primary_occupancy = tuple(next_occupancy)
        self._time_slot += 1
        return self._make_snapshot()

    def transmit(
        self,
        snapshot: SimulationSnapshot,
        selected_channels: Sequence[int | None],
    ) -> tuple[TransmissionResult, ...]:
        """Apply channel selections using the common packet outcome model.

        Every generated packet for a user is treated as one slot batch. A batch
        succeeds only if its selected channel is unique, the primary user is
        idle, and projected SINR meets the configured threshold.
        """

        if len(selected_channels) != self.scenario.num_secondary_users:
            raise ValueError(
                "selected_channels must contain one entry per secondary user"
            )
        if len(snapshot.packet_arrivals) != self.scenario.num_secondary_users:
            raise ValueError("snapshot has an unexpected number of secondary users")
        if len(snapshot.primary_occupancy) != self.scenario.num_channels:
            raise ValueError("snapshot has an unexpected number of channels")

        channels = tuple(selected_channels)
        for channel_id in channels:
            if channel_id is None:
                continue
            if isinstance(channel_id, bool) or not isinstance(channel_id, int):
                raise TypeError("each selected channel must be an integer or None")
            if not 0 <= channel_id < self.scenario.num_channels:
                raise ValueError(f"channel id is out of range: {channel_id}")

        users_by_channel: dict[int, list[int]] = {}
        for user_id, channel_id in enumerate(channels):
            if snapshot.packet_arrivals[user_id] > 0 and channel_id is not None:
                users_by_channel.setdefault(channel_id, []).append(user_id)

        results: list[TransmissionResult] = []
        for user_id, channel_id in enumerate(channels):
            packets_generated = snapshot.packet_arrivals[user_id]
            if packets_generated == 0:
                results.append(
                    TransmissionResult(
                        secondary_user_id=user_id,
                        channel_id=channel_id,
                        packets_generated=0,
                        packets_attempted=0,
                        packets_delivered=0,
                        outcome="NO_TRAFFIC",
                        throughput_bits=0,
                    )
                )
                continue

            if channel_id is None:
                results.append(
                    TransmissionResult(
                        secondary_user_id=user_id,
                        channel_id=None,
                        packets_generated=packets_generated,
                        packets_attempted=0,
                        packets_delivered=0,
                        outcome="NO_AVAILABLE_CHANNEL",
                        throughput_bits=0,
                    )
                )
                continue

            if len(users_by_channel[channel_id]) > 1:
                outcome = "SU_COLLISION"
            elif snapshot.primary_occupancy[channel_id]:
                outcome = "PRIMARY_USER_ACTIVE"
            else:
                reading = snapshot.readings_for_user(user_id)[channel_id]
                if reading.sinr_db < self.scenario.minimum_sinr_db:
                    outcome = "LOW_SINR"
                else:
                    outcome = "SUCCESS"

            packets_delivered = packets_generated if outcome == "SUCCESS" else 0
            results.append(
                TransmissionResult(
                    secondary_user_id=user_id,
                    channel_id=channel_id,
                    packets_generated=packets_generated,
                    packets_attempted=packets_generated,
                    packets_delivered=packets_delivered,
                    outcome=outcome,
                    throughput_bits=(
                        packets_delivered * self.scenario.packet_size_bits
                    ),
                )
            )
        return tuple(results)

    def _traffic_probability_for_current_slot(self) -> float:
        config = self.scenario
        if (
            config.spike_interval_slots is not None
            and self._time_slot % config.spike_interval_slots
            < config.spike_duration_slots
        ):
            return config.spike_arrival_probability
        return config.traffic_arrival_probability

    def _make_snapshot(self) -> SimulationSnapshot:
        traffic_probability = self._traffic_probability_for_current_slot()
        packet_arrivals = tuple(
            self._traffic_rng.randint(1, self.scenario.max_packets_per_arrival)
            if self._traffic_rng.random() < traffic_probability
            else 0
            for _ in range(self.scenario.num_secondary_users)
        )
        readings = tuple(
            self._make_reading(user_id, channel_id)
            for user_id in range(self.scenario.num_secondary_users)
            for channel_id in range(self.scenario.num_channels)
        )
        return SimulationSnapshot(
            time_slot=self._time_slot,
            primary_occupancy=self._primary_occupancy,
            packet_arrivals=packet_arrivals,
            sensing_readings=readings,
        )

    def _make_reading(self, user_id: int, channel_id: int) -> SensingReading:
        config = self.scenario
        primary_busy = self._primary_occupancy[channel_id]

        # The sensing decision uses configured false-alarm and missed-detection
        # probabilities directly; this is not a calibrated RF detector model.
        if primary_busy:
            sensed_busy = (
                self._sensing_rng.random() >= config.missed_detection_probability
            )
        else:
            sensed_busy = (
                self._sensing_rng.random() < config.false_alarm_probability
            )

        # Sum primary-user energy at the candidate channel. Adjacent-channel
        # energy is attenuated by distance in channel indices.
        received_primary_powers: list[float] = []
        for source_channel, source_is_busy in enumerate(self._primary_occupancy):
            if not source_is_busy:
                continue
            channel_distance = abs(channel_id - source_channel)
            attenuation = channel_distance * config.adjacent_channel_attenuation_db
            fading_db = self._sensing_rng.gauss(0.0, 2.0)
            received_primary_powers.append(
                config.primary_signal_dbm - attenuation + fading_db
            )

        interference_dbm = _sum_dbm(received_primary_powers)
        rssi_dbm = _sum_dbm(
            [config.noise_floor_dbm, *received_primary_powers]
        )

        # SNR/SINR use a hypothetical secondary-user link with small independent
        # fading. Actual transmission quality will be modeled in a later phase.
        desired_secondary_dbm = (
            config.secondary_signal_dbm + self._sensing_rng.gauss(0.0, 2.0)
        )
        snr_db = desired_secondary_dbm - config.noise_floor_dbm
        sinr_denominator_dbm = _sum_dbm(
            [config.noise_floor_dbm, *received_primary_powers]
        )
        sinr_db = desired_secondary_dbm - sinr_denominator_dbm

        return SensingReading(
            secondary_user_id=user_id,
            channel_id=channel_id,
            sensed_busy=sensed_busy,
            rssi_dbm=rssi_dbm,
            snr_db=snr_db,
            sinr_db=sinr_db,
            interference_dbm=interference_dbm,
        )


def _sum_dbm(power_levels_dbm: list[float]) -> float | None:
    """Add independent power levels expressed in dBm without linear overflow."""

    if not power_levels_dbm:
        return None
    peak = max(power_levels_dbm)
    linear_sum = sum(10 ** ((power - peak) / 10.0) for power in power_levels_dbm)
    return peak + 10.0 * math.log10(linear_sum)