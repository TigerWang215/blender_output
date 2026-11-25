"""Paraxial beam profiles along the layout's directed connections (mm and radians)."""

from collections import defaultdict, deque
from dataclasses import dataclass
import math

import numpy as np

from .model import (BEAM_SOURCE_TYPES, DEFAULT_APERTURE_DIAMETER_MM, DEFAULT_SOURCE_DIAMETER_MM,
                    DEFAULT_WAVELENGTH_NM, SCH_KINDS)

ABSORBING_PARTS = {"dump", "ccd", "photodiode"}


@dataclass(frozen=True)
class BeamProfile:
    sections: tuple[tuple[float, float], ...]  # distance, radius in mm
    transmission: float  # surviving fraction from aperture clipping alone


@dataclass(frozen=True)
class _Bundle:
    # A Gaussian uses two independent coefficients per transverse coordinate.
    # After clipping, the same arrays contain the sampled (y, z) rays instead.
    position: np.ndarray
    slope: np.ndarray
    sampled: bool = False
    transmission: float = 1.0

    @classmethod
    def launch(cls, source, wavelength_nm):
        waist = (source.source_diameter_mm or DEFAULT_SOURCE_DIAMETER_MM) / 2
        wavelength_mm = (wavelength_nm or DEFAULT_WAVELENGTH_NM) * 1e-6
        return cls(np.array([waist / 2, 0.0]), np.array([0.0, wavelength_mm / (2 * math.pi * waist)]))

    def advance(self, distance):
        return _Bundle(self.position + distance * self.slope, self.slope, self.sampled, self.transmission)

    def refract(self, focal_length):
        return _Bundle(self.position, self.slope - self.position / focal_length, self.sampled, self.transmission)

    def radius(self, distance=0.0):
        positions = self.position + distance * self.slope
        if not self.sampled:
            return 2 * float(np.linalg.norm(positions))
        # A clipped profile is no longer Gaussian. Use its second-moment radius,
        # capped by the outermost surviving ray at this plane.
        squared_radii = np.sum(positions**2, axis=1)
        return math.sqrt(min(2 * float(squared_radii.mean()), float(squared_radii.max())))

    def clip(self, diameter):
        aperture = diameter / 2
        if aperture == 0:
            return None
        if self.sampled:
            passes = np.sum(self.position**2, axis=1) <= aperture**2
            if passes.all():
                return self
            if not passes.any():
                return None
            return _Bundle(self.position[passes], self.slope[passes], True,
                           self.transmission * float(passes.mean()))

        waist = self.radius()
        fraction = -math.expm1(-2 * (aperture / waist)**2)
        if fraction >= 1 - 1e-10:
            return self
        # Sample the *transmitted* Gaussian directly so a small but open first
        # aperture cannot disappear due to a lack of samples in its centre.
        count = 2048
        rng = np.random.default_rng(0)
        quantiles = (np.arange(count) + 0.5) / count
        azimuth = rng.uniform(0, 2 * math.pi, count)
        radii = waist * np.sqrt(-0.5 * np.log1p(-fraction * quantiles))
        positions = radii[:, None] * np.column_stack((np.cos(azimuth), np.sin(azimuth)))
        curvature = float(self.position @ self.slope) / float(self.position @ self.position)
        angular_sigma = np.linalg.norm(self.slope - curvature * self.position)
        slopes = curvature * positions + angular_sigma * rng.standard_normal(positions.shape)
        return _Bundle(positions, slopes, True, self.transmission * fraction)

    def profile(self, length):
        distances = np.linspace(0.0, length, 17)
        slopes = self.slope.ravel()
        variance = float(slopes @ slopes)
        if variance > 0:
            focus = -float(self.position.ravel() @ slopes) / variance
            if 0 < focus < length:
                # Concentrate rings around the waist, even when it is much
                # smaller than the separation between two layout components.
                slope_radius = (2 * variance / len(self.slope) if self.sampled else 4 * variance)**0.5
                rayleigh_range = self.radius(focus) / slope_radius
                near_focus = focus + rayleigh_range * np.array([-8, -2, -0.5, 0, 0.5, 2, 8])
                distances = np.append(distances, near_focus.clip(0, length))
        sections = tuple((float(d), self.radius(d)) for d in np.unique(distances))
        return BeamProfile(sections, self.transmission)


def _through_part(bundle, part):
    if bundle is None or part.type in ABSORBING_PARTS:
        return None
    if part.type == "variable_iris":
        diameter = part.aperture_diameter_mm
        return bundle.clip(DEFAULT_APERTURE_DIAMETER_MM if diameter is None else diameter)
    if part.type in SCH_KINDS["lens"][2] and part.focal_length_mm:
        return bundle.refract(part.focal_length_mm)
    return bundle


def trace_beams(layout, origins, *, profiles=True) -> dict[str, BeamProfile]:
    """Trace each reachable segment once, keeping blocked paths dark downstream.

    A layout with no explicit source at the head of a route uses a nominal input.
    Folding follows the drawn ray axis. Branches carry independent copies of the
    input state; no splitting ratio or coherent recombination is implied.
    """
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    edges = [b for b in layout.beams.values() if b.source in origins and b.target in origins]
    for beam in edges:
        incoming[beam.target].append(beam)
        outgoing[beam.source].append(beam)

    output = {}
    visited = set()
    queue = deque()

    def launch(beam):
        part = layout.components[beam.source]
        bundle = _Bundle.launch(part, beam.wavelength_nm)
        queue.append((beam, _through_part(bundle, part)))

    def propagate():
        while queue:
            beam, bundle = queue.popleft()
            if beam.id in output or (bundle is None and beam.id in visited):
                continue
            visited.add(beam.id)
            part = layout.components[beam.target]
            if bundle is not None:
                length = math.dist(origins[beam.source], origins[beam.target])
                resolved_width = profiles or bundle.transmission < 1.0
                output[beam.id] = (bundle.profile(length) if resolved_width else BeamProfile((), bundle.transmission))
                bundle = bundle.advance(length)
            if part.type in BEAM_SOURCE_TYPES:
                continue  # the source starts its own outputs
            bundle = _through_part(bundle, part)
            for next_beam in outgoing[part.id]:
                wavelength = next_beam.wavelength_nm
                if wavelength and beam.wavelength_nm != wavelength and any(
                        other.wavelength_nm == wavelength for other in incoming[part.id]):
                    continue
                queue.append((next_beam, bundle))

    for beam in edges:
        if layout.components[beam.source].type in BEAM_SOURCE_TYPES or not incoming[beam.source]:
            launch(beam)
    propagate()

    # A legacy closed loop can have no source or upstream connection. Draw one
    # pass for orientation, without chasing the loop or relaunching blocked paths.
    for beam in edges:
        if beam.id not in visited:
            launch(beam)
            propagate()
    return output
