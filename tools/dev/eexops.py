"""Static operand-type list per EEX opcode, from the interpreter at 0x80022cfc (dev helper)."""
import struct, capstone
d = open('extract/SLPS_015.95', 'rb').read()
B = 0x80010000
def w(va): return struct.unpack_from('<I', d, va - B + 0x800)[0]
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
ends = sorted({w(0x8011fcf0 + 4*i) for i in range(0x58)})
out = {}
for op in range(0x58):
    case = w(0x8011fcf0 + 4*op)
    x = w(case)
    if x >> 26 != 3:
        out[op] = None; continue
    h = 0x80000000 | ((x & 0x3ffffff) << 2)
    # scan handler until next 'jr ra' after epilogue, collecting typed reads
    types = []; a1 = None; va = h
    for _ in range(600):
        i = next(md.disasm(struct.pack('<I', w(va)), va))
        if i.mnemonic == 'addiu' and i.op_str.startswith('$a1, $zero,'):
            a1 = int(i.op_str.split(',')[-1], 0)
        if i.mnemonic == 'jal':
            t = int(i.op_str, 0)
            nxt = next(md.disasm(struct.pack('<I', w(va+4)), va+4))
            if nxt.mnemonic == 'addiu' and nxt.op_str.startswith('$a1, $zero,'):
                a1 = int(nxt.op_str.split(',')[-1], 0)
            if t == 0x80023de0: types.append(a1)
            elif t in (0x80024468, 0x800244b0, 0x800244f4, 0x80024440): types.append('raw%x' % t)
            else: types.append('call%x' % t)
        if i.mnemonic == 'jr' and i.op_str == '$ra' and va > h: break
        va += 4
    out[op] = (h, types)
if __name__ == '__main__':
    for op, v in out.items():
        if v is None: print(hex(op), 'inline'); continue
        h, t = v
        print(hex(op), hex(h), ' '.join(hex(x) if isinstance(x, int) else x for x in t))
