| run | join phase | first-frame delay ms | steady delay ms: median (p05..p95, max) | drift ms/min | buffered ahead s: median (min) | Shaka buffering: n / ms | freezes >100 ms: n / ms | presented fps | skipped | seeks | outage: before -> after ms | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r10-seg1 | 0.02 | 3180 | 3116 (3111..3122, 3125) | 11.6 | 3.97 (1.96) | 0 / 0 | 12 / 36028 | 0.3 | 0 | 0 | - | yes |
| r10-seg0.5 | 0.23 | 1778 | 2695 (2679..2695, 2695) | 2097.1 | 2.47 (0.96) | 0 / 0 | 11 / 30990 | 10.1 | 0 | 0 | - | yes |
| r10-seg0.25 | 0.33 | 1009 | 2985 (2984..2986, 2986) | 607.1 | 2.59 (0.74) | 0 / 0 | 2 / 5058 | 51.9 | 0 | 0 | - | yes |
| r10-seg0.5-long | 0.04 | 1663 | 1626 (1615..1629, 1630) | 8.2 | 2.72 (1.21) | 0 / 0 | 12 / 36036 | 0.3 | 0 | 0 | - | yes |
| r10-seg0.5-shaka5.0.1 | 0.07 | 1678 | 1637 (1631..1644, 1645) | -6.0 | 2.49 (0.98) | 0 / 0 | 12 / 36034 | 0.3 | 0 | 0 | - | yes |
| r10-seg0.5-window12 | 0.05 | 1657 | 10818 (10818..10819, 10819) | -2.4 | 9.98 (6.49) | 0 / 0 | 0 / 0 | 46.3 | 0 | 0 | - | yes |

| configuration | runs | steady delay ms: median of runs (range of run medians) | p95 (worst run) | first-frame delay (range) | Shaka buffering events / ms (sum) | freezes n / ms (sum) | after outage: delay change ms (range) | seeks (sum) | note |
|---|---|---|---|---|---|---|---|---|---|
| r10-seg1 | 1 | 3116 (3116..3116) | 3122 | 3180..3180 | 0 / 0 | 12 / 36028 | - | 0 | framework config, rebufferingGoal 10 |
| r10-seg0.5 | 1 | 2695 (2695..2695) | 2695 | 1778..1778 | 0 / 0 | 11 / 30990 | - | 0 |  |
| r10-seg0.25 | 1 | 2985 (2985..2985) | 2986 | 1009..1009 | 0 / 0 | 2 / 5058 | - | 0 |  |
| r10-seg0.5-long | 1 | 1626 (1626..1626) | 1629 | 1663..1663 | 0 / 0 | 12 / 36036 | - | 0 | one 1 s segment (sequence 20) among 0.5 s ones |
| r10-seg0.5-shaka5.0.1 | 1 | 1637 (1637..1637) | 1644 | 1678..1678 | 0 / 0 | 12 / 36034 | - | 0 |  |
| r10-seg0.5-window12 | 1 | 10818 (10818..10818) | 10819 | 1657..1657 | 0 / 0 | 0 / 0 | - | 0 | 14 s playlist |
