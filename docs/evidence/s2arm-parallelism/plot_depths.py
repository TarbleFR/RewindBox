"""Plot the first eight measured frames of each policy in block one."""
import argparse
from collections import defaultdict
import csv
import gzip
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_gz", type=Path)
    parser.add_argument("output_svg", type=Path)
    args = parser.parse_args()
    policies = [(1, "1 image en vol"), (2, "2 images en vol"), (3, "3 images en vol"), (0, "Profondeur adaptative")]
    groups = defaultdict(list)
    with gzip.open(args.raw_gz, "rt", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["pair"]) == 1 and 0 <= int(row["frame"]) < 8:
                groups[int(row["limit"])].append(row)
    colors = {"wait": "#a2aab3", "cpu": "#17629a", "gpu": "#e48a20", "missing": "#863031"}
    plt.rcParams.update({"font.size": 10, "svg.fonttype": "none", "svg.hashsalt": "s2arm-depths"})
    fig, axes = plt.subplots(2, 2, sharex=True, sharey=True, figsize=(11, 6.9))
    for (policy, title), ax in zip(policies, axes.flat):
        rows = groups[policy]
        if [int(r["frame"]) for r in rows] != list(range(8)):
            raise ValueError(f"missing or unordered frames for {policy}")
        t0 = float(rows[0]["start"])
        for row in rows:
            y = int(row["frame"])
            def stamp(key):
                return (float(row[key]) - t0) * 1000
            for kind, a, b, offset in (("wait","start","after_wait",-.15), ("cpu","after_wait","before_commit",-.15),
                                       ("gpu","gpu_start","gpu_end",.15)):
                if kind == "gpu" and not (stamp("before_commit") <= stamp(a) < stamp(b) <= stamp("callback")):
                    ax.plot(stamp("callback"), y+offset, "x", color=colors["missing"], markersize=5)
                else:
                    ax.barh(y+offset, stamp(b)-stamp(a), height=.26, left=stamp(a), color=colors[kind])
            ax.plot(stamp("callback"), y+.15, ".", color="#25262a", markersize=3)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_yticks(range(8), [str(i+1) for i in range(8)])
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="x", alpha=.2)
    axes[0, 0].invert_yaxis()
    axes[0, 0].set_xlim(left=0)
    fig.supylabel("Image du banc", x=.025)
    fig.supxlabel("Temps écoulé depuis la première demande du bloc (ms)", y=.11)
    fig.suptitle("Préparation CPU et exécution GPU hors écran", fontweight="bold", fontsize=17, y=.99)
    fig.text(.5,.935, "Premier bloc, huit premières images mesurées de chaque politique · GPU Apple paravirtualisé",
             ha="center")
    fig.legend(handles=[Patch(color=colors["wait"],label="Attente d’admission"),
                        Patch(color=colors["cpu"],label="Préparation CPU (temps mural)"),
                        Patch(color=colors["gpu"],label="Intervalle GPU"),
                        Line2D([],[],marker=".",ls="",color="#25262a",label="Callback"),
                        Line2D([],[],marker="x",ls="",color=colors["missing"],label="Temps GPU indisponible")],
               ncol=3,loc="lower center",frameon=False,fontsize=9)
    fig.subplots_adjust(top=.86,bottom=.21,left=.09,right=.98,hspace=.35)
    fig.savefig(args.output_svg, metadata={"Date": None})


if __name__ == "__main__":
    main()
