/* VMU persistence: the menu's settings record (16 bytes) and the controls
 * library (ctl_lib_t, 116 bytes) saved to a memory card as one file.
 * Spec: docs/superpowers/specs/2026-11-01-vmu-persistence-design.md.
 *
 * Pure half (payload, root guard, consent decision): no KOS, host-tested by
 * shims/test/test_vmu_save.c. KOS half (scan/load/write): vmu_save.c under
 * !HOST_TEST.
 *
 * Root block (block 255, read raw into the struct: vmufs_root_read,
 * tools/kos/kernel/arch/dreamcast/fs/vmufs.c:79-88) is vmu_root_t,
 * tools/kos/kernel/arch/dreamcast/include/dc/vmufs.h:55-70, uint16_t fields
 * read as host integers by a raw block read, so little-endian on the SH-4
 * (KOS builds with -ml: tools/kos/environ_dreamcast.sh:32):
 *   0x00 magic[16] (all 0x55)  0x10 use_custom  0x11 custom_color[4]
 *   0x15 pad1[27]  0x30 timestamp (8 BCD bytes, vmufs.h:41-50)  0x38 pad2[8]
 *   0x40 unk1[6]   0x46 fat_loc  0x48 fat_size  0x4a dir_loc  0x4c dir_size
 *   0x4e icon_shape  0x50 blk_cnt
 * KOS checks little of it: it refuses fat_size > 1 (vmufs.c:174, after
 * mallocing fat_size * 512, :525-526), mallocs dir_size * 512 straight from
 * the root (vmufs.c:503-504) and indexes the
 * 256-entry FAT by blk_cnt (vmufs.c:291-321, :448-457) and by chain entries
 * up to blk_cnt inclusive (vmufs_file_delete, vmufs.c:425) -- the
 * memory-safety bound, so blk_cnt <= 255. Hence vmu_root_ok.
 *
 * Card identity (fp, VMU_FP_LEN = 16): the root timestamp (8 bytes @0x30),
 * then our SENKOSP_SYS dirent's timestamp (8 bytes, vmu_dir_t.timestamp,
 * vmufs.h:80; zeros when there is no file). The dirent half is filled from
 * the RTC on every vmufs_write (vmufs.c:743 -> vmufs_dir_fill_time,
 * :61-77), so cards whose root stamps collide (formatted in the same second;
 * every Flycast blank card carries the same one) still differ once they carry
 * a save. */
#ifndef VMU_SAVE_H
#define VMU_SAVE_H

#include "ctl_lib.h"

#define VMU_FILE_NAME    "SENKOSP_SYS"
#define VMU_PAYLOAD_LEN  140
#define VMU_FP_LEN       16              /* root ts + our dirent ts (above) */
#define VMU_ROOT_FP_OFF  0x30            /* vmu_root_t.timestamp: 16 magic + 1 + 4 + 27 pad */

typedef struct { unsigned char port, unit, has_file, fp[VMU_FP_LEN]; } vmu_card_t;  /* a readable card; has_file: a SENKOSP_SYS dirent exists by name */
typedef struct { unsigned char valid, port, unit, fp[VMU_FP_LEN]; } vmu_home_t;

#define VMU_ASK       (-1)
#define VMU_NO_CARD   (-2)
#define VMU_DECLINED  (-3)

/* Payload v1: "SKSP", version 1, 3 reserved zeros, the 16-byte record, the
 * 116-byte ctl_lib_t as laid out in memory. */
void vmu_payload_build(unsigned char out[VMU_PAYLOAD_LEN], const unsigned char rec[16], const ctl_lib_t *L);
int  vmu_payload_parse(const unsigned char *buf, unsigned len, unsigned char rec[16], ctl_lib_t *L);  /* 0 ok; -1 reject, outputs untouched */
int  vmu_root_ok(const unsigned char root[512]);                                                      /* 1 = readable card */
int  vmu_decide(const vmu_home_t *home, int declined, const vmu_card_t *cards, int n);               /* >= 0: index of home in cards -> silent write; else VMU_ASK / VMU_NO_CARD / VMU_DECLINED */

/* KOS half (Task 3) */
int  vmu_scan(vmu_card_t out[8]);                                                                    /* readable cards, enumeration order; count */
int  vmu_load(const vmu_card_t *c, unsigned char rec[16], ctl_lib_t *L);                             /* 0 ok; < 0 absent/invalid */
/* vmu_write re-checks all of c->fp first. After a write our dirent's timestamp
 * is new, so it re-reads the card: OK = c->fp is the card's new identity;
 * NOFP = written, but the re-read failed and c->fp is stale (the caller drops
 * home, so the next change asks again). */
#define VMU_WRITE_OK    0
#define VMU_WRITE_NOFP  1
#define VMU_WRITE_FULL  (-1)
#define VMU_WRITE_FAIL  (-2)
int  vmu_write(vmu_card_t *c, const unsigned char rec[16], const ctl_lib_t *L);

#endif
