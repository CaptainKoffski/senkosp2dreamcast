# senkosp's identity/mastering values, read by the kit (kit/scripts/kitpath.py).
GAME_NAME = "Senko no Ronde Special"    # release folder name in the DreamShell README (make_preset.py)
DAT = "senkosp.dat"                     # flat cart image at the port root (--rom default; generators)
CART_SIZE = 251342848                   # len(DAT); make_gdi.py asserts it and cross-checks shim_iface.h
IP_PRODUCT = "T-SRS001M"                # IP.BIN 0x40 serial (make_gdi.py brand_ip, make_cdi.py mkdcdisc)
IP_VERSION = "V1.000"                   # IP.BIN 0x4a version (same two users)
IP_DATE = "20260822"                    # IP.BIN 0x50 date (same two users)
IP_COMPANY = "SEGA LC-T-99"             # IP.BIN 0x70 company (same two users)
IP_TITLE = "SENKO NO RONDE SPECIAL"     # IP.BIN 0x80 title; CDI/DreamShell README heading, preset title
CDI_FILE = "senkosp.cdi"                # CDI release file name named in the burn README (make_cdi.py)
ISO_VOLUME = "SENKOSP"                  # CDI data-track volume label (make_cdi.py mkisofs -V)
TEXPATCH = True                         # make_gdi.py/make_cdi.py splice build/texpatch/ (scripts/shrink_vq.py)
PATCH_PREFIX = "senkosp"                # patch_table.h array prefix (scripts/build_patch_table.py)
GHIDRA_PROJECT = "senkosp3"             # Ghidra project name (kit/scripts/ghidra/run.sh)
MIE_ORACLE_LOG = "captures/phase4/pc2.log"   # optional: kit test_gen_mie_blobs.py oracle capture (absent -> SKIP)
ENTRY_PC = "8c021000"                   # boot entry PC: arms the fork's BIOSEXEC watch (kit/scripts/capture_leg.sh
                                        # FLYCAST_ENTRYPC); hex without 0x, as the fork reads it (strtoul base 16,
                                        # ../flycast4naomi2dreamcast core/hw/sh4/interpr/sh4_interpreter.cpp:34-35)
STREAM_FLOOR = 0x100000                 # 1 MB boot region (BOOT_END, kit/scripts/parse_cartlog.py --boot-end) --
                                        # rest of senkosp.dat is streamed asset data (kit/scripts/test_maple_literals.py)
# RAM landmarks for kit/scripts/carve_ram_snapshot.py's control tests (Naomi main-RAM offsets,
# docs/kb/tooling.md §Phase 3: RAM snapshot): the syMalloc banner, the GDFS error strings, and the
# heap-create code compared against its .dat twin.
RAM_BANNER_OFF = 0x15C980
RAM_GDFS_OFF = 0x15B2C4
RAM_HEAP_LO, RAM_HEAP_HI = 0x85B00, 0x85BB4
