from pathlib import Path
import unicodedata

s = Path("flag.txt").read_text("utf-8")
cf = [ch for ch in s if unicodedata.category(ch) == "Cf"]

mp = {
    0x200c: '0',
    0x200d: '1',
    0x202c: '2',
    0xfeff: '3',
}

digits = ''.join(mp[ord(ch)] for ch in cf)
out = bytes(int(digits[i:i+8], 4) for i in range(0, len(digits), 8))
print(out.decode())