import bcrypt
print("bcrypt imported successfully")
hashed = bcrypt.hashpw(b"test", bcrypt.gensalt())
print(f"hashed: {hashed}")
if bcrypt.checkpw(b"test", hashed):
    print("verification successful")
