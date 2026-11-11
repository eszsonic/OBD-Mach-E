# Vgate vLinker MC+ on Windows — setup and known behaviour

What is established (vendor and user sources; nothing here was tested in this session):

* The MC+ is marketed as compatible with the ELM327/ELM329 AT set **and** the STN "ST" command set,
  supports the five legacy OBD protocols plus Ford MS-CAN and GM SW-CAN, and is one of the adapters
  the vendor recommends for FORScan on Windows ([vendor page][vgate], [manual][manual]).
* It is dual-mode Bluetooth: pair **"vLinker MC-Android"** with PIN **1234** from Windows or
  Android (classic SPP → virtual COM port); the BLE name is for iOS and does not give a COM port
  ([listing][ubuy]).
* FORScan forum: one user's MC+ failed on Windows 10 until the device was added through
  *Devices and Printers*; afterwards FORScan read modules and DTCs normally. Wired adapters are
  repeatedly described as more reliable than Bluetooth ones ([FORScan forum][fs1], [Bronco forum][bs]).
* A Dutch reseller states the MC+ has **no HS/MS-CAN hardware switch** and depends on app-side
  switching, while the vendor says MS-CAN is supported; how (if at all) `STP53` works on it is
  unverified ([astools][ast]). Irrelevant for this project (all needed modules are on HS-CAN).

## Windows procedure

1. Plug the adapter into the OBD port (left of the steering column), put the car in **Ready**.
2. *Settings → Bluetooth & devices → Add device → Bluetooth*, choose `vLinker MC-Android`, PIN `1234`.
3. *Bluetooth & devices → Devices → More Bluetooth settings → COM Ports*: note the **Outgoing** port
   (e.g. `COM5`). `python -m mache_obd ports` lists it as "Standard Serial over Bluetooth link".
4. `python -m mache_obd --port COM5 info` — expect something like `ELM327 v2.x`, an `STN…` string
   from `STI`, and a `12–15 V` reading from `ATRV`. If `ATRV` shows ~12.4 V with the car in Ready,
   the DC-DC converter is not running and the car is not actually in Ready.
5. `python -m mache_obd --port COM5 scan` — the BECM, SOBDMC, PCM, BCM lines should say "answers".

Troubleshooting:

| Symptom | Likely cause | Action |
|---|---|---|
| No COM port after pairing | Paired the BLE name, or Windows paired without SPP | Remove device, pair `…-Android`; if still none, use *Devices and Printers → Add a device* |
| `ports` shows two COM ports | Incoming + outgoing | Use outgoing |
| `info` times out | Adapter asleep or another app holds the port | Unplug/replug adapter; close FORScan / Car Scanner |
| `scan` finds nothing, `ATRV` fine | Car not in Ready, or 2025 addressing | Press Start with brake; then `--addressing 29`; then FORScan to confirm |
| `CAN ERROR` on every request | Wrong protocol selected | Driver forces `ATSP6`; try `ATSP7` via `--addressing 29` |
| Values freeze / `STOPPED` | Bluetooth retransmits / adapter buffer | Lower `--period`, trim `POWER_LIMIT_SET`, keep laptop near the port |

Baud rate is irrelevant over Bluetooth SPP (the parameter is ignored by the virtual port); the
default 115200 is fine.

[vgate]: https://www.vgatemall.com/products-detail/i-5/
[manual]: https://manuals.plus/asin/B088LW211V
[ubuy]: https://www.ubuy.com.pk/en/product/4BNAA28-vlinker-mc-bluetooth-obd2-car-diagnostic-scan-tool-for-ios-android-and-windows
[fs1]: https://forscan.org/forum/viewtopic.php?t=23131
[bs]: https://www.broncosportforum.com/forum/threads/windows-11-and-forscan.4981/
[ast]: https://www.astools.eu/products/vgate-vlinker-mc-elm327-interface-bluetooth-4-0
