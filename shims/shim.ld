OUTPUT_ARCH(sh)
/* This sh-elf toolchain (dc-chain, gcc 15.2.0) prepends a leading underscore
 * to all C symbols (__USER_LABEL_PREFIX__ is "_") -- verified via
 * `sh-elf-gcc -dM -E`. ENTRY() must match the mangled name or ld silently
 * defaults the entry point (with a warning) instead of resolving it. */
ENTRY(_shim_cart_service)
SECTIONS {
  . = 0x8c010000;
  .text : { *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  ASSERT(. <= 0x8c014000, "shim exceeds SHIM_CODE_MAX")
}
