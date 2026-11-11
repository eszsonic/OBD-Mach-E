# Sources consulted

Primary data (cloned and used directly):

* OBDb Ford-Mustang-Mach-E signal set and per-model-year test captures — https://github.com/OBDb/Ford-Mustang-Mach-E (CC BY-SA 4.0)
* sillygoose/mme-record (module addresses, DID scanner, state files; Raspberry Pi + SocketCAN logger for the Mach-E) — https://github.com/sillygoose/mme-record (MIT)
* OBDb/Pelican per-year PID support page — https://pelican.clutch.engineering/cars/ford/mustang-mach-e/

Owner-forum threads (read in full):

* "MachE GT/GTPE Performance Limiters Explained" — https://www.macheforum.com/site/threads/mache-gt-gtpe-performance-limiters-explained.31200/ (+ page-2)
* "Grey bar now on all the time!?" — https://www.macheforum.com/site/threads/grey-bar-now-on-all-the-time.32343/
* "Blue bar and jail bars" — https://www.macheforum.com/site/threads/blue-bar-and-jail-bars.35507/
* "So so so many power bars" — https://www.macheforum.com/site/threads/so-so-so-many-power-bars.12863/
* "GT/GTPE power gauge" — https://www.macheforum.com/site/threads/gt-gtpe-power-gauge.10732/
* "Ford Mustang Mach-E Extended PIDs for Torque Project" — https://www.macheforum.com/site/threads/ford-mustang-mach-e-extended-pids-for-torque-project.7427/ (+ page-2)
* "How to use FORScan to view Mach-E live data" (module/bus list) — https://www.macheforum.com/how-to-use-forscan-to-view-mach-e-live-data-charge-rate-battery-current-etc/
* "ODBII connector schematic/pinout" — https://www.macheforum.com/site/threads/odbii-connector-schematic-pinout.11857/
* "How To: Enable Power Meter on Non-GT Mach E" — https://www.macheforum.com/site/threads/how-to-enable-power-meter-on-non-gt-mach-e.18783/
* "Post recall software HVBJB failure" — https://www.macheforum.com/site/threads/post-recall-software-hvbjb-failure.19396/

Recalls / regulatory:

* NHTSA 25V-441 remedy notice (HVBJB, 2021–22) — https://static.nhtsa.gov/odi/rcl/2025/RCMN-25V441-8204.pdf
* NHTSA 23V-687 (BECM software, contactor power reduction) — https://static.nhtsa.gov/odi/rcl/2023/RMISC-23V687-5070.pdf
* 2023–2025 LFP replacement-BECM recall 26S68 coverage — https://www.autoevolution.com/news/ford-mustang-mach-e-with-lfp-battery-recalled-over-potential-loss-of-power-and-fire-risk-275623.html , https://fordauthority.com/2026/09/2023-2025-ford-mustang-mach-e-recalled-over-incorrect-software-issue/
* 2022 contactor recall coverage — https://www.nbcnews.com/business/autos/ford-recalls-mach-e-electric-vehicle-potential-power-loss-rcna33535

Adapter / tooling:

* Vgate vLinker MC+ product page and manuals — https://www.vgatemall.com/products-detail/i-5/ , https://manuals.plus/asin/B088LW211V , https://manuals.plus/vlinker/vlinker-mc-quick-manual
* FORScan forum "VLinker MC+ und Windows 10" — https://forscan.org/forum/viewtopic.php?t=23131 (site refused automated fetch; summary via search result)
* Reseller note on MC+ lacking an HS/MS switch — https://www.astools.eu/products/vgate-vlinker-mc-elm327-interface-bluetooth-4-0
* python-OBD custom commands (why it was not used) — https://python-obd.readthedocs.io/en/latest/Custom%20Commands/
* py-obdii Bluetooth/COM notes — https://py-obdii.readthedocs.io/en/latest/connection.html
