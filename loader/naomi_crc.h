/* T9: Naomi EEPROM CRC-16 + game-area builder. Freestanding (host-tested by
 * shims/test/test_naomi_crc.c; linked into the loader for the menu poke). */
#ifndef NAOMI_CRC_H
#define NAOMI_CRC_H
unsigned short naomi_eeprom_crc(const unsigned char *buf, int size);
void naomi_build_game_area(unsigned char out[40], const unsigned char rec[16]);
#endif
