import unittest
from unittest import mock

import blingmud
import set_admin_pw


class SetAdminPasswordTests(unittest.TestCase):
    @staticmethod
    def password_reader(*answers):
        remaining = iter(answers)
        return lambda prompt: next(remaining)

    def test_short_mismatched_and_oversized_passwords_do_not_write(self):
        cases = (
            ("different passwords", "do not match"),
            ("short", "short"),
            (
                "x" * (blingmud.MAX_PASSWORD_LENGTH + 1),
                "x" * (blingmud.MAX_PASSWORD_LENGTH + 1)
            )
        )

        for first, second in cases:
            with mock.patch.object(
                set_admin_pw,
                "write_admin_password_hash"
            ) as write_hash, mock.patch("builtins.print"):
                result = set_admin_pw.main(
                    self.password_reader(first, second)
                )

            self.assertEqual(result, 1)
            write_hash.assert_not_called()

    def test_valid_password_is_hashed_and_written(self):
        with mock.patch.object(
            set_admin_pw,
            "password_hash",
            return_value="safe stored hash"
        ) as make_hash, mock.patch.object(
            set_admin_pw,
            "write_admin_password_hash"
        ) as write_hash, mock.patch("builtins.print"):
            result = set_admin_pw.main(
                self.password_reader(
                    "a sufficiently long admin password",
                    "a sufficiently long admin password"
                )
            )

        self.assertEqual(result, 0)
        make_hash.assert_called_once_with(
            "a sufficiently long admin password"
        )
        write_hash.assert_called_once_with("safe stored hash")


if __name__ == "__main__":
    unittest.main()
