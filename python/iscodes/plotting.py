"""Plotting helpers (matplotlib, Agg backend) for beam/column/footing output.

BMD follows the Indian convention (drawn on the tension side): sagging
(positive) moments are plotted below the axis.

Units: kN, kN.m, m.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # noqa: E402  headless, before pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def _zero_crossings(x, y):
    """Interpolated x-locations where y changes sign (points of contraflexure)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    pts = []
    for i in range(len(y) - 1):
        y1, y2 = y[i], y[i + 1]
        if y1 == 0.0:
            pts.append(x[i])
        elif y1 * y2 < 0:
            pts.append(x[i] - y1 * (x[i + 1] - x[i]) / (y2 - y1))
    return pts


def plot_sfd_bmd(x, V, M, title: str, path_png: str,
                 tension_side: bool = True, loads_desc=None) -> str:
    """Stacked load diagram, SFD and BMD -> PNG. Returns path_png.

    tension_side=True inverts the BMD y-axis (sagging plots below the axis).
    """
    x = np.asarray(x, float)
    V = np.asarray(V, float)
    M = np.asarray(M, float)
    L = float(x[-1])

    fig, (ax0, ax1, ax2) = plt.subplots(
        3, 1, sharex=True, figsize=(8, 9),
        gridspec_kw={"height_ratios": [1.0, 1.3, 1.3]})

    # ---- (a) load schematic ----------------------------------------------
    ax0.plot([0, L], [0, 0], color="black", lw=3)
    ax0.plot([0], [0], marker="^", ms=14, color="black")
    ax0.plot([L], [0], marker="^", ms=14, color="black")
    for xa in np.linspace(0.05 * L, 0.95 * L, 10):
        ax0.annotate("", xy=(xa, 0.0), xytext=(xa, 0.6),
                     arrowprops=dict(arrowstyle="->", color="tab:blue"))
    ax0.plot([0, L], [0.6, 0.6], color="tab:blue", lw=1)
    ax0.text(L / 2, 0.9, loads_desc or "Loading", ha="center", va="bottom",
             fontsize=9)
    ax0.set_ylim(-0.5, 1.4)
    ax0.set_yticks([])
    ax0.set_title(title, fontsize=12, fontweight="bold")
    ax0.set_ylabel("Load")

    # ---- (b) SFD ---------------------------------------------------------
    ax1.axhline(0, color="black", lw=0.8)
    ax1.plot(x, V, color="tab:red", lw=1.5)
    ax1.fill_between(x, V, 0, color="tab:red", alpha=0.25, hatch="///")
    iv = int(np.argmax(np.abs(V)))
    ax1.annotate(f"Vmax = {V[iv]:.1f} kN at {x[iv]:.2f} m",
                 xy=(x[iv], V[iv]), xytext=(0.05, 0.85),
                 textcoords="axes fraction", fontsize=9,
                 arrowprops=dict(arrowstyle="->"))
    ax1.set_ylabel("Shear V (kN)")
    ax1.grid(True, alpha=0.3)

    # ---- (c) BMD (tension side / Indian convention) ----------------------
    ax2.axhline(0, color="black", lw=0.8)
    ax2.plot(x, M, color="tab:green", lw=1.5)
    ax2.fill_between(x, M, 0, color="tab:green", alpha=0.25)
    ip = int(np.argmax(np.abs(M)))
    ax2.annotate(f"Mmax = {M[ip]:.1f} kN.m at {x[ip]:.2f} m",
                 xy=(x[ip], M[ip]), xytext=(0.05, 0.85),
                 textcoords="axes fraction", fontsize=9,
                 arrowprops=dict(arrowstyle="->"))
    for xc in _zero_crossings(x, M):
        ax2.axvline(xc, color="grey", ls=":", lw=0.8)
        ax2.annotate(f"contraflexure\n{xc:.2f} m", xy=(xc, 0),
                     xytext=(xc, 0), fontsize=7, ha="center", va="bottom",
                     color="grey")
    if tension_side:
        ax2.invert_yaxis()  # sagging (+) drawn below the axis
        ax2.text(0.98, 0.05, "BMD drawn on tension side", ha="right",
                 va="bottom", transform=ax2.transAxes, fontsize=8,
                 style="italic")
    ax2.set_ylabel("Moment M (kN.m)")
    ax2.set_xlabel("Distance along span x (m)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(path_png, dpi=150)
    plt.close(fig)
    return path_png


def plot_pm_interaction(curve_kN_kNm: np.ndarray, points, title: str,
                        path_png: str) -> str:
    """Column P-M interaction diagram with design point(s) marked.

    curve_kN_kNm: array with columns [P (kN), M (kN.m)].
    points: iterable of (M_kNm, P_kN) design demands.
    """
    curve = np.asarray(curve_kN_kNm, float)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(curve[:, 1], curve[:, 0], color="tab:blue", lw=1.8,
            label="capacity envelope")
    for i, (Mp, Pp) in enumerate(points or []):
        ax.plot([Mp], [Pp], marker="o", ms=9, color="tab:red",
                label="design point" if i == 0 else None)
        ax.annotate(f"({Mp:.0f}, {Pp:.0f})", xy=(Mp, Pp),
                    xytext=(6, 6), textcoords="offset points", fontsize=8)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xlabel("Moment M (kN.m)")
    ax.set_ylabel("Axial load P (kN)")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path_png, dpi=150)
    plt.close(fig)
    return path_png


def plot_pressure_diagram(length_m: float, q_min: float, q_max: float,
                          title: str, path_png: str,
                          width_m: float | None = None) -> str:
    """Trapezoidal soil-pressure diagram under a footing.

    q in kN/m2, plotted over the footing length (m).
    """
    fig, ax = plt.subplots(figsize=(8, 4))
    xs = [0.0, length_m]
    qs = [q_min, q_max]
    ax.plot([0, length_m], [0, 0], color="black", lw=3)  # footing base
    ax.fill_between(xs, [-q_min, -q_max], 0, color="tab:orange", alpha=0.3)
    ax.plot(xs, [-q_min, -q_max], color="tab:orange", lw=1.5)
    ax.annotate(f"q_min = {q_min:.1f} kN/m2", xy=(0, -q_min),
                xytext=(4, -6), textcoords="offset points", fontsize=9)
    ax.annotate(f"q_max = {q_max:.1f} kN/m2", xy=(length_m, -q_max),
                xytext=(-4, -6), textcoords="offset points",
                ha="right", fontsize=9)
    ax.set_xlabel("Footing length (m)")
    ax.set_ylabel("Base pressure (kN/m2, downward)")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path_png, dpi=150)
    plt.close(fig)
    return path_png
