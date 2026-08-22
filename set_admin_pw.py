from blingmud import password_hash, write_admin_password_hash
from getpass import getpass

print("This script will set the admin password in admin.hash")
print("If you don't want to continue, hit ctrl-c now")
print("Otherwise, go ahead")

admin_pwd = getpass("Admin password: ")
admin_pwd_confirm = getpass("Confirm admin password: ")

if admin_pwd == admin_pwd_confirm:
   admin_hash = password_hash(admin_pwd)
   write_admin_password_hash(admin_hash)
   print("Updated admin.hash!")
else:
   print("Passwords don't match! Not updating")
