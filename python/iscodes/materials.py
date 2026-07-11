"""Material models per IS 456:2000 LSM.

Units: N, mm, MPa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import tables


@dataclass(frozen=True)
class Concrete:
    fck: float  # characteristic cube strength, MPa

    @property
    def Ec(self) -> float:
        """Short-term modulus, cl 6.2.3.1."""
        return 5000.0 * math.sqrt(self.fck)

    @property
    def fcd(self) -> float:
        """Design stress in flexural compression block = 0.446 fck (cl 38.1)."""
        return 0.446 * self.fck

    @property
    def fcr(self) -> float:
        """Flexural tensile strength (modulus of rupture), cl 6.2.2."""
        return 0.7 * math.sqrt(self.fck)

    def tau_c(self, pt: float) -> float:
        return tables.tau_c(pt, self.fck)

    @property
    def tau_c_max(self) -> float:
        return tables.tau_c_max(self.fck)


@dataclass(frozen=True)
class Steel:
    fy: float  # characteristic yield / 0.2% proof stress, MPa
    Es: float = tables.ES

    @property
    def fd(self) -> float:
        """Design yield stress 0.87 fy (gamma_s = 1.15)."""
        return 0.87 * self.fy

    @property
    def xu_max_by_d(self) -> float:
        return tables.xu_max_by_d(self.fy)

    def stress_at_strain(self, eps: float) -> float:
        """Design stress-strain curve (cl 38.1 / SP 16 Fig).

        Fe250: bilinear. HYSD (Fe415/500): bilinear-with-knee approximated by
        the SP 16 piecewise points between 0.8fd and fd.
        """
        s = 1.0 if eps >= 0 else -1.0
        e = abs(eps)
        fd = self.fd
        if self.fy <= 250:  # mild steel: elastic-perfectly-plastic at fd
            return s * min(self.Es * e, fd)
        # SP 16 Table A piecewise (stress ratio -> inelastic strain)
        pts = [(0.80, 0.0), (0.85, 0.0001), (0.90, 0.0003),
               (0.95, 0.0007), (0.975, 0.0010), (1.00, 0.0020)]
        e_el = 0.8 * fd / self.Es
        if e <= e_el:
            return s * self.Es * e
        for (r1, i1), (r2, i2) in zip(pts, pts[1:]):
            e1 = r1 * fd / self.Es + i1
            e2 = r2 * fd / self.Es + i2
            if e <= e2:
                return s * fd * (r1 + (r2 - r1) * (e - e1) / (e2 - e1))
        return s * fd


def concrete_stress_block(fck: float, xu: float, b: float) -> tuple[float, float]:
    """Resultant force (N) and its depth from compression face (mm) of the
    rectangular-parabolic block over depth xu (cl 38.1): C = 0.36 fck b xu at
    0.42 xu from the extreme compression fiber."""
    return 0.36 * fck * b * xu, 0.42 * xu
