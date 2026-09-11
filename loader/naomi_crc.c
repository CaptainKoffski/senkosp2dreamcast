/* Port of Flycast's eeprom_crc (naomi_flashrom.cpp:26-51 -- the emulator's
 * implementation of the Naomi BIOS algorithm; KB cite
 * docs/kb/phase4-conversion.md §EEPROM: both stored CRCs of our captured
 * image recompute correctly under it). Seed 0xdebdeb00, one trailing round,
 * result is the top half. */
#include "naomi_crc.h"

unsigned short naomi_eeprom_crc(const unsigned char *buf, int size) {
    unsigned int n = 0xdebdeb00u;
    for (int i = 0; i < size; i++) {
        n = (n & 0xffffff00u) + buf[i];
        for (int c = 0; c < 8; c++)
            n = (n & 0x80000000u) ? (n << 1) + 0x10210000u : n << 1;
    }
    for (int c = 0; c < 8; c++)
        n = (n & 0x80000000u) ? (n << 1) + 0x10210000u : n << 1;
    return (unsigned short)(n >> 16);
}

/* Game area 0x24..0x4B: [crc_lo crc_hi 0x10 0x10] x2, then the record x2.
 * Header layout verified against three BIOS-written areas (KB §T9 /
 * test_naomi_crc.c): CRC little-endian, 0x10 = record length, twice. */
void naomi_build_game_area(unsigned char out[40], const unsigned char rec[16]) {
    unsigned short c = naomi_eeprom_crc(rec, 16);
    out[0] = (unsigned char)(c & 0xff);
    out[1] = (unsigned char)(c >> 8);
    out[2] = 0x10;
    out[3] = 0x10;
    for (int i = 0; i < 4; i++)  out[4 + i]  = out[i];
    for (int i = 0; i < 16; i++) { out[8 + i] = rec[i]; out[24 + i] = rec[i]; }
}
