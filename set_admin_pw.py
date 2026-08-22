from getpass import getpass
import sys

from blingmud import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    password_hash,
    write_admin_password_hash
)


def main(password_reader=getpass):
    print("This script will set the admin password in admin.hash")
    print("If you don't want to continue, hit ctrl-c now")
    print("Otherwise, go ahead")

    admin_password = password_reader("Admin password: ")
    confirmation = password_reader("Confirm admin password: ")

    if admin_password != confirmation:
        print("Passwords don't match! Not updating")
        return 1

    if len(admin_password) < MIN_PASSWORD_LENGTH:
        print("Admin passwords must contain at least twelve characters.")
        return 1

    if len(admin_password) > MAX_PASSWORD_LENGTH:
        print("That admin password is too long.")
        return 1

    admin_hash = password_hash(admin_password)
    write_admin_password_hash(admin_hash)
    print("Updated admin.hash!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
