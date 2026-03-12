import os
import struct

S_BOXES = [
    [3, 8, 15, 1, 10, 6, 5, 11, 14, 13, 4, 2, 7, 0, 9, 12],
    [15, 12, 2, 7, 9, 0, 5, 10, 1, 11, 14, 8, 6, 13, 3, 4],
    [8, 6, 7, 9, 3, 12, 10, 15, 13, 1, 14, 4, 0, 11, 5, 2],
    [0, 15, 11, 8, 12, 9, 6, 3, 13, 1, 2, 4, 10, 7, 5, 14],
    [1, 15, 8, 3, 12, 0, 11, 6, 2, 5, 4, 10, 9, 14, 7, 13],
    [15, 5, 2, 11, 4, 10, 9, 12, 0, 3, 14, 8, 13, 6, 7, 1],
    [7, 2, 12, 5, 8, 4, 6, 11, 14, 9, 1, 15, 13, 3, 10, 0],
    [1, 13, 15, 0, 14, 8, 2, 11, 7, 4, 12, 10, 9, 3, 5, 6]
]

S_BOXES_INV = []
for sbox in S_BOXES:
    inv = [0] * 16
    for i, v in enumerate(sbox):
        inv[v] = i
    S_BOXES_INV.append(inv)

def rotate_left(val, n, width=32):
    n = n % width
    return ((val << n) | (val >> (width - n))) & ((1 << width) - 1)

def rotate_right(val, n, width=32):
    n = n % width
    return ((val >> n) | (val << (width - n))) & ((1 << width) - 1)

PHI = 0x9e3779b9

def serpent_key_schedule(key):
    key = key.ljust(32, b'\x00')[:32]
    w = list(struct.unpack('<8I', key))
    
    for i in range(8, 140):
        x = w[i-8] ^ w[i-5] ^ w[i-3] ^ w[i-1] ^ PHI ^ (i - 8)
        w.append(rotate_left(x, 11))
    
    subkeys = []
    for i in range(33):
        sbox_idx = (35 - i) % 8
        k = [0, 0, 0, 0]
        for j in range(32):
            input_bits = 0
            for b in range(4):
                input_bits |= ((w[8 + i*4 + b] >> j) & 1) << b
            output_bits = S_BOXES[sbox_idx][input_bits]
            for b in range(4):
                k[b] |= ((output_bits >> b) & 1) << j
        subkeys.append(tuple(k))
    
    return subkeys

def apply_sbox(state, sbox_idx):
    result = [0, 0, 0, 0]
    sbox = S_BOXES[sbox_idx]
    for j in range(32):
        input_bits = 0
        for b in range(4):
            input_bits |= ((state[b] >> j) & 1) << b
        output_bits = sbox[input_bits]
        for b in range(4):
            result[b] |= ((output_bits >> b) & 1) << j
    return result

def apply_sbox_inv(state, sbox_idx):
    result = [0, 0, 0, 0]
    sbox = S_BOXES_INV[sbox_idx]
    for j in range(32):
        input_bits = 0
        for b in range(4):
            input_bits |= ((state[b] >> j) & 1) << b
        output_bits = sbox[input_bits]
        for b in range(4):
            result[b] |= ((output_bits >> b) & 1) << j
    return result

def linear_transform(state):
    x0, x1, x2, x3 = state
    x0 = rotate_left(x0, 13)
    x2 = rotate_left(x2, 3)
    x1 = x1 ^ x0 ^ x2
    x3 = x3 ^ x2 ^ ((x0 << 3) & 0xFFFFFFFF)
    x1 = rotate_left(x1, 1)
    x3 = rotate_left(x3, 7)
    x0 = x0 ^ x1 ^ x3
    x2 = x2 ^ x3 ^ ((x1 << 7) & 0xFFFFFFFF)
    x0 = rotate_left(x0, 5)
    x2 = rotate_left(x2, 22)
    return [x0 & 0xFFFFFFFF, x1 & 0xFFFFFFFF, x2 & 0xFFFFFFFF, x3 & 0xFFFFFFFF]

def linear_transform_inv(state):
    x0, x1, x2, x3 = state
    x2 = rotate_right(x2, 22)
    x0 = rotate_right(x0, 5)
    x2 = x2 ^ x3 ^ ((x1 << 7) & 0xFFFFFFFF)
    x0 = x0 ^ x1 ^ x3
    x3 = rotate_right(x3, 7)
    x1 = rotate_right(x1, 1)
    x3 = x3 ^ x2 ^ ((x0 << 3) & 0xFFFFFFFF)
    x1 = x1 ^ x0 ^ x2
    x2 = rotate_right(x2, 3)
    x0 = rotate_right(x0, 13)
    return [x0 & 0xFFFFFFFF, x1 & 0xFFFFFFFF, x2 & 0xFFFFFFFF, x3 & 0xFFFFFFFF]

