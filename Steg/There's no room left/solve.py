s = open('flag.txt', 'r', encoding='utf-8').read()
zw = ''.join(c for c in s if ord(c) in (0x200b, 0x200c))
bits = ''.join('0' if ord(c)==0x200b else '1' for c in zw)
print(''.join(chr(int(bits[i:i+8],2)) for i in range(0,len(bits),8) if len(bits[i:i+8])==8))