# What the single grey "jail bar" means — findings from the research

## 1. What you are looking at

* The strip under the state-of-charge readout is what the owner's manual calls the **Power Gauge**.
  Blue fills to the right with motor power, green fills to the left under regeneration, and the
  **grey hatched bars at the far right are power the car is refusing to deliver**. Owners call them
  "jail bars". The gauge exists on GT / GT Performance / Rally clusters; on other trims the bars are
  not drawn even when the same limits are active, and the FORScan "enable power meter" hack for
  non-GT cars explicitly does **not** draw the grey bars and reportedly no longer works on 2025 cars
  ([power gauge thread][gauge], [limiters thread][lim], [non-GT power meter thread][nongt]).
* **Bars are cumulative.** Several independent limiters add their bars; one bar means one limiter
  at its lowest step ([limiters thread][lim]).
* Ford has publicly confirmed only one of the limiters (the 5-second full-power limit). Every
  threshold below is **community-measured**, not a Ford specification.

## 2. Catalogue of causes (community evidence, 2021–2024 cars)

| Cause | Bars | Observed thresholds / notes | Source |
|---|---|---|---|
| Vehicle speed | 1–2 at ≥73 mph, rising to ~8 by 92 mph | Immediately disappears below ~72 mph | [lim] |
| Wide-open-throttle acceleration | +5 after ~5 s | Fade off over minutes; Ford-confirmed 5 s peak limit | [lim] |
| **State of charge** | **1 bar at ≤~74 %**, 2 at ≤64 %, 3 at ≤36 %, ~12 at ≤23 %, 13 at ≤15 % | Applies even when parked, warm, no faults | [lim], [bluebar] |
| **Pack temperature** | **1 bar when the pack is below ~60 °F / 15 °C** ("appears ~2 h after preconditioning ends, persists all day at 50–60 °F outside") | Bars are driven by *pack* temperature, which tracks ambient ±5 °F after an overnight soak; software updates reduced the cold penalty (≈7 bars → 2 at freezing) | [lim], [greybar] |
| After DC fast charging | 4–8 | Clear in ~7–15 min of driving; occasionally persists for hours | [lim], [manybars] |
| Hot pack after sustained 80+ mph | several | Clear once the pack cools | [manybars] |
| **HV Battery Junction Box (contactor) failure** | **21 bars**, ~50 % power | Always accompanied by a non-dismissable **powertrain-malfunction wrench**, often preceded by "Service Vehicle Soon" and followed by "Stop Safely Now"; DTCs such as P0ADE / P0AA1 / P1A10 set in BECM/SOBDMC. Subject of recall 23S56 for 2021–22 cars | [lim], [hvbjb], [nhtsa23s56] |
| "Ghost" bars | 1 or ~13, random | Cleared by a key cycle or a FordPass remote start; 2021 cars showed ~8 bars at every cold start | [lim], [lim2] |

Context for a 2025 car:

* Recall **26S68 / NHTSA 26V-582** (2023–2025 Mach-E with LFP packs that received a *replacement*
  BECM) describes BECM software initialising state-of-health at 100 % and causing "unexpected power
  limitation" with wrench and turtle tell-tales. It only applies to cars that had a BECM replaced, and
  its symptom is a hard power limit with warnings, not a quiet single bar ([recall coverage][lfp]).
* The 2021–22 HVBJB contactor recall does not cover 2025 production ([nhtsa23s56]).

## 3. Ranked hypotheses for *one persistent bar* with no warning light

1. **Displayed SOC at or below ~74 %.** The most common reason owners report a single bar that will
   not go away. Test: charge above 80 % and look again.
2. **Pack temperature below ~15 °C (60 °F).** Typical for a car parked outside or in an unheated
   garage in autumn; the bar can sit there all day and disappears after a preconditioned departure.
   Test: set a departure time with cabin/battery warm-up, check immediately after it completes.
3. **Stale limiter state ("ghost bar").** Test: full key cycle (car off, exit, lock, wait >2 min).
4. **A real fault.** Only plausible if a wrench / "Service Vehicle Soon" / turtle appears, or if the
   bar persists at >80 % SOC with a warm pack. That is the case where OBD data is worth collecting.

If the bar persists after tests 1–3, the software in this repository is designed to tell the
difference between "operating limiter" and "fault": it reads the fault memory of every HV/powertrain
module and logs the battery-management quantities that drive the limiter (SOC, pack min/max
temperature, discharge power limit, cell-voltage spread, contactor voltages, inverter and motor
temperatures) so they can be correlated with the number of bars you see.

## 4. Information still needed from the owner (do not assume)

* Trim (GT / Rally / Premium / Select) and battery (standard-range LFP vs extended-range NMC).
* Displayed SOC, outside temperature, and whether the car had been preconditioned when the bar was seen.
* Whether the bar disappears after charging above 80 %, after a key cycle, or after a warm departure.
* Whether any wrench, "Service Vehicle Soon", or turtle symbol has ever appeared.
* Whether the car has had any dealer service (BECM replacement would put it under recall 26S68).

[gauge]: https://www.macheforum.com/site/threads/gt-gtpe-power-gauge.10732/
[lim]: https://www.macheforum.com/site/threads/mache-gt-gtpe-performance-limiters-explained.31200/
[lim2]: https://www.macheforum.com/site/threads/mache-gt-gtpe-performance-limiters-explained.31200/page-2
[bluebar]: https://www.macheforum.com/site/threads/blue-bar-and-jail-bars.35507/
[greybar]: https://www.macheforum.com/site/threads/grey-bar-now-on-all-the-time.32343/
[manybars]: https://www.macheforum.com/site/threads/so-so-so-many-power-bars.12863/
[nongt]: https://www.macheforum.com/site/threads/how-to-enable-power-meter-on-non-gt-mach-e.18783/
[hvbjb]: https://www.macheforum.com/site/threads/post-recall-software-hvbjb-failure.19396/
[nhtsa23s56]: https://static.nhtsa.gov/odi/rcl/2025/RCMN-25V441-8204.pdf
[lfp]: https://www.autoevolution.com/news/ford-mustang-mach-e-with-lfp-battery-recalled-over-potential-loss-of-power-and-fire-risk-275623.html