def serpent_encrypt_block(plaintext, subkeys):
    state = list(struct.unpack('<4I', plaintext))
    
    for r in range(31):
        state = [state[i] ^ subkeys[r][i] for i in range(4)]
        state = apply_sbox(state, r % 8)
        state = linear_transform(state)
    
    state = [state[i] ^ subkeys[31][i] for i in range(4)]
    state = apply_sbox(state, 7)
    state = [state[i] ^ subkeys[32][i] for i in range(4)]
    
    return struct.pack('<4I', *state)

def serpent_decrypt_block(ciphertext, subkeys):
    state = list(struct.unpack('<4I', ciphertext))
    
    state = [state[i] ^ subkeys[32][i] for i in range(4)]
    state = apply_sbox_inv(state, 7)
    state = [state[i] ^ subkeys[31][i] for i in range(4)]
    
    for r in range(30, -1, -1):
        state = linear_transform_inv(state)
        state = apply_sbox_inv(state, r % 8)
        state = [state[i] ^ subkeys[r][i] for i in range(4)]
    
    return struct.pack('<4I', *state)

def pad(data, block_size=16):
    padding_len = block_size - (len(data) % block_size)
    return data + bytes([padding_len] * padding_len)

def unpad(data):
    padding_len = data[-1]
    if padding_len > 16 or padding_len == 0:
        raise ValueError("Invalid padding")
    for i in range(padding_len):
        if data[-(i+1)] != padding_len:
            raise ValueError("Invalid padding")
    return data[:-padding_len]

def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))

class SerpentCipher:
    def __init__(self, key=None):
        if key is None:
            key = os.environ.get('ENCRYPTION_KEY', 'default_serpent_key_32')
        if isinstance(key, str):
            key = key.encode('utf-8')
        import hashlib
        self.key = hashlib.sha256(key).digest()
        self.subkeys = serpent_key_schedule(self.key)
    
    def encrypt(self, plaintext):
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        
        iv = os.urandom(16)
        padded = pad(plaintext)
        
        ciphertext = iv
        prev_block = iv
        
        for i in range(0, len(padded), 16):
            block = padded[i:i+16]
            xored = xor_bytes(block, prev_block)
            encrypted = serpent_encrypt_block(xored, self.subkeys)
            ciphertext += encrypted
            prev_block = encrypted
        
        import base64
        return base64.b64encode(ciphertext).decode('utf-8')
    
    def decrypt(self, ciphertext):
        import base64
        try:
            data = base64.b64decode(ciphertext)
            iv = data[:16]
            encrypted = data[16:]
            
            plaintext = b''
            prev_block = iv
            
            for i in range(0, len(encrypted), 16):
                block = encrypted[i:i+16]
                decrypted = serpent_decrypt_block(block, self.subkeys)
                plaintext += xor_bytes(decrypted, prev_block)
                prev_block = block
            
            return unpad(plaintext).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")
    
    def encrypt_file(self, file_data):
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        
        iv = os.urandom(16)
        padded = pad(file_data)
        
        ciphertext = iv
        prev_block = iv
        
        for i in range(0, len(padded), 16):
            block = padded[i:i+16]
            xored = xor_bytes(block, prev_block)
            encrypted = serpent_encrypt_block(xored, self.subkeys)
            ciphertext += encrypted
            prev_block = encrypted
        
        return ciphertext
    
    def decrypt_file(self, encrypted_data):
        try:
            iv = encrypted_data[:16]
            encrypted = encrypted_data[16:]
            
            plaintext = b''
            prev_block = iv
            
            for i in range(0, len(encrypted), 16):
                block = encrypted[i:i+16]
                decrypted = serpent_decrypt_block(block, self.subkeys)
                plaintext += xor_bytes(decrypted, prev_block)
                prev_block = block
            
            return unpad(plaintext)
        except Exception as e:
            raise ValueError(f"File decryption failed: {str(e)}")

def serpent_encrypt(data, key=None):
    cipher = SerpentCipher(key)
    return cipher.encrypt(data)

def serpent_decrypt(data, key=None):
    cipher = SerpentCipher(key)
    return cipher.decrypt(data)

def serpent_encrypt_file(file_data, key=None):
    cipher = SerpentCipher(key)
    return cipher.encrypt_file(file_data)

def serpent_decrypt_file(encrypted_data, key=None):
    cipher = SerpentCipher(key)
    return cipher.decrypt_file(encrypted_data)
